"""Chat transcript and message composer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import customtkinter


class ChatFrame(customtkinter.CTkFrame):
    """Display chat messages and forward submitted text to a callback."""

    def __init__(
        self,
        master: Any,
        on_send: Callable[[str], None],
        on_choose_files: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create the transcript, text entry, and send control."""
        super().__init__(master, **kwargs)
        self._on_send = on_send
        self._on_choose_files = on_choose_files
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.transcript = customtkinter.CTkTextbox(self, wrap="word", state="disabled")
        self.transcript.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.entry = customtkinter.CTkEntry(self, placeholder_text="Message")
        self.entry.grid(row=1, column=0, padx=(0, 8), pady=(8, 0), sticky="ew")
        self.entry.bind("<Return>", self._submit)
        self.file_button = customtkinter.CTkButton(
            self,
            text="File...",
            width=76,
            command=self._choose_files,
            state="normal" if on_choose_files is not None else "disabled",
        )
        self.file_button.grid(row=1, column=1, padx=(0, 8), pady=(8, 0))
        self.send_button = customtkinter.CTkButton(
            self,
            text="Send",
            width=84,
            command=self._submit,
        )
        self.send_button.grid(row=1, column=2, pady=(8, 0))

    def append_message(self, sender: str, text: str) -> None:
        """Append a timestamped message to the read-only transcript."""
        timestamp = datetime.now().strftime("%H:%M")
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"[{timestamp}] {sender}: {text}\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the message entry and send button."""
        state = "normal" if enabled else "disabled"
        self.entry.configure(state=state)
        self.send_button.configure(state=state)
        self.file_button.configure(
            state=(
                "normal"
                if enabled and self._on_choose_files is not None
                else "disabled"
            )
        )

    def _choose_files(self) -> None:
        """Invoke the file chooser callback when one is configured."""
        if self._on_choose_files is not None:
            self._on_choose_files()

    def _submit(self, event: Any = None) -> str:
        """Submit non-empty text and clear the composer."""
        if event is not None:
            event.widget.focus_set()
        message = self.entry.get().strip()
        if message:
            self.entry.delete(0, "end")
            self._on_send(message)
        return "break"