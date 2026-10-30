"""Test giao diện PySide6 (bước 2) ở chế độ offscreen; bỏ qua nếu chưa cài PySide6 hoặc thiếu thư viện hệ thống."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
except ImportError:   # thiếu libEGL và thư viện Qt khác trên máy này
    pytest.skip("không nạp được Qt (thiếu thư viện hệ thống)", allow_module_level=True)

from ocrnhat import gui, ui_logic as L  # noqa: E402


@pytest.fixture
def settings_store(monkeypatch):
    """Không ghi settings.json thật: lưu trong bộ nhớ."""
    store = {}
    monkeypatch.setattr(L, "save_settings", lambda data: store.update(data))
    monkeypatch.setattr(L, "load_settings", lambda: dict(store))
    return store


@pytest.fixture
def window(settings_store):
    w = gui.MainWindow()
    yield w
    w.ocr._save = lambda: None   # đã kiểm tra ở test khác; tránh ghi khi đóng
    w.close()


def test_thanh_ben_co_bon_muc_dung_thu_tu(window):
    names = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert names == ["OCR", "Tách PDF", "Ghép PDF", "Công cụ khác"]
    assert window.stack.count() == 4


def test_chon_muc_doi_trang(window):
    window.nav.setCurrentRow(2)
    assert window.stack.currentIndex() == 2


def test_danh_sach_ngon_ngu_theo_cong_cu(window):
    ocr = window.ocr
    ocr.engine.setCurrentIndex(ocr.engine.findData("paddle"))
    assert [ocr.lang.itemData(i) for i in range(ocr.lang.count())] == ["en", "zh"]
    ocr.engine.setCurrentIndex(ocr.engine.findData("ndlocr"))
    assert [ocr.lang.itemData(i) for i in range(ocr.lang.count())] == ["ja"]


def test_tuy_chon_mac_dinh_hop_le(window):
    opts = window.ocr.options()
    assert opts["lang"] == "ja" and opts["merge_pages"] is True and opts["kana_reader"] == ""


def test_tuy_chon_sai_bao_loi(window):
    window.ocr.upscale.setText("abc")
    with pytest.raises(ValueError, match="Phóng to"):
        window.ocr.options()


def test_luu_va_khoi_phuc_tuy_chon(settings_store, monkeypatch):
    w1 = gui.MainWindow()
    w1.ocr.upscale.setText("2")
    w1.ocr.ruby.setChecked(True)
    w1.ocr.engine.setCurrentIndex(w1.ocr.engine.findData("paddle"))
    w1.ocr._save()
    w1.close()
    w2 = gui.MainWindow()
    assert w2.ocr.upscale.text() == "2"
    assert w2.ocr.ruby.isChecked() is True
    assert w2.ocr.engine.currentData() == "paddle"
    w2.close()


def test_worker_xu_ly_tung_file_va_ghi_loi_rieng(window, monkeypatch, tmp_path):
    """Một file lỗi không làm dừng các file còn lại; trạng thái và thông điệp cuối được phát đúng."""
    good, bad = tmp_path / "a.png", tmp_path / "b.png"
    good.write_bytes(b""); bad.write_bytes(b"")

    def fake_process(path, out, dpi, pages, **kw):
        if path == bad:
            raise RuntimeError("ảnh hỏng")
        return {"docx": str(tmp_path / "out.docx")}

    monkeypatch.setattr(gui.pipeline, "process_file", fake_process)
    states, done = [], []
    worker = gui.OcrWorker([good, bad], None, None, {})
    worker.file_state.connect(lambda i, s: states.append((i, s)))
    worker.finished_ok.connect(lambda msg, outs: done.append((msg, outs)))
    worker.run()   # chạy đồng bộ để test không cần vòng lặp sự kiện

    assert (0, "Xong") in states and any(s.startswith("Lỗi") for i, s in states if i == 1)
    msg, outs = done[0]
    assert "ảnh hỏng" in msg
    assert len(outs) == 1 and outs[0][0] == good and outs[0][1]["docx"] == str(tmp_path / "out.docx")


def test_responsive_cua_so_hep(window):
    from PySide6.QtCore import Qt
    window.show()
    window.resize(1180, 800)
    app.processEvents()
    app.processEvents()   # bố cục trong QScrollArea cần thêm một vòng
    assert window.side.width() == 228
    assert window.ocr.splitter.orientation() == Qt.Orientation.Horizontal
    window.resize(800, 700)
    app.processEvents()
    app.processEvents()   # bố cục trong QScrollArea cần thêm một vòng
    assert window.side.width() < 120 and window.nav.item(1).text() == "Tách\nPDF"
    assert window.ocr.splitter.orientation() == Qt.Orientation.Vertical
    window.resize(1180, 800)
    app.processEvents()
    app.processEvents()   # bố cục trong QScrollArea cần thêm một vòng
    assert window.nav.item(1).text() == "Tách PDF"


def test_phim_tat_va_ten_truy_cap(window):
    window.show()
    window.nav.setCurrentRow(0)
    assert window.run_btn.accessibleName()
    assert window.ocr.engine.accessibleName() == "Công cụ OCR"
    from PySide6.QtGui import QShortcut
    keys = {s.key().toString() for s in window.findChildren(QShortcut)}
    assert {"Ctrl+O", "Ctrl+R", "F5", "Esc", "Ctrl+2"} <= keys


def test_mau_tai_lieu_dat_san_tuy_chon(window):
    ocr = window.ocr
    ocr.preset.setCurrentIndex(ocr.preset.findText("Ảnh chụp điện thoại"))
    assert ocr.upscale.text() == "2" and ocr.cell_reocr.isChecked()
    ocr.preset.setCurrentIndex(ocr.preset.findText("Chỉ văn bản (không bảng)"))
    assert ocr.upscale.text() == "1" and not ocr.cell_reocr.isChecked()


def test_do_trong_suot_khong_qua_90(window):
    from ocrnhat.gui_extra import ALPHA_LEVELS
    assert min(ALPHA_LEVELS) >= 90   # chữ mờ hơn thì khó đọc


def test_o_nhap_co_ten_truy_cap(window):
    from PySide6.QtWidgets import QComboBox, QLineEdit, QSpinBox
    hidden = {window.ocr.crop_src, window.ocr.crop_page}   # điều khiển ẩn, chỉ giữ để đồng bộ logic
    # ô con bên trong QSpinBox là phần soạn thảo nội bộ của chính nó, không tính
    widgets = [w for cls in (QLineEdit, QComboBox, QSpinBox) for w in window.ocr.findChildren(cls)
               if not isinstance(w.parentWidget(), QSpinBox)]
    missing = [type(w).__name__ for w in widgets if w not in hidden and not w.accessibleName()]
    assert missing == []


def test_dung_o_header_bat_theo_trang_thai(window):
    """Nút Dừng nằm trên header, bật khi OCR đang chạy và tắt khi xong."""
    window._on_ocr_busy(True)
    assert window.stop_btn.isEnabled() and not window.run_btn.isEnabled()
    window._on_ocr_busy(False)
    assert not window.stop_btn.isEnabled() and window.run_btn.isEnabled()


def test_muc_file_co_ten_de_doc_va_goi_y_keo_tha_rut_gon(window, tmp_path):
    f = tmp_path / "so_tay.pdf"
    f.write_bytes(b"")
    window.ocr._add([f])
    assert window.ocr.listing.item(0).text() == "so_tay.pdf"
    assert window.ocr.drop.text() == gui.DROP_HINT_SHORT
    window.ocr.clear()
    assert window.ocr.drop.text() == gui.DROP_HINT


def test_mo_thu_muc_ket_qua_theo_luc_bat_dau(window, tmp_path):
    """Đổi ô thư mục lưu khi đang chạy không làm nút mở nhầm thư mục."""
    window.ocr._run_out = None
    window.ocr._on_done("Xong. Đã xử lý 1 file.", [(tmp_path / "a.png", {"docx": "x"})])
    assert window.ocr._out_dir == tmp_path
    assert window.ocr.btn_open_out.isVisibleTo(window.ocr)
