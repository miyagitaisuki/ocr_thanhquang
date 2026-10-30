"""Phần còn thiếu của bản Qt so với Tkinter (bước 4): kết quả và xem trước, mô hình AI, menu Hiển thị.

- ResultsBox: bảng kết quả, mở file Word/thư mục/file so sánh, Tìm nhanh, xem trước ảnh trang và chữ.
- ModelBox: tải PaddleOCR/VietOCR, Chandra (có tick điều khoản), cài gói GPU; chạy nền, có tiến trình.
- apply_view / build_view_menu: giao diện sáng/tối, độ trong suốt, cỡ chữ; áp dụng ngay, không cần khởi động lại.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QGroupBox, QHBoxLayout, QLabel, QMenu, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from . import gpupack, textview
from . import ui_logic as L

log = logging.getLogger("ocrnhat.gui")

ALPHA_LEVELS = (100, 95, 90, 85, 80)
FONT_SIZES = {"Nhỏ": 9, "Vừa": 10, "Lớn": 12}
THEMES = ("sáng", "tối")


# ---------- kết quả và xem trước ----------

def render_page(src: Path, pno: int, box: tuple[int, int]) -> QPixmap | None:
    """Ảnh trang nguồn (PDF hoặc ảnh) vừa khung box. None nếu không đọc được."""
    try:
        if src.suffix.lower() == ".pdf":
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(str(src))
            if pno > len(doc):
                return None
            page = doc[pno - 1]
            scale = min(box[0] / page.get_width(), box[1] / page.get_height())
            pil = page.render(scale=scale).to_pil().convert("RGB")
        else:
            from PIL import Image
            pil = Image.open(src).convert("RGB")
            pil.thumbnail(box)
        data = pil.tobytes("raw", "RGB")
        img = QImage(data, pil.width, pil.height, 3 * pil.width, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(img)
    except Exception:
        log.exception("Không vẽ được bản xem trước %s", src)
        return None


class ResultsBox(QGroupBox):
    """Kết quả các file vừa OCR: bảng, nút mở, Tìm nhanh, xem trước trang (ảnh và chữ)."""

    def __init__(self):
        super().__init__("Kết quả")
        self.rows: list[tuple[Path, dict]] = []
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Tên file", "Trang", "Bảng", "File Word"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(160)
        self.btn_docx = QPushButton("Mở file Word")
        self.btn_dir = QPushButton("Mở thư mục")
        self.btn_review = QPushButton("Mở file so sánh")
        self.btn_find = QPushButton("Tìm nhanh")
        self.btn_find.setToolTip("Mở thư mục của kết quả đang chọn, hoặc kết quả gần nhất.")
        bar = QHBoxLayout()
        for b in (self.btn_docx, self.btn_dir, self.btn_review, self.btn_find):
            bar.addWidget(b)
        bar.addStretch(1)
        self.page = QSpinBox()
        self.page.setRange(1, 9999)
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.page_info = QLabel("")
        nav = QHBoxLayout()
        nav.addWidget(QLabel("Trang:"))
        for w in (self.btn_prev, self.page, self.btn_next, self.page_info):
            nav.addWidget(w)
        nav.addStretch(1)
        self.image = QLabel("Chọn một kết quả để xem trước.")
        self.image.setMinimumSize(360, 300)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setStyleSheet("border: 1px solid palette(mid);")
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(300)
        preview = QHBoxLayout()
        preview.addWidget(self.image)
        preview.addWidget(self.text, 1)
        root = QVBoxLayout(self)
        root.addWidget(self.table)
        root.addLayout(bar)
        root.addLayout(nav)
        root.addLayout(preview)
        self.set_enabled_actions(False)
        self.table.itemSelectionChanged.connect(self.refresh_preview)
        self.page.valueChanged.connect(lambda _: self.refresh_preview())
        self.btn_prev.clicked.connect(lambda: self.page.setValue(max(1, self.page.value() - 1)))
        self.btn_next.clicked.connect(lambda: self.page.setValue(self.page.value() + 1))
        self.btn_docx.clicked.connect(lambda: self._open("docx"))
        self.btn_dir.clicked.connect(lambda: self._open("dir"))
        self.btn_review.clicked.connect(lambda: self._open("review"))
        self.btn_find.clicked.connect(self.find_output)

    def set_enabled_actions(self, on: bool):
        for b in (self.btn_docx, self.btn_dir, self.btn_find):
            b.setEnabled(on)
        self.btn_review.setEnabled(on)

    def set_results(self, rows: list[tuple[Path, dict]]):
        self.rows = rows
        self.table.setRowCount(len(rows))
        for i, (src, r) in enumerate(rows):
            for col, value in enumerate((src.name, str(r.get("pages", 0)), str(r.get("tables", 0)), Path(r["docx"]).name)):
                self.table.setItem(i, col, QTableWidgetItem(value))
        self.set_enabled_actions(bool(rows))
        if rows:
            self.table.selectRow(0)
        self.refresh_preview()

    def _selected(self):
        idx = self.table.currentRow()
        return self.rows[idx] if 0 <= idx < len(self.rows) else None

    def _open(self, what: str):
        item = self._selected()
        if not item:
            return
        src, r = item
        try:
            if what == "docx":
                L.open_path(Path(r["docx"]))
            elif what == "dir":
                L.open_path(Path(r["docx"]).parent)
            elif r.get("review"):
                L.open_path(Path(r["review"]))
            else:
                QMessageBox.information(self, "Kiểm tra kết quả",
                                        "Chưa có file so sánh. Bật “Tạo file so sánh để kiểm tra” trong Nâng cao rồi chạy lại.")
        except OSError as e:
            QMessageBox.critical(self, "Mở file", f"Không mở được: {e}")

    def find_output(self):
        item = self._selected() or (self.rows[-1] if self.rows else None)
        if item:
            target = Path(item[1]["docx"]).parent
        else:
            QMessageBox.information(self, "Tìm nhanh", "Chưa có kết quả nào.")
            return
        if not target.is_dir():
            QMessageBox.information(self, "Tìm nhanh", f"Chưa có thư mục kết quả:\n{target}")
            return
        try:
            L.open_path(target)
        except OSError as e:
            QMessageBox.critical(self, "Tìm nhanh", f"Không mở được thư mục này: {e}")

    def refresh_preview(self):
        item = self._selected()
        pno = self.page.value()
        if not item:
            self.image.setText("Chọn một kết quả để xem trước.")
            self.image.setPixmap(QPixmap())
            self.text.clear()
            self.page_info.setText("")
            return
        src, r = item
        pix = render_page(src, pno, (360, 300))
        if pix is None:
            self.image.setPixmap(QPixmap())
            self.image.setText("Không vẽ được trang này.")
        else:
            self.image.setPixmap(pix)
        txt_path = Path(r["docx"]).with_suffix(".txt")
        if txt_path.exists():
            text = textview.page_text(txt_path.read_text(encoding="utf-8"), pno)
            self.text.setPlainText(text if text is not None else "Không có chữ cho trang này.")
            self.page_info.setText("")
        else:
            self.text.setPlainText("Không có file .txt. Bật “Ghi kèm file .txt” rồi chạy lại để xem chữ ở đây.")
        if src.suffix.lower() == ".pdf":
            try:
                import pypdfium2 as pdfium
                self.page_info.setText(f"/ {len(pdfium.PdfDocument(str(src)))} trang")
            except Exception:
                self.page_info.setText("")
        else:
            self.page_info.setText("1 ảnh")


# ---------- mô hình AI ----------

class ModelWorker(QThread):
    """Chạy một việc tải/cài ở luồng nền. report(chữ, tỷ lệ 0..1; -1 = không xác định)."""
    progress = Signal(str, float)
    done = Signal(bool, str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            msg = self.fn(lambda text, frac: self.progress.emit(text, frac))
            self.done.emit(True, msg or "Xong.")
        except Exception as e:
            log.exception("Lỗi tải mô hình")
            self.done.emit(False, f"Thất bại: {e}")


class ModelBox(QGroupBox):
    """Mô hình AI (tùy chọn, chỉ tải một lần). Gọn: nằm cuối mục OCR, thu gọn được."""

    def __init__(self, chandra_available: bool):
        super().__init__("Mô hình AI (tùy chọn)")
        self.setCheckable(True)
        self.setChecked(False)
        self.worker: ModelWorker | None = None
        from .engines import models as mdl
        from .engines.paddle import PaddleEngine
        from .engines.viet import VietnameseEngine

        self.rows = {}
        self.body = QWidget()   # nội dung thu gọn: ẩn hẳn khi bỏ chọn
        root = QVBoxLayout(self.body)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setVisible(False)
        self._specs = [
            ("paddle", "Tải mô hình OCR (PaddleOCR, tiếng Anh/Trung, vài chục MB)",
             lambda rep: "\n".join(mdl.download_paddle(progress=lambda i, n, name, frac: rep(
                 f"Đang tải {name} (tệp {min(i + 1, n)}/{n})", (i + frac) / max(1, n)))),
             lambda: PaddleEngine.is_available()[0]),
            ("vi", "Tải mô hình tiếng Việt (VietOCR, khoảng 32 MB)",
             lambda rep: "\n".join(mdl.download_vi(progress=lambda i, n, name, frac: rep(
                 f"Đang tải {name} (tệp {min(i + 1, n)}/{n})", (i + frac) / max(1, n)))),
             lambda: VietnameseEngine.is_available()[0]),
        ]
        for key, label, fn, ready in self._specs:
            btn = QPushButton(label)
            btn.setEnabled(not ready())
            btn.clicked.connect(lambda _=False, k=key, f=fn: self._start(f, f"Đã tải xong: {label.split('(')[0].replace('Tải ', '').strip()}."))
            self.rows[key] = (btn, ready)
            root.addWidget(btn)

        self.license = QCheckBox("Tôi đồng ý điều khoản sử dụng của mô hình Chandra (OpenRAIL-M)")
        self.chandra_btn = QPushButton("Tải mô hình Chandra (vài GB, chỉ tải một lần)")
        self.chandra_btn.clicked.connect(self._chandra)
        self.chandra_box = QWidget()
        cb = QVBoxLayout(self.chandra_box)
        cb.setContentsMargins(0, 0, 0, 0)
        cb.addWidget(self.license)
        cb.addWidget(self.chandra_btn)
        self.chandra_box.setVisible(chandra_available)
        self.chandra_on = chandra_available   # cờ riêng: isVisible() còn phụ thuộc cửa sổ cha đã hiện chưa
        root.addWidget(self.chandra_box)

        self.pack_btn = QPushButton("Cài tăng tốc GPU (vài GB, chỉ dùng cho Chandra)")
        self.pack_btn.clicked.connect(self._pack)
        self.pack_btn.setVisible(not gpupack.installed())
        root.addWidget(self.pack_btn)
        root.addWidget(self.bar)
        root.addWidget(self.status)
        QVBoxLayout(self).addWidget(self.body)
        self.body.setVisible(False)
        self.toggled.connect(self.body.setVisible)
        self._refresh_status()

    def _refresh_status(self):
        from .engines import chandra as ch_mod
        from .engines.paddle import PaddleEngine
        from .engines.viet import VietnameseEngine
        lines = ["PaddleOCR: " + ("đã có." if PaddleEngine.is_available()[0] else "chưa có."),
                 "VietOCR: " + ("đã có." if VietnameseEngine.is_available()[0] else "chưa có.")]
        if self.chandra_on:
            try:
                ready = ch_mod.model_downloaded()
            except ImportError:   # thiếu gói phụ thuộc của Chandra: coi như chưa có, không làm sập cửa sổ
                ready = False
            lines.append("Chandra: " + ("đã có trên máy." if ready else "chưa có."))
        self.status.setText("\n".join(lines))
        for btn, ready in self.rows.values():
            btn.setEnabled(not ready() and not self.busy())

    def busy(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def _set_busy(self, busy: bool):
        for btn, ready in self.rows.values():
            btn.setEnabled(not busy and not ready())
        self.chandra_btn.setEnabled(not busy)
        self.pack_btn.setEnabled(not busy)
        self.bar.setVisible(busy)
        if busy:
            self.bar.setRange(0, 0)   # chờ tiến trình đầu tiên
        else:
            self.bar.setRange(0, 100)

    def _start(self, fn, done_text: str):
        if self.busy():
            return
        self._set_busy(True)
        self.status.setText("Đang tải…")
        self.worker = ModelWorker(fn)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(lambda ok, msg: self._on_done(ok, msg if not ok else done_text))
        self.worker.start()

    def _on_progress(self, text: str, frac: float):
        self.status.setText(text)
        if frac >= 0:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(100 * frac))

    def _on_done(self, ok: bool, msg: str):
        self._set_busy(False)
        self.status.setText(msg)
        self._refresh_status()

    def _chandra(self):
        if not self.license.isChecked():
            QMessageBox.warning(self, "Chandra", "Hãy tick đồng ý điều khoản Chandra trước khi tải mô hình.")
            return
        from .engines.chandra import download_model
        self._start(lambda rep: download_model(progress=lambda d, t: rep(
            f"Đang tải Chandra: {d * 100 // max(1, t)}% ({d // 2**20} / {t // 2**20} MB)", d / max(1, t))),
            "Đã tải xong mô hình Chandra.")

    def _pack(self):
        if QMessageBox.question(self, "Tăng tốc GPU", "Tải phần mềm tăng tốc GPU, khoảng vài GB. Tiếp tục?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._start(lambda rep: gpupack.install(progress=lambda m: rep(m, -1)) or "Đã cài xong. Hãy khởi động lại để dùng Chandra.",
                    "Đã cài xong tăng tốc GPU. Hãy khởi động lại để dùng Chandra.")


# ---------- hiển thị ----------

def _dark_palette() -> QPalette:
    p = QPalette()
    dark = {QPalette.ColorRole.Window: "#1B1E23", QPalette.ColorRole.Base: "#1E2228", QPalette.ColorRole.AlternateBase: "#262A31",
            QPalette.ColorRole.Text: "#E6E8EC", QPalette.ColorRole.WindowText: "#E6E8EC", QPalette.ColorRole.Button: "#262A31",
            QPalette.ColorRole.ButtonText: "#E6E8EC", QPalette.ColorRole.Highlight: "#2F4A70",
            QPalette.ColorRole.HighlightedText: "#E6E8EC", QPalette.ColorRole.ToolTipBase: "#262A31",
            QPalette.ColorRole.ToolTipText: "#E6E8EC", QPalette.ColorRole.Mid: "#3A404A", QPalette.ColorRole.PlaceholderText: "#9AA3B2"}
    for role, color in dark.items():
        p.setColor(role, QColor(color))
    return p


def apply_view(app, theme: str, font_pt: int, alpha: int, window) -> None:
    """Áp dụng giao diện ngay: màu, cỡ chữ, độ trong suốt cửa sổ."""
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if theme == "tối" else app.style().standardPalette())
    font = QFont(app.font())
    font.setPointSize(font_pt)
    app.setFont(font)
    window.setWindowOpacity(alpha / 100)


def build_view_menu(window, app, settings: dict, save) -> QMenu:
    """Menu Hiển thị. settings là dict dùng chung; save() ghi ra settings.json."""
    view = QMenu("Hiển thị", window)
    theme_group = QActionGroup(window)
    for name in THEMES:
        act = QAction(f"Giao diện {name}", window, checkable=True)
        act.setChecked(settings.get("qt_view", {}).get("theme", "sáng") == name)
        act.triggered.connect(lambda _=False, n=name: _set(window, app, settings, save, theme=n))
        theme_group.addAction(act)
        view.addAction(act)
    size_menu = view.addMenu("Cỡ chữ")
    for label, pt in FONT_SIZES.items():
        act = QAction(f"{label} ({pt})", window)
        act.triggered.connect(lambda _=False, p=pt: _set(window, app, settings, save, font_pt=p))
        size_menu.addAction(act)
    trans = view.addMenu("Độ trong suốt cửa sổ")
    alpha_group = QActionGroup(window)
    current = settings.get("qt_view", {}).get("alpha", 100)
    for pct in ALPHA_LEVELS:
        act = QAction(f"{pct}%", window, checkable=True)
        act.setChecked(pct == current)
        act.triggered.connect(lambda _=False, p=pct: _set(window, app, settings, save, alpha=p))
        alpha_group.addAction(act)
        trans.addAction(act)
    return view


def _set(window, app, settings: dict, save, **change) -> None:
    view = settings.setdefault("qt_view", {"theme": "sáng", "font_pt": 10, "alpha": 100})
    view.update(change)
    apply_view(app, view["theme"], view["font_pt"], view["alpha"], window)
    save()
