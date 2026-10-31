"""Hậu xử lý tiếng Việt (vi_text): không cần model."""
from ocrnhat import vi_text
from ocrnhat.layout import Para, Table, Cell


def _valid():
    return vi_text._lexicon()[0]


def test_bo_nhieu_so_dai_va_ky_tu_ngan():
    out = vi_text._drop_noise("Điều 2 bb Quyết định 00100000000119 ỗ", _valid())
    assert "00100000000119" not in out
    assert "bb" not in out.split()
    assert "Quyết định" in out


def test_giu_viet_tat_in_hoa():
    # tên viết tắt in hoa không bị coi là nhiễu
    assert "KT" in vi_text._drop_noise("Phòng KT&BĐCL", _valid())


def test_sua_dau_theo_tan_suat_trong_tai_lieu():
    # "tố chức" xuất hiện nhiều lần đúng là "tổ chức"; "tổ chức" là âm tiết hợp lệ
    lines = ["Ban tố chức kỳ thi"] * 1 + ["Ban tổ chức kỳ thi"] * 6
    paras = [Para(text=t) for t in lines]
    res = vi_text.correct_results([(1, paras)])
    assert all("tố chức" not in p.text for p in res[0][1])


def test_khong_sua_cum_da_co_trong_tu_dien():
    # "kỳ thi" có trong từ điển, dù tài liệu có vài chỗ "kỳ thị" thì vẫn giữ nguyên
    lines = ["Kỳ thi kết thúc học phần"] * 5 + ["kỳ thị"]
    paras = [Para(text=t) for t in lines]
    res = vi_text.correct_results([(1, paras)])
    assert res[0][1][0].text == "Kỳ thi kết thúc học phần"


def test_giu_nguyen_chu_hoa_khi_sua():
    lines = ["Đào tạo đại học"] * 8 + ["Đảo tạo đại học"]   # 8 >= RATIO * (1 + 1)
    paras = [Para(text=t) for t in lines]
    res = vi_text.correct_results([(1, paras)])
    assert res[0][1][-1].text.startswith("Đào tạo")


def test_bo_doan_rong_sau_loc_va_sua_o_bang():
    paras = [Para(text="bb ca c")]
    table = Table(n_rows=1, n_cols=1, cells=[Cell(r=0, c=0, text="tố chức")])
    res = vi_text.correct_results([(1, paras + [table])])
    items = res[0][1]
    assert all(not (isinstance(i, Para) and not i.text.strip()) for i in items)
    assert isinstance(items[-1], Table)


def test_tach_dieu_bi_gop_vao_doan():
    paras = [Para(text="Trường Đại học Quy Nhơn Điều 2. Quyết định này có hiệu lực.")]
    res = vi_text.correct_results([(1, paras)])
    texts = [p.text for p in res[0][1]]
    assert texts == ["Trường Đại học Quy Nhơn", "Điều 2. Quyết định này có hiệu lực."]


def test_khong_tach_tham_chieu_dieu_trong_cau():
    # "Điều 15 Quy chế" trong câu tham chiếu không có dấu chấm sau số, giữ nguyên
    paras = [Para(text="theo Điều 15 Quy chế đào tạo, và Điều 5, 7 của quy định")]
    res = vi_text.correct_results([(1, paras)])
    assert len(res[0][1]) == 1


def test_bo_day_chu_so_lap_tu_dau_mo():
    assert "3 3 3" not in vi_text._drop_noise("nội dung 3 3 3 Thời hạn", _valid())
    # dãy số thứ tự khác nhau (bảng) giữ nguyên
    assert "1 2 3 4" in vi_text._drop_noise("cột 1 2 3 4 5", _valid())


def test_tach_dieu_khi_thieu_khoang_trang_sau_dau_cham():
    paras = [Para(text="bãi bỏ. Điều 9.In sao đề thi 1 Trưởng phòng")]
    texts = [p.text for p in vi_text.correct_results([(1, paras)])[0][1]]
    assert texts[-1].startswith("Điều 9.In")
