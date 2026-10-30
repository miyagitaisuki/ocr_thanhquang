"""Giao diện chung của bản Qt (kiểu OCR-Thanh Quang): thanh bên trắng, thẻ bo góc, nút xanh lá, nhãn trạng thái file.

Một khuôn QSS cho cả hai giao diện; màu lấy từ PALETTES. Chọn theo menu Hiển thị (apply_view).
"""
from __future__ import annotations

APP_NAME = "OCR-Thanh Quang"

PALETTES = {
    "sáng": {
        "page": "#F8FAFC", "card": "#FFFFFF", "field": "#FFFFFF", "border": "#E2E8F0", "text": "#1E293B",
        "muted": "#64748B", "accent": "#047857", "accent_dark": "#065F46", "accent_soft": "#ECFDF5",
        "accent_hi": "#10B981", "accent_lo": "#059669", "shadow": "#0F172A",
        "nav_text": "#374151", "hover": "#F1F5F9", "pdf_bg": "#FDE8E8", "pdf_fg": "#B3261E", "danger": "#B3261E",
        # nút chính: chữ trắng trên nền đậm (tương phản >= 5,5:1)
        "btn_hi": "#047857", "btn_lo": "#065F46", "btn_fg": "#FFFFFF", "btn_hover_hi": "#065F46", "btn_hover_lo": "#064E3B",
        "off_bg": "#E2E8F0", "off_fg": "#64748B",
        "ctl_border": "#8091A7",   # viền ô nhập, checkbox: >= 3:1 với nền
    },
    "tối": {
        "page": "#14171C", "card": "#1F232A", "field": "#181C22", "border": "#2F3640", "text": "#E6E8EC",
        "muted": "#9AA3B2", "accent": "#34D399", "accent_dark": "#6EE7B7", "accent_soft": "#17332A",
        "accent_hi": "#34D399", "accent_lo": "#10B981", "shadow": "#000000",
        "nav_text": "#C9CFD8", "hover": "#2E333B", "pdf_bg": "#4A2A2A", "pdf_fg": "#FF8A80", "danger": "#FF8A80",
        "btn_hi": "#34D399", "btn_lo": "#10B981", "btn_fg": "#052E22", "btn_hover_hi": "#6EE7B7", "btn_hover_lo": "#34D399",
        "off_bg": "#2F3640", "off_fg": "#9AA3B2",
        "ctl_border": "#6B7B90",
    },
}

# nhãn trạng thái file: (nền, chữ) theo khóa trạng thái, mỗi giao diện một bộ (chữ >= 4,5:1 với nền)
PILLS = {
    "sáng": {
        "wait": ("#FFF6DB", "#7A5200"), "run": ("#E3EEFF", "#1D4ED8"), "done": ("#E6F6EF", "#065F46"),
        "stop": ("#EEF1F5", "#374151"), "error": ("#FDE8E8", "#B3261E"),
    },
    "tối": {
        "wait": ("#3A2F10", "#FBBF24"), "run": ("#1E3A5F", "#93C5FD"), "done": ("#14392B", "#6EE7B7"),
        "stop": ("#33383F", "#CBD5E1"), "error": ("#4A2323", "#FCA5A5"),
    },
}
PILL = PILLS["sáng"]   # giữ tên cũ

_TEMPLATE = """
QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget { background: @page@; }
QWidget#sidebar { background: @card@; border-right: 1px solid @border@; }
QWidget#sideFoot { border: 1px solid @border@; }
QWidget { color: @text@; }
QLabel#logo { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 @btn_hi@, stop:1 @btn_lo@); color: @btn_fg@; border-radius: 14px; font-weight: bold; font-size: @fs_app@pt; }
QLabel#appTitle { font-weight: bold; font-size: @fs_app@pt; }
QLabel#hint, QLabel#footTitle { color: @muted@; }
QLabel#footTitle { font-size: @fs_small@pt; font-weight: 600; }
QLabel#pageTitle { font-size: @fs_title@pt; font-weight: bold; }
QLabel#dot { color: @accent@; font-size: @fs_app@pt; }
QWidget#sideFoot { background: @accent_soft@; border-radius: 14px; }
QListWidget#nav { background: transparent; border: 2px solid transparent; border-radius: 14px; outline: 0; }
QListWidget#nav:focus { border: 2px solid @accent@; }
QListWidget#nav::item { padding: 12px 14px; margin: 2px 4px; border-radius: 12px; color: @nav_text@; font-weight: 600; border-left: 3px solid transparent; }
QListWidget#nav::item:selected { background: @accent_soft@; color: @accent_dark@; border-left: 3px solid @accent@; }
QListWidget#nav::item:hover:!selected { background: @hover@; }
QGroupBox { background: @card@; border: 1px solid @border@; border-radius: 16px; margin-top: 16px; padding: 14px 12px 12px 12px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; padding: 0 4px; }
QLineEdit, QComboBox, QSpinBox { background: @field@; border: 1px solid @ctl_border@; border-radius: 12px; padding: 6px 10px; min-height: 22px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid @accent@; padding: 5px 9px; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { border-color: @border@; color: @off_fg@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: @field@; border: 1px solid @ctl_border@; selection-background-color: @accent_soft@; selection-color: @accent_dark@; }
QPushButton { background: @card@; border: 1px solid @ctl_border@; border-radius: 12px; padding: 6px 12px; }
QPushButton:hover { background: @hover@; }
QPushButton:focus { border: 2px solid @accent@; padding: 5px 11px; }
QPushButton:disabled { color: @off_fg@; border-color: @border@; }
QPushButton#runBtn { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 @btn_hi@, stop:1 @btn_lo@); color: @btn_fg@; border: 2px solid transparent; border-radius: 14px; padding: 9px 19px; font-weight: bold; font-size: @fs_app@pt; }
QPushButton#runBtn:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 @btn_hover_hi@, stop:1 @btn_hover_lo@); }
QPushButton#runBtn:focus { border: 2px solid @text@; }
QPushButton#runBtn:disabled { background: @off_bg@; color: @off_fg@; }
QPushButton#dangerBtn { color: @danger@; }
QListWidget#files { background: @field@; border: 1px solid @border@; border-radius: 16px; }
QListWidget#files:focus { border: 2px solid @accent@; }
QListWidget#files::item { border-bottom: 1px solid @border@; }
QLabel#dropzone { border: 1px dashed @accent@; border-radius: 16px; color: @accent_dark@; background: @accent_soft@; padding: 8px; }
QLabel#pdfIcon { background: @pdf_bg@; color: @pdf_fg@; border-radius: 12px; font-weight: bold; font-size: @fs_small@pt; }
QLabel#badge { background: @accent_soft@; color: @accent_dark@; border-radius: 12px; padding: 3px 10px; font-weight: 600; }
QLabel#pill { border-radius: 12px; padding: 3px 10px; font-weight: 600; }
QLabel#pill[state="wait"] { background: @wait_bg@; color: @wait_fg@; }
QLabel#pill[state="run"] { background: @run_bg@; color: @run_fg@; }
QLabel#pill[state="done"] { background: @done_bg@; color: @done_fg@; }
QLabel#pill[state="stop"] { background: @stop_bg@; color: @stop_fg@; }
QLabel#pill[state="error"] { background: @error_bg@; color: @error_fg@; }
QLabel#banner { background: @accent_soft@; border: 1px solid @accent@; border-radius: 12px; padding: 8px 12px; }
QLabel#banner[kind="error"] { background: @error_bg@; border-color: @error_fg@; color: @error_fg@; }
QProgressBar { border: none; background: @border@; border-radius: 4px; min-height: 8px; max-height: 8px; text-align: center; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @accent_hi@, stop:1 @accent_lo@); border-radius: 4px; }
QCheckBox { spacing: 8px; }
QCheckBox:focus { color: @accent_dark@; font-weight: 600; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid @ctl_border@; border-radius: 4px; background: @field@; }
QCheckBox::indicator:focus { border: 2px solid @accent@; }
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; }
QTableWidget { background: @field@; border: 1px solid @border@; border-radius: 12px; gridline-color: @border@; }
QHeaderView::section { background: @card@; color: @muted@; border: none; border-bottom: 1px solid @border@; padding: 4px 6px; }
QTextEdit { background: @field@; border: 1px solid @border@; border-radius: 12px; }
"""


def stylesheet(theme: str, font_pt: int = 10) -> str:
    """QSS cho giao diện đã chọn; theme lạ thì dùng bản sáng. Cỡ chữ tiêu đề tính theo font_pt để menu Cỡ chữ kéo theo."""
    theme = theme if theme in PALETTES else "sáng"
    colors = dict(PALETTES[theme])
    for key, (bg, fg) in PILLS[theme].items():
        colors[f"{key}_bg"], colors[f"{key}_fg"] = bg, fg
    colors.update(fs_app=str(font_pt + 1), fs_title=str(font_pt + 4), fs_small=str(max(font_pt - 2, 7)))
    qss = _TEMPLATE
    for key, value in colors.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


def contrast(fg: str, bg: str) -> float:
    """Tỉ lệ tương phản WCAG giữa hai màu '#RRGGBB'."""
    def lum(h: str) -> float:
        rgb = [int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


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
