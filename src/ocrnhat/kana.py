"""Đọc ô bảng chữ kana bằng Tesseract (tùy chọn, chỉ khi máy có lệnh tesseract và dữ liệu jpn).
Engine NDLOCR không đọc đáng tin từng chữ kana trong ô lưới; Tesseract đọc tốt hơn khi chỉ lấy nét đen."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

_THRESH = 185               # nét kana xám khoảng 120–160 trên nền trắng; nền hồng và romaji sáng hơn


def available() -> bool:
    return shutil.which("tesseract") is not None


def read_cell(cell_rgb: np.ndarray) -> str:
    """Trả về đúng một ký tự kana, hoặc chuỗi rỗng nếu không chắc."""
    h, w = cell_rgb.shape[:2]
    # chữ kana nằm ở nửa trái ô, phía trên giữa; romaji hồng nằm bên phải
    crop = cell_rgb[8:h - 8, 8:max(9, int(0.5 * w))]
    if crop.size == 0:
        return ""
    gray = cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_RGB2GRAY)
    out = np.where(gray < _THRESH, 0, 255).astype(np.uint8)
    out = cv2.resize(out, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    out = cv2.copyMakeBorder(out, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "cell.png"
        Image.fromarray(out).save(p)
        res = subprocess.run(["tesseract", str(p), "stdout", "-l", "jpn", "--psm", "10"],
                             capture_output=True, text=True, timeout=20)
    text = "".join(ch for ch in res.stdout if ch.strip())
    return text if _is_kana(text) else ""


def _is_kana(ch: str) -> bool:
    return len(ch) == 1 and (0x3040 <= ord(ch) <= 0x30FF)
