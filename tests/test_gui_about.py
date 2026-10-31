"""Menu Trợ giúp và thông tin hệ thống (không cần model)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
except ImportError:
    pytest.skip("thiếu thư viện hệ thống cho Qt (libEGL)", allow_module_level=True)

from ocrnhat import gui_about


def test_gioi_thieu_co_thong_tin_tac_gia_va_giay_phep():
    html = gui_about.ABOUT_HTML
    for text in ("Nguyễn Thanh Quang", "Đại học Quy Nhơn", "08686 08647", "nguyenthanhquang@qnu.edu.vn",
                 "CC BY 4.0", "OpenRAIL-M", "LGPL-3.0"):
        assert text in html


def test_system_info_bao_card_nvidia_va_torch(monkeypatch):
    from ocrnhat import gpu
    monkeypatch.setattr(gpu, "detect", lambda: [gpu.Gpu("NVIDIA GeForce RTX 3060", 12288)])
    monkeypatch.setattr(gpu, "ort_cuda_available", lambda: False)
    text = "\n".join(gui_about.system_info())
    assert "RTX 3060" in text and "12288" in text and "Thư mục nhật ký lỗi" in text


def test_menu_tro_giup_va_bao_loi_mo_thu_muc_log(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMainWindow
    opened = []
    monkeypatch.setattr(gui_about.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    monkeypatch.setattr(gui_about.L, "LOG_FILE", tmp_path / "logs" / "app.log")
    win = QMainWindow()
    menu = gui_about.build_help_menu(win)
    titles = [a.text() for a in menu.actions()]
    assert menu.title() == "Trợ giúp" and any("Giới thiệu" in t for t in titles)
    next(a for a in menu.actions() if "Báo lỗi" in a.text()).trigger()
    assert opened == [str(tmp_path / "logs")] and (tmp_path / "logs").is_dir()
    app.processEvents()
