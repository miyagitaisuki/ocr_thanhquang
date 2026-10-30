"""Kiểm tra end-to-end với model thật. Bỏ qua nếu chưa có model (scripts/fetch_models.py, export_vi.py)."""
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from ocrnhat.engines.paddle import PaddleEngine
from ocrnhat.engines.viet import VietnameseEngine

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _page(text):
    try:
        font = ImageFont.truetype(FONT, 32)
    except OSError:
        pytest.skip("không có font DejaVu")
    im = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(im).text((20, 30), text, font=font, fill="black")
    return np.asarray(im)


@pytest.mark.skipif(not PaddleEngine.is_available()[0], reason="chưa có model PaddleOCR")
def test_paddle_doc_tieng_anh():
    page = PaddleEngine().ocr(_page("Invoice No. 2024-0153 Total"))
    text = "".join(l.text for b in page.blocks for l in b.lines)
    assert "Invoice" in text and "2024" in text


@pytest.mark.skipif(not VietnameseEngine.is_available()[0], reason="chưa có model VietOCR")
def test_vietocr_doc_tieng_viet():
    page = VietnameseEngine().ocr(_page("Độc lập Tự do Hạnh phúc"))
    text = " ".join(l.text for b in page.blocks for l in b.lines)
    assert "lập" in text or "Tự do" in text
