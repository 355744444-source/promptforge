"""Design tokens and the global stylesheet for PromptForge."""
from __future__ import annotations

from PySide6.QtGui import QFont

APP_NAME = "提示词工坊"
APP_EN = "PromptForge"
APP_VERSION = "1.2.0"
PUBLISHER = "江苏振远智能科技有限公司"

COL = {
    "bg": "#F4F5F9",
    "surface": "#FFFFFF",
    "surface_2": "#FAFBFD",
    "border": "#E4E7EF",
    "border_2": "#D6DBE6",
    "text": "#161A23",
    "muted": "#666E80",
    "faint": "#98A0B2",
    "accent": "#4F46E5",
    "accent_hover": "#4338CA",
    "accent_press": "#3730A3",
    "accent_soft": "#EEF0FE",
    "accent_soft_2": "#E1E4FD",
    "accent_line": "#C3C8FA",
    "ok": "#0E9F6E",
    "warn": "#D97706",
    "danger": "#DC2626",
    "hover": "#F5F6FA",
}

UI_FAMILIES = '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif'
BASE_FONT_PX = 13


def app_font() -> QFont:
    font = QFont("Microsoft YaHei UI")
    font.setStyleHint(QFont.SansSerif)
    font.setPixelSize(BASE_FONT_PX)
    return font

STEPS = [
    ("01", "任务与背景", "说清要什么、为什么"),
    ("02", "语气与风格", "决定 AI 怎么说话"),
    ("03", "参考范例", "给例子胜过讲道理"),
    ("04", "任务拆解", "复杂任务分步走"),
    ("05", "输出要求", "格式与红线"),
]


def qss() -> str:
    c = COL
    return f"""
* {{
    outline: none;
}}
QWidget#Root {{ background: {c['bg']}; }}

QFrame#Sidebar {{
    background: {c['surface']};
    border-right: 1px solid {c['border']};
}}
QFrame#PreviewPanel {{
    background: {c['surface']};
    border-left: 1px solid {c['border']};
}}

QLabel {{ color: {c['text']}; background: transparent; }}
QLabel#Brand {{ font-size: 15px; font-weight: 700; }}
QLabel#BrandSub {{ font-size: 11px; color: {c['faint']}; }}
QLabel#Logo {{
    background: {c['accent']};
    color: #FFFFFF;
    border-radius: 10px;
    font-size: 17px;
    font-weight: 700;
}}
QLabel#H1 {{ font-size: 20px; font-weight: 700; }}
QLabel#Sub {{ font-size: 12px; color: {c['muted']}; }}
QLabel#CardTitle {{ font-size: 14px; font-weight: 700; }}
QLabel#CardDesc {{ font-size: 12px; color: {c['muted']}; }}
QLabel#FieldLabel {{ font-size: 12px; font-weight: 700; color: {c['muted']}; }}
QLabel#Hint {{ font-size: 11px; color: {c['faint']}; }}
QLabel#SlotLine {{
    font-size: 11px;
    color: {c['accent']};
    background: {c['surface_2']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 5px 9px;
}}
QLabel#Tip {{ font-size: 11px; color: {c['muted']}; }}
QLabel#StepBadge {{
    font-size: 12px;
    font-weight: 700;
    color: {c['accent']};
    background: {c['accent_soft']};
    border-radius: 10px;
    padding: 4px 10px;
}}
QLabel#Empty {{
    font-size: 12px;
    color: {c['faint']};
    border: 1px dashed {c['border_2']};
    border-radius: 10px;
    padding: 18px;
}}
QLabel#Publisher {{ font-size: 11px; color: {c['faint']}; }}

QFrame#Card {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}
QFrame#Inner {{
    background: {c['surface_2']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}

QPushButton#Nav {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    text-align: left;
    padding: 0px;
}}
QPushButton#Nav:hover {{ background: {c['hover']}; }}
QPushButton#Nav:checked {{ background: {c['accent_soft']}; }}

QPushButton#Primary {{
    background: {c['accent']};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 700;
}}
QPushButton#Primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#Primary:pressed {{ background: {c['accent_press']}; }}
QPushButton#Primary:disabled {{ background: #C9CCE4; color: #F2F3FA; }}

QPushButton#Ghost {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton#Ghost:hover {{ background: {c['hover']}; border-color: {c['border_2']}; }}
QPushButton#Ghost:disabled {{ color: {c['faint']}; border-color: {c['border']}; }}

QPushButton#Soft {{
    background: {c['accent_soft']};
    color: {c['accent_hover']};
    border: none;
    border-radius: 8px;
    padding: 9px 14px;
    font-weight: 700;
}}
QPushButton#Soft:hover {{ background: {c['accent_soft_2']}; }}

QPushButton#Tiny {{
    background: transparent;
    color: {c['muted']};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 12px;
}}
QPushButton#Tiny:hover {{ background: {c['hover']}; color: {c['text']}; border-color: {c['border']}; }}
QPushButton#TinyDanger {{
    background: transparent;
    color: {c['faint']};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 12px;
}}
QPushButton#TinyDanger:hover {{ background: #FDECEC; color: {c['danger']}; }}

QPushButton#Chip {{
    background: {c['surface_2']};
    color: {c['muted']};
    border: 1px solid {c['border']};
    border-radius: 15px;
    padding: 5px 14px;
    font-size: 12px;
}}
QPushButton#Chip:hover {{ border-color: {c['accent_line']}; color: {c['accent_hover']}; }}
QPushButton#Chip:checked {{
    background: {c['accent_soft']};
    border-color: {c['accent_line']};
    color: {c['accent_hover']};
    font-weight: 700;
}}

QFrame#TemplateCard {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}
QFrame#TemplateCard:hover {{ border-color: {c['accent_line']}; background: {c['surface_2']}; }}

QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 6px 10px;
    color: {c['text']};
    selection-background-color: {c['accent_line']};
    selection-color: {c['text']};
}}
QLineEdit:hover, QPlainTextEdit:hover {{ border-color: {c['border_2']}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}

QPlainTextEdit#Preview {{
    background: {c['surface_2']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    padding: 10px;
    font-size: 12px;
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {c['border_2']};
    border-radius: 3px;
    min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: #B9C0CF; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QMenu {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['accent_soft']}; color: {c['accent_hover']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 6px; }}

QToolTip {{
    background: #1F2430;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 8px;
}}

QDialog {{ background: {c['surface']}; }}
QScrollArea#DialogScroll {{ background: {c['surface']}; }}
"""
