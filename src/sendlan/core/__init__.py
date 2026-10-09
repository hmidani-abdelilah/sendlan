"""Network discovery, packet framing, and transfer components."""

from .discovery import Peer, PeerDiscovery
from .protocol import FileTransferTask, Message, Protocol, ProtocolError
from .receiver import Receiver
from .sender import (
    FileOfferTimeout,
    FileTransferRejected,
    TransferCancelled,
    send_file,
    send_text,
)

__all__ = [
    "FileTransferTask",
    "FileOfferTimeout",
    "FileTransferRejected",
    "Message",
    "Peer",
    "PeerDiscovery",
    "Protocol",
    "ProtocolError",
    "Receiver",
    "TransferCancelled",
    "send_file",
    "send_text",
]