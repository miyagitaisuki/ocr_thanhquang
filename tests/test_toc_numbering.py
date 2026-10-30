"""Đánh số lại mục lục có ký hiệu ①②③ bị engine đọc sai (layout._number_toc)."""
from ocrnhat.layout import _number_toc
from ocrnhat.model import Block, Line, Page


def _l(text, x, y, w=800, h=25, order=0):
    return Line(text, x=x, y=y, w=w, h=h, conf=0.9, order=order)


def _texts(page):
    return [l.text for b in page.blocks for l in b.lines]


def test_phan_truoc_chuong_dau_khong_danh_so():
    page = Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("はしがき……003", 100, 20),
        _l("Chapter 1", 100, 80, w=110),
        _l("日本語入力の基本 Basics……012", 100, 120),
    ])])
    _number_toc(page)
    assert _texts(page)[0] == "はしがき……003"
    assert _texts(page)[2] == "①日本語入力の基本 Basics……012"


def test_moi_chuong_dat_lai_bo_dem():
    page = Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("Chapter 1", 100, 20, w=110),
        _l("名乗る……034", 100, 60),
        _l("書き出し……036", 100, 100),
        _l("Chapter 2", 100, 140, w=110),
        _l("報告する……092", 100, 180),
    ])])
    _number_toc(page)
    t = _texts(page)
    assert t[1].startswith("①") and t[2].startswith("②") and t[4].startswith("①")


def test_ten_mục_tach_hai_dong_duoc_ghep():
    page = Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("Chapter 3", 100, 20, w=110),
        _l("11", 90, 60, w=28, h=28),
        _l("連絡する", 128, 62, w=90, h=22),
        _l("Communicating……094", 221, 63, w=779, h=24),
    ])])
    _number_toc(page)
    t = _texts(page)
    assert t[2] == "" and t[3] == "①連絡するCommunicating……094"


def test_chu_dau_bi_tach_duoc_ghep_va_khong_lap():
    page = Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("Chapter 4", 100, 20, w=110),
        _l("お悔やみ……109", 114, 60, w=883),
        _l("予約", 90, 100, w=82, h=22),
        _l("約Making reservations……110", 147, 102, w=851),
        _l("お礼を言う", 130, 170, w=110, h=18),          # bản đọc lẻ của chính mục bên dưới
        _l("♪お礼を言うThanking……082", 135, 180, w=870),
    ])])
    _number_toc(page)
    t = [l.text for b in page.blocks for l in b.lines]
    assert t[2] == "" and t[3] == "②予約Making reservations……110"
    assert t[4] == ""                       # dòng lặp của tên mục bị bỏ
    assert t[5] == "③お礼を言うThanking……082"
