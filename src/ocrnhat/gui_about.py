"""Menu Trợ giúp (Giới thiệu, Giấy phép, Báo lỗi) và hộp thoại Thông tin hệ thống (bấm vào ô Trạng thái hệ thống).

`system_info()` và `ABOUT_HTML` là dữ liệu thuần, test được không cần cửa sổ.
"""
from __future__ import annotations

import platform
import sys

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMenu, QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout

from . import __version__, gpu
from . import ui_logic as L
from .gui_style import APP_NAME

AUTHOR = "Nguyễn Thanh Quang"
AUTHOR_ROLE = "Giảng viên chuyên ngành Nhật Bản học, Trường Đại học Quy Nhơn"
PHONE = "08686 08647"
EMAIL = "nguyenthanhquang@qnu.edu.vn"

# (thành phần, giấy phép, ghi chú); nội dung đầy đủ nằm trong NOTICE.md
LICENSES = (
    ("NDLOCR-Lite (Thư viện Quốc hội Nhật Bản)", "CC BY 4.0", "engine đọc tiếng Nhật mặc định"),
    ("PaddleOCR PP-OCRv4", "Apache-2.0", "engine tiếng Anh, Trung"),
    ("VietOCR", "Apache-2.0", "engine tiếng Việt"),
    ("pyvi", "MIT", "từ điển hậu xử lý tiếng Việt"),
    ("PySide6 (Qt for Python)", "LGPL-3.0", "giao diện; dùng dạng thư viện động, không sửa Qt"),
    ("onnxruntime, python-docx, pip", "MIT", ""),
    ("OpenCV, pypdfium2, PyYAML", "Apache-2.0 / BSD-3-Clause", ""),
    ("NumPy", "BSD-3-Clause", ""),
    ("Pillow", "MIT-CMU", ""),
    ("PyInstaller", "GPL-2.0+ có ngoại lệ đóng gói", "chỉ dùng để dựng exe"),
    ("Thư viện CUDA của NVIDIA", "giấy phép NVIDIA", "kèm trong bản exe GPU"),
)


def _licenses_rows() -> str:
    return "".join(f"<tr><td><b>{n}</b></td><td>{lic}</td><td>{note}</td></tr>" for n, lic, note in LICENSES)


ABOUT_HTML = f"""
<h2>{APP_NAME}</h2>
<p>Nhận dạng văn bản tiếng Nhật từ PDF scan và ảnh, xuất Word (.docx) và .txt.
Miễn phí, chạy offline. Phiên bản {__version__}.</p>
<h3>Tác giả</h3>
<p><b>{AUTHOR}</b><br>{AUTHOR_ROLE}<br>
Điện thoại: {PHONE}<br>Email: <a href="mailto:{EMAIL}">{EMAIL}</a></p>
<h3>Giấy phép các thành phần</h3>
<table cellpadding="4" cellspacing="0" border="0">{_licenses_rows()}</table>
<p>Chi tiết đầy đủ: xem <b>NOTICE.md</b> trong thư mục phần mềm.</p>
"""


def system_info() -> list[str]:
    """Các dòng mô tả máy và trạng thái GPU, dùng cho hộp thoại Thông tin hệ thống và khi báo lỗi.
    Gọi từ luồng nền (SysInfoWorker): dò GPU và nạp onnxruntime mất vài giây."""
    lines = [f"{APP_NAME} {__version__}",
             f"Hệ điều hành: {platform.platform()}",
             f"Python: {sys.version.split()[0]}{' (exe đóng gói)' if getattr(sys, 'frozen', False) else ''}"]
    gpus = gpu.detect()
    if gpus:
        for g in gpus:
            lines.append(f"Card NVIDIA: {g.name}, VRAM {g.vram_mb} MB" if g.vram_mb else f"Card NVIDIA: {g.name}")
    else:
        lines.append("Card NVIDIA: không thấy (nvidia-smi không chạy được; kiểm tra driver NVIDIA)")
    lines.append("onnxruntime CUDA (NDLOCR): " + ("có" if gpu.ort_cuda_available() else "không (bản CPU)"))
    from . import engines
    eng, why = engines.resolve("auto")
    lines.append(f"Công cụ tự động chọn: {eng} ({why})")
    lines.append(f"Thư mục nhật ký lỗi: {L.LOG_FILE.parent}")
    return lines


class SysInfoWorker(QThread):
    ready = Signal(str)

    def run(self):
        try:
            self.ready.emit("\n".join(system_info()))
        except Exception as e:
            self.ready.emit(f"Không thu thập được thông tin: {e}")


def open_log_dir() -> None:
    d = L.LOG_FILE.parent
    d.mkdir(parents=True, exist_ok=True)   # chưa có lỗi nào thì thư mục chưa tồn tại; vẫn mở được
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))


class AboutDialog(QDialog):
    def __init__(self, parent=None, title: str = "Giới thiệu"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml(ABOUT_HTML)
        view.setAccessibleName("Giới thiệu phần mềm")
        lay.addWidget(view)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


class SystemDialog(QDialog):
    """Thông tin hệ thống: GPU, onnxruntime CUDA, đường dẫn. Có nút sao chép để dán khi báo lỗi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thông tin hệ thống")
        self.resize(640, 360)
        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit("Đang thu thập thông tin…")
        self.text.setReadOnly(True)
        self.text.setAccessibleName("Thông tin hệ thống")
        lay.addWidget(self.text)
        copy = QPushButton("Sao chép")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.text.toPlainText()))
        logs = QPushButton("Mở thư mục nhật ký lỗi")
        logs.clicked.connect(open_log_dir)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.addButton(copy, QDialogButtonBox.ButtonRole.ActionRole)
        box.addButton(logs, QDialogButtonBox.ButtonRole.ActionRole)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.worker = SysInfoWorker(self)
        self.worker.ready.connect(self.text.setPlainText)
        self.worker.start()

    def done(self, r):
        self.worker.wait(15000)   # luồng nền còn dò GPU: đợi xong rồi mới hủy hộp thoại
        super().done(r)


def build_help_menu(window) -> QMenu:
    """Menu Trợ giúp, đặt cạnh menu Hiển thị."""
    menu = QMenu("Trợ giúp", window)
    about = QAction("Giới thiệu và giấy phép…", window)
    about.triggered.connect(lambda: AboutDialog(window).exec())
    sysinfo = QAction("Thông tin hệ thống…", window)
    sysinfo.triggered.connect(lambda: SystemDialog(window).exec())
    bug = QAction("Báo lỗi (mở thư mục nhật ký)…", window)
    bug.setToolTip("Mở thư mục chứa app.log; gửi file này kèm mô tả lỗi cho tác giả")
    bug.triggered.connect(open_log_dir)
    for act in (about, sysinfo, bug):
        menu.addAction(act)
    return menu
