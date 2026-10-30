"""Giao diện PySide6 (bước 2 chuyển từ Tkinter). Thanh bên 4 mục: OCR, Tách PDF, Ghép PDF, Công cụ khác.

Bản này mới có mục OCR đầy đủ; ba mục PDF là chỗ giữ, sẽ làm ở bước 3. Logic dùng chung với Tkinter nằm ở ui_logic.py.
Giao diện Tkinter (gui.py) vẫn là bản mặc định cho đến khi bản Qt ngang tính năng.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QStackedWidget, QVBoxLayout, QWidget,
)

from . import gpu, gpupack, pipeline
from . import ui_logic as L
from .cli import collect
from .gui_qt_pdf import MergeSection, SplitSection, ToolsSection

gpupack.activate()   # trước khi đọc find_spec('chandra')

log = logging.getLogger("ocrnhat.gui")

SECTIONS = ("OCR", "Tách PDF", "Ghép PDF", "Công cụ khác")
ENGINES = ("auto", "ndlocr") + (("chandra",) if importlib.util.find_spec("chandra") else ()) + ("paddle", "ocr_vi")
FILE_FILTER = "PDF / ảnh (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"


class OcrWorker(QThread):
    """Chạy OCR cho từng file ở luồng nền; báo tiến độ qua tín hiệu, không đụng widget từ luồng khác."""
    progress = Signal(int, int, str)     # đã xong, tổng, mô tả
    file_state = Signal(int, str)        # chỉ số file, trạng thái
    finished_ok = Signal(str, list)      # thông điệp cuối, danh sách đường dẫn .docx

    def __init__(self, files: list[Path], out: Path | None, pages, opts: dict):
        super().__init__()
        self.files, self.out, self.pages, self.opts = files, out, pages, opts
        self.cancel_requested = False

    def run(self):
        outputs, errors = [], []
        for i, f in enumerate(self.files):
            if self.cancel_requested:
                break
            self.file_state.emit(i, "Đang xử lý")
            try:
                r = pipeline.process_file(
                    f, self.out, 200, self.pages if f.suffix.lower() == ".pdf" else None,
                    progress=lambda d, t, m: self.progress.emit(d, t, m),
                    cancel=lambda: self.cancel_requested, **self.opts)
                outputs.append(r["docx"])
                self.file_state.emit(i, "Dừng" if self.cancel_requested else "Xong")
            except Exception as e:   # một file lỗi không làm dừng các file còn lại
                log.exception("Không xử lý được %s", f)
                errors.append(f"{f.name}: {e}")
                self.file_state.emit(i, f"Lỗi: {str(e)[:60]}")
        if self.cancel_requested:
            msg = "Đã dừng. Các trang đã đọc vẫn được lưu."
        else:
            msg = f"Xong. Đã xử lý {len(outputs)} file."
        if errors:
            msg += f" Có {len(errors)} file lỗi: " + "; ".join(errors[:3]) + f". Chi tiết trong nhật ký: {L.LOG_FILE}"
        self.finished_ok.emit(msg, [str(p) for p in outputs])


class FileList(QListWidget):
    """Danh sách file nhận kéo-thả từ Explorer; phát `dropped` với danh sách đường dẫn."""
    dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setToolTip("Kéo thả file hoặc thư mục vào đây")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.dropped.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
        e.acceptProposedAction()


class OcrPage(QWidget):
    """Mục OCR: danh sách file (kéo-thả được), ngôn ngữ, công cụ, thư mục lưu, tùy chọn nâng cao, chạy."""

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.files: list[Path] = []
        self.worker: OcrWorker | None = None
        self.last_outputs: list[str] = []
        self._build()
        self._restore()

    # ---------- bố cục ----------

    def _build(self):
        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.btn_add = QPushButton("Thêm file…")
        self.btn_dir = QPushButton("Thêm thư mục…")
        self.btn_del = QPushButton("Bỏ mục đã chọn")
        self.btn_clear = QPushButton("Bỏ tất cả")
        for b in (self.btn_add, self.btn_dir, self.btn_del, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        self.count = QLabel("Chưa có file nào")
        bar.addWidget(self.count)
        root.addLayout(bar)

        self.listing = FileList()
        self.listing.setMinimumHeight(160)
        root.addWidget(self.listing, 1)

        form = QGroupBox("Cách đọc")
        grid = QVBoxLayout(form)
        self.lang = QComboBox()
        self.engine = QComboBox()
        self.device = QComboBox()
        for key in ENGINES:
            self.engine.addItem(L.ENGINE_LABELS[key], key)
        for key, label in L.dev_labels(gpu.ort_cuda_available()).items():
            self.device.addItem(label, key)
        self.merge = QComboBox()
        for key, label in L.MERGE_LABELS.items():
            self.merge.addItem(label, key)
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("ví dụ 1-5,8 · để trống = tất cả (chỉ áp dụng cho PDF)")
        self.out = QLineEdit()
        self.out.setPlaceholderText("để trống = lưu cạnh file gốc")
        self.btn_out = QPushButton("Chọn…")
        for label, widget in (("Công cụ", self.engine), ("Ngôn ngữ", self.lang), ("Phần cứng", self.device),
                              ("Cách ghép trang", self.merge), ("Trang", self.pages)):
            grid.addWidget(QLabel(label))
            grid.addWidget(widget)
        grid.addWidget(QLabel("Thư mục lưu"))
        out_row = QHBoxLayout()
        out_row.addWidget(self.out, 1)
        out_row.addWidget(self.btn_out)
        grid.addLayout(out_row)
        self.txt = QCheckBox("Ghi kèm file .txt")
        self.marker = QCheckBox("Ghi số trang gốc 【原本 p.N】")
        self.ruby = QCheckBox("Giữ chữ phiên âm kana trên chữ Hán (ruby)")
        for c in (self.txt, self.marker, self.ruby):
            grid.addWidget(c)
        root.addWidget(form)

        adv = QGroupBox("Nâng cao")
        adv.setCheckable(True)
        adv.setChecked(False)
        agrid = QVBoxLayout(adv)
        self.upscale = QLineEdit("1")
        self.crop = QLineEdit()
        self.crop.setPlaceholderText("trái, trên, phải, dưới (pixel) · để trống = cả trang")
        self.kana = QComboBox()
        for key, label in L.KANA_LABELS.items():
            self.kana.addItem(label, key)
        self.cell_reocr = QCheckBox("Đọc lại ô bảng bị lẫn đường kẻ")
        self.use_cache = QCheckBox("Nhớ kết quả đã đọc (chạy lại file cũ sẽ nhanh hơn)")
        for label, widget in (("Phóng to ảnh", self.upscale), ("Chỉ đọc một vùng", self.crop),
                              ("Đọc bảng chữ kana (thử nghiệm)", self.kana)):
            agrid.addWidget(QLabel(label))
            agrid.addWidget(widget)
        agrid.addWidget(self.cell_reocr)
        agrid.addWidget(self.use_cache)
        self.advanced = adv
        root.addWidget(adv)

        run = QHBoxLayout()
        self.btn_run = QPushButton("▶  Chạy OCR")
        self.btn_stop = QPushButton("Dừng")
        self.btn_stop.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("Sẵn sàng.")
        self.status.setWordWrap(True)
        run.addWidget(self.btn_run)
        run.addWidget(self.btn_stop)
        run.addWidget(self.progress, 1)
        root.addLayout(run)
        root.addWidget(self.status)

        self.btn_add.clicked.connect(self.add_files)
        self.btn_dir.clicked.connect(self.add_dir)
        self.btn_del.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_out.clicked.connect(self.pick_out)
        self.listing.dropped.connect(self._add_dropped)
        self.btn_run.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.request_stop)
        self.engine.currentIndexChanged.connect(self._sync_lang)
        self._sync_lang()

    # ---------- ngôn ngữ theo công cụ ----------

    def _sync_lang(self):
        key = self.engine.currentData()
        allowed = L.ENGINE_LANGS.get(key, L.ENGINE_LANGS["auto"])
        current = self.lang.currentData()
        self.lang.blockSignals(True)
        self.lang.clear()
        for k in allowed:
            self.lang.addItem(L.LANG_LABELS[k], k)
        idx = self.lang.findData(current) if current in allowed else 0
        self.lang.setCurrentIndex(idx)
        self.lang.blockSignals(False)

    # ---------- danh sách file ----------

    def _add_dropped(self, paths: list):
        self._add(collect(paths))

    def add_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Chọn file", "", FILE_FILTER)
        self._add(collect(names))

    def add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if d:
            self._add(collect([d]))

    def _add(self, found: list[Path]):
        if self.worker and self.worker.isRunning():
            self.status.setText("Đang OCR, chưa sửa được danh sách. Bấm Dừng trước.")
            return
        added = dup = 0
        for f in found:
            if f in self.files:
                dup += 1
                continue
            self.files.append(f)
            self.listing.addItem(QListWidgetItem(f"{f.name}    ·  Chờ    ·  {f.parent}"))
            added += 1
        self._refresh_count()
        if not found:
            self.status.setText("Không tìm thấy PDF hoặc ảnh nào trong mục đã chọn.")
        elif dup:
            self.status.setText(f"Đã thêm {added} file; bỏ qua {dup} file đã có trong danh sách.")
        else:
            self.status.setText(f"Đã thêm {added} file.")

    def remove_selected(self):
        if self.worker and self.worker.isRunning():
            return
        for idx in sorted((self.listing.row(i) for i in self.listing.selectedItems()), reverse=True):
            del self.files[idx]
            self.listing.takeItem(idx)
        self._refresh_count()

    def clear(self):
        if self.worker and self.worker.isRunning():
            return
        self.files.clear()
        self.listing.clear()
        self._refresh_count()

    def _refresh_count(self):
        n = len(self.files)
        self.count.setText(f"{n} file" if n else "Chưa có file nào")

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu kết quả")
        if d:
            self.out.setText(d)

    def _set_file_state(self, i: int, text: str):
        if 0 <= i < len(self.files):
            self.listing.item(i).setText(f"{self.files[i].name}    ·  {text}    ·  {self.files[i].parent}")

    # ---------- tùy chọn ----------

    def options(self) -> dict:
        """Tùy chọn đầy đủ cho pipeline. Ném ValueError với thông báo tiếng Việt nếu sai.
        Giá trị lấy theo nhãn (như ô nhập của bản Tkinter) để dùng chung quy tắc trong ui_logic."""
        dev_map = L.dev_labels(gpu.ort_cuda_available())
        vals = {
            "conf": "0.8", "upscale": self.upscale.text(), "crop": self.crop.text(),
            "dev": dev_map[self.device.currentData()], "lang": L.LANG_LABELS[self.lang.currentData()],
            "engine": L.ENGINE_LABELS[self.engine.currentData()], "merge": L.MERGE_LABELS[self.merge.currentData()],
            "kana": L.KANA_LABELS[self.kana.currentData()],
            "txt": self.txt.isChecked(), "marker": self.marker.isChecked(), "ruby": self.ruby.isChecked(),
            "cell_reocr": self.cell_reocr.isChecked(), "use_cache": self.use_cache.isChecked(),
        }
        return L.read_options(lambda name, default: vals.get(name, default), dev_map)

    def _engine_check(self, opts: dict) -> str | None:
        from .engines import paddle, viet
        return L.engine_problem(opts, {"paddle": paddle.PaddleEngine, "ocr_vi": viet.VietnameseEngine}.get)

    # ---------- chạy ----------

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.files:
            QMessageBox.information(self, "OCR", "Chưa chọn file.")
            return
        try:
            pages = pipeline.parse_pages(self.pages.text())
        except ValueError:
            QMessageBox.critical(self, "OCR", "Số trang không hợp lệ. Ví dụ: 1-5,8.")
            return
        try:
            opts = self.options()
        except ValueError as e:
            QMessageBox.critical(self, "OCR", str(e))
            return
        why = self._engine_check(opts)
        if why:
            QMessageBox.warning(self, "OCR", why + "\nHãy tải mô hình trong giao diện Tkinter hoặc chọn công cụ khác.")
            return
        self._save()
        for i in range(len(self.files)):
            self._set_file_state(i, "Chờ")
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        out = self.out.text().strip()
        self.worker = OcrWorker(list(self.files), Path(out) if out else None, pages, opts)
        self.worker.progress.connect(self._on_progress)
        self.worker.file_state.connect(self._set_file_state)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.start()

    def request_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel_requested = True
            self.status.setText("Đang dừng… chờ trang hiện tại đọc xong.")

    def _on_progress(self, d: int, t: int, m: str):
        self.progress.setValue(int(100 * d / max(1, t)))
        self.status.setText(f"[{d}/{t}] {m}")

    def _on_done(self, msg: str, outputs: list):
        self.last_outputs = outputs
        self.status.setText(msg)
        self.progress.setValue(100)
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def busy(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    # ---------- nhớ tùy chọn ----------

    _SAVED = ("txt", "marker", "ruby", "cell_reocr", "use_cache", "upscale", "crop", "pages", "out")

    _COMBOS = ("engine", "device", "merge", "kana", "lang")   # lưu theo khóa, không theo nhãn

    def _restore(self):
        saved = self.settings.get("qt_ocr", {})
        for name in self._SAVED:
            widget = getattr(self, name)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(saved.get(name, widget.isChecked())))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(saved.get(name, widget.text())))
        for name in self._COMBOS:   # engine đứng trước lang: đổi engine sẽ tự dựng lại danh sách ngôn ngữ
            combo = getattr(self, name)
            idx = combo.findData(saved.get(name))
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _save(self):
        data = {}
        for name in self._SAVED:
            widget = getattr(self, name)
            data[name] = widget.isChecked() if isinstance(widget, QCheckBox) else widget.text()
        for name in self._COMBOS:
            data[name] = getattr(self, name).currentData()
        self.settings["qt_ocr"] = data
        L.save_settings(self.settings)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OCR-Nhat · nhiều ngôn ngữ")
        self.resize(1040, 820)
        self.settings = L.load_settings()

        self.nav = QListWidget()
        self.nav.setFixedWidth(180)
        for name in SECTIONS:
            self.nav.addItem(QListWidgetItem(name))
        self.stack = QStackedWidget()
        self.ocr = OcrPage(self.settings)
        self.split = SplitSection("Tách PDF", self.settings, "split")
        self.merge = MergeSection("Ghép PDF", self.settings, "merge")
        self.tools = ToolsSection("Công cụ khác", self.settings, "tools")
        for page in (self.ocr, self.split, self.merge, self.tools):
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        split = QSplitter()
        split.addWidget(self.nav)
        split.addWidget(self.stack)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)

    def _busy_pages(self):
        return [p for p in (self.ocr, self.split, self.merge, self.tools) if p.busy()]

    def closeEvent(self, event):
        if self._busy_pages():
            answer = QMessageBox.question(self, "Đang xử lý",
                                          "Đang có việc chạy nền. Đóng bây giờ sẽ dừng sau file/trang hiện tại; "
                                          "các file đã xong vẫn được giữ. Đóng?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for page in self._busy_pages():
                page.stop_running()
                if isinstance(page, ToolsSection) and page.watcher is not None:
                    page.watcher.stop_event.set()
                    page.watcher.wait(10000)
                    page.watcher = None
                if page.worker is not None:
                    page.worker.wait(30000)
        self.ocr._save()
        self.split._save()
        self.merge._save()
        self.tools._save()
        event.accept()


def run():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()
    return app.exec()
