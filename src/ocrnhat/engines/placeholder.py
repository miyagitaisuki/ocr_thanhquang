"""Engine giữ chỗ cho tiếng Anh và tiếng Việt: đã có trong danh sách engine, chưa có cài đặt.

Dùng để giao diện và dòng lệnh đã có chỗ cho ngôn ngữ mới; chọn sẽ báo chưa có engine.
"""
from __future__ import annotations

import numpy as np

from ..model import Page
from .base import OcrEngine


class _Placeholder(OcrEngine):
    lang = ""
    needs_gpu = False

    @classmethod
    def is_available(cls):
        return False, f"engine {cls.lang} chưa được phát triển"

    def __init__(self, **_):
        raise NotImplementedError(f"Engine {self.lang} chưa được phát triển.")

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:  # pragma: no cover
        raise NotImplementedError(f"Engine {self.lang} chưa được phát triển.")


class EnglishPlaceholder(_Placeholder):
    name = "ocr_en"
    version = "placeholder"
    lang = "tiếng Anh"


class VietnamesePlaceholder(_Placeholder):
    name = "ocr_vi"
    version = "placeholder"
    lang = "tiếng Việt"
