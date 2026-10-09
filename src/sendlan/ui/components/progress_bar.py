"""File transfer progress display with a cancellation action."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import customtkinter

TransferDirection = Literal["Sending", "Receiving"]


class TransferProgressFrame(customtkinter.CTkFrame):
    """Show transfer progress and expose a cancel button."""

    def __init__(
        self,
        master: Any,
        on_cancel: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        """Create an idle progress bar and disabled cancel control."""
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._on_cancel = on_cancel
        self.grid_columnconfigure(0, weight=1)
        self.bar = customtkinter.CTkProgressBar(
            self,
            height=10,
            corner_radius=5,
            progress_color=("#7253d6", "#9278ed"),
        )
        self.bar.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.bar.set(0)
        self.label = customtkinter.CTkLabel(self, text="Idle", width=190, anchor="e")
        self.label.grid(row=0, column=1, padx=(0, 8))
        self.cancel_button = customtkinter.CTkButton(
            self,
            text="Cancel",
            width=76,
            command=self._on_cancel,
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=2)

    def set_progress(
        self,
        filename: str,
        transferred: int,
        total: int,
        direction: TransferDirection = "Sending",
    ) -> None:
        """Update the bar and label from a transfer progress event."""
        fraction = min(1.0, transferred / total) if total else 1.0
        self.bar.set(fraction)
        self.label.configure(text=f"{direction} · {fraction:.0%} · {filename}")
        self.bar.configure(
            progress_color=(
                ("#23856d", "#43b394")
                if direction == "Receiving"
                else ("#7253d6", "#9278ed")
            )
        )
        self.cancel_button.configure(state="normal")

    def reset(self) -> None:
        """Return the progress display to its idle state."""
        self.bar.set(0)
        self.label.configure(text="Idle")
        self.cancel_button.configure(state="disabled")