"""Generate the application icon (assets/app.ico + app.png)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    radius = size * 0.22
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)

    grad = QLinearGradient(0, 0, size * 0.4, size)
    grad.setColorAt(0.0, QColor("#6D6AF8"))
    grad.setColorAt(1.0, QColor("#4338CA"))
    p.fillPath(path, grad)

    # subtle light streak
    p.setClipPath(path)
    streak = QLinearGradient(0, 0, size, size)
    streak.setColorAt(0.0, QColor(255, 255, 255, 42))
    streak.setColorAt(0.55, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(0, 0, size, size), streak)
    p.setClipping(False)

    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(int(size * 0.62))
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(0, -size * 0.03, size, size), Qt.AlignCenter, "P")
    p.end()
    return img


def main() -> int:
    app = QApplication(sys.argv[:1])
    out_dir = os.path.join(ROOT, "assets")
    os.makedirs(out_dir, exist_ok=True)

    png = os.path.join(out_dir, "app.png")
    ico = os.path.join(out_dir, "app.ico")

    big = render(256)
    big.save(png, "PNG")
    ok = big.save(ico, "ICO")
    print("png", os.path.getsize(png), "ico", ok, os.path.getsize(ico) if os.path.exists(ico) else 0)
    app.quit()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
