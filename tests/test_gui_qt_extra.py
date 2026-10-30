"""Test kết quả và xem trước, mô hình AI, menu Hiển thị của bản Qt (bước 4); bỏ qua nếu thiếu PySide6."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
except ImportError:
    pytest.skip("không nạp được Qt (thiếu thư viện hệ thống)", allow_module_level=True)

from pypdf import PdfWriter  # noqa: E402

from ocrnhat import gui_qt, ui_logic as L  # noqa: E402
from ocrnhat.gui_qt_extra import ModelBox, ResultsBox, apply_view, render_page  # noqa: E402


def _pdf(path, pages=2):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=300, height=300)
    with open(path, "wb") as fh:
        w.write(fh)
    return path


@pytest.fixture
def store(monkeypatch):
    data = {}
    monkeypatch.setattr(L, "save_settings", lambda d: data.update(d))
    monkeypatch.setattr(L, "load_settings", lambda: dict(data))
    return data


def test_ket_qua_hien_bang_va_xem_truoc_trang_pdf(tmp_path):
    src = _pdf(tmp_path / "sach.pdf", 2)
    docx = tmp_path / "OCR_sach.docx"
    docx.write_bytes(b"")
    (tmp_path / "OCR_sach.txt").write_text("=== Trang 1 ===\n日本語のテキスト\n=== Trang 2 ===\nTrang hai\n", encoding="utf-8")
    box = ResultsBox()
    box.set_results([(src, {"docx": str(docx), "pages": 2, "tables": 0})])
    assert box.table.rowCount() == 1 and box.table.item(0, 3).text() == "OCR_sach.docx"
    assert box.btn_docx.isEnabled()
    assert not box.image.pixmap().isNull()          # ảnh trang PDF được vẽ
    assert "日本語" in box.text.toPlainText()


def test_render_page_ngoai_so_trang_tra_none(tmp_path):
    src = _pdf(tmp_path / "a.pdf", 1)
    assert render_page(src, 5, (300, 300)) is None


def test_ket_qua_rong_tat_nut(tmp_path):
    box = ResultsBox()
    box.set_results([])
    assert not box.btn_docx.isEnabled() and not box.btn_find.isEnabled()


def test_mo_hinh_ai_dung_trang_thai_san_co(tmp_path):
    box = ModelBox(chandra_available=False)
    assert "Chandra" not in box.status.text()
    assert "PaddleOCR" in box.status.text() and "VietOCR" in box.status.text()


def test_chandra_chi_hien_khi_co_engine(tmp_path):
    box = ModelBox(chandra_available=True)
    assert "Chandra" in box.status.text()


def test_hien_thi_ap_dung_ngay_va_luu(store):
    w = gui_qt.MainWindow()
    w.settings.setdefault("qt_view", {})
    from ocrnhat import gui_qt_extra as ex
    ex._set(w, QApplication.instance(), w.settings, w._save_view, theme="tối", alpha=90, font_pt=12)
    assert w.windowOpacity() == pytest.approx(0.9, abs=0.01)
    assert QApplication.instance().font().pointSize() == 12
    assert store["qt_view"]["theme"] == "tối"
    apply_view(QApplication.instance(), "sáng", 10, 100, w)   # trả lại mặc định cho các test khác
    w.close()


def test_ket_qua_co_trong_ocr_va_tuy_chon_kiem_tra(store):
    w = gui_qt.MainWindow()
    w.ocr.conf.setText("0.6")
    w.ocr.review.setChecked(True)
    opts = w.ocr.options()
    assert opts["conf_threshold"] == 0.6 and opts["review"] is True
    w.close()
