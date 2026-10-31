"""Kiểm giao diện theo đợt cải thiện UX/trợ năng: lỗi nhập hiện trong giao diện, khóa khi đang chạy,
độ tương phản chữ phụ, palette tối lấy từ token chung. Offscreen; bỏ qua nếu thiếu Qt."""
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
except ImportError:
    pytest.skip("không nạp được Qt (thiếu thư viện hệ thống)", allow_module_level=True)

from PySide6.QtGui import QPalette  # noqa: E402

from ocrnhat import gui, ui_logic as L  # noqa: E402
from ocrnhat.gui_extra import _palette  # noqa: E402
from ocrnhat.gui_style import PALETTES, contrast  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "ocrnhat"


@pytest.fixture
def window(monkeypatch):
    store = {}
    monkeypatch.setattr(L, "save_settings", lambda data: store.update(data))
    monkeypatch.setattr(L, "load_settings", lambda: dict(store))
    w = gui.MainWindow()
    yield w
    w.close()


def test_ocr_thieu_file_bao_bang_banner_khong_mo_hop_thoai(window):
    window.ocr.files.clear()
    window.ocr.start()
    assert window.ocr.banner.isVisibleTo(window.ocr)
    assert "Chưa chọn file" in window.ocr.banner.text()
    assert window.ocr.worker is None


def test_ocr_loi_so_trang_dua_con_tro_vao_o_nhap(window, tmp_path, monkeypatch):
    img = tmp_path / "a.png"
    img.write_bytes(b"")
    window.ocr.files.append(img)
    window.ocr.pages.setText("abc")
    focused = []
    monkeypatch.setattr(window.ocr.pages, "setFocus", lambda *a: focused.append(True))   # cửa sổ ẩn: chỉ kiểm lời gọi
    window.ocr.start()
    assert "Số trang không hợp lệ" in window.ocr.banner.text()
    assert focused


def test_dang_chay_khoa_danh_sach_va_cau_hinh(window):
    ocr = window.ocr
    ocr._set_running(True)
    try:
        assert not ocr.btn_add.isEnabled()
        assert not ocr.btn_clear.isEnabled()
        for w in ocr._locked_while_running:
            assert not w.isEnabled()
        assert ocr.btn_add.toolTip()   # có lý do, không khóa im lặng
    finally:
        ocr._set_running(False)
    assert ocr.btn_add.isEnabled()
    assert all(w.isEnabled() for w in ocr._locked_while_running)


def test_chu_phu_dat_tuong_phan_4_5_tren_moi_nen():
    for theme, t in PALETTES.items():
        for bg in ("page", "card", "accent_soft"):
            assert contrast(t["muted"], t[bg]) >= 4.5, (theme, bg)
        assert contrast(t["off_fg"], t["off_bg"]) >= 4.5, theme


@pytest.mark.parametrize("theme", ["sáng", "tối"])
def test_palette_lay_tu_token_chung_khong_phu_thuoc_he_dieu_hanh(theme):
    # palette Qt phải khớp QSS của cùng giao diện, không lấy từ chế độ tối/sáng của Windows
    t = PALETTES[theme]
    p = _palette(theme)
    assert p.color(QPalette.ColorRole.Window).name() == t["page"].lower()
    assert p.color(QPalette.ColorRole.Base).name() == t["field"].lower()
    assert p.color(QPalette.ColorRole.Text).name() == t["text"].lower()


def test_khong_con_mau_cung_trong_mau_giao_dien():
    # màu giao diện chỉ nằm trong gui_style (và ảnh xem trước của PageView, là dữ liệu hiển thị)
    hex_re = re.compile(r'"#[0-9A-Fa-f]{6}"')
    for name in ("gui.py", "gui_pdf.py"):
        assert not hex_re.search((SRC / name).read_text(encoding="utf-8")), name
    text = (SRC / "gui_extra.py").read_text(encoding="utf-8")
    start = text.index("def _palette")
    end = text.index("def apply_view")
    assert not hex_re.search(text[start:end])
    assert "QMessageBox.information" not in (SRC / "gui_pdf.py").read_text(encoding="utf-8")
