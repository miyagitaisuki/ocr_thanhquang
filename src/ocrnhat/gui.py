"""Giao diện chính OCR-Thanh Quang (PySide6). Thanh bên 4 mục: OCR, Tách PDF, Ghép PDF, Công cụ khác.

Logic không phụ thuộc giao diện nằm ở ui_logic.py; khuôn màu và kiểu ở gui_style.py.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from . import gpu, pipeline
from . import ui_logic as L
from .cli import collect
from .gui_about import SystemDialog, SysInfoWorker, build_help_menu
from .gui_extra import SCAN_DPI, ModelBox, PageView, ResultsBox, apply_view, build_view_menu, source_image
from .gui_style import APP_NAME, add_soft_shadows, show_banner, state_key
from .gui_pdf import MergeSection, SplitSection, ToolsSection
from .gui_progress import AnimatedProgress

log = logging.getLogger("ocrnhat.gui")

SECTIONS = ("OCR", "Tách PDF", "Ghép PDF", "Công cụ khác")
SECTIONS_SHORT = ("OCR", "Tách\nPDF", "Ghép\nPDF", "Công cụ\nkhác")   # thanh bên thu gọn khi cửa sổ hẹp (hai dòng)
NARROW_WINDOW = 980    # dưới mức này (px): thanh bên chỉ còn nhãn ngắn và cột cấu hình xuống dưới danh sách file
SIDEBAR_W, SIDEBAR_W_COMPACT = 228, 96          # chiều rộng thanh bên (px), bình thường và thu gọn
RIGHT_MIN_W, RIGHT_MAX_W = 300, 560             # cột cấu hình: kéo được trong khoảng này (px)
DROP_HINT = "Kéo thả PDF, PNG, JPG, TIFF vào danh sách bên dưới, hoặc bấm “+ Thêm file” (Ctrl+O)"
DROP_HINT_SHORT = "Kéo thả thêm file vào đây · Ctrl+O để chọn file"
ENGINES = ("auto", "ndlocr", "paddle", "ocr_vi")
FILE_FILTER = "PDF / ảnh (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
PRESETS = {   # mẫu tài liệu: đặt sẵn độ phóng to và đọc bảng; các ô khác giữ nguyên
    "Sổ tay / sách (mặc định)": dict(upscale="1", cell_reocr=True),
    "Ảnh chụp điện thoại": dict(upscale="2", cell_reocr=True),
    "Chỉ văn bản (không bảng)": dict(upscale="1", cell_reocr=False),
}


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
                opts = dict(self.opts)
                dpi = opts.pop("dpi", 200)   # DPI là tham số vị trí của process_file, không đi qua **opts
                r = pipeline.process_file(
                    f, self.out, dpi, self.pages if f.suffix.lower() == ".pdf" else None,
                    progress=lambda d, t, m: self.progress.emit(d, t, m),
                    cancel=lambda: self.cancel_requested, **opts)
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


def labeled(text: str, widget) -> QLabel:
    """Nhãn gắn với ô nhập (buddy): đọc đúng tên trên trình đọc màn hình, bấm nhãn thì focus ô."""
    label = QLabel(text)
    label.setBuddy(widget)
    widget.setAccessibleName(text)
    return label


def crops_text(rects) -> str:
    """Danh sách vùng -> chuỗi ô nhập: 'x0,y0,x1,y1;x0,y0,x1,y1'."""
    return ";".join(",".join(str(v) for v in r) for r in rects)


class ElidedLabel(QLabel):
    """Nhãn cắt bằng '…' theo bề ngang: không đẩy dòng rộng ra ngoài danh sách; rê chuột xem đủ."""

    def __init__(self, text: str, mode=Qt.TextElideMode.ElideMiddle):
        super().__init__()
        self._full, self._mode = text, mode
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.setText(self.fontMetrics().elidedText(self._full, self._mode, max(self.width() - 2, 0)))


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
        name = ElidedLabel(path.name)
        name.setObjectName("fileName")
        where = ElidedLabel(str(path.parent), Qt.TextElideMode.ElideLeft)
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
        root = QVBoxLayout(self)
        # hai cột ngăn bằng tay kéo được; cửa sổ hẹp thì đổi thành xếp dọc (set_narrow)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(12)
        root.addWidget(self.splitter)

        # cột trái: danh sách file, xem trước vùng chọn, kết quả
        left = QVBoxLayout()
        self.files_box = QGroupBox("Danh sách file (0)")
        fb = QVBoxLayout(self.files_box)
        bar = QGridLayout()   # lưới 2×2: hẹp thì các nút xếp hai hàng thay vì đẩy rộng cột
        self.btn_add = QPushButton("+ Thêm file")
        self.btn_dir = QPushButton("+ Thêm thư mục")
        self.btn_del = QPushButton("Bỏ mục đã chọn")
        self.btn_clear = QPushButton("Bỏ tất cả")
        self.btn_clear.setObjectName("dangerBtn")
        for i, b in enumerate((self.btn_add, self.btn_dir, self.btn_del, self.btn_clear)):
            bar.addWidget(b, i // 2, i % 2)
        fb.addLayout(bar)
        drop = QLabel(DROP_HINT)
        drop.setObjectName("dropzone")
        drop.setWordWrap(True)   # xuống dòng khi hẹp: không đẩy cả cột trái rộng ra
        drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop.setMinimumHeight(44)
        fb.addWidget(drop)
        self.listing = FileList()
        self.listing.setObjectName("files")
        self.listing.setMinimumHeight(150)
        self.listing.setAccessibleName("Danh sách file cần OCR")
        fb.addWidget(self.listing)
        self.drop = drop
        left.addWidget(self.files_box)

        self.preview_box = QGroupBox("Xem trước vùng chọn")
        pv = QVBoxLayout(self.preview_box)
        head = QHBoxLayout()
        self.page_badge = QLabel("Chưa có file")
        self.page_badge.setObjectName("badge")
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.btn_prev.setAccessibleName("Trang trước")
        self.btn_next.setAccessibleName("Trang sau")
        self.btn_prev.setToolTip("Trang trước")
        self.btn_next.setToolTip("Trang sau")
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
        hint = QLabel("Kéo chuột để chọn vùng; giữ Shift để thêm vùng thứ hai trở lên. Vùng áp dụng cho mọi trang của mọi file.")
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
        left_col = QWidget()
        left_col.setLayout(left)
        self.splitter.addWidget(left_col)
        self.splitter.setStretchFactor(0, 1)   # cột trái giãn theo cửa sổ, cột cấu hình giữ bề rộng khi kéo

        # cột phải: cấu hình, tùy chọn, tiến trình, mô hình AI
        right = QVBoxLayout()
        cfg = QGroupBox("Cấu hình nhận diện")
        cg = QVBoxLayout(cfg)
        self.preset = QComboBox()
        for name in PRESETS:
            self.preset.addItem(name)
        cg.addWidget(labeled("Loại tài liệu", self.preset))
        cg.addWidget(self.preset)
        preset_hint = QLabel("Chọn sẵn độ phóng to và đọc bảng theo loại tài liệu. Có thể chỉnh lại ở Chi tiết kỹ thuật.")
        preset_hint.setObjectName("hint")
        preset_hint.setWordWrap(True)
        cg.addWidget(preset_hint)
        self.engine = QComboBox()
        self.lang = QComboBox()
        self.device = QComboBox()
        for key in ENGINES:
            self.engine.addItem(L.ENGINE_LABELS[key], key)
        for key, label in L.dev_labels(gpu.gpu_selectable()).items():
            self.device.addItem(label, key)
        self.out = QLineEdit()
        self.out.setPlaceholderText("Trống = cạnh file gốc")
        self.btn_out = QPushButton("Chọn…")
        out_row = QHBoxLayout()
        out_row.addWidget(self.out, 1)
        out_row.addWidget(self.btn_out)
        for label, widget in (("Công cụ OCR", self.engine), ("Ngôn ngữ", self.lang), ("Phần cứng", self.device)):
            cg.addWidget(labeled(label, widget))
            cg.addWidget(widget)
        cg.addWidget(labeled("Thư mục lưu", self.out))
        cg.addLayout(out_row)
        right.addWidget(cfg)

        # cấu hình cơ bản: thêm file .txt vào khối cấu hình (cg); phần còn lại thu gọn trong "Tùy chọn nâng cao"
        opt = QGroupBox("Tùy chọn nâng cao")
        opt.setCheckable(True)
        opt.setProperty("collapsible", True)
        opt.setChecked(False)
        opt_body = QWidget()
        og = QVBoxLayout(opt_body)
        QVBoxLayout(opt).addWidget(opt_body)
        self.txt = QCheckBox("Ghi kèm file .txt")
        cg.addWidget(self.txt)
        self.marker = QCheckBox("Ghi số trang gốc 【原本 p.N】")
        self.ruby = QCheckBox("Giữ chữ phiên âm kana trên chữ Hán (ruby)")
        self.markdown = QCheckBox("Xuất Markdown có đánh dấu để nhờ AI (LLM) hiệu đính (*.md)")
        self.markdown.setToolTip("Ghi kèm file .md (tiêu đề, bảng, ⟦?…⟧ chỗ nghi ngờ) và ocr_markdown_rules.md để dán vào chỉ dẫn của LLM. Dùng chung ngưỡng nghi ngờ bên dưới.")
        self.vi_fix = QCheckBox("Sửa dấu và bỏ nhiễu dấu mộc (chỉ tiếng Việt)")
        self.vi_fix.setToolTip("Sửa dấu theo tần suất trong tài liệu và bỏ chữ rác từ dấu mộc. Tắt nếu muốn giữ nguyên chữ engine đọc.")
        for c in (self.marker, self.ruby, self.markdown, self.vi_fix):
            og.addWidget(c)
        self.merge = QComboBox()
        for key, label in L.MERGE_LABELS.items():
            self.merge.addItem(label, key)
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("ví dụ 1-5,8 · để trống = tất cả (chỉ áp dụng cho PDF)")
        og.addWidget(labeled("Cách ghép trang", self.merge))
        og.addWidget(self.merge)
        og.addWidget(labeled("Trang", self.pages))
        og.addWidget(self.pages)

        # chi tiết kỹ thuật: thu gọn, ẩn hẳn khi bỏ chọn
        adv = QGroupBox("Chi tiết kỹ thuật")
        adv.setCheckable(True)
        adv.setProperty("collapsible", True)
        adv.setChecked(False)
        adv_body = QWidget()
        agrid = QVBoxLayout(adv_body)
        QVBoxLayout(adv).addWidget(adv_body)
        self.upscale = QLineEdit("1")
        self.dpi = QComboBox()
        for value in (150, 200, 300):
            self.dpi.addItem(f"{value} dpi", value)
        self.dpi.setCurrentIndex(self.dpi.findData(SCAN_DPI))
        self._dpi_prev = SCAN_DPI
        self.crop = QLineEdit()
        self.crop.setPlaceholderText("trái, trên, phải, dưới (pixel) · để trống = cả trang")
        self.kana = QComboBox()
        for key, label in L.KANA_LABELS.items():
            self.kana.addItem(label, key)
        self.cell_reocr = QCheckBox("Đọc lại ô bảng bị lẫn đường kẻ")
        self.use_cache = QCheckBox("Nhớ kết quả đã đọc (chạy lại file cũ sẽ nhanh hơn)")
        self.review = QCheckBox("Tạo file so sánh để kiểm tra (*_review.html)")
        self.conf = QLineEdit("0.8")
        conf_hint = QLabel("Dòng có độ chắc chắn thấp hơn mức này được tô đỏ trong file so sánh (mặc định 0,8).")
        conf_hint.setObjectName("hint")
        conf_hint.setWordWrap(True)
        for label, widget in (("Độ phân giải (DPI)", self.dpi), ("Phóng to ảnh", self.upscale), ("Vùng đọc (x0,y0,x1,y1; nhiều vùng cách bằng ;)", self.crop),
                              ("Đọc bảng chữ kana (thử nghiệm)", self.kana)):
            agrid.addWidget(labeled(label, widget))
            agrid.addWidget(widget)
        agrid.addWidget(self.cell_reocr)
        agrid.addWidget(self.use_cache)
        agrid.addWidget(self.review)
        agrid.addWidget(labeled("Ngưỡng nghi ngờ (file so sánh)", self.conf))
        agrid.addWidget(self.conf)
        agrid.addWidget(conf_hint)
        og.addWidget(adv)
        self.advanced = adv
        adv_body.setVisible(False)
        adv.toggled.connect(adv_body.setVisible)
        opt_body.setVisible(False)
        opt.toggled.connect(opt_body.setVisible)
        right.addWidget(opt)

        run_box = QGroupBox("Tiến trình")
        rb = QVBoxLayout(run_box)
        self.progress = AnimatedProgress()
        self.progress.setAccessibleName("Tiến trình OCR")
        self.status = QLabel("Sẵn sàng.")
        self.status.setWordWrap(True)
        self.banner = QLabel("")   # thông báo lỗi/kết quả cuối, hiện sau khi chạy xong
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        self.btn_log = QPushButton("Mở thư mục nhật ký")
        self.btn_log.setVisible(False)
        self.btn_open_out = QPushButton("Mở thư mục kết quả")
        self.btn_open_out.setVisible(False)
        self.btn_open_out.clicked.connect(self._open_out_dir)
        rb.addWidget(self.progress)
        rb.addWidget(self.status)
        rb.addWidget(self.banner)
        rb.addWidget(self.btn_open_out)
        rb.addWidget(self.btn_log)
        right.insertWidget(0, run_box)   # tiến trình lên đầu cột: thấy ngay khi chạy, không cần cuộn

        self.models = ModelBox()
        right.addWidget(self.models)
        right.addStretch(1)
        right_col = QWidget()
        right_col.setLayout(right)
        right_col.setMinimumWidth(RIGHT_MIN_W)   # cửa sổ hẹp thì xuống dưới (MainWindow.resizeEvent)
        right_col.setMaximumWidth(RIGHT_MAX_W)
        self.right_col = right_col
        self.splitter.addWidget(right_col)
        self.splitter.setStretchFactor(1, 0)
        self.btn_log.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(L.LOG_FILE.parent))))

        self.btn_add.clicked.connect(self.add_files)
        self.btn_dir.clicked.connect(self.add_dir)
        self.btn_del.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_out.clicked.connect(self.pick_out)
        self.listing.dropped.connect(self._add_dropped)
        self.engine.currentIndexChanged.connect(self._sync_lang)
        self.lang.currentIndexChanged.connect(self._sync_vi_fix)
        self.preset.currentIndexChanged.connect(self._apply_preset)
        self.listing.currentRowChanged.connect(self._sync_crop_src)
        self.btn_prev.clicked.connect(lambda: self.crop_page.setValue(self.crop_page.value() - 1))
        self.btn_next.clicked.connect(lambda: self.crop_page.setValue(self.crop_page.value() + 1))
        self.btn_crop_clear.clicked.connect(lambda: self.crop.setText(""))
        self.dpi.currentIndexChanged.connect(self._on_dpi_changed)
        self.crop_view.cropsChanged.connect(lambda rs: self.crop.setText(crops_text(rs)))
        self.crop.textChanged.connect(self._sync_crop_view)
        self.crop_src.currentIndexChanged.connect(lambda _=0: self._load_crop_page())
        self.crop_page.valueChanged.connect(lambda _=0: self._load_crop_page())
        self._sync_lang()
        # đang OCR thì khóa các khối này (xem _set_running); xem trước vẫn xem được nhưng không đổi vùng cắt
        self._locked_while_running = [
            self.btn_add, self.btn_dir, self.btn_del, self.btn_clear, self.btn_out,
            cfg, opt, self.preview_box,
        ]

    def set_narrow(self, narrow: bool):
        """Cửa sổ hẹp: cột cấu hình xuống dưới danh sách file. Quyết định theo cửa sổ vì bề rộng tối thiểu của trang
        (khi xếp ngang) lớn hơn vùng nhìn nên không đo được từ chính trang."""
        wanted = Qt.Orientation.Vertical if narrow else Qt.Orientation.Horizontal
        if self.splitter.orientation() != wanted:
            self.splitter.setOrientation(wanted)
            self.right_col.setMaximumWidth(16777215 if narrow else RIGHT_MAX_W)

    def _apply_preset(self, _i: int = 0):
        p = PRESETS[self.preset.currentText()]
        self.upscale.setText(p["upscale"])
        self.cell_reocr.setChecked(p["cell_reocr"])

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
        self._sync_vi_fix()

    def _sync_vi_fix(self):
        self.vi_fix.setVisible(self.lang.currentData() == "vi")

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
            item = QListWidgetItem()   # chữ hiển thị do FileRow vẽ; tên chỉ để trình đọc màn hình (không vẽ dưới widget)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, f.name)
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
        self.files_box.setTitle(f"Danh sách file ({n})")
        self.drop.setText(DROP_HINT if n == 0 else DROP_HINT_SHORT)   # gợi ý kéo thả luôn hiện, chỉ rút gọn
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
        dpi_now = self.dpi.currentData()
        got = source_image(Path(path), self.crop_page.value(), dpi_now)
        self.crop_view.set_image(got[0], got[1], got[2]) if got else self.crop_view.set_image(None)
        if got:   # thông tin ảnh theo đúng hệ tọa độ của pipeline (DPI đang chọn với PDF, ảnh gốc với ảnh)
            dpi = f"{dpi_now} dpi" if path.lower().endswith(".pdf") else "ảnh gốc"
            self.image_info.setText(f"{Path(path).name}  ·  {dpi}  ·  {got[1]} × {got[2]} px")
        self._sync_crop_view()

    def _on_dpi_changed(self, _i: int = 0):
        """Đổi DPI thì tọa độ pixel đổi theo; nhân vùng cắt với tỉ lệ để giữ đúng phần trang đã chọn."""
        new = self.dpi.currentData()
        old = self._dpi_prev
        self._dpi_prev = new
        try:
            rects = pipeline.parse_crops(self.crop.text())
        except ValueError:
            rects = None
        if rects and old:
            k = new / old
            self.crop.setText(crops_text([tuple(round(v * k) for v in r) for r in rects]))
        self._load_crop_page()

    def _sync_crop_view(self):
        try:
            rects = pipeline.parse_crops(self.crop.text())
        except ValueError:
            rects = None
        self.crop_view.set_crops(rects or [])

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
        Giá trị lấy theo nhãn hiển thị để dùng chung quy tắc trong ui_logic."""
        dev_map = L.dev_labels(gpu.gpu_selectable())
        vals = {
            "conf": self.conf.text(), "upscale": self.upscale.text(), "crop": self.crop.text(),
            "dpi": str(self.dpi.currentData()),
            "dev": dev_map[self.device.currentData()], "lang": L.LANG_LABELS[self.lang.currentData()],
            "engine": L.ENGINE_LABELS[self.engine.currentData()], "merge": L.MERGE_LABELS[self.merge.currentData()],
            "kana": L.KANA_LABELS[self.kana.currentData()],
            "txt": self.txt.isChecked(), "marker": self.marker.isChecked(), "ruby": self.ruby.isChecked(), "markdown": self.markdown.isChecked(),
            "cell_reocr": self.cell_reocr.isChecked(), "use_cache": self.use_cache.isChecked(),
            "review": self.review.isChecked(), "vi_fix": self.vi_fix.isChecked(),
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
            self._problem("Chưa chọn file. Thêm file ở danh sách bên trái.", self.btn_add)
            return
        try:
            pages = pipeline.parse_pages(self.pages.text())
        except ValueError:
            self._problem("Số trang không hợp lệ. Ví dụ: 1-5,8.", self.pages)
            return
        try:
            opts = self.options()
        except ValueError as e:
            self._problem(str(e))
            return
        why = self._engine_check(opts)
        if why:
            self._problem(why + " Hãy tải mô hình ở mục “Mô hình AI” hoặc chọn công cụ khác.")
            return
        self._save()
        for i in range(len(self.files)):
            self._set_file_state(i, "Chờ")
        self.progress.setValue(0)
        self.progress.setActive(True)
        self.banner.setVisible(False)
        self.btn_log.setVisible(False)
        self.btn_open_out.setVisible(False)
        self._set_running(True)
        out = self.out.text().strip()
        self._run_out = Path(out) if out else None   # chốt lúc bắt đầu: người dùng đổi ô khi đang chạy không ảnh hưởng
        self.worker = OcrWorker(list(self.files), self._run_out, pages, opts)
        self.worker.progress.connect(self._on_progress)
        self.worker.file_state.connect(self._set_file_state)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.start()

    def request_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel_requested = True
            self.status.setText("Đang dừng… chờ trang hiện tại đọc xong.")

    def _open_out_dir(self):
        if self._out_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._out_dir)))

    def _on_progress(self, d: int, t: int, m: str):
        self.progress.setValue(int(100 * d / max(1, t)))
        self.status.setText(f"[{d}/{t}] {m}")

    def _problem(self, text: str, focus=None):
        """Lỗi nhập: hiện ngay trong banner, không mở hộp thoại; con trỏ về ô bị lỗi."""
        show_banner(self.banner, text, focus=focus)

    def _on_done(self, msg: str, outputs: list):
        self.results.set_results(outputs)
        self.status.setText(msg)
        failed = "file lỗi" in msg
        show_banner(self.banner, msg, error=failed)   # báo kết quả cho trình đọc màn hình (Alert)
        self._out_dir = self._run_out or (outputs[0][0].parent if outputs else None)
        self.btn_open_out.setVisible(bool(outputs) and self._out_dir is not None)
        self.btn_log.setVisible(failed)
        self.progress.setActive(False)
        self.progress.setValue(100)
        self._set_running(False)

    def _set_running(self, on: bool):
        # khi OCR đang chạy: khóa danh sách, cấu hình và xem trước; tooltip giải thích lý do
        reason = "Đang OCR. Bấm Dừng trước khi đổi." if on else ""
        for w in self._locked_while_running:
            w.setEnabled(not on)
            w.setToolTip(reason)
        self.models.setEnabled(not on)
        self.busy_changed.emit(on)

    def busy(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    # ---------- nhớ tùy chọn ----------

    _SAVED = ("txt", "marker", "ruby", "markdown", "vi_fix", "cell_reocr", "use_cache", "upscale", "crop", "pages", "out")
    _out_dir: Path | None = None   # thư mục kết quả của lần chạy gần nhất (nút "Mở thư mục kết quả")
    _run_out: Path | None = None   # thư mục lưu chốt khi bấm chạy

    _COMBOS = ("engine", "device", "merge", "kana", "lang", "dpi")   # lưu theo khóa, không theo nhãn

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


class ClickableFoot(QWidget):
    """Ô trạng thái hệ thống ở thanh bên: bấm hoặc Enter/Space để mở thông tin chi tiết."""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)   # lớp con QWidget không tự vẽ nền QSS
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(e)


class HardwareProbe(QThread):
    """Dò phần cứng một lần lúc mở app, trả về một dòng ngắn cho ô trạng thái."""
    ready = Signal(str)

    def run(self):
        gpus = gpu.detect()
        if not gpus:
            self.ready.emit("Chỉ có CPU (không thấy card NVIDIA)")
            return
        g = max(gpus, key=lambda x: x.vram_mb or 0)
        vram = f" · {round(g.vram_mb / 1024)} GB" if g.vram_mb else ""
        use = "GPU dùng được cho OCR" if gpu.ort_cuda_available() else "chỉ dùng CPU (onnxruntime không có CUDA)"
        self.ready.emit(f"{g.name}{vram}\n{use}")


SECTION_TITLES = ("Xử lý tài liệu OCR", "Tách PDF", "Ghép PDF", "Công cụ khác")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 840)
        self.settings = L.load_settings()

        self.menubar_view = build_view_menu(self, QApplication.instance(), self.settings, self._save_view)
        self.menuBar().addMenu(self.menubar_view)
        self.menubar_help = build_help_menu(self)
        self.menuBar().addMenu(self.menubar_help)
        view = self.settings.get("qt_view", {})
        apply_view(QApplication.instance(), view.get("theme", "sáng"), view.get("font_pt", 10), view.get("alpha", 100), self)

        # thanh bên: logo, bốn mục, trạng thái hệ thống
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(SIDEBAR_W)
        self.side = side
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
        sub = QLabel("Nhận dạng văn bản PDF và ảnh")
        sub.setObjectName("hint")
        self.brand_texts = (app_name, sub)
        names.addWidget(app_name)
        names.addWidget(sub)
        brand.addWidget(logo)
        brand.addLayout(names, 1)
        sl.addLayout(brand)
        sl.addSpacing(18)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setAccessibleName("Chọn mục (Ctrl+1 đến Ctrl+4)")
        for name in SECTIONS:
            item = QListWidgetItem(name)
            item.setToolTip(name)
            item.setSizeHint(QSize(0, 46))   # mỗi mục cao 46 px: đủ đệm như hình mẫu
            self.nav.addItem(item)
        sl.addWidget(self.nav, 1)

        foot = ClickableFoot()
        foot.setObjectName("sideFoot")
        foot.setToolTip("Bấm để xem thông tin hệ thống: GPU, onnxruntime CUDA")
        foot.setAccessibleName("Trạng thái hệ thống. Bấm để xem chi tiết")
        foot.clicked.connect(lambda: SystemDialog(self).exec())
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(14, 12, 14, 12)
        foot_title = QLabel("TRẠNG THÁI HỆ THỐNG")
        foot_title.setObjectName("footTitle")
        state_row = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setObjectName("dot")
        self.sys_status = QLabel("Sẵn sàng hoạt động")
        state_row.addWidget(self.dot)
        state_row.addWidget(self.sys_status, 1)
        self.sys_hw = QLabel("Đang dò phần cứng…")   # dòng thứ hai: GPU đang dùng được hay chỉ CPU
        self.sys_hw.setObjectName("hint")
        self.sys_hw.setWordWrap(True)
        fl.addWidget(foot_title)
        fl.addLayout(state_row)
        fl.addWidget(self.sys_hw)
        sl.addWidget(foot)
        self.side_foot = foot

        # nội dung: tiêu đề trang, nút Bắt đầu xử lý (chỉ ở mục OCR), các mục
        self.page_title = QLabel(SECTION_TITLES[0])
        self.page_title.setObjectName("pageTitle")
        self.run_btn = QPushButton("▶  Bắt đầu xử lý")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.setToolTip("Bắt đầu xử lý (Ctrl+R hoặc F5)")
        self.run_btn.setAccessibleName("Bắt đầu xử lý")
        # Dừng nằm cạnh nút chạy trên header (chỉ mục OCR), bật khi đang chạy
        self.stop_btn = QPushButton("■  Dừng")
        self.stop_btn.setObjectName("dangerBtn")
        self.stop_btn.setToolTip("Dừng sau trang hiện tại (Esc)")
        self.stop_btn.setAccessibleName("Dừng xử lý")
        self.stop_btn.setEnabled(False)
        head = QHBoxLayout()
        head.addWidget(self.page_title)
        self.file_badge = QLabel("")
        self.file_badge.setObjectName("badge")
        self.file_badge.setVisible(False)   # hiện khi có file (xem _refresh_sys_status)
        head.addWidget(self.file_badge)
        head.addStretch(1)
        head.addWidget(self.stop_btn)
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
        self.setMinimumSize(760, 560)
        self._compact = False
        self._setup_shortcuts()
        add_soft_shadows(central)   # bóng mềm cho các thẻ sau khi đã dựng xong

        self.run_btn.clicked.connect(self.ocr.start)
        self.stop_btn.clicked.connect(self._stop_here)
        self.ocr.busy_changed.connect(self._on_ocr_busy)
        self.nav.currentRowChanged.connect(self._show_section)
        self.nav.setCurrentRow(0)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_sys_status)
        self._status_timer.start(500)
        self._hw_probe = HardwareProbe(self)   # nvidia-smi có thể chậm: dò ở luồng nền
        self._hw_probe.ready.connect(self.sys_hw.setText)
        self._hw_probe.start()

    def _setup_shortcuts(self):
        def add(keys, slot):
            for k in ((keys,) if isinstance(keys, str) else keys):
                QShortcut(QKeySequence(k), self, activated=slot)
        add("Ctrl+O", self._add_files_here)
        add(("Ctrl+R", "F5"), self._run_here)
        add("Esc", self._stop_here)
        for i in range(len(SECTIONS)):
            add(f"Ctrl+{i + 1}", lambda i=i: self.nav.setCurrentRow(i))
        QShortcut(QKeySequence("Delete"), self.ocr, activated=self.ocr.remove_selected).setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _add_files_here(self):
        page = self.stack.currentWidget().widget()
        btn = getattr(page, "btn_add", None)
        if btn is not None and btn.isEnabled():
            btn.click()

    def _run_here(self):
        if self.stack.currentIndex() == 0 and self.run_btn.isEnabled():
            self.run_btn.click()

    def _stop_here(self):
        if self.ocr.busy() and self.stack.currentIndex() == 0:
            if QMessageBox.question(self, "Dừng OCR", "Dừng sau trang hiện tại? Các trang đã đọc vẫn được lưu.") == QMessageBox.StandardButton.Yes:
                self.ocr.request_stop()
                self.stop_btn.setEnabled(False)   # đã yêu cầu dừng; bật lại khi OCR kết thúc (busy_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < NARROW_WINDOW
        self.ocr.set_narrow(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self.side.setFixedWidth(SIDEBAR_W_COMPACT if compact else SIDEBAR_W)
        self.nav.setProperty("compact", compact)   # kiểu thu gọn nằm trong gui_style (QListWidget#nav[compact="true"])
        self.nav.style().unpolish(self.nav)
        self.nav.style().polish(self.nav)
        align = Qt.AlignmentFlag.AlignCenter if compact else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        self.side_foot.setVisible(not compact)
        for w in self.brand_texts:
            w.setVisible(not compact)
        for i in range(self.nav.count()):
            self.nav.item(i).setText(SECTIONS_SHORT[i] if compact else SECTIONS[i])
            self.nav.item(i).setSizeHint(QSize(0, 58 if compact else 46))   # nhãn thu gọn hai dòng cần cao hơn
            self.nav.item(i).setTextAlignment(align)

    def _show_section(self, row: int):
        self.stack.setCurrentIndex(row)
        self.page_title.setText(SECTION_TITLES[row])
        self.run_btn.setVisible(row == 0)
        self.stop_btn.setVisible(row == 0)

    def _on_ocr_busy(self, on: bool):
        self.run_btn.setEnabled(not on)
        self.stop_btn.setEnabled(on)

    def _refresh_sys_status(self):
        busy = bool(self._busy_pages())
        loading = self.ocr.models.busy()
        state = "busy" if busy or loading else "ready"
        self.sys_status.setText("Đang xử lý…" if busy else "Đang tải mô hình…" if loading else "Sẵn sàng hoạt động")
        if self.dot.property("state") != state:   # màu chấm đổi theo trạng thái (QSS theo thuộc tính)
            self.dot.setProperty("state", state)
            self.dot.style().unpolish(self.dot)
            self.dot.style().polish(self.dot)
        n = len(self.ocr.files)
        self.file_badge.setText(f"{n} file" if n else "")
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
        if self._hw_probe.isRunning():
            self._hw_probe.wait(5000)   # dò GPU có thể còn chạy: đợi để không hủy luồng đang chạy
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
