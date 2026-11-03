"""PromptForge entry point."""
from __future__ import annotations

import os
import sys


def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative)


def main() -> int:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from pforge.app import MainWindow
    from pforge.theme import app_font

    app = QApplication(sys.argv)
    app.setApplicationName("PromptForge")
    app.setOrganizationName("Zhenyuan")
    app.setStyle("Fusion")
    app.setFont(app_font())

    icon_path = resource_path(os.path.join("assets", "app.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
