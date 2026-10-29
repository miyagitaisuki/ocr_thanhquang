"""Giao diện chung của engine OCR. Mọi engine trả về `Page` (xem model.py); layout.py không biết engine nào đã chạy."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..model import Page


class OcrEngine(ABC):
    name: str = ""
    version: str = ""   # đưa vào khóa cache: đổi model/commit thì cache cũ không bị dùng lại

    @abstractmethod
    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:
        """Nhận ảnh trang RGB, trả về khối/dòng có tọa độ pixel và độ tin cậy 0..1."""
