"""Gộp trang thành một khối liền mạch, và engine giữ chỗ tiếng Anh/Việt. Không cần model."""
import pytest

from ocrnhat import engines
from ocrnhat.layout import Para, merge_pages
from ocrnhat.engines.placeholder import EnglishPlaceholder, VietnamesePlaceholder


def _p(text, kind="body", **kw):
    return Para(text, kind, x=100, y=0, x1=500, y1=40, size=40, conf=0.9, **kw)


def test_doan_bi_cat_cuoi_trang_noi_voi_dau_trang_sau():
    pages = [(1, [_p("トラブルが起こったとき、自分のミスを")]), (2, [_p("認めて謝る文書です。")])]
    out = merge_pages(pages)
    assert len(out) == 1 and out[0][0] == 1
    assert [i.text for i in out[0][1]] == ["トラブルが起こったとき、自分のミスを認めて謝る文書です。"]


def test_cau_ket_thuc_khong_noi():
    pages = [(1, [_p("一文目です。")]), (2, [_p("二文目です。")])]
    out = merge_pages(pages)
    assert [i.text for pno, items in out for i in items] == ["一文目です。", "二文目です。"]


def test_tieu_de_khong_noi_va_trang_trong_bi_bo():
    pages = [(1, [_p("本文の途中で")]), (2, []), (3, [_p("見出し", kind="heading")]), (4, [_p("続き")])]
    out = merge_pages(pages)
    assert [pno for pno, _ in out] == [1, 3, 4]
    assert [i.text for i in out[1][1]] == ["見出し"]


def test_ruby_duoc_dich_theo_do_dai_sau_khi_noi():
    a = _p("漢字の", ruby=[(0, 2, "かんじ")])
    b = _p("読み", ruby=[(0, 2, "よみ")])
    out = merge_pages([(1, [a]), (2, [b])])
    assert out[0][1][0].ruby == [(0, 2, "かんじ"), (3, 5, "よみ")]


def test_engine_giu_cho_chua_cai_va_bao_loi():
    assert "ocr_en" in engines.available() and "ocr_vi" in engines.available()
    assert engines.engine_version("ocr_en") == "placeholder"
    ok, why = EnglishPlaceholder.is_available()
    assert ok is False and "chưa" in why
    with pytest.raises(NotImplementedError):
        VietnamesePlaceholder()
