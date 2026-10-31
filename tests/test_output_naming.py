"""Tên file kết quả ocr_<tên không dấu>_<trang đầu>_<trang cuối> và thư mục mặc định cạnh file gốc. Không cần model."""
from pathlib import Path

import pytest
from PIL import Image

from ocrnhat import pipeline


@pytest.mark.parametrize("name,want", [
    ("Hợp đồng số 12", "Hop_dong_so_12"),
    ("Đề án ĐỒ", "De_an_DO"),
    ("sổ tay (bản 2).pdf", "so_tay_ban_2_pdf"),
    ("scan", "scan"),
    ("売上", "file"),
])
def test_ten_khong_dau(name, want):
    assert pipeline.ascii_name(name) == want


def test_tien_to_theo_trang():
    p = Path("/x/Hợp đồng.pdf")
    assert pipeline.output_stem(p, None, 12) == "ocr_Hop_dong_1_12"
    assert pipeline.output_stem(p, [5, 3, 4], 12) == "ocr_Hop_dong_3_5"
    assert pipeline.output_stem(Path("/x/anh.png"), None, 1) == "ocr_anh_1_1"


def test_mac_dinh_canh_file_goc(tmp_path, monkeypatch):
    src = tmp_path / "tài liệu"
    src.mkdir()
    pdf = src / "Báo cáo.pdf"
    Image.new("RGB", (800, 1000), "white").save(pdf, "PDF", resolution=200)

    from ocrnhat.engines.base import OcrEngine
    from ocrnhat.model import Page

    class _E(OcrEngine):
        name = version = "fake"

        def __init__(self, device="cpu"):
            pass

        def ocr(self, img, name="page.png"):
            return Page(img.shape[1], img.shape[0], [])

    from ocrnhat import engines
    monkeypatch.setattr(engines, "create", lambda name, device="cpu": _E())
    monkeypatch.setattr(engines, "resolve", lambda name=None: (name if name not in (None, "auto") else "ndlocr", "test"))
    monkeypatch.setattr(pipeline, "_tls", __import__("threading").local())
    r = pipeline.process_file(pdf, None, 200, None, device="cpu", use_cache=False)
    assert Path(r["docx"]).parent == src
    assert Path(r["docx"]).name == "ocr_Bao_cao_1_1.docx"
