from __future__ import annotations

import sys
from pathlib import Path

import flet as ft

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sendlan.flet_app import SendLanFletApp


def main(page: ft.Page) -> None:
    app = SendLanFletApp()
    app.build(page)


if __name__ == "__main__":
    ft.app(target=main, assets_dir=str(PROJECT_ROOT / "assets"))

