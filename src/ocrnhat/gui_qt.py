"""Giao diện PySide6 (bước 2 chuyển từ Tkinter). Thanh bên 4 mục: OCR, Tách PDF, Ghép PDF, Công cụ khác.

Bản này mới có mục OCR đầy đủ; ba mục PDF là chỗ giữ, sẽ làm ở bước 3. Logic dùng chung với Tkinter nằm ở ui_logic.py.
Giao diện Tkinter (gui.py) vẫn là bản mặc định cho đến khi bản Qt ngang tính năng.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from . import gpu, gpupack, pipeline
from . import ui_logic as L
from .cli import collect
from .gui_qt_extra import SCAN_DPI, ModelBox, PageView, ResultsBox, apply_view, build_view_menu, source_image
from .gui_qt_style import APP_NAME, state_key
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
    finished_ok = Signal(str, list)      # thông điệp cuối, danh sách (đường dẫn gốc, kết quả pipeline)

    def __init__(self, files: list[Path], out: Path | None, pages, opts: dict):
        super().__init__()
        self.files, self.out, self.pages, self.opts = files, out, pages, opts
        self.cancel_requested = False

    def run(self):
        outputs, errors = [], []   # outputs: (đường dẫn gốc, kết quả pipeline)
        for i, f in enumerate(self.files):
            if self.cancel_requested:
                break
            self.file_state.emit(i, "Đang xử lý")
            try:
                r = pipeline.process_file(
                    f, self.out, 200, self.pages if f.suffix.lower() == ".pdf" else None,
                    progress=lambda d, t, m: self.progress.emit(d, t, m),
                    cancel=lambda: self.cancel_requested, **self.opts)
                outputs.append((f, r))
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
        self.finished_ok.emit(msg, outputs)


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


class FileRow(QWidget):
    """Một dòng file trong danh sách: ô PDF/ảnh, tên, thư mục, nhãn trạng thái (pill)."""
    LABELS = {"wait": "Chờ xử lý", "run": "Đang xử lý", "done": "Xong", "stop": "Dừng", "error": "Lỗi"}

    def __init__(self, path: Path):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 12, 8)
        icon = QLabel("PDF" if path.suffix.lower() == ".pdf" else "ẢNH")
        icon.setObjectName("pdfIcon")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texts = QVBoxLayout()
        name = QLabel(path.name)
        name.setStyleSheet("font-weight: 600;")
        where = QLabel(str(path.parent))
        where.setObjectName("hint")
        texts.addWidget(name)
        texts.addWidget(where)
        self.pill = QLabel()
        self.pill.setObjectName("pill")
        row.addWidget(icon)
        row.addLayout(texts, 1)
        row.addWidget(self.pill)
        self.set_state("wait")

    def set_state(self, key: str, text: str | None = None):
        self.pill.setProperty("state", key)
        self.pill.setText(text if key == "error" and text else self.LABELS.get(key, key))
        self.pill.setToolTip(text or "")
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)


class OcrPage(QWidget):
    """Mục OCR: danh sách file, xem trước vùng chọn, cấu hình, tiến trình và kết quả."""
    busy_changed = Signal(bool)   # đang OCR hay không: cửa sổ dùng để khóa nút "Bắt đầu xử lý"

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.files: list[Path] = []
        self.worker: OcrWorker | None = None
        self._build()
        self._restore()

    # ---------- bố cục ----------

    def _build(self):
        root = QHBoxLayout(self)
        root.setSpacing(16)

        # cột trái: danh sách file, xem trước vùng chọn, kết quả
        left = QVBoxLayout()
        self.files_box = QGroupBox("Danh sách File (0)")
        fb = QVBoxLayout(self.files_box)
        bar = QHBoxLayout()
        self.btn_add = QPushButton("+ Thêm file")
        self.btn_dir = QPushButton("+ Thêm thư mục")
        self.btn_del = QPushButton("Bỏ mục đã chọn")
        self.btn_clear = QPushButton("Bỏ tất cả")
        self.btn_clear.setObjectName("dangerBtn")
        for b in (self.btn_add, self.btn_dir, self.btn_del, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        fb.addLayout(bar)
        drop = QLabel("Kéo thả PDF, PNG, JPG, TIFF vào danh sách bên dưới, hoặc bấm “+ Thêm file”")
        drop.setObjectName("dropzone")
        drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop.setMinimumHeight(44)
        fb.addWidget(drop)
        self.listing = FileList()
        self.listing.setObjectName("files")
        self.listing.setMinimumHeight(150)
        fb.addWidget(self.listing)
        left.addWidget(self.files_box)

        self.preview_box = QGroupBox("Xem trước vùng chọn")
        pv = QVBoxLayout(self.preview_box)
        head = QHBoxLayout()
        self.page_badge = QLabel("Chưa có file")
        self.page_badge.setObjectName("badge")
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.btn_crop_clear = QPushButton("Bỏ vùng chọn")
        head.addWidget(self.page_badge)
        head.addStretch(1)
        for w in (self.btn_prev, self.btn_next, self.btn_crop_clear):
            head.addWidget(w)
        pv.addLayout(head)
        self.crop_view = PageView(mode="crop", min_size=(300, 260))
        pv.addWidget(self.crop_view, 1)
        self.image_info = QLabel("")
        self.image_info.setObjectName("hint")
        pv.addWidget(self.image_info)
        hint = QLabel("Kéo chuột trên ảnh để chọn vùng áp dụng OCR (mọi trang, mọi file trong danh sách).")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        pv.addWidget(hint)
        # file và trang mẫu: lấy theo dòng đang chọn trong danh sách (điều khiển ẩn, giữ để đồng bộ logic)
        self.crop_src = QComboBox()
        self.crop_src.hide()
        self.crop_page = QSpinBox()
        self.crop_page.setRange(1, 9999)
        self.crop_page.hide()
        left.addWidget(self.preview_box, 1)
        self.results = ResultsBox()
        left.addWidget(self.results)
        root.addLayout(left, 1)

        # cột phải: cấu hình, tùy chọn, tiến trình, mô hình AI
        right = QVBoxLayout()
        cfg = QGroupBox("Cấu hình nhận diện")
        cg = QVBoxLayout(cfg)
        self.engine = QComboBox()
        self.lang = QComboBox()
        self.device = QComboBox()
        for key in ENGINES:
            self.engine.addItem(L.ENGINE_LABELS[key], key)
        for key, label in L.dev_labels(gpu.ort_cuda_available()).items():
            self.device.addItem(label, key)
        self.out = QLineEdit()
        self.out.setPlaceholderText("Để trống = lưu cạnh file gốc")
        self.btn_out = QPushButton("Chọn…")
        out_row = QHBoxLayout()
        out_row.addWidget(self.out, 1)
        out_row.addWidget(self.btn_out)
        for label, widget in (("Công cụ OCR", self.engine), ("Ngôn ngữ", self.lang), ("Phần cứng", self.device)):
            cg.addWidget(QLabel(label))
            cg.addWidget(widget)
        cg.addWidget(QLabel("Thư mục lưu"))
        cg.addLayout(out_row)
        right.addWidget(cfg)

        opt = QGroupBox("Tùy chọn nâng cao")
        og = QVBoxLayout(opt)
        self.txt = QCheckBox("Ghi kèm file .txt")
        self.marker = QCheckBox("Ghi số trang gốc 【原本 p.N】")
        self.ruby = QCheckBox("Giữ chữ phiên âm kana trên chữ Hán (ruby)")
        for c in (self.txt, self.marker, self.ruby):
            og.addWidget(c)
        self.merge = QComboBox()
        for key, label in L.MERGE_LABELS.items():
            self.merge.addItem(label, key)
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("ví dụ 1-5,8 · để trống = tất cả (chỉ áp dụng cho PDF)")
        og.addWidget(QLabel("Cách ghép trang"))
        og.addWidget(self.merge)
        og.addWidget(QLabel("Trang"))
        og.addWidget(self.pages)

        # chi tiết kỹ thuật: thu gọn, ẩn hẳn khi bỏ chọn
        adv = QGroupBox("Chi tiết kỹ thuật")
        adv.setCheckable(True)
        adv.setChecked(False)
        adv_body = QWidget()
        agrid = QVBoxLayout(adv_body)
        QVBoxLayout(adv).addWidget(adv_body)
        self.upscale = QLineEdit("1")
        self.crop = QLineEdit()
        self.crop.setPlaceholderText("trái, trên, phải, dưới (pixel) · để trống = cả trang")
        self.kana = QComboBox()
        for key, label in L.KANA_LABELS.items():
            self.kana.addItem(label, key)
        self.cell_reocr = QCheckBox("Đọc lại ô bảng bị lẫn đường kẻ")
        self.use_cache = QCheckBox("Nhớ kết quả đã đọc (chạy lại file cũ sẽ nhanh hơn)")
        self.review = QCheckBox("Tạo file so sánh để kiểm tra (*_review.html)")
        self.conf = QLineEdit("0.8")
        self.conf.setToolTip("Dòng có độ chắc chắn thấp hơn mức này sẽ bị tô đỏ trong file so sánh (mặc định 0,8).")
        for label, widget in (("Phóng to ảnh", self.upscale), ("Chỉ đọc một vùng (tự điền khi kéo chuột)", self.crop),
                              ("Đọc bảng chữ kana (thử nghiệm)", self.kana)):
            agrid.addWidget(QLabel(label))
            agrid.addWidget(widget)
        agrid.addWidget(self.cell_reocr)
        agrid.addWidget(self.use_cache)
        agrid.addWidget(self.review)
        agrid.addWidget(QLabel("Ngưỡng nghi ngờ (file so sánh)"))
        agrid.addWidget(self.conf)
        og.addWidget(adv)
        self.advanced = adv
        adv_body.setVisible(False)
        adv.toggled.connect(adv_body.setVisible)
        right.addWidget(opt)

        run_box = QGroupBox("Tiến trình")
        rb = QVBoxLayout(run_box)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.status = QLabel("Sẵn sàng.")
        self.status.setWordWrap(True)
        self.btn_stop = QPushButton("Dừng")
        self.btn_stop.setObjectName("dangerBtn")
        self.btn_stop.setEnabled(False)
        rb.addWidget(self.progress)
        rb.addWidget(self.status)
        rb.addWidget(self.btn_stop)
        right.addWidget(run_box)

        self.models = ModelBox(chandra_available="chandra" in ENGINES)
        right.addWidget(self.models)
        right.addStretch(1)
        right_col = QWidget()
        right_col.setLayout(right)
        right_col.setFixedWidth(360)   # cột cấu hình cố định như hình mẫu; cột trái co giãn
        root.addWidget(right_col)

        self.btn_add.clicked.connect(self.add_files)
        self.btn_dir.clicked.connect(self.add_dir)
        self.btn_del.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_out.clicked.connect(self.pick_out)
        self.listing.dropped.connect(self._add_dropped)
        self.btn_stop.clicked.connect(self.request_stop)
        self.engine.currentIndexChanged.connect(self._sync_lang)
        self.listing.currentRowChanged.connect(self._sync_crop_src)
        self.btn_prev.clicked.connect(lambda: self.crop_page.setValue(self.crop_page.value() - 1))
        self.btn_next.clicked.connect(lambda: self.crop_page.setValue(self.crop_page.value() + 1))
        self.btn_crop_clear.clicked.connect(lambda: self.crop.setText(""))
        self.crop_view.cropChanged.connect(lambda *r: self.crop.setText(",".join(map(str, r))))
        self.crop.textChanged.connect(self._sync_crop_view)
        self.crop_src.currentIndexChanged.connect(lambda _=0: self._load_crop_page())
        self.crop_page.valueChanged.connect(lambda _=0: self._load_crop_page())
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
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 70))
            self.listing.addItem(item)
            self.listing.setItemWidget(item, FileRow(f))
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
        self.files_box.setTitle(f"Danh sách File ({n})")
        if hasattr(self, "crop_src"):
            self._refresh_crop_files()

    def _refresh_crop_files(self):
        self.crop_src.blockSignals(True)
        self.crop_src.clear()
        for f in self.files:
            self.crop_src.addItem(f.name, str(f))
        row = self.listing.currentRow()
        self.crop_src.setCurrentIndex(row if 0 <= row < len(self.files) else (0 if self.files else -1))
        self.crop_src.blockSignals(False)
        self._load_crop_page()

    def _sync_crop_src(self, row: int):
        """Dòng được chọn trong danh sách là file mẫu của khung xem trước."""
        if 0 <= row < self.crop_src.count() and self.crop_src.currentIndex() != row:
            self.crop_src.setCurrentIndex(row)

    def _load_crop_page(self):
        path = self.crop_src.currentData()
        if not path:
            self.page_badge.setText("Chưa có file")
            self.image_info.setText("")
            self.crop_view.set_image(None)
            self._sync_crop_view()
            return
        try:
            n = pipeline.page_count(Path(path))
        except Exception:
            n = 1
        self.crop_page.blockSignals(True)   # đổi giới hạn trang không được kích hoạt tải lại ảnh
        self.crop_page.setMaximum(max(1, n))
        self.crop_page.blockSignals(False)
        self.page_badge.setText(f"Trang {self.crop_page.value()} / {max(1, n)}")
        got = source_image(Path(path), self.crop_page.value())
        self.crop_view.set_image(got[0], got[1], got[2]) if got else self.crop_view.set_image(None)
        if got:   # thông tin ảnh theo đúng hệ tọa độ của pipeline (200 dpi với PDF, ảnh gốc với ảnh)
            dpi = f"{SCAN_DPI} dpi" if path.lower().endswith(".pdf") else "ảnh gốc"
            self.image_info.setText(f"{Path(path).name}  ·  {dpi}  ·  {got[1]} × {got[2]} px")
        self._sync_crop_view()

    def _sync_crop_view(self):
        try:
            rect = pipeline.parse_crop(self.crop.text())
        except ValueError:
            rect = None
        self.crop_view.set_crop(rect)

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu kết quả")
        if d:
            self.out.setText(d)

    def _set_file_state(self, i: int, text: str):
        if 0 <= i < self.listing.count():
            row = self.listing.itemWidget(self.listing.item(i))
            if row is not None:
                row.set_state(state_key(text), text)

    # ---------- tùy chọn ----------

    def options(self) -> dict:
        """Tùy chọn đầy đủ cho pipeline. Ném ValueError với thông báo tiếng Việt nếu sai.
        Giá trị lấy theo nhãn (như ô nhập của bản Tkinter) để dùng chung quy tắc trong ui_logic."""
        dev_map = L.dev_labels(gpu.ort_cuda_available())
        vals = {
            "conf": self.conf.text(), "upscale": self.upscale.text(), "crop": self.crop.text(),
            "dev": dev_map[self.device.currentData()], "lang": L.LANG_LABELS[self.lang.currentData()],
            "engine": L.ENGINE_LABELS[self.engine.currentData()], "merge": L.MERGE_LABELS[self.merge.currentData()],
            "kana": L.KANA_LABELS[self.kana.currentData()],
            "txt": self.txt.isChecked(), "marker": self.marker.isChecked(), "ruby": self.ruby.isChecked(),
            "cell_reocr": self.cell_reocr.isChecked(), "use_cache": self.use_cache.isChecked(),
            "review": self.review.isChecked(),
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
        self._set_running(True)
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
        self.results.set_results(outputs)
        self.status.setText(msg)
        self.progress.setValue(100)
        self._set_running(False)

    def _set_running(self, on: bool):
        self.btn_stop.setEnabled(on)
        self.models.setEnabled(not on)
        self.busy_changed.emit(on)

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


SECTION_TITLES = ("Xử lý tài liệu OCR", "Tách PDF", "Ghép PDF", "Công cụ khác")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 840)
        self.settings = L.load_settings()

        self.menubar_view = build_view_menu(self, QApplication.instance(), self.settings, self._save_view)
        self.menuBar().addMenu(self.menubar_view)
        view = self.settings.get("qt_view", {})
        apply_view(QApplication.instance(), view.get("theme", "sáng"), view.get("font_pt", 10), view.get("alpha", 100), self)

        # thanh bên: logo, bốn mục, trạng thái hệ thống
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(228)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 18, 16, 16)
        brand = QHBoxLayout()
        logo = QLabel("OCR")
        logo.setObjectName("logo")
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        names = QVBoxLayout()
        app_name = QLabel(APP_NAME)
        app_name.setObjectName("appTitle")
        sub = QLabel("Nhận dạng tiếng Nhật")
        sub.setObjectName("hint")
        names.addWidget(app_name)
        names.addWidget(sub)
        brand.addWidget(logo)
        brand.addLayout(names, 1)
        sl.addLayout(brand)
        sl.addSpacing(18)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for name in SECTIONS:
            item = QListWidgetItem(name)
            item.setSizeHint(QSize(0, 46))   # mỗi mục cao 46 px: đủ đệm như hình mẫu
            self.nav.addItem(item)
        sl.addWidget(self.nav, 1)

        foot = QWidget()
        foot.setObjectName("sideFoot")
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(14, 12, 14, 12)
        foot_title = QLabel("TRẠNG THÁI HỆ THỐNG")
        foot_title.setObjectName("footTitle")
        state_row = QHBoxLayout()
        dot = QLabel("●")
        dot.setObjectName("dot")
        self.sys_status = QLabel("Sẵn sàng hoạt động")
        state_row.addWidget(dot)
        state_row.addWidget(self.sys_status, 1)
        fl.addWidget(foot_title)
        fl.addLayout(state_row)
        sl.addWidget(foot)

        # nội dung: tiêu đề trang, nút Bắt đầu xử lý (chỉ ở mục OCR), các mục
        self.page_title = QLabel(SECTION_TITLES[0])
        self.page_title.setObjectName("pageTitle")
        self.run_btn = QPushButton("▶  Bắt đầu xử lý")
        self.run_btn.setObjectName("runBtn")
        head = QHBoxLayout()
        head.addWidget(self.page_title)
        self.file_badge = QLabel("")
        self.file_badge.setObjectName("badge")
        self.file_badge.setVisible(False)   # hiện khi có file (xem _refresh_sys_status)
        head.addWidget(self.file_badge)
        head.addStretch(1)
        head.addWidget(self.run_btn)
        self.stack = QStackedWidget()
        self.ocr = OcrPage(self.settings)
        self.split = SplitSection("Tách PDF", self.settings, "split")
        self.merge = MergeSection("Ghép PDF", self.settings, "merge")
        self.tools = ToolsSection("Công cụ khác", self.settings, "tools")
        for page in (self.ocr, self.split, self.merge, self.tools):
            scroll = QScrollArea()   # mỗi mục cuộn được khi cửa sổ thấp (laptop 768 px)
            scroll.setObjectName("page")
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(22, 16, 22, 16)
        cl.addLayout(head)
        cl.addWidget(self.stack, 1)

        central = QWidget()
        hl = QHBoxLayout(central)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(side)
        hl.addWidget(content, 1)
        self.setCentralWidget(central)

        self.run_btn.clicked.connect(self.ocr.start)
        self.ocr.busy_changed.connect(lambda on: self.run_btn.setEnabled(not on))
        self.nav.currentRowChanged.connect(self._show_section)
        self.nav.setCurrentRow(0)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_sys_status)
        self._status_timer.start(500)

    def _show_section(self, row: int):
        self.stack.setCurrentIndex(row)
        self.page_title.setText(SECTION_TITLES[row])
        self.run_btn.setVisible(row == 0)

    def _refresh_sys_status(self):
        busy = bool(self._busy_pages())
        self.sys_status.setText("Đang xử lý…" if busy else "Sẵn sàng hoạt động")
        n = len(self.ocr.files)
        self.file_badge.setText(f"{n} tệp" if n else "")
        self.file_badge.setVisible(self.stack.currentIndex() == 0 and n > 0)

    def _save_view(self):
        L.save_settings(self.settings)

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
