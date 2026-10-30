"""Test nhận dạng lại ô bảng (_reocr_cells, _has_ink) bằng engine giả: không cần model."""
import numpy as np

from ocrnhat.layout import Cell, _Filter, _has_ink, _reocr_cells
from ocrnhat.model import Block, Line, Page


class _Res:
    def __init__(self, blocks):
        self.blocks = blocks


def _fake(lines_per_call, calls=None):
    """Engine giả: mỗi lần gọi trả về `lines_per_call` (danh sách Line) trong một khối; ghi lại kích thước ảnh cắt."""
    def reocr(crop):
        if calls is not None:
            calls.append(crop.shape)
        if not lines_per_call:
            return _Res([])
        return _Res([Block("text", 0, 0, crop.shape[1], crop.shape[0],
                           [Line(l.text, l.x, l.y, l.w, l.h, conf=l.conf) for l in lines_per_call])])
    return reocr


def _flt():
    return _Filter(Page(400, 100, []))


XS = [0, 200, 400]
YS = [0, 60]
CELLS = [Cell(0, 0), Cell(0, 1)]


def _img(h=100, w=400):
    return np.full((h, w, 3), 255, np.uint8)


def test_khong_co_anh_tra_ve_nguyen_ban():
    old = [Line("一二", x=150, y=20, w=100, h=20, conf=0.9)]
    out = _reocr_cells(old, YS, XS, CELLS, None, _fake([Line("東京", 0, 0, 50, 20, conf=0.9)]), _flt())
    assert out == old


def test_dong_vuot_duong_ke_duoc_thay_bang_ket_qua_nhan_dang_lai():
    old = [Line("一二", x=150, y=20, w=100, h=20, conf=0.9)]   # cx=200 nằm trong ô (0,1), vượt đường kẻ x=200
    out = _reocr_cells(old, YS, XS, CELLS, _img(), _fake([Line("東京", 0, 0, 50, 20, conf=0.9)]), _flt())
    assert all(l.text == "東京" for l in out)
    assert len(out) == 2                                        # một dòng mới cho mỗi ô bị đánh dấu
    assert sorted(l.x for l in out) == [3, 203]                 # cộng lại offset ix0 = x0 + 3 (ô 0: 0+3, ô 1: 200+3)


def test_engine_khong_doc_duoc_thi_giu_ket_qua_cu():
    old = [Line("一二", x=150, y=20, w=100, h=20, conf=0.9)]
    out = _reocr_cells(old, YS, XS, CELLS, _img(), _fake([]), _flt())
    assert out == old


def test_dong_conf_thap_hoac_latin_bi_loc():
    old = [Line("一二", x=150, y=20, w=100, h=20, conf=0.9)]
    rac = [Line("東京", 0, 0, 50, 20, conf=0.05),              # conf < 0.1: engine bịa
           Line("ABCD", 0, 0, 50, 20, conf=0.9)]               # Latin: bị lọc
    out = _reocr_cells(old, YS, XS, CELLS, _img(), _fake(rac), _flt())
    assert out == old


def test_o_hep_hon_100px_khong_goi_engine():
    # cột 0 rộng 80 px (<100): không được nhận dạng lại, chỉ ô rộng được gọi
    xs = [0, 80, 400]
    cells = [Cell(0, 0), Cell(0, 1)]
    old = [Line("一二", x=60, y=20, w=40, h=20, conf=0.9)]     # cx=80 vượt đường kẻ x=80
    calls = []
    _reocr_cells(old, YS, xs, cells, _img(), _fake([], calls), _flt())
    assert len(calls) == 1
    assert calls[0][1] >= 100


def test_dong_khong_vuot_va_o_trong_khong_co_net_chu_khong_bi_dong():
    old = [Line("一二", x=20, y=20, w=60, h=20, conf=0.9)]     # nằm gọn trong ô (0,0), không vượt
    calls = []
    out = _reocr_cells(old, YS, XS, CELLS, _img(), _fake([], calls), _flt())
    assert out == old
    assert calls == []


def test_o_trong_co_net_chu_duoc_nhan_dang_lai():
    # ô (0,1) không có dòng nào nhưng có nét đậm: engine đã bỏ sót, phải gọi lại
    img = _img()
    img[20:80, 250:255] = 0                                    # cọc đen trong ô (0,1)
    calls = []
    out = _reocr_cells([], YS, XS, CELLS, img, _fake([Line("東京", 0, 0, 50, 20, conf=0.9)], calls), _flt())
    assert len(calls) == 1
    assert [l.text for l in out] == ["東京"]


def test_has_ink_nen_trang_va_cuc_rong():
    img = _img()
    assert not _has_ink(img, 0, 0, 100, 100)                   # nền trắng đồng nhất
    assert not _has_ink(img, 50, 50, 50, 50)                   # ô rỗng: cắt ra không có điểm ảnh


def test_has_ink_phat_hien_net_dam():
    img = _img()
    img[10:90, 40:46] = 0                                      # nét đen rõ trên nền trắng
    assert _has_ink(img, 0, 0, 100, 100)
