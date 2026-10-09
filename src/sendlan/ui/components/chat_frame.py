"""Chat transcript and message composer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

import customtkinter

SenderType = Literal["me", "other", "system"]
MessageKind = Literal["text", "file", "system"]


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

        self.transcript = customtkinter.CTkScrollableFrame(
            self,
            corner_radius=14,
            border_width=1,
            border_color=("#e1e5ee", "#30343f"),
            fg_color=("#f4f6fb", "#191b22"),
        )
        self.transcript.grid(
            row=0,
            column=0,
            columnspan=3,
            padx=2,
            pady=(0, 10),
            sticky="nsew",
        )
        self._message_count = 0
        self.entry = customtkinter.CTkEntry(
            self,
            height=40,
            corner_radius=12,
            placeholder_text="Message",
        )
        self.entry.grid(row=1, column=0, padx=(0, 8), pady=(8, 0), sticky="ew")
        self.entry.bind("<Return>", self._submit)
        self.file_button = customtkinter.CTkButton(
            self,
            text="File...",
            width=76,
            height=40,
            corner_radius=12,
            fg_color=("#e8eaf1", "#30343f"),
            hover_color=("#dce0eb", "#3b404d"),
            text_color=("#323747", "#e6e8ef"),
            command=self._choose_files,
            state="normal" if on_choose_files is not None else "disabled",
        )
        self.file_button.grid(row=1, column=1, padx=(0, 8), pady=(8, 0))
        self.send_button = customtkinter.CTkButton(
            self,
            text="Send",
            width=84,
            height=40,
            corner_radius=12,
            fg_color=("#7253d6", "#7253d6"),
            hover_color=("#6042c4", "#6042c4"),
            command=self._submit,
        )
        self.send_button.grid(row=1, column=2, pady=(8, 0))

    def append_message(
        self,
        sender: str,
        text: str,
        *,
        sender_type: SenderType = "other",
        kind: MessageKind = "text",
    ) -> None:
        """Append a colored, timestamped message bubble."""
        timestamp = datetime.now().strftime("%H:%M")
        styles: dict[str, dict[str, Any]] = {
            "me": {
                "background": ("#7253d6", "#7253d6"),
                "text": ("#ffffff", "#ffffff"),
                "metadata": ("#e9e2ff", "#e9e2ff"),
                "border": ("#7253d6", "#7253d6"),
            },
            "other": {
                "background": ("#ffffff", "#282b35"),
                "text": ("#222532", "#f1f2f6"),
                "metadata": ("#777d8e", "#a9afbf"),
                "border": ("#e1e5ee", "#383c48"),
            },
            "sent_file": {
                "background": ("#287a9b", "#287a9b"),
                "text": ("#ffffff", "#ffffff"),
                "metadata": ("#d8f3ff", "#d8f3ff"),
                "border": ("#287a9b", "#287a9b"),
            },
            "received_file": {
                "background": ("#e4f5ef", "#203b35"),
                "text": ("#19483c", "#dff8ee"),
                "metadata": ("#4f7b6d", "#99c8b8"),
                "border": ("#cce9de", "#31584d"),
            },
            "system": {
                "background": ("#fff4d6", "#47391d"),
                "text": ("#614514", "#ffe9ad"),
                "metadata": ("#8a6a27", "#d6bd79"),
                "border": ("#f0dfb3", "#66552f"),
            },
        }
        if sender_type == "system" or kind == "system":
            style = styles["system"]
        elif kind == "file":
            style = styles["sent_file" if sender_type == "me" else "received_file"]
        else:
            style = styles[sender_type]
        bubble_row = customtkinter.CTkFrame(
            self.transcript,
            fg_color="transparent",
        )
        bubble_row.grid(
            row=self._message_count,
            column=0,
            padx=8,
            pady=4,
            sticky="ew",
        )
        bubble_row.grid_columnconfigure(0, weight=1)
        bubble_row.grid_columnconfigure(1, weight=1)

        bubble = customtkinter.CTkFrame(
            bubble_row,
            fg_color=style["background"],
            border_width=1,
            border_color=style["border"],
            corner_radius=16,
        )
        header = customtkinter.CTkFrame(bubble, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 2))
        header.grid_columnconfigure(0, weight=1)
        customtkinter.CTkLabel(
            header,
            text=sender,
            text_color=style["metadata"],
            font=("Arial", 11, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        customtkinter.CTkLabel(
            header,
            text=timestamp,
            text_color=style["metadata"],
            font=("Arial", 10),
            anchor="e",
        ).grid(row=0, column=1, sticky="e")
        customtkinter.CTkLabel(
            bubble,
            text=text,
            text_color=style["text"],
            font=("Arial", 13),
            wraplength=min(420, max(180, int(self.transcript.winfo_width() * 0.68))),
            justify="left",
            anchor="w",
        ).pack(padx=12, pady=(0, 9), anchor="w")

        self._message_count += 1
        if sender_type == "system":
            bubble.grid(
                row=0,
                column=0,
                columnspan=2,
                sticky="",
            )
        else:
            bubble.grid(
                row=0,
                column=1 if sender_type == "me" else 0,
                sticky="e" if sender_type == "me" else "w",
            )

        self.transcript.update_idletasks()
        self.transcript._parent_canvas.yview_moveto(1.0)

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