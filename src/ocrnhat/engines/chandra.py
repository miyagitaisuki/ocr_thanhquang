"""PLACEHOLDER: engine Chandra OCR 2 (datalab-to/chandra-ocr-2, VLM ~4-5B, cần GPU, trọng số OpenRAIL-M sửa đổi).

Chưa cài đặt. Khi làm:
  1. Cài tùy chọn `pip install chandra-ocr` (không đóng vào exe); chạy HuggingFace cục bộ hoặc máy chủ vLLM.
  2. Gửi ảnh trang, nhận Markdown/HTML; phân tích thành Block("text"/"table") + Line trong `Page`.
     Bảng HTML có rowspan/colspan -> Block("table") kèm Line theo ô, hoặc mở rộng model.py để mang cấu trúc ô sẵn.
  3. VLM không có độ tin cậy từng dòng: đặt conf cố định hoặc đối chiếu với NDLOCR để đánh dấu chỗ lệch.
  4. Đặt `version` theo id model + revision để khóa cache đúng.
"""
from __future__ import annotations

import numpy as np

from ..model import Page
from .base import OcrEngine


class ChandraEngine(OcrEngine):
    name = "chandra"
    version = "placeholder"
    needs_gpu = True

    @classmethod
    def is_available(cls):
        # TODO: kiểm tra đã cài chandra-ocr + backend (torch CUDA/ROCm, DirectML hoặc máy chủ vLLM)
        return False, "chưa cài đặt"

    def __init__(self, **_):
        raise NotImplementedError("Engine Chandra chưa được cài đặt (xem docstring engines/chandra.py).")

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:  # pragma: no cover
        raise NotImplementedError
