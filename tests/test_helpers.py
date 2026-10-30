"""Test đơn vị cho các hàm phụ không cần model: ký tự rác, ①②③, furigana theo tọa độ, đường kẻ bảng và cache trang."""
from ocrnhat.cache import PageCache
from ocrnhat.layout import Cell, _crosses_grid, _fix_circled, _kana_core, _line_ruby
from ocrnhat.model import Block, Line, Page


# ---------- _kana_core ----------

def test_kana_core_chuoi_thuan_kana_giu_nguyen():
    assert _kana_core("ちょうしつ") == "ちょうしつ"
    assert _kana_core("カタカナ・ひらがな") == "カタカナ・ひらがな"


def test_kana_core_chuoi_rong():
    assert _kana_core("") == ""
    assert _kana_core("   ") == ""


def test_kana_core_nhieu_chu_latin_khong_phai_rac():
    # ba chữ Latin trở lên: coi là nhãn, không lọc
    assert _kana_core("ABC きょう") == ""


def test_kana_core_bo_so_va_ky_hieu():
    assert _kana_core("2024 きょう") == "きょう"
    assert _kana_core("＄ かな#*") == "かな"


# ---------- _fix_circled ----------

def _col(*texts):
    return [Cell(0, 0, text="項目")] + [Cell(i + 1, 0, text=t) for i, t in enumerate(texts)]


def test_fix_circled_mot_o_thi_khong_doi():
    cells = _col("(1")
    _fix_circled(cells)
    assert cells[1].text == "(1"


def test_fix_circled_bo_qua_o_gop_hang():
    cells = [Cell(0, 0, text="項目"), Cell(1, 0, rs=2, text="(1"), Cell(3, 0, text="19")]
    _fix_circled(cells)
    assert [c.text for c in cells[1:]] == ["(1", "19"]


def test_fix_circled_bo_qua_o_dai():
    cells = _col("(1", "一二三四")          # ô dài hơn 3 ký tự: không phải mã khoanh
    _fix_circled(cells)
    assert [c.text for c in cells[1:]] == ["(1", "一二三四"]


def test_fix_circled_can_it_nhat_mot_o_mo_ngoac():
    cells = _col("19", "O1")                # không có ô nào mở bằng ngoặc: giữ nguyên
    _fix_circled(cells)
    assert [c.text for c in cells[1:]] == ["19", "O1"]


def test_fix_circled_qua_20_hang_khong_doi():
    cells = _col(*(["(1"] + ["19"] * 20))   # 21 ô thân bảng
    _fix_circled(cells)
    assert cells[1].text == "(1"


# ---------- _crosses_grid ----------

def test_crosses_grid_dong_vuot_duong_ke_doc():
    xs = [0, 100, 200]
    ys = [0, 100]
    line = Line("一二", x=80, y=40, w=60, h=20)   # đi qua x=100
    assert _crosses_grid(line, ys, xs)


def test_crosses_grid_dong_nam_trong_mot_o():
    xs = [0, 100, 200]
    ys = [0, 100]
    line = Line("一二", x=20, y=40, w=60, h=20)
    assert not _crosses_grid(line, ys, xs)


def test_crosses_grid_sat_duong_ke_trong_bien_do_khong_tinh():
    xs = [0, 100, 200]
    ys = [0, 100]
    line = Line("一二", x=98, y=40, w=2, h=20)   # chỉ chạm, nằm trong biên an toàn 3 px
    assert not _crosses_grid(line, ys, xs)


def test_crosses_grid_duong_ke_ngang():
    xs = [0, 100]
    ys = [0, 50, 100]
    line = Line("一二", x=10, y=40, w=30, h=20)  # đi qua y=50
    assert _crosses_grid(line, ys, xs)


# ---------- _line_ruby ----------

def _line(text, x=0, w=600):
    return Line(text, x=x, y=0, w=w, h=20)


def test_line_ruby_gan_cach_doc_theo_vi_tri_ngang():
    # 6 ký tự, mỗi ký tự 100 px; cụm '東京' ở ký tự 0-1, '大阪' ở ký tự 4-5
    line = _line("東京です大阪")
    out = _line_ruby(line, [(0, 200, "とうきょう"), (400, 600, "おおさか")], off=0)
    assert out == [(0, 2, "とうきょう"), (4, 6, "おおさか")]


def test_line_ruby_cong_offset_vao_chi_so():
    line = _line("東京です大阪")
    out = _line_ruby(line, [(400, 600, "おおさか")], off=10)
    assert out == [(14, 16, "おおさか")]


def test_line_ruby_khong_co_chu_han_thi_bo():
    line = _line("ちょうしつ")
    assert _line_ruby(line, [(0, 300, "ちょう")], off=0) == []


def test_line_ruby_dong_rong_hoac_bang_khong():
    assert _line_ruby(_line(""), [(0, 100, "あ")], off=0) == []
    assert _line_ruby(_line("東京", w=0), [(0, 100, "とうきょう")], off=0) == []


# ---------- PageCache ----------

def _page():
    return Page(100, 200, [Block("text", 0, 0, 100, 50,
                                 [Line("東京", x=1, y=2, w=30, h=10, conf=0.9, order=3)], label="")])


def test_cache_tra_lai_dung_cau_truc(tmp_path):
    c = PageCache(tmp_path, "h", 200, "ndlocr", "v1")
    c.put(2, _page())
    got = c.get(2)
    assert got.width == 100 and got.height == 200
    line = got.blocks[0].lines[0]
    assert line.text == "東京" and line.conf == 0.9 and line.order == 3


def test_cache_has_va_trang_chua_co(tmp_path):
    c = PageCache(tmp_path, "h", 200, "ndlocr", "v1")
    assert not c.has(1) and c.get(1) is None
    c.put(1, _page())
    assert c.has(1)
    assert not c.has(5)


def test_cache_khac_dpi_khong_dung_chung(tmp_path):
    PageCache(tmp_path, "h", 200, "ndlocr", "v1").put(1, _page())
    assert PageCache(tmp_path, "h", 300, "ndlocr", "v1").get(1) is None


def test_cache_file_hong_tra_ve_none(tmp_path):
    c = PageCache(tmp_path, "h", 200, "ndlocr", "v1")
    c.put(1, _page())
    c._path(1).write_text("{ không phải json", encoding="utf-8")
    assert c.get(1) is None


def test_cache_tao_thu_muc_khi_ghi(tmp_path):
    root = tmp_path / "a" / "b" / ".cache"
    PageCache(root, "h", 200, "ndlocr", "v1").put(1, _page())
    assert root.is_dir()
