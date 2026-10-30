"""Dòng hỗn hợp Nhật-Anh (mục lục, nhãn song ngữ): giữ phần tiếng Nhật, không loại cả dòng."""
from ocrnhat.layout import _Filter, _jp_part, build_page
from ocrnhat.model import Block, Line, Page


def _line(text, x, y, order):
    return Line(text, x=x, y=y, w=700, h=30, conf=0.9, order=order)


def test_jp_part_bo_latin_va_chuoi_dan():
    assert _jp_part("日本語入力の基本Basics of inputting Japanese characters………………12") == "日本語入力の基本"
    assert _jp_part("名乗るIdentifying yourself …………………………034") == "名乗る"
    assert _jp_part("3確認する Confirming 064") == "3確認する"
    assert _jp_part("Basics of inputting………012") == ""
    assert _jp_part("日本語です。") == "日本語です。"        # câu thuần Nhật không đổi


def test_keep_dong_hon_hop_va_dong_latin_thuan():
    flt = _Filter(Page(1000, 600, []))
    assert flt.keep(_line("日本語入力の基本Basics of inputting Japanese", 0, 0, 1))
    assert not flt.keep(_line("Basics of inputting Japanese characters", 0, 0, 2))


def test_doan_van_giu_phan_nhat_cua_dong_hon_hop():
    page = Page(1000, 600, [Block("text", 100, 20, 800, 200, [
        _line("日本語入力の基本Basics of inputting Japanese………012", 100, 20, 1),
        _line("これは本文です。", 100, 60, 2),
    ])])
    items = build_page(page)
    assert [i.text for i in items] == ["日本語入力の基本これは本文です。"]


def test_dong_muc_luc_thanh_cac_doan_rieng():
    # mỗi dòng có dấu chấm dẫn là một mục, kể cả khi engine tách thành các khối riêng
    page = Page(1000, 600, [
        Block("text", 100, 20, 800, 30, [_line("名乗る Identifying yourself ……034", 100, 20, 1)]),
        Block("text", 100, 60, 800, 30, [_line("書き出し Opening words ……036", 100, 60, 2)]),
    ])
    assert [i.text for i in build_page(page)] == ["名乗る", "書き出し"]


def test_bo_so_tieu_de_chay_va_o_vuong_o_dau_doan():
    from ocrnhat.layout import _strip_prefix
    assert _strip_prefix("2すぐに使える例文集:社外編") == "すぐに使える例文集:社外編"
    assert _strip_prefix("1日本語メールの基本とコツ") == "日本語メールの基本とコツ"
    assert _strip_prefix("□と判明しました") == "と判明しました"
    assert _strip_prefix("■本文") == "本文"
    assert _strip_prefix("※名前がわからない相手") == "※名前がわからない相手"   # ghi chú của sách: giữ
    assert _strip_prefix("10月に展示会を開催します") == "10月に展示会を開催します"   # số trong câu: giữ
    assert _strip_prefix("4月1日より御社を担当") == "4月1日より御社を担当"
    assert _strip_prefix("19早くご返事を") == "19早くご返事を"                  # không phải tiêu đề chạy: giữ


def test_so_dung_dau_dong_van_bi_bo_trong_doan():
    page = Page(1000, 600, [Block("text", 100, 20, 800, 200, [
        _line("2すぐに使える例文集", 100, 20, 1),
        _line("本文です。", 100, 60, 2),
    ])])
    assert [i.text for i in build_page(page)][0].startswith("すぐに使える例文集")
