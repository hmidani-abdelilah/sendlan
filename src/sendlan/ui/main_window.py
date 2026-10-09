"""CustomTkinter peer chat window with queue-based network updates."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import customtkinter
import CTkFileDialog
from CTkMenuBarPlus import CTkMenuBar, CustomDropdownMenu
from CTkMessagebox import CTkMessagebox
from PIL import Image, ImageTk
from playsound3 import PlaysoundException, playsound
from tkinterdnd2 import DND_FILES, DND_TEXT, TkinterDnD
from tkinter import TclError

from ..config import ConfigError, ConfigStore, default_device_name
from ..core.discovery import PeerDiscovery
from ..core.receiver import Receiver
from ..core.sender import (
    FileOfferTimeout,
    FileTransferRejected,
    TransferCancelled,
    send_file,
    send_text,
)
from ..ui.components import (
    ChatFrame,
    PeerListFrame,
    TransferDirection,
    TransferProgressFrame,
)
from ..utils.helpers import resolve_downloads_dir

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class MainWindow(customtkinter.CTk, TkinterDnD.DnDWrapper):
    """Main application window and owner of network service lifetimes."""

    def __init__(self) -> None:
        super().__init__()
        self.config_store = ConfigStore(PROJECT_ROOT / "config.json")
        self.settings = self.config_store.load()
        customtkinter.set_appearance_mode(self.settings.appearance_mode)
        self._dnd_available = False
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            self._dnd_available = True
        except RuntimeError:
            self.TkdndVersion = None
        self.title("sendlan - LAN File & Chat Transfer")
        self.geometry("920x640")
        self.minsize(760, 520)
        self._set_window_icon()

        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.peers: dict[str, dict[str, Any]] = {}
        self.selected_peer_id: str | None = None
        self._transfer: dict[str, Any] | None = None
        self._closing = False
        self._queue_after_id: str | None = None
        self._settings_dialog: customtkinter.CTkToplevel | None = None
        self._file_offer_dialogs: dict[str, customtkinter.CTkToplevel] = {}

        self._build_layout()
        if self._dnd_available:
            self.drop_target_register(DND_FILES, DND_TEXT)
            self.dnd_bind("<<Drop>>", self._on_drop)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        downloads_dir = resolve_downloads_dir(
            PROJECT_ROOT,
            self.settings.downloads_dir,
        )
        self.receiver = Receiver(
            downloads_dir,
            self.events,
            port=self.settings.tcp_port,
        )
        self.discovery: PeerDiscovery | None = None
        try:
            tcp_port = self.receiver.start()
            self.discovery = PeerDiscovery(
                username=self.settings.username,
                tcp_port=tcp_port,
                event_queue=self.events,
                device_id=self.settings.device_id,
                discovery_port=self.settings.discovery_port,
                heartbeat_interval=self.settings.heartbeat_interval,
                peer_timeout=self.settings.peer_timeout,
            )
            self.discovery.start()
            self._set_status(
                f"TCP {tcp_port} active; UDP discovery on "
                f"{self.settings.discovery_port}"
            )
        except OSError as exc:
            self.receiver.stop()
            self._show_error(
                f"Network services could not start: {exc}"
            )
            self._set_status("Network services unavailable")
        if not self._dnd_available:
            self._set_status("Drag and drop unavailable; use File > Choose files")

        self._queue_after_id = self.after(100, self.poll_queue)

    def _set_window_icon(self) -> None:
        """Load the packaged PNG icon through Pillow when it is available."""
        icon_path = PROJECT_ROOT / "assets" / "icon.png"
        try:
            with Image.open(icon_path) as image:
                self._icon_photo: Any = ImageTk.PhotoImage(image.convert("RGBA"))
            self.iconphoto(
                True,
                self._icon_photo,
            )
        except (OSError, TclError):
            self._icon_photo = None

    def _build_layout(self) -> None:
        """Compose the menu, peer selector, chat, and transfer controls."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_menu()

        self.peer_list = PeerListFrame(
            self,
            self._select_peer,
            width=250,
            corner_radius=0,
        )
        self.peer_list.grid(row=1, column=0, sticky="nsew")

        content = customtkinter.CTkFrame(self, corner_radius=0, fg_color="transparent")
        content.grid(row=1, column=1, padx=18, pady=16, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self.chat_frame = ChatFrame(
            content,
            self._send_chat_text,
            self._choose_files,
            fg_color="transparent",
        )
        self.chat_frame.grid(row=0, column=0, sticky="nsew")
        self.chat_frame.set_enabled(False)

        self.progress_frame = TransferProgressFrame(
            content,
            self._cancel_transfer,
            fg_color="transparent",
        )
        self.progress_frame.grid(row=1, column=0, pady=(10, 0), sticky="ew")

        self.status_label = customtkinter.CTkLabel(
            content,
            text="Starting network services...",
            anchor="w",
        )
        self.status_label.grid(row=2, column=0, pady=(8, 0), sticky="ew")

    def _build_menu(self) -> None:
        """Create file and appearance menus with CTkMenuBarPlus."""
        self.menu_bar = CTkMenuBar(self)
        self.menu_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        file_button = self.menu_bar.add_cascade("File")
        file_menu = CustomDropdownMenu(widget=file_button, master=self)
        file_menu.add_option("Choose files...", command=self._choose_files)
        file_menu.add_option("Settings...", command=self._open_settings)
        file_menu.add_option("Change device name...", command=self._change_device_name)
        file_menu.add_separator()
        file_menu.add_option("Exit", command=self._on_close)
        view_button = self.menu_bar.add_cascade("Appearance")
        view_menu = CustomDropdownMenu(widget=view_button, master=self)
        for mode in ("system", "light", "dark"):
            view_menu.add_option(
                mode.title(),
                command=lambda selected_mode=mode: self._set_theme_mode(selected_mode),
            )

    def _open_settings(self) -> None:
        """Open a modal editor for persistent application preferences."""
        if self._settings_dialog is not None:
            if self._settings_dialog.winfo_exists():
                self._settings_dialog.deiconify()
                self._settings_dialog.lift()
                return
            self._settings_dialog = None

        dialog = customtkinter.CTkToplevel(self)
        dialog.title("SendLan Settings")
        dialog.geometry("540x500")
        dialog.minsize(500, 460)
        dialog.transient(self)
        dialog.grid_columnconfigure(1, weight=1)
        self._settings_dialog = dialog

        fields = (
            ("username", "Device name", self.settings.username),
            ("tcp_port", "TCP port", str(self.settings.tcp_port)),
            (
                "discovery_port",
                "UDP discovery port",
                str(self.settings.discovery_port),
            ),
            (
                "heartbeat_interval",
                "Heartbeat interval (seconds)",
                str(self.settings.heartbeat_interval),
            ),
            (
                "peer_timeout",
                "Peer timeout (seconds)",
                str(self.settings.peer_timeout),
            ),
            ("downloads_dir", "Downloads folder", self.settings.downloads_dir),
        )
        entries: dict[str, customtkinter.CTkEntry] = {}
        for row, (key, label, value) in enumerate(fields):
            customtkinter.CTkLabel(dialog, text=label, anchor="w").grid(
                row=row,
                column=0,
                padx=(20, 12),
                pady=7,
                sticky="w",
            )
            entry = customtkinter.CTkEntry(dialog)
            entry.insert(0, value)
            entry.grid(
                row=row,
                column=1,
                padx=(0, 10 if key == "downloads_dir" else 20),
                pady=7,
                sticky="ew",
            )
            entries[key] = entry
            if key == "downloads_dir":
                customtkinter.CTkButton(
                    dialog,
                    text="Browse...",
                    width=86,
                    command=lambda target=entry: self._browse_download_folder(target),
                ).grid(row=row, column=2, padx=(0, 20), pady=7)

        appearance_row = len(fields)
        customtkinter.CTkLabel(dialog, text="Appearance", anchor="w").grid(
            row=appearance_row,
            column=0,
            padx=(20, 12),
            pady=7,
            sticky="w",
        )
        appearance_menu = customtkinter.CTkOptionMenu(
            dialog,
            values=["system", "light", "dark"],
        )
        appearance_menu.set(self.settings.appearance_mode)
        appearance_menu.grid(
            row=appearance_row,
            column=1,
            padx=(0, 20),
            pady=7,
            sticky="w",
        )

        network_note = customtkinter.CTkLabel(
            dialog,
            text="Port and timing changes take effect after restarting SendLan.",
            text_color=("gray45", "gray65"),
            wraplength=490,
            justify="left",
        )
        network_note.grid(
            row=appearance_row + 1,
            column=0,
            columnspan=3,
            padx=20,
            pady=(12, 4),
            sticky="w",
        )

        buttons = customtkinter.CTkFrame(dialog, fg_color="transparent")
        buttons.grid(
            row=appearance_row + 2,
            column=0,
            columnspan=3,
            padx=20,
            pady=(12, 18),
            sticky="e",
        )
        customtkinter.CTkButton(
            buttons,
            text="Cancel",
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=lambda: self._close_settings(dialog),
        ).grid(row=0, column=0, padx=(0, 8))
        customtkinter.CTkButton(
            buttons,
            text="Save settings",
            command=lambda: self._save_settings(
                dialog,
                entries,
                appearance_menu,
            ),
        ).grid(row=0, column=1)
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_settings(dialog))
        dialog.grab_set()

    def _browse_download_folder(self, entry: customtkinter.CTkEntry) -> None:
        """Choose a destination directory and place it in the settings form."""
        selected = CTkFileDialog.askdirectory(
            style="Mini",
            initial_dir=str(Path.home()),
            title="Choose downloads folder",
        )
        if selected:
            entry.delete(0, "end")
            entry.insert(0, selected)

    def _save_settings(
        self,
        dialog: customtkinter.CTkToplevel,
        entries: dict[str, customtkinter.CTkEntry],
        appearance_menu: customtkinter.CTkOptionMenu,
    ) -> None:
        """Validate and persist settings before applying supported live changes."""
        try:
            username = entries["username"].get().strip()
            new_settings = replace(
                self.settings,
                username=username,
                username_customized=username != default_device_name(),
                tcp_port=int(entries["tcp_port"].get().strip()),
                discovery_port=int(entries["discovery_port"].get().strip()),
                heartbeat_interval=float(
                    entries["heartbeat_interval"].get().strip()
                ),
                peer_timeout=float(entries["peer_timeout"].get().strip()),
                downloads_dir=entries["downloads_dir"].get().strip(),
                appearance_mode=appearance_menu.get(),
            )
            new_settings.validate()
            downloads_dir = resolve_downloads_dir(
                PROJECT_ROOT,
                new_settings.downloads_dir,
            )
            downloads_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, TypeError, ValueError) as exc:
            self._show_error(f"Invalid settings: {exc}")
            return

        network_changed = any(
            getattr(new_settings, name) != getattr(self.settings, name)
            for name in (
                "tcp_port",
                "discovery_port",
                "heartbeat_interval",
                "peer_timeout",
            )
        )
        try:
            self.config_store.save(new_settings)
        except ConfigError as exc:
            self._show_error(f"Could not save settings: {exc}")
            return

        self.settings = new_settings
        self.receiver.download_dir = downloads_dir
        if self.discovery is not None:
            self.discovery.set_username(new_settings.username)
        customtkinter.set_appearance_mode(new_settings.appearance_mode)
        if network_changed:
            self._set_status("Settings saved; restart SendLan to apply network changes")
        else:
            self._set_status("Settings saved")
        self._close_settings(dialog)

    def _close_settings(self, dialog: customtkinter.CTkToplevel) -> None:
        """Release the settings modal and clear its tracked window reference."""
        try:
            dialog.grab_release()
            dialog.destroy()
        except TclError:
            pass
        if self._settings_dialog is dialog:
            self._settings_dialog = None

    def poll_queue(self) -> None:
        """Drain worker events on the Tk main thread every 100 ms."""
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        if not self._closing:
            self._queue_after_id = self.after(100, self.poll_queue)

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Apply one queued network event to UI state and widgets."""
        event_type = event.get("type")
        if event_type == "file_offer":
            self._show_file_offer(event)
        elif event_type == "file_offer_timeout":
            self._close_file_offer(event["transfer_id"])
            self._set_status(f'File offer timed out: {event["filename"]}')
        elif event_type == "file_offer_rejected":
            self._close_file_offer(event["transfer_id"])
            self._set_status(f'File offer rejected: {event["filename"]}')
        elif event_type in ("outgoing_offer_timeout", "outgoing_rejected"):
            filename = event["filename"]
            message = (
                f"File offer expired: {filename}"
                if event_type == "outgoing_offer_timeout"
                else f"File offer rejected: {filename}"
            )
            self._set_status(message)
            self._finish_transfer(event["transfer_id"])
        elif event_type == "device_id_changed":
            self.settings.device_id = event["device_id"]
            try:
                self.config_store.save(self.settings)
                self._set_status(
                    "Updated device identity after a duplicate was detected"
                )
            except ConfigError as exc:
                self._show_error(
                    f"Could not save the new device identity: {exc}"
                )
        elif event_type in ("peer_discovered", "peer_updated"):
            peer = event["peer"]
            self.peers[peer["device_id"]] = peer
            self._render_peers()
        elif event_type == "peer_lost":
            self.peers.pop(event["peer"]["device_id"], None)
            if self.selected_peer_id not in self.peers:
                self.selected_peer_id = None
            self._render_peers()
        elif event_type == "chat":
            self.chat_frame.append_message(
                f'{event["sender"]} ({event["source"]})',
                event["message"],
                sender_type="other",
            )
            self._play_notification_sound()
        elif event_type == "chat_sent":
            self.chat_frame.append_message(
                "Me",
                event["message"],
                sender_type="me",
            )
        elif event_type == "file_progress":
            self._transfer = {
                "direction": "incoming",
                "id": event["transfer_id"],
            }
            self._show_progress(
                event["filename"],
                event["transferred"],
                event["total"],
                "Receiving",
            )
        elif event_type == "outgoing_progress":
            self._transfer = {
                "direction": "outgoing",
                "id": event["transfer_id"],
                "cancel": event["cancel"],
            }
            self._show_progress(
                event["filename"],
                event["transferred"],
                event["total"],
                "Sending",
            )
        elif event_type == "file_received":
            self.chat_frame.append_message(
                "File",
                f'Received {event["filename"]} from {event["source"]}',
                sender_type="other",
                kind="file",
            )
            if (
                self._transfer is not None
                and self._transfer.get("direction") == "incoming"
            ):
                self._finish_transfer(event["transfer_id"])
        elif event_type == "transfer_cancelled":
            self._set_status(f'Cancelled {event.get("filename", "file transfer")}')
            self._finish_transfer(event["transfer_id"])
        elif event_type == "outgoing_file_complete":
            self.chat_frame.append_message(
                "File",
                f'Sent {event["filename"]} to {event["host"]}',
                sender_type="me",
                kind="file",
            )
        elif event_type == "outgoing_complete":
            self._set_status(
                f'Sent {len(event["filenames"])} file(s) to {event["host"]}'
            )
            self._finish_transfer(event["transfer_id"])
        elif event_type == "outgoing_cancelled":
            self._set_status(f'Cancelled {event["filename"]}')
            self._finish_transfer(event["transfer_id"])
        elif event_type == "outgoing_failed":
            self._finish_transfer(event["transfer_id"])
        elif event_type in ("send_error", "error"):
            self._show_error(event.get("message", "Network operation failed"))
            self._set_status("Network operation failed")

    def _render_peers(self) -> None:
        """Refresh peers and enable chat when a live peer is selected."""
        self.peer_list.set_peers(list(self.peers.values()))
        self.chat_frame.set_enabled(self.peer_list.selected_peer() is not None)

    def _play_notification_sound(self) -> None:
        """Play the packaged notification sound without blocking the UI."""
        sound_path = PROJECT_ROOT / "assets" / "notification.wav"
        try:
            playsound(sound_path, block=False)
        except PlaysoundException as exc:
            self._set_status(f"Notification sound unavailable: {exc}")

    def _show_file_offer(self, event: dict[str, Any]) -> None:
        """Ask the user to accept or reject a file before receiving it."""
        transfer_id = event["transfer_id"]
        response_event = event["response_event"]
        response = event["response"]
        remaining = event["deadline"] - time.monotonic()
        if remaining <= 0:
            self.receiver.respond_to_file_offer(
                response_event,
                response,
                False,
                timed_out=True,
            )
            return

        dialog = customtkinter.CTkToplevel(self)
        dialog.title("Incoming file")
        dialog.geometry("420x190")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        self._file_offer_dialogs[transfer_id] = dialog

        customtkinter.CTkLabel(
            dialog,
            text=f'{event["sender"]} ({event["source"]}) wants to send:',
            wraplength=380,
            justify="left",
        ).pack(padx=20, pady=(20, 6), anchor="w")
        customtkinter.CTkLabel(
            dialog,
            text=f'{event["filename"]} · {self._format_file_size(event["size"])}',
            font=("Arial", 13, "bold"),
            wraplength=380,
            justify="left",
        ).pack(padx=20, pady=4, anchor="w")
        customtkinter.CTkLabel(
            dialog,
            text="Accept this file? The request expires in 30 seconds.",
            wraplength=380,
        ).pack(padx=20, pady=4, anchor="w")

        buttons = customtkinter.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=20, pady=(8, 14))
        customtkinter.CTkButton(
            buttons,
            text="Reject",
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray35"),
            command=lambda: self._answer_file_offer(
                transfer_id,
                False,
                response_event,
                response,
            ),
        ).pack(side="right", padx=(8, 0))
        customtkinter.CTkButton(
            buttons,
            text="Accept",
            command=lambda: self._answer_file_offer(
                transfer_id,
                True,
                response_event,
                response,
            ),
        ).pack(side="right")
        dialog.protocol(
            "WM_DELETE_WINDOW",
            lambda: self._answer_file_offer(
                transfer_id,
                False,
                response_event,
                response,
            ),
        )
        dialog.after(
            max(1, int(remaining * 1000)),
            lambda: self._answer_file_offer(
                transfer_id,
                False,
                response_event,
                response,
                timed_out=True,
            ),
        )

    def _answer_file_offer(
        self,
        transfer_id: str,
        accepted: bool,
        response_event: threading.Event,
        response: dict[str, Any],
        *,
        timed_out: bool = False,
    ) -> None:
        """Send the user's decision to the receiver and dismiss its dialog."""
        self.receiver.respond_to_file_offer(
            response_event,
            response,
            accepted,
            timed_out=timed_out,
        )
        self._close_file_offer(transfer_id)
        if timed_out:
            self._set_status("Incoming file request expired")
        elif not accepted:
            self._set_status("Incoming file rejected")

    def _close_file_offer(self, transfer_id: str) -> None:
        """Close a pending offer dialog if it is still open."""
        dialog = self._file_offer_dialogs.pop(transfer_id, None)
        if dialog is not None and dialog.winfo_exists():
            dialog.grab_release()
            dialog.destroy()

    @staticmethod
    def _format_file_size(size: int) -> str:
        """Format a file size for the incoming-offer prompt."""
        if size < 1024:
            return f"{size} B"
        if size < 1024**2:
            return f"{size / 1024:.1f} KB"
        if size < 1024**3:
            return f"{size / 1024**2:.1f} MB"
        return f"{size / 1024**3:.1f} GB"

    def _select_peer(self, peer: dict[str, Any]) -> None:
        """Select a discovered peer for chat and file transfers."""
        self.selected_peer_id = peer["device_id"]
        self._render_peers()
        self._set_status(f'Selected {peer["username"]} at {peer["host"]}')
        self.chat_frame.entry.focus_set()

    def _selected_peer(self) -> dict[str, Any] | None:
        """Return the selected active peer or update the status message."""
        peer = self.peer_list.selected_peer()
        if peer is None:
            self._set_status("Select a peer first")
        return peer

    def _send_chat_text(self, message: str) -> None:
        """Start sending a chat message on a worker thread."""
        peer = self._selected_peer()
        if peer is None or not message:
            return
        threading.Thread(
            target=self._send_chat_worker,
            args=(peer, message),
            name="sendlan-chat-sender",
            daemon=True,
        ).start()

    def _send_chat_worker(self, peer: dict[str, Any], message: str) -> None:
        """Send one chat message and report its result through the queue."""
        try:
            send_text(
                peer["host"],
                message,
                peer["tcp_port"],
                sender_name=self.settings.username,
            )
            self.events.put({"type": "chat_sent", "message": message})
        except (OSError, ValueError) as exc:
            self.events.put({"type": "send_error", "message": str(exc)})

    def _choose_files(self) -> None:
        """Open the native file picker and queue the selected paths."""
        filenames = CTkFileDialog.askopenfilenames(
            style="Mini",
            filetypes=[("All files", "*")],
            initial_dir=str(Path.home()),
            title="Send files",
        )
        if filenames:
            self._start_file_sends(filenames)

    def _change_device_name(self) -> None:
        """Prompt for a display name, persist it, and update discovery."""
        dialog = customtkinter.CTkInputDialog(
            title="Change device name",
            text="Name shown to nearby peers:",
        )
        entered_name = dialog.get_input()
        if entered_name is None:
            return
        new_name = entered_name.strip()
        if not new_name or len(new_name) > 128:
            self._show_error("Device name must contain 1 to 128 characters")
            return

        previous_name = self.settings.username
        previous_customized = self.settings.username_customized
        self.settings.username = new_name
        self.settings.username_customized = True
        try:
            self.config_store.save(self.settings)
        except ConfigError as exc:
            self.settings.username = previous_name
            self.settings.username_customized = previous_customized
            self._show_error(f"Could not save the device name: {exc}")
            return

        if self.discovery is not None:
            self.discovery.set_username(new_name)
        self._set_status(f"Device name changed to {new_name}")

    def _start_file_sends(self, filenames: tuple[str, ...] | list[str]) -> None:
        """Start one cancellable worker that sends files in sequence."""
        peer = self._selected_peer()
        if peer is None or not filenames:
            return
        if self._transfer is not None:
            self._set_status("Finish or cancel the active transfer first")
            return
        paths = tuple(Path(filename) for filename in filenames)
        cancel_event = threading.Event()
        transfer_id = uuid.uuid4().hex
        self._transfer = {
            "direction": "outgoing",
            "id": transfer_id,
            "cancel": cancel_event,
        }
        threading.Thread(
            target=self._send_files_worker,
            args=(peer, paths, transfer_id, cancel_event),
            name="sendlan-file-sender",
            daemon=True,
        ).start()

    def _send_files_worker(
        self,
        peer: dict[str, Any],
        paths: tuple[Path, ...],
        transfer_id: str,
        cancel_event: threading.Event,
    ) -> None:
        """Send selected files and publish progress and completion events."""
        current_path = paths[0]
        try:
            for current_path in paths:
                send_file(
                    peer["host"],
                    current_path,
                    peer["tcp_port"],
                    sender_name=self.settings.username,
                    cancel_event=cancel_event,
                    progress=lambda sent, total, path=current_path: self.events.put(
                        {
                            "type": "outgoing_progress",
                            "transfer_id": transfer_id,
                            "filename": path.name,
                            "transferred": sent,
                            "total": total,
                            "cancel": cancel_event,
                        }
                    ),
                )
                self.events.put(
                    {
                        "type": "outgoing_file_complete",
                        "filename": current_path.name,
                        "host": peer["host"],
                    }
                )
            self.events.put(
                {
                    "type": "outgoing_complete",
                    "transfer_id": transfer_id,
                    "filenames": [path.name for path in paths],
                    "host": peer["host"],
                }
            )
        except TransferCancelled:
            self.events.put(
                {
                    "type": "outgoing_cancelled",
                    "transfer_id": transfer_id,
                    "filename": current_path.name,
                }
            )
        except FileOfferTimeout:
            self.events.put(
                {
                    "type": "outgoing_offer_timeout",
                    "transfer_id": transfer_id,
                    "filename": current_path.name,
                }
            )
        except FileTransferRejected:
            self.events.put(
                {
                    "type": "outgoing_rejected",
                    "transfer_id": transfer_id,
                    "filename": current_path.name,
                }
            )
        except (OSError, ValueError) as exc:
            self.events.put({"type": "send_error", "message": str(exc)})
            self.events.put({"type": "outgoing_failed", "transfer_id": transfer_id})

    def _cancel_transfer(self) -> None:
        """Request cancellation of the active inbound or outbound transfer."""
        if self._transfer is None:
            return
        if self._transfer["direction"] == "outgoing":
            self._transfer["cancel"].set()
        else:
            self.receiver.cancel_transfer(self._transfer["id"])
        self._set_status("Cancelling transfer...")

    def _show_progress(
        self,
        filename: str,
        transferred: int,
        total: int,
        direction: TransferDirection,
    ) -> None:
        """Update the transfer component from a queued progress event."""
        self.progress_frame.set_progress(
            filename,
            transferred,
            total,
            direction,
        )

    def _finish_transfer(self, transfer_id: str | None = None) -> None:
        """Clear progress if the event belongs to the currently shown transfer."""
        if (
            transfer_id is not None
            and self._transfer is not None
            and self._transfer.get("id") != transfer_id
        ):
            return
        self._transfer = None
        self.progress_frame.reset()

    def _on_drop(self, event: Any) -> str:
        """Send dropped local files or forward dropped text to the selected peer."""
        try:
            items = self.tk.splitlist(event.data)
        except TclError:
            items = ()
        paths = [Path(item) for item in items]
        if paths and all(path.is_file() for path in paths):
            self._start_file_sends([str(path) for path in paths])
        else:
            message = event.data.strip()
            if message:
                self._send_chat_text(message)
        return "break"

    def _set_theme_mode(self, mode: str) -> None:
        """Apply and persist the selected CustomTkinter appearance mode."""
        customtkinter.set_appearance_mode(mode)
        self.settings.appearance_mode = mode
        try:
            self.config_store.save(self.settings)
        except ConfigError as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        """Display an application error using CTkMessagebox on the UI thread."""
        CTkMessagebox(
            master=self,
            title="SendLan",
            message=message,
            icon="cancel",
            option_1="OK",
        )

    def _set_status(self, message: str) -> None:
        """Set the short status line shown below the chat."""
        self.status_label.configure(text=message)

    def _on_close(self) -> None:
        """Cancel active work and stop network services before closing Tk."""
        self._closing = True
        if self._queue_after_id is not None:
            self.after_cancel(self._queue_after_id)
        if self._transfer is not None:
            self._cancel_transfer()
        if self.discovery is not None:
            self.discovery.stop()
        self.receiver.stop()
        self.destroy()