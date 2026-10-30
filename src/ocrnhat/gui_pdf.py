"""Ba mục Công cụ PDF của giao diện PySide6 (bước 3):
2. Tách PDF: trích xuất trang, tách file.
3. Ghép PDF: ghép nhiều file, ghép xen kẽ, chèn trang lặp lại.
4. Công cụ khác: xoay trang, nén PDF, tự động theo thư mục.

Mỗi mục có danh sách PDF riêng (kéo-thả để đổi thứ tự), khối đầu ra dùng chung và một thẻ cho mỗi thao tác.
Logic PDF nằm ở pdf_extract.py và pdf_ops.py; file này chỉ dựng giao diện và chạy ở luồng nền.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from . import pdf_extract as pe
from . import pdf_ops
from . import ui_logic as L
from .gui_style import show_banner

log = logging.getLogger("ocrnhat.gui")
PDF_FILTER = "PDF (*.pdf)"
_PATH_ROLE, _PAGES_ROLE = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1


# ---------- trợ giúp chung ----------

def _read(widget):
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QComboBox):
        return widget.currentData()
    return widget.text()


def _write(widget, value):
    if isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QComboBox):
        idx = widget.findData(value)
        if idx >= 0:
            widget.setCurrentIndex(idx)
    elif value is not None:
        widget.setText(str(value))


class PdfJobWorker(QThread):
    """Chạy lần lượt các việc (mỗi file một việc, hoặc một việc chung) ở luồng nền. Hủy được giữa hai việc."""
    progress = Signal(int, int, str)   # việc đang làm, tổng số việc, mô tả
    finished_ok = Signal(str, list)    # thông điệp cuối, danh sách file đầu ra

    def __init__(self, jobs: list[tuple[str, object]], done_text: str):
        super().__init__()
        self.jobs, self.done_text = jobs, done_text
        self.cancel_requested = False

    def run(self):
        outputs, errors = [], []
        n = len(self.jobs)
        for i, (label, task) in enumerate(self.jobs, 1):
            if self.cancel_requested:
                break
            self.progress.emit(i, n, label)
            try:
                res = task()
                outputs += list(res) if isinstance(res, list) else [res]
            except Exception as e:   # một file lỗi không dừng các file còn lại
                log.exception("Lỗi PDF: %s", label)
                errors.append(f"{label}: {e}")
        if self.cancel_requested:
            msg = f"Đã dừng sau {len(outputs)} file đầu ra."
        else:
            where = f", lưu tại {outputs[-1].parent}" if outputs else ""
            msg = f"Xong: {self.done_text}: {len(outputs)} file{where}."
        if errors:
            msg += " Lỗi: " + "; ".join(errors)
        self.finished_ok.emit(msg, [str(p) for p in outputs])


class WatchWorker(QThread):
    """Theo dõi thư mục (pdf_ops.watch_folder) đến khi bấm dừng."""
    report = Signal(str)

    def __init__(self, folder: Path, process):
        super().__init__()
        self.folder, self.process = folder, process
        self.stop_event = threading.Event()

    def run(self):
        def on_result(path, result, err):
            self.report.emit(f"{path.name}: " + (f"lỗi: {err}" if err else f"xong → {result.name}"))
        pdf_ops.watch_folder(self.folder, self.process, self.stop_event, 2.0, on_result)


class PdfFileList(QListWidget):
    """Danh sách PDF: kéo để đổi thứ tự (dùng khi ghép), kéo file từ Explorer để thêm."""
    dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAcceptDrops(True)
        self.setMinimumHeight(140)

    def dropEvent(self, e):
        if e.source() is self:   # đổi thứ tự trong danh sách
            super().dropEvent(e)
            return
        if e.mimeData().hasUrls():
            self.dropped.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
        e.ignore()

    def dragEnterEvent(self, e):
        if e.source() is self or e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()


class PdfFilesBox(QGroupBox):
    """Danh sách PDF dùng chung cho một mục: thêm, bỏ, sắp xếp. Gọi on_change khi danh sách đổi."""

    def __init__(self, on_change, on_error=None):
        super().__init__("Tệp PDF")
        self.on_change, self.on_error = on_change, on_error
        self.list = PdfFileList()
        self.count = QLabel("Chưa có file nào")
        self.btn_add = QPushButton("Thêm file…")
        self.btn_del = QPushButton("Bỏ mục đã chọn")
        self.btn_clear = QPushButton("Bỏ tất cả")
        bar = QHBoxLayout()
        for b in (self.btn_add, self.btn_del, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.count)
        self.hint = QLabel("Kéo mục để đổi thứ tự. Thứ tự này dùng khi ghép file.")
        self.hint.setWordWrap(True)
        root = QVBoxLayout(self)
        root.addLayout(bar)
        root.addWidget(self.list, 1)
        root.addWidget(self.hint)
        self.btn_add.clicked.connect(self.add_files)
        self.btn_del.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear)
        self.list.dropped.connect(self.add_paths)
        self.list.model().rowsMoved.connect(lambda *_: self.on_change())

    def files(self) -> list[Path]:
        return [Path(self.list.item(i).data(_PATH_ROLE)) for i in range(self.list.count())]

    def pages(self, path: Path) -> int:
        for i in range(self.list.count()):
            if self.list.item(i).data(_PATH_ROLE) == str(path):
                return self.list.item(i).data(_PAGES_ROLE)
        return 0

    def add_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Chọn file PDF", "", PDF_FILTER)
        self.add_paths(names)

    def add_paths(self, paths: list):
        """Thêm PDF; bỏ qua file trùng và file không đọc được (báo lỗi)."""
        errors = []
        for p in paths:
            f = Path(p)
            if f.suffix.lower() != ".pdf" or f in self.files():
                continue
            try:
                n = pe.page_count(f)
            except Exception as e:   # PDF hỏng hoặc có mật khẩu
                errors.append(f"{f.name}: {e}")
                continue
            item = QListWidgetItem(f"{f.name}    ·  {n} trang    ·  {f.parent}")
            item.setData(_PATH_ROLE, str(f))
            item.setData(_PAGES_ROLE, n)
            self.list.addItem(item)
        self._refresh()
        if errors and self.on_error:
            self.on_error("Không mở được PDF: " + "; ".join(errors))

    def remove_selected(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._refresh()

    def clear(self):
        self.list.clear()
        self._refresh()

    def _refresh(self):
        n = self.list.count()
        self.count.setText(f"{n} file" if n else "Chưa có file nào")
        self.on_change()


class PdfOutputBox(QGroupBox):
    """Khối đầu ra dùng chung của một mục: thư mục, ghi đè, nén, bookmark, phiên bản PDF."""

    def __init__(self, with_bookmarks: bool = True):
        super().__init__("Đầu ra chung")
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("để trống = lưu cạnh file gốc")
        self.btn_folder = QPushButton("Chọn…")
        self.overwrite = QCheckBox("Ghi đè nếu file đã có (tắt: thêm số (2), (3)...)")
        self.compress = QCheckBox("Nén file đầu ra")
        self.compress.setChecked(True)
        self.keep_bm = QCheckBox("Giữ bookmark (trỏ tới trang được chọn)")
        self.keep_bm.setChecked(True)
        self.version = QComboBox()
        for v in pe.PDF_VERSIONS:
            self.version.addItem(v, v)
        self.version.setCurrentIndex(pe.PDF_VERSIONS.index("1.5"))
        grid = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(self.btn_folder)
        grid.addWidget(QLabel("Thư mục lưu"))
        grid.addLayout(row)
        grid.addWidget(QLabel("Phiên bản PDF"))
        grid.addWidget(self.version)
        for c in (self.overwrite, self.compress):
            grid.addWidget(c)
        self.bookmarks_visible = with_bookmarks
        if with_bookmarks:
            grid.addWidget(self.keep_bm)
        self.btn_folder.clicked.connect(self._pick)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu")
        if d:
            self.folder.setText(d)

    def out(self) -> Path | None:
        text = self.folder.text().strip()
        return Path(text) if text else None

    def options(self, separate: bool = False) -> pe.ExtractOptions:
        return pe.ExtractOptions(separate=separate, overwrite=self.overwrite.isChecked(),
                                 compress=self.compress.isChecked(),
                                 keep_bookmarks=self.keep_bm.isChecked() if self.bookmarks_visible else True,
                                 pdf_version=self.version.currentData())


class PdfSection(QGroupBox):
    """Khung chung của một mục PDF: danh sách bên trên, thẻ thao tác ở giữa, tiến trình ở dưới."""

    def __init__(self, title: str, settings: dict, settings_key: str):
        super().__init__()
        self.settings, self.key = settings, settings_key
        self.worker: QThread | None = None
        self.fields: dict[str, object] = {}   # ô nhập theo tên, để lưu và khôi phục
        self.files_box = PdfFilesBox(self.on_files_changed, self._problem)
        self.output = PdfOutputBox(with_bookmarks=True)
        self.tabs = QTabWidget()
        self.run_buttons: list[QPushButton] = []
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("Thêm file PDF, chọn thao tác rồi bấm Thực hiện.")
        self.status.setWordWrap(True)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("pdfTitle")
        self.banner = QLabel("")   # lỗi nhập hiện ngay trong mục (thay hộp thoại)
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        root = QVBoxLayout(self)
        root.addWidget(self.title_label)
        root.addWidget(self.files_box, 1)
        root.addWidget(self.output)
        root.addWidget(self.tabs)
        root.addWidget(self.banner)
        root.addWidget(self.progress)
        root.addWidget(self.status)
        self.build_tabs()
        self._restore()

    # subclass điền thẻ thao tác
    def build_tabs(self):
        pass

    def on_files_changed(self):
        """Subclass cập nhật danh sách chọn (ô combobox file)."""
        pass

    def field(self, name: str, widget):
        self.fields[name] = widget
        return widget

    def make_run(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("runBtn")   # nút chính dùng cùng kiểu với mục OCR
        btn.clicked.connect(slot)
        self.run_buttons.append(btn)
        return btn

    def busy(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def _problem(self, text: str, focus=None):
        """Lỗi nhập của thao tác: hiện trong banner của mục, đặt con trỏ vào ô bị lỗi nếu có."""
        show_banner(self.banner, text, focus=focus)

    def _set_busy(self, busy: bool):
        for b in self.run_buttons:
            b.setEnabled(not busy)
        self.files_box.setEnabled(not busy)
        self.output.setEnabled(not busy)

    # ---------- chạy ----------

    def start_jobs(self, jobs: list[tuple[str, object]], done_text: str):
        if not jobs:
            return
        self._save()
        self.banner.setVisible(False)
        self.progress.setValue(0)
        self._set_busy(True)
        self.worker = PdfJobWorker(jobs, done_text)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.start()

    def _on_progress(self, i: int, n: int, label: str):
        self.progress.setValue(int(100 * (i - 1) / max(1, n)))
        self.status.setText(f"[{i}/{n}] {label}")

    def _on_done(self, msg: str, outputs: list):
        self.progress.setValue(100)
        self.status.setText(msg)
        self._set_busy(False)

    def stop_running(self):
        if self.busy():
            self.worker.cancel_requested = True
            self.status.setText("Đang dừng sau file hiện tại…")

    # ---------- lưu và khôi phục ----------

    def _save(self):
        data = {name: _read(w) for name, w in self.fields.items()}
        data["_out"] = {"folder": self.output.folder.text(), "overwrite": self.output.overwrite.isChecked(),
                        "compress": self.output.compress.isChecked(), "keep_bm": self.output.keep_bm.isChecked(),
                        "version": self.output.version.currentData()}
        data["_files"] = [str(f) for f in self.files_box.files()]
        self.settings.setdefault("qt_pdf", {})[self.key] = data
        L.save_settings(self.settings)

    def _restore(self):
        saved = self.settings.get("qt_pdf", {}).get(self.key, {})
        for name, w in self.fields.items():
            if name in saved:
                _write(w, saved[name])
        out = saved.get("_out", {})
        if out:
            self.output.folder.setText(out.get("folder", ""))
            self.output.overwrite.setChecked(out.get("overwrite", False))
            self.output.compress.setChecked(out.get("compress", True))
            self.output.keep_bm.setChecked(out.get("keep_bm", True))
            _write(self.output.version, out.get("version", "1.5"))
        existing = [Path(p) for p in saved.get("_files", []) if Path(p).is_file()]
        if existing:
            self.files_box.add_paths([str(p) for p in existing])

# ---------- mục 2: Tách PDF ----------

class SplitSection(PdfSection):
    def build_tabs(self):
        ext = QWidget()
        g = QVBoxLayout(ext)
        g.addWidget(QLabel("Trang cần lấy (ví dụ 2 hoặc 5-23 hoặc 2,5-7,12-)"))
        g.addWidget(self.field("pages", QLineEdit()))
        self.separate = self.field("separate", QCheckBox("Một file riêng cho mỗi nhóm trang"))
        g.addWidget(self.separate)
        g.addWidget(self.make_run("▶  Trích xuất", self.run_extract))
        g.addStretch(1)
        self.tabs.addTab(ext, "Trích xuất trang")

        spl = QWidget()
        g = QVBoxLayout(spl)
        g.addWidget(QLabel("Kiểu tách"))
        self.split_mode = self.field("split_mode", QComboBox())
        for key, label in L.SPLIT_LABELS.items():
            self.split_mode.addItem(label, key)
        g.addWidget(self.split_mode)
        g.addWidget(QLabel("Số trang mỗi file, hoặc MB tối đa (không dùng với bookmark)"))
        g.addWidget(self.field("split_value", QLineEdit("1")))
        g.addWidget(self.make_run("▶  Tách file", self.run_split))
        g.addStretch(1)
        self.tabs.addTab(spl, "Tách file")

    def run_extract(self):
        files = self.files_box.files()
        spec = self.fields["pages"].text().strip()
        if not files:
            self._problem("Thêm ít nhất một file PDF.")
            return
        if not spec:
            self._problem("Nhập trang cần lấy, ví dụ 2 hoặc 5-23 hoặc 2,5-7,12-.", self.fields["pages"])
            return
        opts, out = self.output.options(self.separate.isChecked()), self.output.out()
        jobs = [(f"Trích xuất {f.name}", (lambda f=f: pe.extract_pages(f, spec, out, opts))) for f in files]
        self.start_jobs(jobs, "trích xuất")

    def run_split(self):
        files = self.files_box.files()
        if not files:
            self._problem("Thêm ít nhất một file PDF.")
            return
        try:
            mode = self.split_mode.currentData()
            value = L.split_value(mode, self.fields["split_value"].text())
        except ValueError as e:
            self._problem(str(e))
            return
        opts, out = self.output.options(), self.output.out()
        jobs = [(f"Tách {f.name}", (lambda f=f: pe.split_pdf(f, mode, value, out, opts))) for f in files]
        self.start_jobs(jobs, "tách")


# ---------- mục 3: Ghép PDF ----------

class MergeSection(PdfSection):
    def build_tabs(self):
        mg = QWidget()
        g = QVBoxLayout(mg)
        g.addWidget(QLabel("Ghép theo đúng thứ tự trong danh sách. Tên file kết quả:"))
        g.addWidget(self.field("merge_name", QLineEdit("ghep")))
        g.addWidget(self.make_run("▶  Ghép file", self.run_merge))
        g.addStretch(1)
        self.tabs.addTab(mg, "Ghép nhiều file")

        iv = QWidget()
        g = QVBoxLayout(iv)
        g.addWidget(QLabel("Lấy lần lượt trang 1 của từng file, rồi trang 2… Cần ít nhất hai file."))
        g.addWidget(QLabel("Tên file kết quả"))
        g.addWidget(self.field("inter_name", QLineEdit("xen_ke")))
        g.addWidget(self.field("reverse", QCheckBox("Đảo thứ tự file thứ hai (scan mặt sau theo chiều ngược)")))
        g.addWidget(self.make_run("▶  Ghép xen kẽ", self.run_interleave))
        g.addStretch(1)
        self.tabs.addTab(iv, "Ghép xen kẽ")

        rp = QWidget()
        g = QVBoxLayout(rp)
        g.addWidget(QLabel("File chính"))
        self.main_cb = QComboBox()
        g.addWidget(self.main_cb)
        g.addWidget(QLabel("File chứa trang chèn"))
        self.ins_cb = QComboBox()
        g.addWidget(self.ins_cb)
        g.addWidget(QLabel("Số trang chèn"))
        g.addWidget(self.field("insert_page", QLineEdit("1")))
        g.addWidget(self.field("insert_before", QCheckBox("Chèn trước mỗi trang thay vì sau")))
        g.addWidget(QLabel("Tên file kết quả"))
        g.addWidget(self.field("rep_name", QLineEdit("chen_trang")))
        g.addWidget(self.make_run("▶  Chèn trang", self.run_insert))
        g.addStretch(1)
        self.tabs.addTab(rp, "Chèn trang lặp lại")

    def on_files_changed(self):
        """Giữ lựa chọn file trong hai ô chèn trang theo đường dẫn khi danh sách đổi thứ tự hoặc bị bỏ bớt."""
        files = self.files_box.files()
        for cb in (self.main_cb, self.ins_cb):
            want = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            for i, f in enumerate(files):
                cb.addItem(f"{i + 1}. {f.name}", str(f))
            idx = cb.findData(want) if want and Path(want) in files else -1
            cb.setCurrentIndex(idx)
            cb.blockSignals(False)

    @staticmethod
    def _combo_path(cb: QComboBox) -> Path | None:
        data = cb.currentData()
        return Path(data) if data else None

    def _need(self, n: int, title: str) -> bool:
        if len(self.files_box.files()) < n:
            self._problem(f"Thêm ít nhất {n} file PDF.")
            return False
        return True

    def run_merge(self):
        if not self._need(2, "Ghép file"):
            return
        name = L.name_or(self.fields["merge_name"].text(), "ghep")
        jobs = [("Ghép các file", lambda: pe.merge_pdfs(self.files_box.files(), name, self.output.out(), self.output.options()))]
        self.start_jobs(jobs, "ghép file")

    def run_interleave(self):
        if not self._need(2, "Ghép xen kẽ"):
            return
        name = L.name_or(self.fields["inter_name"].text(), "xen_ke")
        files, rev, out, opts = self.files_box.files(), self.fields["reverse"].isChecked(), self.output.out(), self.output.options()
        jobs = [("Ghép xen kẽ", lambda: pe.interleave_pdfs(files, name, out, opts, rev))]
        self.start_jobs(jobs, "ghép xen kẽ")

    def run_insert(self):
        if not self._need(2, "Chèn trang lặp lại"):
            return
        main, ins = self._combo_path(self.main_cb), self._combo_path(self.ins_cb)
        if main is None or ins is None:
            self._problem("Chọn file chính và file chứa trang chèn.", self.main_cb if main is None else self.ins_cb)
            return
        try:
            page = int(self.fields["insert_page"].text().strip() or "1")
        except ValueError:
            self._problem("Số trang chèn phải là số.", self.fields["insert_page"])
            return
        name = L.name_or(self.fields["rep_name"].text(), "chen_trang")
        before = self.fields["insert_before"].isChecked()
        out, opts = self.output.out(), self.output.options()
        jobs = [("Chèn trang", lambda: pe.insert_repeated(main, ins, name, out, opts, page, before))]
        self.start_jobs(jobs, "chèn trang")


# ---------- mục 4: Công cụ khác ----------

class ToolsSection(PdfSection):
    def build_tabs(self):
        rot = QWidget()
        g = QVBoxLayout(rot)
        g.addWidget(QLabel("Góc xoay (theo chiều kim đồng hồ)"))
        self.angle = self.field("angle", QComboBox())
        for a in L.ROTATE_ANGLES:
            self.angle.addItem(str(a), a)
        g.addWidget(self.angle)
        g.addWidget(QLabel("Trang cần xoay (ví dụ 2,5-7 · để trống = tất cả trang)"))
        g.addWidget(self.field("rot_pages", QLineEdit()))
        g.addWidget(self.make_run("▶  Xoay trang", self.run_rotate))
        g.addStretch(1)
        self.tabs.addTab(rot, "Xoay trang")

        comp = QWidget()
        g = QVBoxLayout(comp)
        self.img = self.field("img", QCheckBox("Nén lại ảnh (JPEG)"))
        self.img.setChecked(True)
        g.addWidget(self.img)
        g.addWidget(QLabel("Chất lượng ảnh 1–95; thấp hơn = nhỏ hơn, ảnh kém nét hơn. Ảnh trong suốt giữ nguyên."))
        g.addWidget(self.field("quality", QLineEdit("75")))
        g.addWidget(self.make_run("▶  Nén file", self.run_compress))
        g.addStretch(1)
        self.tabs.addTab(comp, "Nén PDF")

        watch = QWidget()
        g = QVBoxLayout(watch)
        g.addWidget(QLabel("Thư mục theo dõi (file PDF mới được xử lý tự động; file có sẵn cũng được xử lý)"))
        row = QHBoxLayout()
        self.watch_folder_edit = self.field("watch_folder", QLineEdit())
        btn_w = QPushButton("Chọn…")
        btn_w.clicked.connect(self._pick_watch)
        row.addWidget(self.watch_folder_edit, 1)
        row.addWidget(btn_w)
        g.addLayout(row)
        self.watch_op = self.field("watch_op", QComboBox())
        self.watch_op.addItem("Xoay trang (theo thẻ Xoay trang)", "rotate")
        self.watch_op.addItem("Nén file (theo thẻ Nén PDF)", "compress")
        g.addWidget(self.watch_op)
        g.addWidget(QLabel(f"Kết quả vào thư mục con “{pdf_ops.OUT_SUBDIR}”."))
        self.watch_btn = QPushButton("▶  Bắt đầu theo dõi")
        self.watch_btn.clicked.connect(self.toggle_watch)
        g.addWidget(self.watch_btn)
        self.watch_status = QLabel("Chưa theo dõi thư mục nào.")
        self.watch_status.setWordWrap(True)
        g.addWidget(self.watch_status)
        g.addStretch(1)
        self.tabs.addTab(watch, "Tự động theo thư mục")
        self.watcher: WatchWorker | None = None

    def _pick_watch(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục theo dõi")
        if d:
            self.watch_folder_edit.setText(d)

    def run_rotate(self):
        files = self.files_box.files()
        if not files:
            self._problem("Thêm ít nhất một file PDF.")
            return
        angle, pages = self.angle.currentData(), self.fields["rot_pages"].text().strip()
        out, opts = self.output.out(), self.output.options()
        jobs = [(f"Xoay {f.name}", (lambda f=f: pdf_ops.rotate_pdf(f, angle, pages, out, opts))) for f in files]
        self.start_jobs(jobs, "xoay trang")

    def _quality(self) -> int | None:
        return L.image_quality(self.img.isChecked(), self.fields["quality"].text())

    def run_compress(self):
        files = self.files_box.files()
        if not files:
            self._problem("Thêm ít nhất một file PDF.")
            return
        try:
            quality = self._quality()
        except ValueError as e:
            self._problem(str(e))
            return
        out, opts = self.output.out(), self.output.options()
        jobs = [(f"Nén {f.name}", (lambda f=f: pdf_ops.compress_pdf(f, quality, out, opts))) for f in files]
        self.start_jobs(jobs, "nén")

    def toggle_watch(self):
        if self.watcher is not None:   # đang chạy: dừng
            self.watcher.stop_event.set()
            self.watcher.wait(10000)
            self.watcher = None
            self.watch_btn.setText("▶  Bắt đầu theo dõi")
            self.watch_status.setText("Đã dừng theo dõi.")
            self._set_busy(False)
            return
        folder = Path(self.watch_folder_edit.text().strip())
        if not folder.is_dir():
            self._problem("Chọn một thư mục có sẵn.", self.watch_folder_edit)
            return
        opts = self.output.options()
        try:
            if self.watch_op.currentData() == "rotate":
                angle, pages = self.angle.currentData(), self.fields["rot_pages"].text().strip()
                process = lambda f: pdf_ops.rotate_pdf(f, angle, pages, pdf_ops.output_dir(folder), opts)
            else:
                quality = self._quality()
                process = lambda f: pdf_ops.compress_pdf(f, quality, pdf_ops.output_dir(folder), opts)
        except ValueError as e:
            self._problem(str(e))
            return
        self._save()
        self.watcher = WatchWorker(folder, process)
        self.watcher.report.connect(self.watch_status.setText)
        self.watch_btn.setText("■  Dừng theo dõi")
        self.watch_status.setText(f"Đang theo dõi {folder}…")
        self._set_busy(True)
        self.watcher.start()

    def _set_busy(self, busy: bool):
        super()._set_busy(busy)
        self.watch_btn.setEnabled(True)   # nút dừng theo dõi luôn bấm được

    def busy(self) -> bool:
        return super().busy() or self.watcher is not None
