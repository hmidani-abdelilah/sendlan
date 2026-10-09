"""Application entry point."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sendlan.ui.main_window import MainWindow


def main() -> None:
    """Start the SendLan application."""
    MainWindow().mainloop()


if __name__ == "__main__":
    main()