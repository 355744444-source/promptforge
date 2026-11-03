"""Reusable Qt widgets: card, chips, inputs, score ring, markdown highlighter."""
from __future__ import annotations

import re

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import COL


# --------------------------------------------------------------------------
# layout helpers
# --------------------------------------------------------------------------
class FlowLayout(QLayout):
    """Left-to-right layout that wraps onto new rows (used by the chip groups)."""

    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._items: list = []
        self._h = hspacing
        self._v = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_height = eff.x(), eff.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h
            if next_x - self._h > eff.right() and line_height > 0:
                x = eff.x()
                y = y + line_height + self._v
                next_x = x + hint.width() + self._h
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {COL['border']}; border: none;")
    return line


# --------------------------------------------------------------------------
# building blocks
# --------------------------------------------------------------------------
class Card(QFrame):
    def __init__(self, title: str = "", desc: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(18, 16, 18, 18)
        self.v.setSpacing(0)
        if title:
            t = QLabel(title)
            t.setObjectName("CardTitle")
            self.v.addWidget(t)
            if desc:
                d = QLabel(desc)
                d.setObjectName("CardDesc")
                d.setWordWrap(True)
                self.v.addSpacing(4)
                self.v.addWidget(d)
            self.v.addSpacing(14)

    def add(self, widget: QWidget, gap: int = 14) -> None:
        if self.v.count():
            self.v.addSpacing(gap)
        self.v.addWidget(widget)


def field(label: str, widget: QWidget, hint: str = "") -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(6)
    if label:
        lb = QLabel(label)
        lb.setObjectName("FieldLabel")
        v.addWidget(lb)
    v.addWidget(widget)
    if hint:
        h = QLabel(hint)
        h.setObjectName("Hint")
        h.setWordWrap(True)
        v.addWidget(h)
    return box


def line_input(placeholder: str = "") -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setFixedHeight(34)
    return w


class TextArea(QPlainTextEdit):
    """Multiline input that grows with its content between a min and a max height."""

    PAD = 24  # QSS padding (6+6) + border (1+1) + document margin (8) + slack

    def __init__(self, placeholder: str = "", lines: int = 3, max_lines: int = None, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setTabChangesFocus(True)
        lh = self.fontMetrics().lineSpacing()
        self._min_h = lines * lh + self.PAD
        self._max_h = (max_lines or lines + 4) * lh + self.PAD
        self.setFixedHeight(self._min_h)
        self.textChanged.connect(self._schedule_fit)

    def _schedule_fit(self) -> None:
        QTimer.singleShot(0, self._fit)

    def _fit(self) -> None:
        width = self.viewport().width()
        if width <= 0:
            return
        text = self.toPlainText()
        fm = self.fontMetrics()
        if text:
            needed = fm.boundingRect(0, 0, width, 1_000_000, Qt.TextWordWrap, text).height()
        else:
            needed = fm.lineSpacing()
        h = max(self._min_h, min(self._max_h, int(needed) + self.PAD))
        if abs(h - self.height()) > 1:
            self.setFixedHeight(h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_fit()


def text_area(placeholder: str = "", lines: int = 3, max_lines: int = None) -> TextArea:
    return TextArea(placeholder, lines, max_lines)


def make_button(text: str, kind: str = "Ghost", parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    return b


# --------------------------------------------------------------------------
# navigation item
# --------------------------------------------------------------------------
class NavItem(QPushButton):
    def __init__(self, number: str, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Nav")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(56)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)

        self.badge = QLabel(number)
        self.badge.setFixedSize(24, 24)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.badge)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        self.t_title = QLabel(title)
        self.t_title.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.t_sub = QLabel(subtitle)
        self.t_sub.setAttribute(Qt.WA_TransparentForMouseEvents)
        col.addWidget(self.t_title)
        col.addWidget(self.t_sub)
        lay.addLayout(col, 1)

        self._paint_badge(False)
        self.toggled.connect(self._paint_badge)

    def _paint_badge(self, active: bool) -> None:
        if active:
            self.badge.setStyleSheet(
                f"background: {COL['accent']}; color: #FFFFFF; border-radius: 12px;"
                "font-size: 11px; font-weight: 700;"
            )
            self.t_title.setStyleSheet(
                f"color: {COL['accent_hover']}; font-size: 13px; font-weight: 700;"
            )
            self.t_sub.setStyleSheet(f"color: {COL['accent']}; font-size: 11px;")
        else:
            self.badge.setStyleSheet(
                f"background: {COL['bg']}; color: {COL['faint']}; border-radius: 12px;"
                "font-size: 11px; font-weight: 700;"
            )
            self.t_title.setStyleSheet(f"color: {COL['text']}; font-size: 13px; font-weight: 600;")
            self.t_sub.setStyleSheet(f"color: {COL['faint']}; font-size: 11px;")


# --------------------------------------------------------------------------
# chip group
# --------------------------------------------------------------------------
class ChipGroup(QWidget):
    def __init__(self, options, selected, multi=False, on_change=None, parent=None):
        super().__init__(parent)
        self._multi = multi
        self._on_change = on_change
        self._buttons: dict[str, QPushButton] = {}

        lay = FlowLayout(self, margin=0, hspacing=6, vspacing=6)
        for opt in options:
            b = QPushButton(opt)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(opt in selected)
            b.clicked.connect(lambda _=False, o=opt: self._clicked(o))
            lay.addWidget(b)
            self._buttons[opt] = b

        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def _clicked(self, opt: str) -> None:
        if not self._multi:
            for name, btn in self._buttons.items():
                if name != opt:
                    btn.setChecked(False)
            self._buttons[opt].setChecked(True)
        elif not self._buttons[opt].isChecked():
            # keep at least nothing forced: allow empty state
            pass
        if self._on_change:
            self._on_change(self.values())

    def values(self) -> list[str]:
        return [name for name, btn in self._buttons.items() if btn.isChecked()]

    def value(self) -> str:
        vals = self.values()
        return vals[0] if vals else ""


# --------------------------------------------------------------------------
# score ring
# --------------------------------------------------------------------------
class ScoreRing(QWidget):
    def __init__(self, diameter: int = 66, parent=None):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self._score = 0
        self._color = COL["accent"]

    def set_score(self, score: int) -> None:
        score = max(0, min(100, int(score)))
        self._score = score
        self._color = COL["ok"] if score >= 85 else (COL["accent"] if score >= 60 else COL["warn"])
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        width = 6.0
        rect = QRectF(width / 2 + 1, width / 2 + 1, self.width() - width - 2, self.height() - width - 2)
        p.setPen(QPen(QColor(COL["border"]), width, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 0, 360 * 16)
        if self._score > 0:
            p.setPen(QPen(QColor(self._color), width, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 90 * 16, -int(360 * 16 * self._score / 100))

        font = QFont(self.font())
        font.setPixelSize(max(13, int(self.width() * 0.30)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(COL["text"]))
        p.drawText(self.rect(), Qt.AlignCenter, str(self._score))


# --------------------------------------------------------------------------
# preview highlighter
# --------------------------------------------------------------------------
class PreviewHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.h1 = QTextCharFormat()
        self.h1.setForeground(QColor(COL["accent_hover"]))
        self.h1.setFontWeight(QFont.Bold)

        self.h2 = QTextCharFormat()
        self.h2.setForeground(QColor(COL["text"]))
        self.h2.setFontWeight(QFont.Bold)

        self.quote = QTextCharFormat()
        self.quote.setForeground(QColor(COL["muted"]))

        self.bullet = QTextCharFormat()
        self.bullet.setForeground(QColor(COL["accent"]))

    def highlightBlock(self, text: str) -> None:
        if text.startswith("# "):
            self.setFormat(0, len(text), self.h1)
        elif text.startswith("## "):
            self.setFormat(0, len(text), self.h2)
        elif text.startswith("> "):
            self.setFormat(0, len(text), self.quote)
        elif re.match(r"^\s*(?:-|\d+\.)\s", text):
            head = len(text) - len(text.lstrip())
            mark = text.lstrip()[:1]
            self.setFormat(head, max(1, len(mark)), self.bullet)
