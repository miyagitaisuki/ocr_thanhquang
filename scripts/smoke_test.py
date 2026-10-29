"""Kiểm tra nhanh trong CI: vẽ ảnh có chữ Nhật + một bảng, OCR, dựng docx, so kết quả."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TEXT = "日本語のテストです。これは確認用の文章です。"
img = Image.new("RGB", (1700, 700), "white")
d = ImageDraw.Draw(img)
font = None
for f in ["C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc",
          "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
    try:
        font = ImageFont.truetype(f, 56); print("font:", f); break
    except OSError:
        pass
if font is None:
    print("Không có font Nhật"); sys.exit(1)
d.text((60, 50), TEXT, fill="black", font=font)
# bảng 2x2 có đường kẻ
x0, y0, cw, rh = 60, 250, 700, 130
for i in range(3):
    d.line([(x0, y0 + i * rh), (x0 + 2 * cw, y0 + i * rh)], fill="black", width=3)
    d.line([(x0 + i * cw, y0), (x0 + i * cw, y0 + 2 * rh)], fill="black", width=3)
for r, row in enumerate([("会社", "株式会社"), ("銀行", "電話番号")]):
    for c, t in enumerate(row):
        d.text((x0 + c * cw + 40, y0 + r * rh + 35), t, fill="black", font=font)
img.save("smoke.png")

from ocrnhat import pipeline
from ocrnhat.layout import Table
from ocrnhat.engine import Engine
from ocrnhat.layout import build_page
arr = np.array(img)
items = build_page(Engine().ocr(arr), arr)
txt = "".join(i.text for i in items if not isinstance(i, Table))
tables = [i for i in items if isinstance(i, Table)]
print("văn bản:", ascii(txt)); print("số bảng:", len(tables))
ok = "日本語" in txt
if tables:
    cells = {(c.r, c.c): c.text for c in tables[0].cells}
    print("bảng:", ascii(cells))
    ok = ok and "会社" in cells.get((0, 0), "") and "銀行" in cells.get((1, 0), "") and len(cells) >= 4
else:
    ok = False
print("OK" if ok else "FAIL"); sys.exit(0 if ok else 1)
