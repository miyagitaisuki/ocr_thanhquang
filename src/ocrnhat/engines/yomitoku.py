"""Engine YomiToku (tiếng Nhật, thử nghiệm để đối chiếu với NDLOCR): dò dòng DBNet v2.1 + nhận dạng PARSeq v2.

Giấy phép YomiToku là CC BY-NC-SA 4.0 (phi thương mại, phải chia sẻ lại). Vì vậy engine này:
- KHÔNG nằm trong requirements.txt và KHÔNG đóng vào exe; cài bằng `pip install ".[yomitoku]"`.
- Model tải từ Hugging Face khi chạy lần đầu (cache của thư viện yomitoku).
Chạy CPU mặc định; `--device cuda` chỉ dùng khi PyTorch có CUDA.
"""
from __future__ import annotations

import importlib.util

import cv2
import numpy as np

from ..model import Page
from .base import OcrEngine
from .ocr_onnx import boxes_to_page, sort_boxes


class YomitokuEngine(OcrEngine):
    name = "yomitoku"
    version = "yomitoku-0.15.1-dbnetv2_1-parseqv2-1"
    lang = "ja"

    @classmethod
    def is_available(cls):
        if importlib.util.find_spec("yomitoku") is None:
            return False, "chưa cài yomitoku: pip install \".[yomitoku]\" (CC BY-NC-SA, không đóng gói vào exe)"
        return True, ""

    def __init__(self, device: str = "cpu", **_):
        ok, why = self.is_available()
        if not ok:
            raise ImportError(why)
        from yomitoku import OCR   # import lười: torch nặng, chỉ nạp khi dùng engine này

        dev = "cuda" if device == "cuda" else "cpu"
        self.ocr_model = OCR(device=dev, visualize=False)

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:
        h, w = img_rgb.shape[:2]
        bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)   # YomiToku nhận ảnh BGR (cv2)
        result, _ = self.ocr_model(bgr)
        items = []
        for word in result.words:
            pts = np.asarray(word.points if hasattr(word, "points") else word["points"], dtype=np.float32).reshape(-1, 2)
            text = word.content if hasattr(word, "content") else word["content"]
            conf = word.rec_score if hasattr(word, "rec_score") else word["rec_score"]
            if text and text.strip():
                items.append((pts, text, float(conf)))
        # sort_boxes giữ nguyên đối tượng mảng, nên ánh xạ ngược theo id() là an toàn
        by_id = {id(it[0]): it for it in items}
        ordered = [by_id[id(b)] for b in sort_boxes([it[0] for it in items])]
        return boxes_to_page(ordered, w, h)
