"""Tách chữ một trang từ file .txt kết quả (xem trước trong GUI). Không cần model."""
from ocrnhat.textview import page_text

TXT = "=== Trang 1 ===\n第一章\n本文です。\n=== Trang 2 ===\n二ページ目\n"


def test_lay_dung_trang():
    assert page_text(TXT, 1) == "第一章\n本文です。"
    assert page_text(TXT, 2) == "二ページ目"


def test_trang_khong_co_tra_none():
    assert page_text(TXT, 5) is None
