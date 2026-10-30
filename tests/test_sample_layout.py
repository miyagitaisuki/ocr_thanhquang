"""Mẫu câu có số trong ô xám và nhãn ví dụ 'Ex.' (layout._sample_layout)."""
from ocrnhat.layout import build_page
from ocrnhat.model import Block, Line, Page


def _l(text, x, y, w=600, h=25):
    return Line(text, x=x, y=y, w=w, h=h, conf=0.9)


def _texts(page):
    return [l.text for b in page.blocks for l in b.lines]


def test_so_o_xam_ghep_vao_cau_va_bo_dau_hoa_thi():
    page = Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("79", 127, 150, w=29, h=28),
        _l("※本日は長時間お付き合いくださいまして", 133, 150),
    ])])
    from ocrnhat.layout import _sample_layout
    _sample_layout(page)
    assert _texts(page) == ["", "79 本日は長時間お付き合いくださいまして"]
    items = build_page(Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("79", 127, 150, w=29, h=28), _l("※本日は長時間お付き合いくださいまして", 133, 150)])]))
    assert items[0].text.startswith("79 本日は")


def test_so_le_khong_co_dau_hoa_thi_khong_bi_ghep():
    page = Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("10", 91, 150, w=29, h=28),
        _l("アポイントを取る……046", 133, 150),
    ])])
    from ocrnhat.layout import _sample_layout
    _sample_layout(page)
    assert _texts(page) == ["10", "アポイントを取る……046"]


def test_nhan_ex_bi_bo_va_vi_du_thanh_muc_rieng():
    page = Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("Ex.", 139, 186, w=25),
        _l("株式会社富士山ホールディングス御中", 186, 186),
        _l("Ex", 139, 407, w=23),
        _l("1田中様・吉田様・鈴木様", 160, 406, w=263),
        _l("Ex.2", 130, 595, w=41),
        _l("販売局各位", 177, 596, w=601),
        _l("×各位様", 141, 633, w=232),
    ])])
    from ocrnhat.layout import _sample_layout
    _sample_layout(page)
    t = _texts(page)
    assert t[0] == "" and t[2] == "" and t[4] == ""
    assert t[1] == "■株式会社富士山ホールディングス御中"
    assert t[3] == "■田中様・吉田様・鈴木様"
    assert t[5] == "■販売局各位" and t[6] == "■×各位様"
    items = build_page(Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("Ex.2", 130, 595, w=41), _l("販売局各位", 177, 596, w=601), _l("×各位様", 141, 633, w=232)])]))
    assert [i.text for i in items] == ["販売局各位", "×各位様"]   # hai ví dụ không gộp thành một đoạn


def test_nhieu_at_va_nhieu_nhan_ex_khong_lam_hong_cau():
    from ocrnhat.layout import _jp_part, _sample_layout
    assert _jp_part("×××××@×へお送りしたメールが") == "へお送りしたメールが"   # chuỗi nhiễu bị bỏ
    page = Page(1000, 800, [Block("text", 0, 0, 1000, 800, [
        _l("Ex.", 139, 150, w=25),
        _l("1時間ほどお時間をいただけますか。", 160, 150, w=400),
    ])])
    _sample_layout(page)
    assert _texts(page)[1] == "■1時間ほどお時間をいただけますか。"
