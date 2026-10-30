"""Test phân tích HTML của Chandra (không cần model, không cần GPU)."""
from ocrnhat.engines.chandra import ChandraEngine, parse_chandra_html
from ocrnhat.engines import resolve

HTML = (
    '<div data-bbox="100 50 900 120" data-label="Section-Header"><h2>第一章 日本語の基本</h2></div>'
    '<div data-bbox="100 150 900 300" data-label="Text"><p>これは本文の一段落です。</p><p>次の段落です。</p></div>'
    '<div data-bbox="100 400 900 800" data-label="Table"><table>'
    '<tr><th rowspan="2">会社</th><td colspan="2">株式会社</td></tr>'
    '<tr><td>電話</td><td>番号</td></tr>'
    '</table></div>'
    '<div data-bbox="0 0 1000 1000" data-label="Blank-Page"></div>'
)


def test_khoi_van_ban_va_tieu_de_co_toa_do_pixel():
    page = parse_chandra_html(HTML, 1000, 1000)
    head = page.blocks[0]
    body_lines = [l for b in page.blocks if b.label == "Text" for l in b.lines]
    assert head.lines[0].text == "第一章 日本語の基本" and head.lines[0].type == "タイトル本文"
    assert (head.x, head.y) == (100, 50)
    assert [l.text for l in body_lines] == ["これは本文の一段落です。", "次の段落です。"]
    # mỗi đoạn là một khối riêng, đoạn sau nằm dưới đoạn trước
    body_blocks = [b for b in page.blocks if b.label == "Text"]
    assert len(body_blocks) == 2 and body_blocks[1].y > body_blocks[0].y + body_blocks[0].h


def test_tieu_de_va_ngat_doan_qua_build_page():
    # đầu ra cuối cùng: tiêu đề là Para kind heading, hai đoạn không bị gộp
    from ocrnhat.layout import Para, build_page
    items = [i for i in build_page(parse_chandra_html(HTML, 1000, 1000)) if isinstance(i, Para)]
    assert [(p.kind, p.text) for p in items][:3] == [
        ("heading", "第一章 日本語の基本"),
        ("body", "これは本文の一段落です。"),
        ("body", "次の段落です。"),
    ]


def test_bang_co_rowspan_colspan_va_o_dung_vi_tri():
    page = parse_chandra_html(HTML, 1000, 1000)
    table = next(b for b in page.blocks if b.label == "Table")
    assert table.kind == "table"
    cells = {l.text: l for l in table.lines}
    assert set(cells) == {"会社", "株式会社", "電話", "番号"}
    # bảng có 3 cột (cột 0 do rowspan chiếm), 2 hàng; bbox 800x400 bắt đầu tại (100, 400)
    cw = 800 / 3
    assert (cells["会社"].x, cells["会社"].y) == (100, 400)
    assert cells["会社"].h == 2 * 200          # rowspan=2 kéo dài qua hai hàng
    assert cells["株式会社"].w == 2 * cw       # colspan=2 chiếm hai cột
    assert cells["株式会社"].x == 100 + cw
    assert (cells["電話"].x, cells["電話"].y) == (100 + cw, 600)
    assert (cells["番号"].x, cells["番号"].y) == (100 + 2 * cw, 600)


def test_blank_page_bi_bo_va_bbox_sai_bi_bo():
    html = '<div data-bbox="abc" data-label="Text"><p>x</p></div><div data-bbox="0 0 1000 1000" data-label="Blank-Page"></div>'
    assert parse_chandra_html(html, 1000, 1000).blocks == []


def test_bbox_theo_ti_le_anh():
    page = parse_chandra_html(HTML, 2000, 500)     # ảnh 2000x500: x nhân 2, y nhân 0.5
    assert page.blocks[0].x == 200 and page.blocks[0].y == 25


def test_engine_chua_cai_thi_auto_khong_chon_chandra(monkeypatch):
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "chandra" else real(name, *a))
    ok, why = ChandraEngine.is_available()
    assert ok is False and "pip install" in why
    assert resolve("auto")[0] == "ndlocr"


def test_khong_co_cuda_thi_chandra_khong_san_sang(monkeypatch):
    # máy có NVIDIA nhưng torch bản CPU: không được chọn Chandra (chạy CPU quá chậm)
    import torch
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    ok, why = ChandraEngine.is_available()
    assert ok is False and "CUDA" in why
    assert resolve("auto")[0] == "ndlocr"


def test_auto_khong_chon_chandra_khi_khong_co_nvidia(monkeypatch):
    # AMD/Intel hoặc không có card: nvidia-smi không có -> ndlocr, không cần kiểm tra Chandra
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert resolve("auto")[0] == "ndlocr"


def test_model_downloaded_false_khi_chua_co_cache(monkeypatch):
    import huggingface_hub
    from ocrnhat.engines import chandra as ch

    def fake(**kw):
        raise FileNotFoundError("không có trong cache")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake)
    assert ch.model_downloaded() is False
