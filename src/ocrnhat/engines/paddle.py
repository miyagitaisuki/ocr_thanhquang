"""Engine PaddleOCR dùng chung cho tiếng Anh và tiếng Trung: PP-OCRv4 det + rec ONNX (Apache-2.0), chạy CPU.

Dò dòng bằng DB, nhận dạng CTC với từ điển ppocr_keys_v1 (đã gồm chữ Latin, số và ký hiệu).
Model: `python scripts/fetch_models.py`. Xem engines/models.py.
"""
from __future__ import annotations

import cv2
import numpy as np

from ..model import Page
from . import models
from .base import OcrEngine
from .ocr_onnx import DbDetector, boxes_to_page, crop_quad, ctc_greedy, session, sort_boxes

REQUIRED = [models.DET, models.REC_ZH, models.DICT_ZH]


def load_chars(path) -> list[str]:
    keys = [l.rstrip("\n") for l in open(path, encoding="utf-8")]
    return ["blank"] + keys + [" "]   # 0 = blank CTC, ký tự cuối là khoảng trắng


class PaddleEngine(OcrEngine):
    name = "paddle"
    version = "ppocrv4-onnx-1"
    lang = "en,zh"

    @classmethod
    def is_available(cls):
        miss = models.missing(REQUIRED)
        return (not miss), ("thiếu model: " + ", ".join(miss) + " (tải trong tab AI powered)" if miss else "")

    def __init__(self, device: str = "cpu", **_):
        ok, why = self.is_available()
        if not ok:
            raise FileNotFoundError(why)
        self.det = DbDetector(models.find(models.DET))
        self.rec = session(models.find(models.REC_ZH))
        self.rec_in = self.rec.get_inputs()[0].name
        self.chars = load_chars(models.find(models.DICT_ZH))

    def _rec(self, crop: np.ndarray) -> tuple[str, float]:
        h, w = crop.shape[:2]
        nw = max(16, min(int(round(w * 48 / h)), 3200))
        r = cv2.resize(crop, (nw, 48))
        x = ((r.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[None]
        probs = self.rec.run(None, {self.rec_in: x.astype(np.float32)})[0][0]
        return ctc_greedy(probs, self.chars)

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:
        h, w = img_rgb.shape[:2]
        items = []
        for box in sort_boxes(self.det.detect(img_rgb)):
            text, conf = self._rec(crop_quad(img_rgb, box))
            if text.strip():
                items.append((box, text, conf))
        return boxes_to_page(items, w, h)
