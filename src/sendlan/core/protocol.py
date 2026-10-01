"""Length-prefixed JSON headers and bounded binary payloads for TCP."""

from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HEADER_LENGTH = struct.Struct("!I")
MAX_HEADER_SIZE = 64 * 1024
MAX_PAYLOAD_SIZE = 64 * 1024
CHUNK_SIZE = MAX_PAYLOAD_SIZE
PACKET_TYPES = frozenset({"CHAT", "FILE_OFFER", "FILE_CHUNK", "FILE_CANCEL"})


@dataclass(frozen=True, slots=True)
class Message:
    """A decoded chat message received from a peer."""

    sender: str
    text: str
    source: str = ""


@dataclass(slots=True)
class FileTransferTask:
    """Metadata and progress state for one outbound file transfer."""

    transfer_id: str
    path: Path
    total_size: int
    sha256: str
    sender: str
    transferred: int = 0


class ProtocolError(ValueError):
    """Raised when a peer sends malformed or incomplete framing data."""


def recv_exact(connection: socket.socket, size: int) -> bytes:
    """Read exactly ``size`` bytes or raise when the peer closes early."""
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("size must be a non-negative integer")

    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection closed before the frame was complete")
        data.extend(chunk)
    return bytes(data)


def send_header(connection: socket.socket, header: dict[str, Any]) -> None:
    """Send a JSON header prefixed by its four-byte network-order length."""
    packet_type = header.get("type")
    if not isinstance(packet_type, str) or packet_type not in PACKET_TYPES:
        raise ProtocolError("unsupported packet type")
    payload_size = header.get("payload_size")
    if not isinstance(payload_size, int) or isinstance(payload_size, bool):
        raise ProtocolError("header payload_size must be an integer")
    if not 0 <= payload_size <= MAX_PAYLOAD_SIZE:
        raise ProtocolError("payload_size is outside the supported range")

    try:
        encoded = json.dumps(
            header,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ProtocolError("header cannot be encoded as JSON") from exc
    if not encoded or len(encoded) > MAX_HEADER_SIZE:
        raise ProtocolError("header is outside the supported size range")
    connection.sendall(HEADER_LENGTH.pack(len(encoded)) + encoded)


def recv_header(connection: socket.socket) -> dict[str, Any]:
    """Read and validate a length-prefixed JSON header."""
    header_size = HEADER_LENGTH.unpack(recv_exact(connection, HEADER_LENGTH.size))[0]
    if not 0 < header_size <= MAX_HEADER_SIZE:
        raise ProtocolError("header length is outside the supported range")

    try:
        header = json.loads(recv_exact(connection, header_size).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("header is not valid UTF-8 JSON") from exc

    if not isinstance(header, dict):
        raise ProtocolError("header must be a JSON object")
    packet_type = header.get("type")
    if not isinstance(packet_type, str) or packet_type not in PACKET_TYPES:
        raise ProtocolError("unsupported packet type")
    payload_size = header.get("payload_size")
    if not isinstance(payload_size, int) or isinstance(payload_size, bool):
        raise ProtocolError("header payload_size must be an integer")
    if not 0 <= payload_size <= MAX_PAYLOAD_SIZE:
        raise ProtocolError("payload_size is outside the supported range")
    return header


def send_frame(
    connection: socket.socket,
    header: dict[str, Any],
    payload: bytes = b"",
) -> None:
    """Send one header and its matching payload."""
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ProtocolError("payload is outside the supported size range")
    framed_header = dict(header)
    framed_header["payload_size"] = len(payload)
    send_header(connection, framed_header)
    if payload:
        connection.sendall(payload)


def recv_payload(connection: socket.socket, header: dict[str, Any]) -> bytes:
    """Read the payload whose size was declared in ``header``."""
    payload_size = header["payload_size"]
    return recv_exact(connection, payload_size)


class Protocol:
    """Stateless facade for framing TCP packets."""

    recv_exact = staticmethod(recv_exact)
    send_header = staticmethod(send_header)
    recv_header = staticmethod(recv_header)
    send_frame = staticmethod(send_frame)
    recv_payload = staticmethod(recv_payload)