"""Bộ đọc ô kana bằng so khớp mẫu (kana.read_cell_template); cần font IPAGothic, bỏ qua nếu không có."""
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from ocrnhat import kana

pytestmark = pytest.mark.skipif(not kana.font_available(), reason="không có font IPAGothic")


def _cell_with(ch: str) -> np.ndarray:
    """Ô 170×67 giống trang sách: chữ kana đen ở nửa trái, romaji hồng bên phải."""
    im = Image.new("RGB", (170, 67), (255, 255, 255))
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(next(f for f in kana._FONT_PATHS if __import__("pathlib").Path(f).is_file()), 40)
    d.text((22, 12), ch, font=font, fill=(60, 60, 60))
    d.text((110, 30), "ka", font=ImageFont.truetype(next(f for f in kana._FONT_PATHS if __import__("pathlib").Path(f).is_file()), 20), fill=(200, 90, 120))
    return np.array(im)


@pytest.mark.parametrize("ch", ["か", "ざ", "ど"])
def test_doc_dung_chu_kana_tu_mau(ch):
    assert kana.read_cell_template(_cell_with(ch)) == ch


def test_chu_kho_phan_biet_thi_de_trong_chu_khong_doan_sai():
    # ぱ và ば chỉ khác dấu tròn nhỏ: khi không chắc thì để trống, không được trả về chữ sai
    assert kana.read_cell_template(_cell_with("ぱ")) in ("ぱ", "")


def test_o_trong_tra_ve_rong():
    blank = np.full((67, 170, 3), 255, np.uint8)
    assert kana.read_cell_template(blank) == ""


def test_font_di_kem_goi_ton_tai():
    from pathlib import Path
    bundled = Path(kana.__file__).parent / "fonts" / "ipag.ttf"
    assert bundled.is_file()
    assert (bundled.parent / "IPA_FONT_LICENSE.txt").is_file()
