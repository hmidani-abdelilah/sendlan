"""Live list of discoverable LAN peers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import customtkinter


class PeerListFrame(customtkinter.CTkFrame):
    """Scrollable peer selector that reports selection to its owner."""

    def __init__(
        self,
        master: Any,
        on_select: Callable[[dict[str, Any]], None],
        **kwargs: Any,
    ) -> None:
        """Create a titled peer list with a no-peers empty state."""
        super().__init__(master, **kwargs)
        self._on_select = on_select
        self._selected_device_id: str | None = None
        self._peers: list[dict[str, Any]] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.title = customtkinter.CTkLabel(
            self,
            text="Nearby peers",
            anchor="w",
            font=customtkinter.CTkFont(size=14, weight="bold"),
        )
        self.title.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        self.list_frame = customtkinter.CTkScrollableFrame(self, label_text="")
        self.list_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self._empty_label = customtkinter.CTkLabel(
            self.list_frame,
            text="Searching for devices...",
            text_color=("gray45", "gray65"),
            wraplength=200,
        )
        self._empty_label.grid(row=0, column=0, padx=8, pady=12, sticky="ew")

    def set_peers(self, peers: Sequence[dict[str, Any]]) -> None:
        """Replace the visible peer rows while preserving a valid selection."""
        self._peers = sorted(peers, key=lambda peer: peer["username"].casefold())
        device_ids = {peer["device_id"] for peer in self._peers}
        if self._selected_device_id not in device_ids:
            self._selected_device_id = None
        for child in self.list_frame.winfo_children():
            child.destroy()

        if not self._peers:
            self._empty_label = customtkinter.CTkLabel(
                self.list_frame,
                text="No peers discovered",
                text_color=("gray45", "gray65"),
                wraplength=200,
            )
            self._empty_label.grid(row=0, column=0, padx=8, pady=12, sticky="ew")
            return

        for row, peer in enumerate(self._peers):
            device_id = peer["device_id"]
            selected = device_id == self._selected_device_id
            button = customtkinter.CTkButton(
                self.list_frame,
                text=f'{peer["username"]}\n{peer["host"]}:{peer["tcp_port"]}',
                anchor="w",
                height=52,
                fg_color=("#dcebe8", "#244640") if selected else ("#f1f4f3", "#292d2c"),
                text_color=("#163d36", "#e7f1ee"),
                hover_color=("#c8dfd9", "#315950"),
                command=lambda selected_peer=peer: self.select_peer(selected_peer),
            )
            button.grid(row=row, column=0, padx=4, pady=3, sticky="ew")

    def select_peer(self, peer: dict[str, Any]) -> None:
        """Select a peer, redraw the list, and invoke the callback."""
        self._selected_device_id = peer["device_id"]
        self.set_peers(self._peers)
        self._on_select(peer)

    def selected_peer(self) -> dict[str, Any] | None:
        """Return the selected peer record, if the peer is still active."""
        return next(
            (
                peer
                for peer in self._peers
                if peer["device_id"] == self._selected_device_id
            ),
            None,
        )