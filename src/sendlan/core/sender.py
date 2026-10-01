"""TCP peer client for sending messages and chunked files."""

from __future__ import annotations

import getpass
import hashlib
import socket
import threading
import uuid
from pathlib import Path
from typing import Callable

from .protocol import CHUNK_SIZE, FileTransferTask, send_frame, send_header

DEFAULT_TCP_PORT = 50001
ProgressCallback = Callable[[int, int], None]


class TransferCancelled(Exception):
    """Raised when a file transfer is cancelled by its caller."""


def _sender_name(sender_name: str | None) -> str:
    """Return a bounded display name for outgoing packet headers."""
    return (sender_name or getpass.getuser()).strip()[:128] or "SendLan user"


def send_text(
    host: str,
    message: str,
    port: int = DEFAULT_TCP_PORT,
    timeout: float = 10,
    *,
    sender_name: str | None = None,
) -> None:
    """Send one UTF-8 chat message to a peer."""
    payload = message.encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as connection:
        send_frame(
            connection,
            {"type": "CHAT", "sender": _sender_name(sender_name)},
            payload,
        )


def _file_sha256(path: Path, cancel_event: threading.Event | None) -> str:
    """Hash a file incrementally, checking cancellation between chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            if cancel_event is not None and cancel_event.is_set():
                raise TransferCancelled("file transfer was cancelled")
            digest.update(chunk)
    return digest.hexdigest()


def send_file(
    host: str,
    path: str | Path,
    port: int = DEFAULT_TCP_PORT,
    *,
    sender_name: str | None = None,
    cancel_event: threading.Event | None = None,
    progress: ProgressCallback | None = None,
    timeout: float = 10,
) -> str:
    """Send a file in bounded chunks and return its transfer identifier."""
    file_path = Path(path)
    file_size = file_path.stat().st_size
    digest = _file_sha256(file_path, cancel_event)
    sender = _sender_name(sender_name)
    task = FileTransferTask(
        transfer_id=uuid.uuid4().hex,
        path=file_path,
        total_size=file_size,
        sha256=digest,
        sender=sender,
    )
    sent = 0
    sent_digest = hashlib.sha256()
    if cancel_event is not None and cancel_event.is_set():
        raise TransferCancelled("file transfer was cancelled")

    with socket.create_connection((host, port), timeout=timeout) as connection:
        send_header(
            connection,
            {
                "type": "FILE_OFFER",
                "sender": sender,
                "transfer_id": task.transfer_id,
                "filename": task.path.name,
                "size": task.total_size,
                "sha256": task.sha256,
                "payload_size": 0,
            },
        )
        with file_path.open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                if cancel_event is not None and cancel_event.is_set():
                    send_frame(
                        connection,
                        {
                            "type": "FILE_CANCEL",
                            "transfer_id": task.transfer_id,
                            "sender": sender,
                        },
                    )
                    raise TransferCancelled("file transfer was cancelled")
                next_offset = sent + len(chunk)
                send_frame(
                    connection,
                    {
                        "type": "FILE_CHUNK",
                        "sender": sender,
                        "transfer_id": task.transfer_id,
                        "offset": sent,
                        "final": next_offset == file_size,
                    },
                    chunk,
                )
                sent = next_offset
                task.transferred = sent
                sent_digest.update(chunk)
                if progress is not None:
                    progress(sent, file_size)

        if sent != task.total_size or sent_digest.hexdigest() != task.sha256:
            raise OSError("file changed while it was being sent")
        if file_size == 0:
            send_frame(
                connection,
                {
                    "type": "FILE_CHUNK",
                    "sender": sender,
                    "transfer_id": task.transfer_id,
                    "offset": 0,
                    "final": True,
                },
            )

        if progress is not None and file_size == 0:
            progress(0, 0)
    return task.transfer_id