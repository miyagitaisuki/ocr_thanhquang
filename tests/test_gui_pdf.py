"""Test ba mục Công cụ PDF của giao diện PySide6 (bước 3), chạy thật trên PDF tạo trong test; bỏ qua nếu thiếu PySide6."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
except ImportError:
    pytest.skip("không nạp được Qt (thiếu thư viện hệ thống)", allow_module_level=True)

from pypdf import PdfReader, PdfWriter  # noqa: E402

from ocrnhat import gui, ui_logic as L  # noqa: E402


def _pdf(path, pages):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    with open(path, "wb") as fh:
        w.write(fh)
    return path


def _wait(section):
    """Chờ luồng nền xong rồi xử lý sự kiện để tín hiệu về giao diện được nhận."""
    if section.worker is not None:
        section.worker.wait(60000)
    app.processEvents()


@pytest.fixture
def store(monkeypatch):
    data = {}
    monkeypatch.setattr(L, "save_settings", lambda d: data.update(d))
    monkeypatch.setattr(L, "load_settings", lambda: dict(data))
    return data


@pytest.fixture
def window(store):
    w = gui.MainWindow()
    yield w
    w.close()


def test_ba_muc_pdf_co_dung_thẻ_thao_tac(window):
    assert window.stack.count() == 4
    assert [window.split.tabs.tabText(i) for i in range(window.split.tabs.count())] == ["Trích xuất trang", "Tách file"]
    assert [window.merge.tabs.tabText(i) for i in range(window.merge.tabs.count())] == [
        "Ghép nhiều file", "Ghép xen kẽ", "Chèn trang lặp lại"]
    assert [window.tools.tabs.tabText(i) for i in range(window.tools.tabs.count())] == [
        "Xoay trang", "Nén PDF", "Tự động theo thư mục"]


def test_ghep_file_that(window, tmp_path):
    a, b = _pdf(tmp_path / "a.pdf", 3), _pdf(tmp_path / "b.pdf", 2)
    window.merge.files_box.add_paths([str(a), str(b)])
    window.merge.fields["merge_name"].setText("tong")
    window.merge.output.folder.setText(str(tmp_path / "ra"))
    (tmp_path / "ra").mkdir()
    window.merge.run_merge()
    _wait(window.merge)
    out = tmp_path / "ra" / "merge_tong.pdf"
    assert out.exists()
    assert len(PdfReader(str(out)).pages) == 5
    assert window.merge.status.text().startswith("Xong")


def test_trich_xuat_trang_that(window, tmp_path):
    a = _pdf(tmp_path / "a.pdf", 4)
    (tmp_path / "ra").mkdir()
    window.split.files_box.add_paths([str(a)])
    window.split.fields["pages"].setText("1-2")
    window.split.output.folder.setText(str(tmp_path / "ra"))
    window.split.run_extract()
    _wait(window.split)
    outs = list((tmp_path / "ra").glob("*.pdf"))
    assert len(outs) == 1 and len(PdfReader(str(outs[0])).pages) == 2


def test_xoay_trang_that(window, tmp_path):
    a = _pdf(tmp_path / "a.pdf", 1)
    (tmp_path / "ra").mkdir()
    window.tools.files_box.add_paths([str(a)])
    window.tools.angle.setCurrentIndex(window.tools.angle.findData(90))
    window.tools.output.folder.setText(str(tmp_path / "ra"))
    window.tools.run_rotate()
    _wait(window.tools)
    outs = list((tmp_path / "ra").glob("*.pdf"))
    assert len(outs) == 1
    assert PdfReader(str(outs[0])).pages[0].get("/Rotate") == 90


def test_ghep_can_it_nhat_hai_file(window, tmp_path):
    window.merge.files_box.add_paths([str(_pdf(tmp_path / "a.pdf", 1))])
    window.merge.run_merge()
    assert window.merge.banner.isVisibleTo(window.merge)   # lỗi hiện trong mục, không mở hộp thoại
    assert "Thêm ít nhất 2" in window.merge.banner.text()
    assert window.merge.worker is None


def test_chon_file_chen_trang_giu_theo_duong_dan(window, tmp_path):
    a, b = _pdf(tmp_path / "a.pdf", 1), _pdf(tmp_path / "b.pdf", 1)
    window.merge.files_box.add_paths([str(a), str(b)])
    window.merge.main_cb.setCurrentIndex(1)           # chọn b.pdf
    chosen = window.merge.main_cb.currentData()
    window.merge.files_box.list.takeItem(0)           # bỏ a.pdf: b.pdf đổi số thứ tự
    window.merge.files_box._refresh()
    assert window.merge.main_cb.currentData() == chosen
    assert window.merge.main_cb.currentText().startswith("1.")


def test_luu_khoi_phuc_thu_muc_va_danh_sach(store, tmp_path):
    a = _pdf(tmp_path / "a.pdf", 1)
    w1 = gui.MainWindow()
    w1.split.files_box.add_paths([str(a)])
    w1.split.output.folder.setText(str(tmp_path))
    w1.split.fields["pages"].setText("1")
    w1.close()
    w2 = gui.MainWindow()
    assert w2.split.output.folder.text() == str(tmp_path)
    assert w2.split.fields["pages"].text() == "1"
    assert [str(f) for f in w2.split.files_box.files()] == [str(a)]
    w2.close()


# ---------- trợ giúp kiểm tra hộp thoại ----------



