"""Kiểm tra nhanh trong CI: vẽ ảnh có chữ Nhật, OCR, so kết quả (tải/kiểm tra model luôn)."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ocrnhat import core

TEXT = "日本語のテストです"
img = Image.new("RGB", (1200, 260), "white")
d = ImageDraw.Draw(img)
font = None
for f in ["C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc",
          "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
    try:
        font = ImageFont.truetype(f, 90)
        print("font:", f); break
    except OSError:
        pass
if font is None:
    print("Không có font Nhật, chỉ kiểm tra model chạy được")
    core.get_engine()(np.array(img)); sys.exit(0)
d.text((40, 70), TEXT, fill="black", font=font)
arr = np.array(img)
img.save("smoke.png")
raw = core._run(arr)
print("raw:", ascii([l.text for l in raw]))
lines = core.ocr_image(arr)
txt = "".join(l.text for l in lines)
print("filtered:", ascii(txt))
if "日本語" not in txt:
    print("FAIL: OCR không nhận ra chữ Nhật"); sys.exit(1)
print("OK")
