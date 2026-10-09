from __future__ import annotations

from datetime import datetime

import flet as ft


class SendLanFletApp:
    """A modern Facebook-inspired chat interface built with Flet."""

    def __init__(self) -> None:
        self.page: ft.Page | None = None
        self.message_list: ft.Column | None = None
        self.audio: ft.Audio | None = None

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M")

    def receive_message(self, text: str, file_name: str | None = None) -> None:
        if self.page is None or self.message_list is None:
            return

        tint = "#f1f5f9" if file_name is None else "#ede9fe"
        bubble = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        value=text,
                        size=15,
                        weight="w500",
                        color="#111827",
                        selectable=True,
                        max_lines=10,
                    ),
                    ft.Text(
                        value=f"📎 {file_name}" if file_name else self._now(),
                        size=11,
                        color="#64748b",
                    ),
                ],
                spacing=4,
                tight=True,
            ),
            padding=ft.padding.all(12),
            border_radius=18,
            bgcolor=tint,
            margin=ft.margin.only(left=12, right=66, top=8, bottom=8),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color="#e2e8f0",
                offset=ft.Offset(0, 2),
            ),
        )
        self.message_list.controls.append(bubble)
        self.page.update()

        if self.audio is not None:
            try:
                self.audio.play()
            except Exception:
                pass

    def _send_message(self, event: ft.ControlEvent) -> None:
        if self.page is None or self.message_list is None:
            return

        field = self.page.get_control("message_input")
        value = (field.value or "").strip()
        if not value:
            return

        field.value = ""
        self.message_list.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            value=value,
                            size=15,
                            weight="w500",
                            color="#ffffff",
                            selectable=True,
                            max_lines=10,
                        ),
                        ft.Text(
                            value=self._now(),
                            size=11,
                            color="#eef2ff",
                        ),
                    ],
                    spacing=4,
                    tight=True,
                ),
                padding=ft.padding.all(12),
                border_radius=18,
                bgcolor="#1877f2",
                margin=ft.margin.only(left=66, right=12, top=8, bottom=8),
                alignment=ft.alignment.center_right,
                shadow=ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=10,
                    color="#bfdbfe",
                    offset=ft.Offset(0, 2),
                ),
            )
        )
        self.page.update()

    async def _attach_file(self, event: ft.ControlEvent) -> None:
        if self.page is None:
            return

        picker = self.page.get_control("file_picker")
        files = await picker.pick_files(allow_multiple=False)
        if not files or not files.files:
            return

        file_name = files.files[0].name
        self.receive_message(f"📨 File received", file_name=file_name)

    def build(self, page: ft.Page) -> None:
        self.page = page
        page.title = "SendLan"
        page.theme_mode = "light"
        page.bgcolor = "#eef2ff"
        page.padding = 0
        page.window_width = 430
        page.window_height = 860
        page.window_min_width = 360
        page.window_min_height = 640

        self.audio = ft.Audio(src="notification.wav", autoplay=False)
        page.overlay.append(self.audio)

        file_picker = ft.FilePicker()
        file_picker.name = "file_picker"
        page.overlay.append(file_picker)

        header = ft.Container(
            content=ft.Row(
                [
                    ft.CircleAvatar(
                        content=ft.Icon(ft.icons.PERSON_ROUNDED, color="white"),
                        radius=24,
                        bgcolor="#7c3aed",
                    ),
                    ft.Column(
                        [
                            ft.Text("Esraa", size=20, weight="bold", color="#111827"),
                            ft.Text("Online now", size=12, color="#22c55e"),
                        ],
                        tight=True,
                    ),
                    ft.Row(
                        [
                            ft.IconButton(icon=ft.icons.CALL_ROUNDED, tooltip="Call"),
                            ft.IconButton(icon=ft.icons.VIDEO_CAMERA_FRONT_ROUNDED, tooltip="Video call"),
                        ],
                        spacing=0,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor="#ffffff",
            padding=ft.padding.only(left=18, right=18, top=18, bottom=12),
            border_radius=ft.border_radius.only(top_left=28, top_right=28),
        )

        self.message_list = ft.Column(expand=True, spacing=4, scroll="auto")
        self.message_list.controls.extend(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Hello 👋", size=15, weight="w500", color="#111827"),
                            ft.Text("09:41", size=11, color="#64748b"),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    padding=ft.padding.all(12),
                    border_radius=18,
                    bgcolor="#f1f5f9",
                    margin=ft.margin.only(left=12, right=66, top=8, bottom=8),
                    shadow=ft.BoxShadow(
                        spread_radius=0,
                        blur_radius=10,
                        color="#e2e8f0",
                        offset=ft.Offset(0, 2),
                    ),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.icons.ATTACH_FILE_ROUNDED, color="#7c3aed"),
                                    ft.Text("design-v2.zip", size=15, weight="w500", color="#111827"),
                                ],
                                spacing=8,
                                tight=True,
                            ),
                            ft.Text("09:43", size=11, color="#64748b"),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    padding=ft.padding.all(12),
                    border_radius=18,
                    bgcolor="#ede9fe",
                    margin=ft.margin.only(left=12, right=66, top=8, bottom=8),
                    shadow=ft.BoxShadow(
                        spread_radius=0,
                        blur_radius=10,
                        color="#ddd6fe",
                        offset=ft.Offset(0, 2),
                    ),
                ),
            ]
        )

        input_field = ft.TextField(
            hint_text="Type a message",
            border_radius=18,
            filled=True,
            expand=True,
            bgcolor="#f8fafc",
            multiline=False,
            prefix_icon=ft.icons.MESSAGE_ROUNDED,
            on_submit=self._send_message,
            autofocus=True,
            text_size=15,
        )
        input_field.name = "message_input"

        send_button = ft.FilledButton(
            "Send",
            icon=ft.icons.SEND_ROUNDED,
            on_click=self._send_message,
        )
        attach_button = ft.IconButton(
            icon=ft.icons.ATTACH_FILE_ROUNDED,
            tooltip="Attach file",
            on_click=self._attach_file,
        )

        composer = ft.Container(
            content=ft.Row(
                [
                    attach_button,
                    input_field,
                    send_button,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.only(left=12, right=12, top=8, bottom=18),
            bgcolor="#ffffff",
            border_radius=ft.border_radius.only(top_left=24, top_right=24),
        )

        chat_panel = ft.Container(
            content=ft.Column(
                [
                    header,
                    ft.Container(
                        content=self.message_list,
                        expand=True,
                        padding=ft.padding.only(left=4, right=4, top=8, bottom=8),
                    ),
                    composer,
                ],
                expand=True,
            ),
            bgcolor="#f8fafc",
            border_radius=28,
            padding=0,
        )

        page.add(chat_panel)
        page.update()


def main(page: ft.Page) -> None:
    app = SendLanFletApp()
    app.build(page)


if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
