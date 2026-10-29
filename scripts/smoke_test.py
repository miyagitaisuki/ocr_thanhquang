"""Kiểm tra nhanh: vẽ một ảnh có chữ Nhật rồi OCR (chạy trong CI trước khi build exe)."""
import sys
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from ocrnhat import core

img = Image.new("RGB", (900, 200), "white")
d = ImageDraw.Draw(img)
font = None
for f in ["C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/msgothic.ttc", "C:/Windows/Fonts/meiryo.ttc"]:
    try:
        font = ImageFont.truetype(f, 60); break
    except OSError:
        pass
if font is None:
    print("Không có font Nhật, bỏ qua kiểm tra nội dung"); sys.exit(0)
d.text((30, 60), "日本語のテストです", fill="black", font=font)
lines = core.ocr_image(np.array(img))
txt = "".join(l.text for l in lines)
print("OCR:", txt)
assert "日本語" in txt, "OCR không nhận ra chữ Nhật"
