"""TCP listener for incoming messages and verified chunked files."""

from __future__ import annotations

import hashlib
import os
import queue
import re
import socket
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from .protocol import CHUNK_SIZE, Message, recv_exact, recv_header, recv_payload
from .sender import DEFAULT_TCP_PORT
from ..utils.helpers import safe_filename

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class Receiver:
    """Accept peer connections and publish received items through a queue."""

    def __init__(
        self,
        download_dir: str | Path = "downloads",
        event_queue: queue.Queue[dict[str, Any]] | None = None,
        host: str = "0.0.0.0",
        port: int = DEFAULT_TCP_PORT,
    ) -> None:
        self.download_dir = Path(download_dir)
        self.event_queue = event_queue if event_queue is not None else queue.Queue()
        self.host = host
        self.port = port
        self._stop_event = threading.Event()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._clients: set[socket.socket] = set()
        self._active_transfers: dict[str, socket.socket] = {}
        self._clients_lock = threading.Lock()

    def start(self) -> int:
        """Bind the listener, start its daemon thread, and return its TCP port."""
        if self._thread is not None and self._thread.is_alive():
            return self.port

        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.host, self.port))
            listener.listen()
            listener.settimeout(0.5)
        except OSError:
            listener.close()
            raise
        self._listener = listener
        self.port = listener.getsockname()[1]
        self._thread = threading.Thread(
            target=self._accept_loop,
            name="sendlan-receiver",
            daemon=True,
        )
        self._thread.start()
        return self.port

    def stop(self) -> None:
        """Stop accepting connections and close active clients."""
        self._stop_event.set()
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        with self._clients_lock:
            clients = tuple(self._clients)
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def cancel_transfer(self, transfer_id: str) -> bool:
        """Close an active incoming transfer and return whether it was found."""
        with self._clients_lock:
            connection = self._active_transfers.get(transfer_id)
        if connection is None:
            return False
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        connection.close()
        return True

    def _accept_loop(self) -> None:
        """Accept TCP connections and dispatch each peer to a worker thread."""
        listener = self._listener
        if listener is None:
            return
        while not self._stop_event.is_set():
            try:
                connection, address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if not self._stop_event.is_set():
                    self._publish("error", message="TCP listener stopped unexpectedly")
                return
            threading.Thread(
                target=self._handle_connection,
                args=(connection, address),
                name="sendlan-peer-handler",
                daemon=True,
            ).start()

    def _handle_connection(
        self,
        connection: socket.socket,
        address: tuple[str, int],
    ) -> None:
        """Read and dispatch one chat, file offer, or cancellation connection."""
        with self._clients_lock:
            self._clients.add(connection)
        try:
            with connection:
                header = recv_header(connection)
                packet_type = header.get("type")
                if packet_type == "CHAT":
                    message = Message(
                        sender=self._validated_sender(header.get("sender")),
                        text=recv_payload(connection, header).decode("utf-8"),
                        source=address[0],
                    )
                    self._publish(
                        "chat",
                        message=message.text,
                        sender=message.sender,
                        source=message.source,
                    )
                elif packet_type == "FILE_OFFER":
                    self._receive_file(connection, header, address[0])
                elif packet_type == "FILE_CANCEL":
                    self._receive_cancel(header, address[0])
                else:
                    raise ValueError("unsupported packet type")
        except (ConnectionError, OSError, UnicodeDecodeError, ValueError) as exc:
            if not self._stop_event.is_set():
                self._publish("error", message=str(exc), source=address[0])
        finally:
            with self._clients_lock:
                self._clients.discard(connection)

    def _receive_file(
        self,
        connection: socket.socket,
        notice: dict[str, Any],
        source: str,
    ) -> None:
        """Receive one offered file into a temporary path and verify its digest."""
        transfer_id = notice.get("transfer_id")
        filename = notice.get("filename")
        file_size = notice.get("size")
        expected_digest = notice.get("sha256")
        sender = self._validated_sender(notice.get("sender"))
        if notice["payload_size"] != 0:
            raise ValueError("file notice cannot contain a payload")
        if not isinstance(transfer_id, str) or not transfer_id:
            raise ValueError("invalid transfer identifier")
        if (
            not isinstance(filename, str)
            or not filename
            or "\x00" in filename
        ):
            raise ValueError("invalid filename")
        safe_name = safe_filename(filename)
        if safe_name in ("", ".", ".."):
            raise ValueError("invalid filename")
        if (
            not isinstance(file_size, int)
            or isinstance(file_size, bool)
            or file_size < 0
        ):
            raise ValueError("invalid file size")
        if (
            not isinstance(expected_digest, str)
            or not _SHA256_PATTERN.fullmatch(expected_digest)
        ):
            raise ValueError("invalid SHA-256 digest")

        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix=".sendlan-", suffix=".part", dir=self.download_dir
        )
        temporary_path = Path(temporary_name)
        received = 0
        digest = hashlib.sha256()
        cancelled_event: dict[str, Any] | None = None
        with self._clients_lock:
            self._active_transfers[transfer_id] = connection
        try:
            with os.fdopen(temporary_fd, "wb") as destination:
                while True:
                    header = recv_header(connection)
                    packet_type = header.get("type")
                    if packet_type == "FILE_CANCEL":
                        if (
                            header["payload_size"] != 0
                            or header.get("transfer_id") != transfer_id
                            or self._validated_sender(header.get("sender")) != sender
                        ):
                            raise ValueError("invalid file cancellation packet")
                        cancelled_event = {
                            "transfer_id": transfer_id,
                            "filename": safe_name,
                            "sender": sender,
                            "source": source,
                            "transferred": received,
                            "total": file_size,
                        }
                        break
                    if packet_type != "FILE_CHUNK":
                        raise ValueError("expected a file chunk or cancellation packet")
                    payload_size = header["payload_size"]
                    is_final = header.get("final")
                    if (
                        header.get("transfer_id") != transfer_id
                        or self._validated_sender(header.get("sender")) != sender
                        or header.get("offset") != received
                        or not isinstance(is_final, bool)
                        or (payload_size == 0 and not (is_final and file_size == 0))
                        or received + payload_size > file_size
                        or (is_final and received + payload_size != file_size)
                        or (not is_final and received + payload_size >= file_size)
                        or payload_size > CHUNK_SIZE
                    ):
                        raise ValueError("invalid file chunk")
                    chunk = recv_exact(connection, payload_size)
                    destination.write(chunk)
                    digest.update(chunk)
                    received += payload_size
                    self._publish(
                        "file_progress",
                        transfer_id=transfer_id,
                        filename=safe_name,
                        transferred=received,
                        total=file_size,
                        sender=sender,
                        source=source,
                    )
                    if is_final:
                        break

            if cancelled_event is None:
                if (
                    received != file_size
                    or digest.hexdigest() != expected_digest
                ):
                    raise ValueError(
                        "received file failed size or SHA-256 verification"
                    )
                target = self._commit_received_file(temporary_path, safe_name)
                self._publish(
                    "file_received",
                    filename=target.name,
                    path=str(target),
                    size=received,
                    sha256=expected_digest,
                    sender=sender,
                    source=source,
                    transfer_id=transfer_id,
                )
        finally:
            with self._clients_lock:
                self._active_transfers.pop(transfer_id, None)
            temporary_path.unlink(missing_ok=True)
        if cancelled_event is not None:
            self._publish("transfer_cancelled", **cancelled_event)

    def _commit_received_file(self, temporary_path: Path, filename: str) -> Path:
        """Move verified data into a unique filename across filesystem types."""
        target = self._available_path(filename)
        while True:
            try:
                os.link(temporary_path, target)
            except FileExistsError:
                target = self._available_path(filename, increment=True)
                continue
            except OSError:
                try:
                    with target.open("xb") as destination:
                        with temporary_path.open("rb") as source:
                            shutil.copyfileobj(source, destination, CHUNK_SIZE)
                except FileExistsError:
                    target = self._available_path(filename, increment=True)
                    continue
                except OSError:
                    try:
                        target.unlink(missing_ok=True)
                    except OSError:
                        pass
                    raise
            temporary_path.unlink(missing_ok=True)
            return target

    def _receive_cancel(self, header: dict[str, Any], source: str) -> None:
        """Publish a standalone cancellation packet after validating its fields."""
        if header["payload_size"] != 0:
            raise ValueError("file cancellation cannot contain a payload")
        transfer_id = header.get("transfer_id")
        if not isinstance(transfer_id, str) or not transfer_id:
            raise ValueError("invalid transfer identifier")
        self._publish(
            "transfer_cancelled",
            transfer_id=transfer_id,
            sender=self._validated_sender(header.get("sender")),
            source=source,
        )

    @staticmethod
    def _validated_sender(sender: Any) -> str:
        """Validate and normalize a sender name from a packet header."""
        if not isinstance(sender, str) or not sender.strip():
            raise ValueError("missing sender name")
        return sender.strip()[:128]

    def _available_path(self, filename: str, increment: bool = False) -> Path:
        """Return a destination path that will not overwrite an existing file."""
        candidate = self.download_dir / filename
        if not increment and not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        index = 1
        while True:
            candidate = self.download_dir / f"{stem} ({index}){suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def _publish(self, event_type: str, **details: Any) -> None:
        """Publish one receiver event without touching any UI objects."""
        self.event_queue.put({"type": event_type, **details})