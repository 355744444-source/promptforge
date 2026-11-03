"""Dev helper: render the UI to a PNG so layout problems are visible without a human."""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from pforge.app import MainWindow, TemplateDialog
    from pforge.prompts import template_spec
    from pforge.theme import app_font

    args = sys.argv[1:]
    step = 0
    template = -1
    out = os.path.join(ROOT, "build_shot.png")
    dialog = False
    for i, a in enumerate(args):
        if a == "--step":
            step = int(args[i + 1])
        elif a == "--template":
            template = int(args[i + 1])
        elif a == "--out":
            out = args[i + 1]
        elif a == "--dialog":
            dialog = True

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setFont(app_font())

    win = MainWindow()
    if template >= 0:
        win.spec = template_spec(template)
        win._reload_pages()
        win._refresh()
    win._goto(step)
    win.show()

    for _ in range(8):
        app.processEvents()
        time.sleep(0.04)

    target = win
    if dialog:
        dlg = TemplateDialog(win)
        dlg.show()
        for _ in range(6):
            app.processEvents()
            time.sleep(0.04)
        target = dlg

    pix = target.grab()
    pix.save(out)
    print(f"saved {out} {pix.width()}x{pix.height()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
