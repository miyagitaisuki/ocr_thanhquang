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

from ocrnhat import gui_qt, ui_logic as L  # noqa: E402


@pytest.fixture
def settings_store(monkeypatch):
    """Không ghi settings.json thật: lưu trong bộ nhớ."""
    store = {}
    monkeypatch.setattr(L, "save_settings", lambda data: store.update(data))
    monkeypatch.setattr(L, "load_settings", lambda: dict(store))
    return store


@pytest.fixture
def window(settings_store):
    w = gui_qt.MainWindow()
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
    w1 = gui_qt.MainWindow()
    w1.ocr.upscale.setText("2")
    w1.ocr.ruby.setChecked(True)
    w1.ocr.engine.setCurrentIndex(w1.ocr.engine.findData("paddle"))
    w1.ocr._save()
    w1.close()
    w2 = gui_qt.MainWindow()
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

    monkeypatch.setattr(gui_qt.pipeline, "process_file", fake_process)
    states, done = [], []
    worker = gui_qt.OcrWorker([good, bad], None, None, {})
    worker.file_state.connect(lambda i, s: states.append((i, s)))
    worker.finished_ok.connect(lambda msg, outs: done.append((msg, outs)))
    worker.run()   # chạy đồng bộ để test không cần vòng lặp sự kiện

    assert (0, "Xong") in states and any(s.startswith("Lỗi") for i, s in states if i == 1)
    msg, outs = done[0]
    assert "ảnh hỏng" in msg
    assert len(outs) == 1 and outs[0][0] == good and outs[0][1]["docx"] == str(tmp_path / "out.docx")
