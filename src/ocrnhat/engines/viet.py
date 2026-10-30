"""Engine tiếng Việt: dò dòng bằng PP-OCRv4 det (như engine PaddleOCR), nhận dạng bằng VietOCR (MIT/Apache, xem NOTICE.md).

VietOCR là seq2seq (VGG + GRU + attention). Mô hình được xuất sang ONNX (int8) bằng scripts/export_vi.py
và giải mã tham lam (greedy) bằng onnxruntime, nên không cần torch trong exe.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from ..model import Page
from . import models
from .base import OcrEngine
from .ocr_onnx import DbDetector, boxes_to_page, crop_quad, session, sort_boxes

REQUIRED = [models.DET, models.VI_CNN, models.VI_ENC, models.VI_DEC, models.VI_VOCAB]
SOS, EOS, MAX_LEN = 1, 2, 128


def _resize_for_vi(img: np.ndarray, height: int = 32, min_w: int = 32, max_w: int = 512) -> np.ndarray:
    """Giống vietocr.process_image: cao 32, rộng làm tròn bội 10, kẹp trong [32, 512]."""
    h, w = img.shape[:2]
    nw = int(height * w / h)
    nw = math.ceil(nw / 10) * 10
    nw = min(max(nw, min_w), max_w)
    return cv2.resize(img, (nw, height), interpolation=cv2.INTER_LANCZOS4)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


class VietRecognizer:
    def __init__(self):
        self.cnn = session(models.find(models.VI_CNN))
        self.enc = session(models.find(models.VI_ENC))
        self.dec = session(models.find(models.VI_DEC))
        self.chars = [l.rstrip("\n") for l in open(models.find(models.VI_VOCAB), encoding="utf-8")]
        # bảng ký tự của VietOCR: 0..3 là token đặc biệt, ký tự thật từ 4 (xem vietocr.model.vocab.Vocab)
        self.i2c = {i + 4: c for i, c in enumerate(self.chars)}

    def __call__(self, crop_rgb: np.ndarray) -> tuple[str, float]:
        r = _resize_for_vi(crop_rgb).astype(np.float32) / 255.0
        x = r.transpose(2, 0, 1)[None]
        conv = self.cnn.run(None, {self.cnn.get_inputs()[0].name: x})[0]            # N,C,H,W
        feat = conv.transpose(0, 1, 3, 2).reshape(conv.shape[0], conv.shape[1], -1).transpose(2, 0, 1)
        enc_out, hid = self.enc.run(None, {"feat": feat})
        tok = np.array([SOS], dtype=np.int64)
        out, confs = [SOS], []
        for _ in range(MAX_LEN):
            pred, hid = self.dec.run(None, {"tok": tok, "hid": hid, "enc": enc_out})
            p = _softmax(pred[0])
            nxt = int(p.argmax())
            if nxt == EOS:
                break
            confs.append(float(p[nxt]))
            out.append(nxt)
            tok = np.array([nxt], dtype=np.int64)
        text = "".join(self.i2c.get(i, "") for i in out[1:])
        return text, (sum(confs) / len(confs) if confs else 0.0)


class VietnameseEngine(OcrEngine):
    name = "ocr_vi"
    version = "vietocr-onnx-int8-1"
    lang = "vi"

    @classmethod
    def is_available(cls):
        miss = models.missing(REQUIRED)
        return (not miss), ("thiếu model: " + ", ".join(miss) + " (tải trong tab AI powered)" if miss else "")

    def __init__(self, device: str = "cpu", **_):
        ok, why = self.is_available()
        if not ok:
            raise FileNotFoundError(why)
        self.det = DbDetector(models.find(models.DET))
        self.rec = VietRecognizer()

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:
        h, w = img_rgb.shape[:2]
        items = []
        for box in sort_boxes(self.det.detect(img_rgb)):
            text, conf = self.rec(crop_quad(img_rgb, box))
            if text.strip():
                items.append((box, text, conf))
        return boxes_to_page(items, w, h)
