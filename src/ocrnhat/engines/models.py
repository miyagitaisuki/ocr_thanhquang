"""Nơi đặt model ONNX cho engine PaddleOCR và VietOCR, và cách tìm chúng.

Model không đóng vào exe và không nằm trong repo. Thứ tự tìm: biến OCRNHAT_MODELS, thư mục models/ cạnh exe
(bản đóng gói), models/ ở gốc repo, %LOCALAPPDATA%\\OCR-Nhat\\models. Tải bằng `python scripts/fetch_models.py`
(PaddleOCR) và `python scripts/export_vi.py` (VietOCR). Xem NOTICE.md để biết nguồn và giấy phép.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# PaddleOCR (Apache-2.0): dò dòng PP-OCRv4 và nhận dạng PP-OCRv4 tiếng Trung (đã gồm chữ Latin)
DET = "ch_PP-OCRv4_det_infer.onnx"
REC_ZH = "ch_PP-OCRv4_rec_infer.onnx"
DICT_ZH = "ppocr_keys_v1.txt"
# VietOCR (giấy phép xem NOTICE.md): nhận dạng tiếng Việt, xuất sang ONNX lượng tử int8
VI_CNN = "vi_cnn_int8.onnx"
VI_ENC = "vi_enc_int8.onnx"
VI_DEC = "vi_dec_int8.onnx"
VI_VOCAB = "vi_vocab.txt"


def model_dirs() -> list[Path]:
    cands = []
    if os.environ.get("OCRNHAT_MODELS"):
        cands.append(Path(os.environ["OCRNHAT_MODELS"]))
    if getattr(sys, "_MEIPASS", None):
        cands.append(Path(sys._MEIPASS) / "models")
    cands.append(Path(__file__).resolve().parents[3] / "models")
    cands.append(Path.cwd() / "models")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cands.append(Path(local) / "OCR-Nhat" / "models")
    return cands


def find(name: str) -> Path | None:
    for d in model_dirs():
        p = d / name
        if p.is_file():
            return p
    return None


def missing(names: list[str]) -> list[str]:
    return [n for n in names if find(n) is None]


def target_dir() -> Path:
    """Thư mục ghi model khi tải: thư mục đầu tiên có thể ghi."""
    return model_dirs()[0]
