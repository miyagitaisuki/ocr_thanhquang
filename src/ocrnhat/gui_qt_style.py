"""Giao diện chung của bản Qt (kiểu OCR-Thanh Quang): thanh bên trắng, thẻ bo góc, nút xanh lá, nhãn trạng thái file.

Một khuôn QSS cho cả hai giao diện; màu lấy từ PALETTES. Chọn theo menu Hiển thị (apply_view).
"""
from __future__ import annotations

APP_NAME = "OCR-Thanh Quang"

PALETTES = {
    "sáng": {
        "page": "#F8FAFC", "card": "#FFFFFF", "field": "#FFFFFF", "border": "#E2E8F0", "text": "#1E293B",
        "muted": "#64748B", "accent": "#10B981", "accent_dark": "#059669", "accent_soft": "#ECFDF5",
        "accent_hi": "#10B981", "accent_lo": "#059669", "shadow": "#0F172A",
        "nav_text": "#374151", "hover": "#F1F5F9", "pdf_bg": "#FDE8E8", "pdf_fg": "#D93025", "danger": "#B3261E",
    },
    "tối": {
        "page": "#14171C", "card": "#1F232A", "field": "#181C22", "border": "#2F3640", "text": "#E6E8EC",
        "muted": "#9AA3B2", "accent": "#34D399", "accent_dark": "#10B981", "accent_soft": "#17332A",
        "accent_hi": "#34D399", "accent_lo": "#10B981", "shadow": "#000000",
        "nav_text": "#C9CFD8", "hover": "#2E333B", "pdf_bg": "#4A2A2A", "pdf_fg": "#FF8A80", "danger": "#FF8A80",
    },
}

# nhãn trạng thái file: (nền, chữ) theo khóa trạng thái
PILL = {
    "wait": ("#FFF6DB", "#9A6700"), "run": ("#E3EEFF", "#1F6FEB"), "done": ("#E6F6EF", "#0B7F58"),
    "stop": ("#EEF1F5", "#4B5563"), "error": ("#FDE8E8", "#B3261E"),
}

_TEMPLATE = """
QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget { background: @page@; }
QWidget#sidebar { background: @card@; border-right: 1px solid @border@; }
QWidget#sideFoot { border: 1px solid @border@; }
QWidget { color: @text@; }
QLabel#logo { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 @accent_hi@, stop:1 @accent_lo@); color: #FFFFFF; border-radius: 14px; font-weight: bold; font-size: 15px; }
QLabel#appTitle { font-weight: bold; font-size: 15px; }
QLabel#hint, QLabel#footTitle { color: @muted@; }
QLabel#footTitle { font-size: 11px; font-weight: 600; }
QLabel#pageTitle { font-size: 18px; font-weight: bold; }
QLabel#dot { color: @accent@; font-size: 14px; }
QWidget#sideFoot { background: @accent_soft@; border-radius: 14px; }
QListWidget#nav { background: transparent; border: none; outline: 0; }
QListWidget#nav::item { padding: 12px 14px; margin: 2px 4px; border-radius: 12px; color: @nav_text@; font-weight: 600; border-left: 3px solid transparent; }
QListWidget#nav::item:selected { background: @accent_soft@; color: @accent_dark@; border-left: 3px solid @accent@; }
QListWidget#nav::item:hover:!selected { background: @hover@; }
QGroupBox { background: @card@; border: 1px solid @border@; border-radius: 16px; margin-top: 16px; padding: 14px 12px 12px 12px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; padding: 0 4px; }
QLineEdit, QComboBox, QSpinBox { background: @field@; border: 1px solid @border@; border-radius: 12px; padding: 6px 10px; min-height: 22px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid @accent@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: @field@; border: 1px solid @border@; selection-background-color: @accent_soft@; selection-color: @accent@; }
QPushButton { background: @card@; border: 1px solid @border@; border-radius: 12px; padding: 6px 12px; }
QPushButton:hover { background: @hover@; }
QPushButton:disabled { color: @muted@; }
QPushButton#runBtn { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 @accent_hi@, stop:1 @accent_lo@); color: #FFFFFF; border: none; border-radius: 14px; padding: 10px 20px; font-weight: bold; font-size: 14px; }
QPushButton#runBtn:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 @accent_lo@, stop:1 @accent_dark@); }
QPushButton#runBtn:disabled { background: #CBD5E1; color: #F8FAFC; }
QPushButton#dangerBtn { color: @danger@; }
QListWidget#files { background: @field@; border: 1px solid @border@; border-radius: 16px; }
QListWidget#files::item { border-bottom: 1px solid @border@; }
QLabel#dropzone { border: 1px dashed @accent@; border-radius: 16px; color: @accent_dark@; background: @accent_soft@; padding: 8px; }
QLabel#pdfIcon { background: @pdf_bg@; color: @pdf_fg@; border-radius: 12px; font-weight: bold; font-size: 11px; }
QLabel#badge { background: @accent_soft@; color: @accent_dark@; border-radius: 12px; padding: 3px 10px; font-weight: 600; }
QLabel#pill { border-radius: 12px; padding: 3px 10px; font-weight: 600; }
QLabel#pill[state="wait"] { background: @wait_bg@; color: @wait_fg@; }
QLabel#pill[state="run"] { background: @run_bg@; color: @run_fg@; }
QLabel#pill[state="done"] { background: @done_bg@; color: @done_fg@; }
QLabel#pill[state="stop"] { background: @stop_bg@; color: @stop_fg@; }
QLabel#pill[state="error"] { background: @error_bg@; color: @error_fg@; }
QProgressBar { border: none; background: @border@; border-radius: 4px; min-height: 8px; max-height: 8px; text-align: center; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @accent_hi@, stop:1 @accent_lo@); border-radius: 4px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid @border@; border-radius: 4px; background: @field@; }
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; }
QTableWidget { background: @field@; border: 1px solid @border@; border-radius: 12px; gridline-color: @border@; }
QHeaderView::section { background: @card@; color: @muted@; border: none; border-bottom: 1px solid @border@; padding: 4px 6px; }
QTextEdit { background: @field@; border: 1px solid @border@; border-radius: 12px; }
"""


def stylesheet(theme: str) -> str:
    """QSS cho giao diện đã chọn; theme lạ thì dùng bản sáng."""
    colors = dict(PALETTES.get(theme, PALETTES["sáng"]))
    for key, (bg, fg) in PILL.items():
        colors[f"{key}_bg"], colors[f"{key}_fg"] = bg, fg
    qss = _TEMPLATE
    for key, value in colors.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


def state_key(text: str) -> str:
    """Chữ trạng thái file (từ worker) -> khóa màu nhãn."""
    if text.startswith("Lỗi"):
        return "error"
    return {"Chờ": "wait", "Đang xử lý": "run", "Xong": "done", "Dừng": "stop"}.get(text, "wait")


def add_soft_shadows(root) -> None:
    """Đổ bóng mềm cho mọi thẻ (QGroupBox) trong cửa sổ: tạo tầng tự nhiên, không dùng box-shadow của QSS (không có)."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGroupBox
    for box in root.findChildren(QGroupBox):
        if box.graphicsEffect() is not None:
            continue
        shadow = QGraphicsDropShadowEffect(box)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(15, 23, 42, 28))
        box.setGraphicsEffect(shadow)
