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

from ocrnhat import gui, ui_logic as L  # noqa: E402
from ocrnhat.gui_extra import ModelBox, ResultsBox, apply_view, drag_rect, source_image, to_source  # noqa: E402


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


def test_ket_qua_hien_bang_va_rà_soat_trang_pdf(tmp_path):
    src = _pdf(tmp_path / "sach.pdf", 2)
    docx = tmp_path / "OCR_sach.docx"
    docx.write_bytes(b"")
    box = ResultsBox()
    lines = [(10, 10, 100, 30, 0.5, "日本語"), (10, 40, 100, 60, 0.95, "tốt")]
    box.set_results([(src, {"docx": str(docx), "pages": 2, "tables": 0, "page_lines": [(1, lines)],
                            "crop": None, "upscale": 1.0, "conf_threshold": 0.8})])
    assert box.table.rowCount() == 1 and box.table.item(0, 3).text() == "OCR_sach.docx"
    assert box.btn_docx.isEnabled()
    assert box.view.image is not None                  # ảnh trang PDF đã nạp
    assert box.view.lines and len(box.view.lines) == 2  # khung các dòng
    assert box.lines.count() == 2 and "日本語" in box.lines.item(0).text()
    box.only_low.setChecked(True)                      # chỉ dòng nghi ngờ
    assert box.lines.count() == 1 and "日本語" in box.lines.item(0).text()


def test_chon_dong_tren_danh_sach_danh_dau_tren_anh(tmp_path):
    src = _pdf(tmp_path / "a.pdf", 1)
    docx = tmp_path / "a.docx"
    docx.write_bytes(b"")
    box = ResultsBox()
    box.set_results([(src, {"docx": str(docx), "pages": 1, "tables": 0, "page_lines": [(1, [
        (10, 10, 100, 30, 0.2, "a"), (10, 40, 100, 60, 0.9, "b")])], "upscale": 1.0, "conf_threshold": 0.8})])
    box.lines.setCurrentRow(1)
    assert box.view.selected == 1


def test_dong_theo_vung_cat_va_phong_to_quy_ve_trang_goc():
    # cắt từ (100, 200) rồi phóng to 2 lần: dòng ở (20, 40) trong ảnh đã xử lý nằm ở (110, 220) trên trang
    assert to_source(20, 40, (100, 200, 500, 600), 2.0) == (110.0, 220.0)
    assert to_source(20, 40, None, 1.0) == (20.0, 40.0)


def test_khung_keo_chuot_kep_trong_trang_va_bo_khung_nho():
    assert drag_rect((30, 40), (10, 20), 100, 100) == (10, 20, 30, 40)     # kéo ngược chiều vẫn đúng
    assert drag_rect((-5, 50), (200, 90), 100, 100) == (0, 50, 100, 90)    # kẹp trong trang
    assert drag_rect((10, 10), (12, 12), 100, 100) is None                 # quá nhỏ, bỏ qua


def test_anh_trang_ngoai_so_trang_tra_none(tmp_path):
    src = _pdf(tmp_path / "a.pdf", 1)
    assert source_image(src, 5) is None
    got = source_image(src, 1)
    assert got is not None and abs(got[1] - 300 * 200 / 72) <= 1   # render ở 200 dpi như pipeline (pdfium làm tròn)


def test_ket_qua_rong_tat_nut(tmp_path):
    box = ResultsBox()
    box.set_results([])
    assert not box.btn_docx.isEnabled() and not box.btn_find.isEnabled()


def test_vung_cat_trong_o_nhap_khop_khung_tren_anh(tmp_path, store):
    src = _pdf(tmp_path / "a.pdf", 1)
    w = gui.MainWindow()
    w.ocr._add([src])
    w.ocr.crop.setText("10,20,300,400")
    assert w.ocr.crop_view.crops == [(10, 20, 300, 400)]   # ô nhập vẽ thành khung
    w.ocr.crop_view.cropsChanged.emit([(5, 6, 50, 60)])     # kéo chuột ghi ngược vào ô nhập
    assert w.ocr.crop.text() == "5,6,50,60"
    assert w.ocr.options()["crop"] == (5, 6, 50, 60)
    w.close()


def test_mo_hinh_ai_dung_trang_thai_san_co(tmp_path):
    box = ModelBox()
    assert "PaddleOCR" in box.status.text() and "VietOCR" in box.status.text()


def test_hien_thi_ap_dung_ngay_va_luu(store):
    w = gui.MainWindow()
    w.settings.setdefault("qt_view", {})
    from ocrnhat import gui_extra as ex
    ex._set(w, QApplication.instance(), w.settings, w._save_view, theme="tối", font_pt=12)
    assert w.windowOpacity() == pytest.approx(1.0)   # không còn độ trong suốt
    assert QApplication.instance().font().pointSize() == 12
    assert store["qt_view"]["theme"] == "tối"
    apply_view(QApplication.instance(), "sáng", 10)   # trả lại mặc định cho các test khác
    w.close()


def test_ket_qua_co_trong_ocr_va_tuy_chon_kiem_tra(store):
    w = gui.MainWindow()
    w.ocr.conf.setText("0.6")
    w.ocr.review.setChecked(True)
    opts = w.ocr.options()
    assert opts["conf_threshold"] == 0.6 and opts["review"] is True
    w.close()


def test_tay_nam_goc_nhan_dien_va_doi_kich_thuoc():
    from ocrnhat.gui_extra import corner_at, resize_rect
    rect = (100, 100, 300, 200)
    assert corner_at(rect, (101, 99), tol=4) == "tl"
    assert corner_at(rect, (299, 201), tol=4) == "br"
    assert corner_at(rect, (200, 150), tol=4) is None          # giữa khung không phải tay nắm
    # kéo góc br tới (400, 250): góc tl giữ nguyên
    assert resize_rect(rect, "br", (400, 250), 1000, 1000) == (100, 100, 400, 250)
    # kéo góc tl vượt qua góc br: khung được lật lại, không bị âm
    assert resize_rect(rect, "tl", (350, 250), 1000, 1000) == (300, 200, 350, 250)
    # kéo ra ngoài trang: kẹp trong trang
    assert resize_rect(rect, "tr", (2000, 50), 1000, 1000) == (100, 50, 1000, 200)


def test_anh_trang_theo_dpi_dang_chon(tmp_path):
    src = _pdf(tmp_path / "a.pdf", 1)
    w150, w300 = source_image(src, 1, 150)[1], source_image(src, 1, 300)[1]
    assert abs(w300 - 2 * w150) <= 2          # gấp đôi DPI thì gấp đôi pixel (sai số làm tròn của pdfium)


def test_doi_dpi_nhan_vung_cat_de_giu_dung_phan_trang(store):
    w = gui.MainWindow()
    w.ocr.crop.setText("100,100,200,200")
    w.ocr.dpi.setCurrentIndex(w.ocr.dpi.findData(300))   # 200 -> 300 dpi: nhân 1,5
    assert w.ocr.crop.text() == "150,150,300,300"
    assert w.ocr.options()["dpi"] == 300
    w.close()


def _mouse(kind, x, y, shift=False):
    from PySide6.QtCore import Qt
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    etype = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove,
             "release": QEvent.Type.MouseButtonRelease}[kind]
    return QMouseEvent(etype, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, mods)


def test_chuot_them_vung_bang_shift_va_thay_vung_khi_khong_shift():
    from PySide6.QtGui import QImage
    from ocrnhat.gui_extra import PageView
    pv = PageView(mode="crop", min_size=(300, 300))
    pv.resize(300, 300)
    pv.set_image(QImage(300, 300, QImage.Format.Format_RGB888), 300, 300)
    got = []
    pv.cropsChanged.connect(lambda rs: got.append(list(rs)))
    pv.mousePressEvent(_mouse("press", 10, 10, shift=True))
    pv.mouseMoveEvent(_mouse("move", 60, 60, shift=True))
    pv.mouseReleaseEvent(_mouse("release", 60, 60, shift=True))
    pv.mousePressEvent(_mouse("press", 100, 100, shift=True))
    pv.mouseMoveEvent(_mouse("move", 150, 150, shift=True))
    pv.mouseReleaseEvent(_mouse("release", 150, 150, shift=True))
    assert len(pv.crops) == 2                    # Shift: thêm vùng
    pv.mousePressEvent(_mouse("press", 200, 200))
    pv.mouseMoveEvent(_mouse("move", 250, 250))
    pv.mouseReleaseEvent(_mouse("release", 250, 250))
    assert pv.crops == [(200, 200, 250, 250)]     # không Shift: thay mọi vùng cũ
    assert got and len(got[-1]) == 1


def test_o_nhap_nhieu_vung_khop_khung(store):
    w = gui.MainWindow()
    w.ocr.crop.setText("10,10,100,100;150,150,250,250")
    assert w.ocr.crop_view.crops == [(10, 10, 100, 100), (150, 150, 250, 250)]
    assert w.ocr.options()["crop"] == [(10, 10, 100, 100), (150, 150, 250, 250)]
    w.close()
