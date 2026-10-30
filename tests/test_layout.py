"""Test dựng đoạn/bảng từ tọa độ dòng. Không cần model: dùng Page tổng hợp và ảnh vẽ bằng tay."""
import numpy as np
from PIL import Image, ImageDraw

from ocrnhat.layout import Para, Table, build_page
from ocrnhat.model import Block, Line, Page
from ocrnhat.pipeline import parse_pages

RUNS = {(0, 0): "会社", (0, 1): "株式会社", (1, 0): "銀行", (1, 1): "電話番号"}


def _grid_image(x0=100, y0=100, cw=400, rh=200, rows=2, cols=2) -> np.ndarray:
    img = Image.new("RGB", (1000, 600), "white")
    d = ImageDraw.Draw(img)
    for i in range(rows + 1):
        d.line([(x0, y0 + i * rh), (x0 + cols * cw, y0 + i * rh)], fill="black", width=3)
    for j in range(cols + 1):
        d.line([(x0 + j * cw, y0), (x0 + j * cw, y0 + rows * rh)], fill="black", width=3)
    return np.array(img)


def _line(text, x, y, order):
    return Line(text, float(x), float(y), 40.0 * len(text), 40.0, 0.95, "", order)


def _table_page(extra_paragraph: bool = False) -> Page:
    # 2x2 ô, mỗi ô 400x200 bắt đầu từ (100, 100)
    lines = [_line(t, 100 + c * 400 + 40, 100 + r * 200 + 60, r * 2 + c + 1) for (r, c), t in RUNS.items()]
    if extra_paragraph:
        lines.insert(0, _line("これは本文です。", 100, 20, 0))
    return Page(1000, 600, [Block("text", 100, 20, 800, 480, lines)])


def test_bang_theo_luoi_khi_ndlocr_khong_gan_nhan_bang():
    """Khối bị NDLOCR gắn là text vẫn phải thành bảng 2x2 (lỗi cũ: gộp thành đoạn)."""
    items = build_page(_table_page(), _grid_image())
    tables = [i for i in items if isinstance(i, Table)]
    assert len(tables) == 1
    t = tables[0]
    assert (t.n_rows, t.n_cols) == (2, 2)
    got = {(c.r, c.c): c.text for c in t.cells}
    assert got == RUNS


def test_doan_van_ngoai_bang_giu_nguyen():
    items = build_page(_table_page(extra_paragraph=True), _grid_image())
    paras = [i for i in items if isinstance(i, Para)]
    tables = [i for i in items if isinstance(i, Table)]
    assert [p.text for p in paras] == ["これは本文です。"]
    assert len(tables) == 1
    # đoạn văn nằm trước bảng theo thứ tự đọc
    assert items.index(paras[0]) < items.index(tables[0])


def test_khong_co_luoi_thi_khong_tao_bang():
    page = Page(1000, 600, [Block("text", 100, 20, 800, 200,
                                  [_line("日本語の文章です。", 100, 20, 1), _line("二行目です。", 100, 80, 2)])])
    items = build_page(page, np.full((600, 1000, 3), 255, np.uint8))
    assert not [i for i in items if isinstance(i, Table)]
    assert [i.text for i in items if isinstance(i, Para)] == ["日本語の文章です。二行目です。"]


def test_bo_chu_latin_va_furigana_roi_khong_con_trong_doan():
    page = Page(1000, 600, [Block("text", 100, 20, 800, 200, [
        _line("Hello world", 100, 20, 1),
        _line("日本語です。", 100, 80, 2),
    ])])
    items = build_page(page)
    assert [i.text for i in items if isinstance(i, Para)] == ["日本語です。"]


def test_parse_pages():
    assert parse_pages("") is None
    assert parse_pages("1-3,5") == [1, 2, 3, 5]
    assert parse_pages(" 8 ") == [8]


def test_o_trong_co_net_chu_duoc_nhan_dang_lai():
    """Engine bỏ sót chữ trong bảng dày: ô trống có nét chữ phải được nhận dạng lại từ ảnh cắt."""
    from ocrnhat.model import Page as _Page
    img = _grid_image()
    img[320:380, 520:700] = 0            # nét chữ đậm trong ô (r1, c1) — không có dòng nào của engine
    lines = [_line("社外文書", 130, 110, 1)]   # chỉ một dòng, các ô khác trống
    page = Page(1000, 600, [Block("table", 100, 100, 800, 400, lines)])
    crops = []

    def reocr(crop):
        crops.append(crop.shape)
        return _Page(crop.shape[1], crop.shape[0], [Block("text", 0, 0, 10, 10, [_line("依頼状", 40, 40, 1)])])

    items = build_page(page, img, reocr)
    t = next(i for i in items if isinstance(i, Table))
    got = {(c.r, c.c): c.text for c in t.cells}
    assert got[(1, 1)] == "依頼状"      # ô có nét chữ được nhận dạng lại
    assert crops                          # đã gọi engine với ảnh cắt
    assert got[(0, 0)] == "社外文書"     # dòng gốc giữ nguyên


def _para_page(specs):
    """specs: [(text, y)] cùng cỡ chữ 40 px, cùng bề ngang 480 px (chỉ khoảng cách dọc khác nhau)."""
    lines = [Line(t, 100.0, float(y), 480.0, 40.0, 0.95, "", i) for i, (t, y) in enumerate(specs)]
    return Page(1000, 800, [Block("text", 100, 20, 800, 760, lines)])


def test_tieu_de_cung_co_chu_duoc_nhan_theo_khoang_trong():
    # tiêu đề cùng cỡ chữ với thân bài, đứng riêng giữa hai khoảng trống lớn
    page = _para_page([("第一章日本語の基本", 100), ("日本語の文章はこのように続きます", 180),
                       ("同じ段落の二行目です", 236), ("同じ段落の三行目です", 292),
                       ("次の段落が始まります", 372), ("次の段落の二行目です。", 428)])
    paras = [i for i in build_page(page) if isinstance(i, Para)]
    assert [(p.kind, p.text) for p in paras] == [
        ("heading", "第一章日本語の基本"),
        ("body", "日本語の文章はこのように続きます同じ段落の二行目です同じ段落の三行目です"),
        ("body", "次の段落が始まります次の段落の二行目です。"),
    ]


def test_khoang_cach_dong_bat_thuong_ngat_doan():
    # khoảng cách giữa hai đoạn lớn hơn hẳn khoảng cách dòng thường: phải tách đoạn
    page = _para_page([("一行目の文章はここまでです", 100), ("二行目の文章も続いています", 156),
                       ("三行目の文章もまだ続いています", 212), ("新しい段落の一行目です", 292),
                       ("新しい段落の二行目です。", 348)])
    paras = [i for i in build_page(page) if isinstance(i, Para)]
    assert [p.text for p in paras] == [
        "一行目の文章はここまでです二行目の文章も続いています三行目の文章もまだ続いています",
        "新しい段落の一行目です新しい段落の二行目です。",
    ]


def test_khoang_cach_deu_nhau_khong_tach_doan():
    # mọi dòng cách đều: không có khoảng trống nào đáng kể, không tách đoạn và không có tiêu đề
    page = _para_page([("一行目の文章はここまでです", 100), ("二行目の文章も続いています", 156),
                       ("三行目の文章もまだ続いています", 212), ("四行目の文章もまだ続いています", 268)])
    paras = [i for i in build_page(page) if isinstance(i, Para)]
    assert len(paras) == 1 and paras[0].kind == "body"
