"""Discover LAN peers through periodic UDP broadcast heartbeats."""

from __future__ import annotations

import ipaddress
import json
import queue
import socket
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

import psutil

DEFAULT_DISCOVERY_PORT = 50000
DEFAULT_HEARTBEAT_INTERVAL = 3.0
DEFAULT_PEER_TIMEOUT = 10.0
VIRTUAL_INTERFACE_PREFIXES = (
    "br-",
    "cni",
    "docker",
    "flannel",
    "podman",
    "tap",
    "tailscale",
    "tun",
    "utun",
    "vbox",
    "veth",
    "virbr",
    "vmnet",
    "wg",
    "zt",
)


@dataclass(frozen=True, slots=True)
class Peer:
    """A peer currently visible on the local network."""

    device_id: str
    username: str
    host: str
    tcp_port: int
    last_seen: float

    def to_dict(self) -> dict[str, Any]:
        """Return a UI- and JSON-friendly copy of this peer record."""
        return asdict(self)


class PeerDiscovery:
    """Broadcast this peer and track recently heard peers."""

    def __init__(
        self,
        username: str | None = None,
        tcp_port: int = 50001,
        event_queue: queue.Queue[dict[str, Any]] | None = None,
        *,
        discovery_port: int = DEFAULT_DISCOVERY_PORT,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
        peer_timeout: float = DEFAULT_PEER_TIMEOUT,
        broadcast_address: str = "255.255.255.255",
        device_id: str | None = None,
    ) -> None:
        if not 1 <= tcp_port <= 65535:
            raise ValueError("tcp_port must be between 1 and 65535")
        if not 1 <= discovery_port <= 65535:
            raise ValueError("discovery_port must be between 1 and 65535")
        if heartbeat_interval <= 0 or peer_timeout <= heartbeat_interval:
            raise ValueError(
                "peer_timeout must be greater than a positive heartbeat interval"
            )
        if username is None:
            try:
                username = socket.gethostname()
            except OSError:
                username = ""
        self.username = username.strip()[:128] or "SendLan device"
        self.tcp_port = tcp_port
        self.event_queue = (
            event_queue if event_queue is not None else queue.Queue()
        )
        self.discovery_port = discovery_port
        self.heartbeat_interval = heartbeat_interval
        self.peer_timeout = peer_timeout
        self.broadcast_address = broadcast_address
        self.device_id = device_id or uuid.uuid4().hex
        self._stop_event = threading.Event()
        self._identity_lock = threading.Lock()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._peers: dict[str, Peer] = {}
        self._peers_lock = threading.Lock()

    def start(self) -> None:
        """Bind the UDP discovery port and begin sending/receiving heartbeats."""
        if self._thread is not None and self._thread.is_alive():
            return
        discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            discovery_socket.bind(("", self.discovery_port))
            discovery_socket.settimeout(0.25)
        except OSError:
            discovery_socket.close()
            raise
        self._socket = discovery_socket
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="sendlan-discovery",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop heartbeats and close the UDP socket."""
        self._stop_event.set()
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=2)

    def peers_snapshot(self) -> list[dict[str, Any]]:
        """Return a stable snapshot of peers seen before their timeout."""
        with self._peers_lock:
            return [peer.to_dict() for peer in self._peers.values()]

    def set_username(self, username: str) -> None:
        """Change the display name included in future discovery heartbeats."""
        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("username cannot be empty")
        if len(normalized_username) > 128:
            raise ValueError("username must not exceed 128 characters")
        with self._identity_lock:
            self.username = normalized_username

    def _run(self) -> None:
        """Send periodic heartbeats, receive peers, and expire stale entries."""
        discovery_socket = self._socket
        if discovery_socket is None:
            return
        next_heartbeat = 0.0
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now >= next_heartbeat:
                self._send_heartbeat(discovery_socket)
                next_heartbeat = now + self.heartbeat_interval
            self._expire_peers(now)
            try:
                payload, address = discovery_socket.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                if not self._stop_event.is_set():
                    self.event_queue.put(
                        {
                            "type": "error",
                            "message": "UDP discovery stopped unexpectedly",
                        }
                    )
                return
            self._handle_heartbeat(
                payload,
                address[0],
            )

    def _send_heartbeat(self, discovery_socket: socket.socket) -> None:
        """Broadcast this node's identifier, display name, and TCP port."""
        with self._identity_lock:
            username = self.username
        message = json.dumps(
            {
                "username": username,
                "tcp_port": self.tcp_port,
                "device_id": self.device_id,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        for address in self._broadcast_targets():
            try:
                discovery_socket.sendto(message, (address, self.discovery_port))
            except OSError as exc:
                if not self._stop_event.is_set():
                    self.event_queue.put({"type": "error", "message": str(exc)})

    def _broadcast_targets(self) -> tuple[str, ...]:
        """Return global and directed broadcasts for active IPv4 interfaces."""
        targets = {self.broadcast_address}
        try:
            interface_addresses = psutil.net_if_addrs()
            interface_stats = psutil.net_if_stats()
        except (OSError, psutil.Error):
            return tuple(sorted(targets))

        for interface, addresses in interface_addresses.items():
            normalized_interface = interface.casefold()
            if (
                not normalized_interface.startswith("vethernet")
                and normalized_interface.startswith(VIRTUAL_INTERFACE_PREFIXES)
            ):
                continue
            stats = interface_stats.get(interface)
            if stats is not None and not stats.isup:
                continue
            for address in addresses:
                if address.family != socket.AF_INET or not address.address:
                    continue
                if address.address.startswith("127.") or not address.netmask:
                    continue
                try:
                    network = ipaddress.IPv4Network(
                        f"{address.address}/{address.netmask}",
                        strict=False,
                    )
                except ipaddress.AddressValueError:
                    continue
                if network.prefixlen >= 31:
                    continue
                directed_broadcast = address.broadcast or str(network.broadcast_address)
                if directed_broadcast not in {"0.0.0.0", address.address}:
                    targets.add(directed_broadcast)
        return tuple(sorted(targets))

    def _handle_heartbeat(self, payload: bytes, host: str) -> None:
        """Validate a heartbeat and update the active peer table."""
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(message, dict):
            return
        device_id = message.get("device_id") or message.get("instance_id")
        username = message.get("username")
        tcp_port = message.get("tcp_port")
        if (
            not isinstance(device_id, str)
            or not device_id
            or not isinstance(username, str)
            or not isinstance(tcp_port, int)
            or isinstance(tcp_port, bool)
            or not 1 <= tcp_port <= 65535
        ):
            return
        if device_id == self.device_id:
            if self._is_local_address(host):
                return
            previous_device_id = self.device_id
            self.device_id = uuid.uuid4().hex
            self.event_queue.put(
                {
                    "type": "device_id_changed",
                    "previous_device_id": previous_device_id,
                    "device_id": self.device_id,
                }
            )

        peer = Peer(
            device_id=device_id,
            username=username[:128],
            host=host,
            tcp_port=tcp_port,
            last_seen=time.monotonic(),
        )
        with self._peers_lock:
            is_new = device_id not in self._peers
            self._peers[device_id] = peer
        event_type = "peer_discovered" if is_new else "peer_updated"
        self.event_queue.put({"type": event_type, "peer": peer.to_dict()})

    @staticmethod
    def _is_local_address(host: str) -> bool:
        """Return whether an IPv4 source matches one of this device's adapters."""
        try:
            return any(
                address.family == socket.AF_INET and address.address == host
                for addresses in psutil.net_if_addrs().values()
                for address in addresses
            )
        except (OSError, psutil.Error):
            return False

    def _expire_peers(self, now: float) -> None:
        """Remove peers whose last heartbeat exceeds the configured timeout."""
        expired: list[Peer] = []
        with self._peers_lock:
            for device_id, peer in tuple(self._peers.items()):
                if now - peer.last_seen > self.peer_timeout:
                    expired.append(self._peers.pop(device_id))
        for peer in expired:
            self.event_queue.put({"type": "peer_lost", "peer": peer.to_dict()})


DiscoveryService = PeerDiscovery