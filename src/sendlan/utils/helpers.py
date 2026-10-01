"""Network address, checksum, path, and display-formatting helpers."""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path, PurePosixPath

DEFAULT_CHUNK_SIZE = 64 * 1024


def get_local_ip() -> str:
    """Return the primary local IPv4 address without sending a packet."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def calculate_sha256(path: str | Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Calculate a file's SHA-256 digest using bounded memory."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def safe_filename(filename: str, fallback: str = "received-file") -> str:
    """Normalize an untrusted filename to one safe path component."""
    basename = PurePosixPath(filename.replace("\\", "/")).name
    forbidden = set('<>:"/\\|?*')
    cleaned = "".join(
        "_" if char in forbidden or ord(char) < 32 else char
        for char in basename
    )
    cleaned = cleaned.strip(" .")[:240]
    return cleaned or fallback


def format_bytes(size: int) -> str:
    """Format a non-negative byte count using binary units."""
    if size < 0:
        raise ValueError("size must not be negative")
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def resolve_downloads_dir(project_root: str | Path, configured_path: str) -> Path:
    """Resolve the download directory relative to the project when needed."""
    root = Path(project_root).resolve()
    target = Path(configured_path).expanduser()
    if not target.is_absolute():
        target = root / target
    return target.resolve()