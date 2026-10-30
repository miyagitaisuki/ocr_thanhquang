"""Kết quả và xem trước, mô hình AI, menu Hiển thị của giao diện chính.

- ResultsBox: bảng kết quả, mở file Word/thư mục/file so sánh, Tìm nhanh, xem trước ảnh trang và chữ.
- ModelBox: tải PaddleOCR/VietOCR, Chandra (có tick điều khoản), cài gói GPU; chạy nền, có tiến trình.
- apply_view / build_view_menu: giao diện sáng/tối, độ trong suốt, cỡ chữ; áp dụng ngay, không cần khởi động lại.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QImage, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import gpupack
from . import ui_logic as L

log = logging.getLogger("ocrnhat.gui")

ALPHA_LEVELS = (100, 95, 90)   # dưới 90% chữ mờ, khó đọc: không cho chọn
FONT_SIZES = {"Nhỏ": 9, "Vừa": 10, "Lớn": 12, "Rất lớn": 14}
THEMES = ("sáng", "tối")


# ---------- ảnh trang, vùng cắt và rà soát ----------

SCAN_DPI = 200   # phải khớp pipeline.iter_pages: vùng cắt tính theo pixel ở 200 dpi (PDF) hoặc ảnh gốc


@functools.lru_cache(maxsize=8)
def _source_bytes(src: str, pno: int, dpi: int) -> tuple[bytes, int, int] | None:
    """Trang nguồn ở đúng hệ tọa độ của pipeline (PDF render ở SCAN_DPI, ảnh giữ nguyên). Có cache nhỏ."""
    try:
        if src.lower().endswith(".pdf"):
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(src)
            if pno > len(doc):
                return None
            pil = doc[pno - 1].render(scale=dpi / 72).to_pil().convert("RGB")
        else:
            from PIL import Image
            pil = Image.open(src).convert("RGB")
        return pil.tobytes("raw", "RGB"), pil.width, pil.height
    except Exception:
        log.exception("Không đọc được trang %s", src)
        return None


def source_image(src: Path, pno: int, dpi: int = SCAN_DPI) -> tuple[QImage, int, int] | None:
    got = _source_bytes(str(src), pno, dpi)
    if got is None:
        return None
    data, w, h = got
    return QImage(data, w, h, 3 * w, QImage.Format.Format_RGB888).copy(), w, h


def to_source(x: float, y: float, crop, upscale: float) -> tuple[float, float]:
    """Tọa độ dòng trong ảnh đã cắt/phóng to (pipeline) -> tọa độ trang nguồn."""
    ox, oy = (crop[0], crop[1]) if crop else (0, 0)
    up = upscale or 1.0
    return ox + x / up, oy + y / up


CORNERS = ("tl", "tr", "bl", "br")


def corner_at(rect: tuple[int, int, int, int], pt: tuple[float, float], tol: float) -> str | None:
    """Tay nắm góc nào nằm trong bán kính tol (đơn vị trang nguồn) quanh điểm pt; None nếu không có."""
    x0, y0, x1, y1 = rect
    corners = {"tl": (x0, y0), "tr": (x1, y0), "bl": (x0, y1), "br": (x1, y1)}
    best, hit = None, None
    for name, (cx, cy) in corners.items():
        d = max(abs(pt[0] - cx), abs(pt[1] - cy))
        if d <= tol and (best is None or d < best):
            best, hit = d, name
    return hit


def resize_rect(rect: tuple[int, int, int, int], corner: str, pt: tuple[float, float],
                full_w: int, full_h: int) -> tuple[int, int, int, int]:
    """Kéo một góc tới pt; cạnh đối diện giữ nguyên. Kết quả kẹp trong trang; quá nhỏ thì giữ khung cũ."""
    x0, y0, x1, y1 = rect
    if "l" in corner:
        x0 = pt[0]
    else:
        x1 = pt[0]
    if "t" in corner:
        y0 = pt[1]
    else:
        y1 = pt[1]
    return drag_rect((x0, y0), (x1, y1), full_w, full_h) or rect


def drag_rect(p0: tuple[float, float], p1: tuple[float, float], full_w: int, full_h: int) -> tuple[int, int, int, int] | None:
    """Khung kéo chuột (tọa độ trang nguồn) -> (x0, y0, x1, y1) đã kẹp trong trang; None nếu quá nhỏ."""
    x0, x1 = sorted((min(max(p0[0], 0), full_w), min(max(p1[0], 0), full_w)))
    y0, y1 = sorted((min(max(p0[1], 0), full_h), min(max(p1[1], 0), full_h)))
    rect = (int(x0), int(y0), int(x1), int(y1))
    return rect if rect[2] - rect[0] >= 4 and rect[3] - rect[1] >= 4 else None


class PageView(QWidget):
    """Ảnh trang nguồn. mode 'crop': chọn một hoặc nhiều vùng đọc (kéo chuột; giữ Shift để thêm vùng; kéo tay nắm góc để
    đổi kích thước). mode 'view': vẽ khung các dòng, dòng độ tin cậy thấp tô đỏ, bấm khung để chọn dòng."""
    cropsChanged = Signal(object)   # danh sách vùng (x0, y0, x1, y1) theo trang nguồn
    lineClicked = Signal(int)
    MAX_REGIONS = 10

    def __init__(self, mode: str = "view", min_size: tuple[int, int] = (360, 300)):
        super().__init__()
        self.mode = mode
        self.image: QImage | None = None
        self.full = (0, 0)
        self.lines: list[tuple[float, float, float, float, float, str]] = []   # hệ trang nguồn
        self.thr = 0.8
        self.selected = -1
        self.crops: list[tuple[int, int, int, int]] = []
        self._drag: tuple[tuple[float, float], tuple[float, float]] | None = None
        self._drag_append = False          # kéo với Shift: thêm vùng; không Shift: thay các vùng cũ
        self._handle: tuple[int, str] | None = None   # (chỉ số vùng, góc) đang kéo tay nắm
        self.setMinimumSize(*min_size)
        self.label = ""

    def set_image(self, img: QImage | None, w: int = 0, h: int = 0):
        self.image, self.full = img, (w, h)
        self.update()

    def set_lines(self, lines, thr: float):
        self.lines, self.thr, self.selected = lines, thr, -1
        self.update()

    def select(self, idx: int):
        self.selected = idx
        self.update()

    def set_crops(self, crops):
        self.crops = [tuple(c) for c in (crops or [])][: self.MAX_REGIONS]
        self.update()

    def _layout(self) -> tuple[float, float, float]:
        """(lề trái, lề trên, tỷ lệ hiển thị) để ảnh vừa khung và căn giữa."""
        w, h = self.full
        if not w or not h:
            return 0.0, 0.0, 1.0
        sc = min(self.width() / w, self.height() / h)
        return (self.width() - w * sc) / 2, (self.height() - h * sc) / 2, sc

    def _to_page(self, pos) -> tuple[float, float]:
        ox, oy, sc = self._layout()
        return (pos.x() - ox) / sc, (pos.y() - oy) / sc

    def paintEvent(self, _e):
        from PySide6.QtGui import QPainter, QPen, QColor, QBrush
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        if self.mode == "crop":   # nền lưới tối như khung xem trước của thiết kế
            p.fillRect(self.rect(), QColor("#2B313B"))
            p.setPen(QPen(QColor("#3A4250"), 1))
            for gx in range(0, self.width(), 24):
                p.drawLine(gx, 0, gx, self.height())
            for gy in range(0, self.height(), 24):
                p.drawLine(0, gy, self.width(), gy)
        if self.image is None:
            p.setPen(QColor("#EEEEEE"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Chưa có ảnh trang để xem.")
            p.end()
            return
        ox, oy, sc = self._layout()
        w, h = self.full
        p.drawImage(QRectF(ox, oy, w * sc, h * sc), self.image)
        if self.mode == "view":
            for i, (x0, y0, x1, y1, conf, _t) in enumerate(self.lines):
                low = conf < self.thr
                if not low and i != self.selected:
                    continue
                color = QColor("#FF5A4D") if low else QColor("#4C8DFF")   # sáng đủ nổi trên ảnh trang; dòng nghi ngờ thêm nét đứt
                pen = QPen(color, 3 if i == self.selected else 2)
                if low:
                    pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawRect(QRectF(ox + x0 * sc, oy + y0 * sc, (x1 - x0) * sc, (y1 - y0) * sc))
        if self.mode == "crop":
            rects = list(self.crops)
            if self._drag is not None:
                r = drag_rect(*self._drag, w, h)
                if r:
                    rects = rects + [r] if self._drag_append else [r]
            for n, (x0, y0, x1, y1) in enumerate(rects, 1):
                box = QRectF(ox + x0 * sc, oy + y0 * sc, (x1 - x0) * sc, (y1 - y0) * sc)
                p.setPen(QPen(QColor("#F2A03D"), 3))
                p.setBrush(QBrush(QColor(242, 160, 61, 40)))
                p.drawRect(box)
                p.setPen(QPen(QColor("#FFFFFF"), 1))
                p.setBrush(QBrush(QColor("#F2A03D")))
                for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):   # bốn tay nắm góc
                    p.drawEllipse(QRectF(ox + cx * sc - 5, oy + cy * sc - 5, 10, 10))
                chip = f"Vùng chọn OCR {n:02d} ({x0}, {y0}, {x1}, {y1})"
                fm = p.fontMetrics()
                p.setPen(QPen(QColor("#F2A03D"), 1))
                p.drawRect(QRectF(box.x(), box.y() - 20, fm.horizontalAdvance(chip) + 14, 18))
                p.setPen(QPen(QColor("#FFFFFF")))
                p.drawText(QRectF(box.x() + 7, box.y() - 20, 2000, 18), Qt.AlignmentFlag.AlignVCenter, chip)
        p.end()

    def mousePressEvent(self, e):
        if self.image is None:
            return
        pt = self._to_page(e.position())
        if self.mode == "crop":
            _ox, _oy, sc = self._layout()
            tol = 8 / sc   # tay nắm bắt được trong 8 px trên màn hình
            for i in reversed(range(len(self.crops))):   # vùng vẽ sau nằm trên cùng
                corner = corner_at(self.crops[i], pt, tol)
                if corner:
                    self._handle = (i, corner)
                    self.update()
                    return
            self._drag = (pt, pt)
            self._drag_append = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.update()
        else:
            hit = -1
            best = None
            for i, (x0, y0, x1, y1, _c, _t) in enumerate(self.lines):
                if x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1:
                    area = (x1 - x0) * (y1 - y0)
                    if best is None or area < best:
                        best, hit = area, i
            self.selected = hit
            self.update()
            self.lineClicked.emit(hit)

    def mouseMoveEvent(self, e):
        if self.mode != "crop":
            return
        if self._handle is not None:
            i, corner = self._handle
            self.crops[i] = resize_rect(self.crops[i], corner, self._to_page(e.position()), *self.full)
            self.cropsChanged.emit(list(self.crops))
            self.update()
        elif self._drag is not None:
            self._drag = (self._drag[0], self._to_page(e.position()))
            self.update()

    def mouseReleaseEvent(self, e):
        if self.mode != "crop":
            return
        if self._handle is not None:
            self._handle = None
            self.update()
            return
        if self._drag is not None:
            rect = drag_rect(self._drag[0], self._to_page(e.position()), *self.full)
            self._drag = None
            if rect:
                if self._drag_append and len(self.crops) < self.MAX_REGIONS:
                    self.crops = self.crops + [rect]
                elif not self._drag_append:
                    self.crops = [rect]
                self.cropsChanged.emit(list(self.crops))
            self.update()


class ResultsBox(QGroupBox):
    """Kết quả các file vừa OCR: bảng, nút mở, Tìm nhanh, rà soát từng trang (ảnh có khung dòng + danh sách dòng)."""

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
        self.page.setAccessibleName("Số trang xem trước")
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.page_info = QLabel("")
        self.only_low = QCheckBox("Chỉ dòng nghi ngờ")
        nav = QHBoxLayout()
        nav.addWidget(QLabel("Trang:"))
        for w in (self.btn_prev, self.page, self.btn_next, self.page_info):
            nav.addWidget(w)
        nav.addStretch(1)
        nav.addWidget(self.only_low)
        self.view = PageView(mode="view", min_size=(300, 300))
        self.lines = QListWidget()
        self.lines.setMinimumWidth(260)
        self.lines.setToolTip("Bấm một dòng để xem vị trí trên ảnh. Dòng đỏ là độ tin cậy thấp.")
        preview = QVBoxLayout()   # xếp dọc: ảnh trang trên, danh sách dòng dưới (không chiếm bề ngang)
        preview.addWidget(self.view, 1)
        preview.addWidget(self.lines, 1)
        root = QVBoxLayout(self)
        root.addWidget(self.table)
        root.addLayout(bar)
        root.addLayout(nav)
        root.addLayout(preview)
        self._row_to_line: list[int] = []
        self.set_enabled_actions(False)
        self.table.itemSelectionChanged.connect(self.refresh_preview)
        self.page.valueChanged.connect(lambda _: self.refresh_preview())
        self.only_low.toggled.connect(lambda _: self._fill_lines())
        self.btn_prev.clicked.connect(lambda: self.page.setValue(max(1, self.page.value() - 1)))
        self.btn_next.clicked.connect(lambda: self.page.setValue(self.page.value() + 1))
        self.btn_docx.clicked.connect(lambda: self._open("docx"))
        self.btn_dir.clicked.connect(lambda: self._open("dir"))
        self.btn_review.clicked.connect(lambda: self._open("review"))
        self.btn_find.clicked.connect(self.find_output)
        self.lines.currentRowChanged.connect(self._on_row)
        self.view.lineClicked.connect(self._on_view_line)
        self._line_data: list = []

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
            self.view.set_image(None)
            self.lines.clear()
            self.page_info.setText("")
            return
        src, r = item
        got = source_image(src, pno, r.get("dpi", SCAN_DPI))
        if got is None:
            self.view.set_image(None)
        else:
            self.view.set_image(got[0], got[1], got[2])
        entries = next((lines for n, lines in r.get("page_lines", []) if n == pno), None)
        thr = r.get("conf_threshold", 0.8)
        if entries is None:
            self._line_data = []
            self.view.set_lines([], thr)
        else:
            self._line_data = [(x, y, x1, y1, conf, text) for x, y, x1, y1, conf, text in entries]   # đã ở hệ trang nguồn
            self.view.set_lines(self._line_data, thr)
        self._fill_lines()
        self.view.thr = thr
        if src.suffix.lower() == ".pdf":
            try:
                import pypdfium2 as pdfium
                self.page_info.setText(f"/ {len(pdfium.PdfDocument(str(src)))} trang")
            except Exception:
                self.page_info.setText("")
        else:
            self.page_info.setText("1 ảnh")

    def _fill_lines(self):
        """Danh sách dòng của trang; dòng đỏ là độ tin cậy thấp. Có thể lọc chỉ hiện dòng nghi ngờ."""
        thr = self.view.thr
        self.lines.blockSignals(True)
        self.lines.clear()
        self._row_to_line = []
        for i, (_x0, _y0, _x1, _y1, conf, text) in enumerate(self._line_data):
            low = conf < thr
            if self.only_low.isChecked() and not low:
                continue
            item = QListWidgetItem(f"{'⚠ ' if low else '   '}{conf:.2f}  {text}")   # dấu ⚠: không chỉ dựa vào màu
            if low:
                dark = self.lines.palette().base().color().lightness() < 128
                item.setForeground(QColor("#FF8A80" if dark else "#B3261E"))
            self.lines.addItem(item)
            self._row_to_line.append(i)
        if not self._line_data:
            self.lines.addItem(QListWidgetItem("Không có dữ liệu dòng cho trang này."))
        self.lines.blockSignals(False)

    def _on_row(self, row: int):
        if 0 <= row < len(self._row_to_line):
            self.view.select(self._row_to_line[row])

    def _on_view_line(self, idx: int):
        if idx in self._row_to_line:
            self.lines.blockSignals(True)
            self.lines.setCurrentRow(self._row_to_line.index(idx))
            self.lines.blockSignals(False)


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
            ("paddle", "Tải PaddleOCR (tiếng Anh, Trung)",
             lambda rep: "\n".join(mdl.download_paddle(progress=lambda i, n, name, frac: rep(
                 f"Đang tải {name} (tệp {min(i + 1, n)}/{n})", (i + frac) / max(1, n)))),
             lambda: PaddleEngine.is_available()[0]),
            ("vi", "Tải VietOCR (tiếng Việt)",
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
        self.chandra_btn = QPushButton("Tải Chandra (vài GB, một lần)")
        self.chandra_btn.clicked.connect(self._chandra)
        self.chandra_box = QWidget()
        cb = QVBoxLayout(self.chandra_box)
        cb.setContentsMargins(0, 0, 0, 0)
        cb.addWidget(self.license)
        cb.addWidget(self.chandra_btn)
        self.chandra_box.setVisible(chandra_available)
        self.chandra_on = chandra_available   # cờ riêng: isVisible() còn phụ thuộc cửa sổ cha đã hiện chưa
        root.addWidget(self.chandra_box)

        self.pack_btn = QPushButton("Cài tăng tốc GPU (vài GB)")
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
    from .gui_style import stylesheet
    qss = stylesheet(theme, font_pt)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if theme == "tối" else app.style().standardPalette())
    if app.styleSheet() != qss:   # đặt lại QSS tốn ~0,5 s (vẽ lại mọi widget): chỉ làm khi đổi giao diện
        app.setStyleSheet(qss)
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
