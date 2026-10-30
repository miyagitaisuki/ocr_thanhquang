"""Nơi đặt model ONNX cho engine PaddleOCR và VietOCR, và cách tìm chúng.

Model không đóng vào exe và không nằm trong repo. Thứ tự tìm: biến OCRNHAT_MODELS, thư mục models/ cạnh exe
(bản đóng gói), models/ ở gốc repo, %LOCALAPPDATA%\\OCR-Nhat\\models. Tải bằng `python scripts/fetch_models.py`
(PaddleOCR) và `python scripts/export_vi.py` (VietOCR). Xem NOTICE.md để biết nguồn và giấy phép.
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
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


# (URL, SHA-256) của model PaddleOCR tải được tự động. VietOCR không có ở đây: xuất bằng scripts/export_vi.py.
PADDLE_FILES = {
    DET: ("https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv4/ch_PP-OCRv4_det_infer.onnx",
          "d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9"),
    REC_ZH: ("https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv4/ch_PP-OCRv4_rec_infer.onnx",
             "48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b"),
    DICT_ZH: ("https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/release/2.7/ppocr/utils/ppocr_keys_v1.txt",
              "28b2362ad4ab2dc38769aa72feb535e3a9ddb3fd2a7585a05920e6393b1dc7f7"),
}
VI_FILES = [VI_CNN, VI_ENC, VI_DEC, VI_VOCAB]


def target_dir() -> Path:
    """Thư mục ghi model khi tải. Bản exe không ghi vào _MEIPASS (thư mục tạm), dùng %LOCALAPPDATA%."""
    if os.environ.get("OCRNHAT_MODELS"):
        return Path(os.environ["OCRNHAT_MODELS"])
    if getattr(sys, "_MEIPASS", None):
        local = os.environ.get("LOCALAPPDATA")
        return (Path(local) / "OCR-Nhat" / "models") if local else Path.home() / ".ocrnhat" / "models"
    return Path(__file__).resolve().parents[3] / "models"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# VietOCR: 4 file đã xuất sẵn (assets/vi-ocr/ trong repo, Apache-2.0). Cần thêm file detector của PaddleOCR.
VI_BASE = "https://raw.githubusercontent.com/miyagitaisuki/ocr_thanhquang/main/assets/vi-ocr/"
VI_FILES = {
    DET: PADDLE_FILES[DET],
    VI_CNN: (VI_BASE + VI_CNN, "e1df17f69d77ad8f7bf41c0041ecede0ce32ca13c0fbbe936e238db0e64fcc5a"),
    VI_ENC: (VI_BASE + VI_ENC, "b082f20a7edec5aec8ae750274346df30724932a74cbf71d3920fbf1d5bf4d20"),
    VI_DEC: (VI_BASE + VI_DEC, "da549f352e4ec88642db935cc3316ef32a6dfbfe7472c32c161f4900b1d9f279"),
    VI_VOCAB: (VI_BASE + VI_VOCAB, "f6a3f5998d0460b2dac9dd63e5c1289bee26eea8265dc966d1ebf532a7d8d8f5"),
}


def download_files(files: dict, progress=None, dest: Path | None = None) -> list[str]:
    """Tải các file còn thiếu, kiểm SHA-256. progress(i, n, tên, tỉ lệ_tệp) với i là chỉ số tệp (từ 0).

    Tệp đã có và đúng SHA-256 thì bỏ qua. Ném RuntimeError nếu sai SHA-256 hoặc lỗi mạng.
    """
    out = dest or target_dir()
    out.mkdir(parents=True, exist_ok=True)
    names = list(files)
    for i, name in enumerate(names):
        url, want = files[name]
        dst = out / name
        if dst.is_file() and sha256(dst) == want:
            if progress:
                progress(i, len(names), name, 1.0)
            continue
        tmp = dst.with_name(dst.name + ".part")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress:
                    progress(i, len(names), name, min(1.0, got / total) if total else 0.0)
        if sha256(tmp) != want:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"sai SHA-256 của {name}")
        tmp.replace(dst)
        if progress:
            progress(i + 1, len(names), name, 1.0)
    return names


def download_paddle(progress=None, dest: Path | None = None) -> list[str]:
    return download_files(PADDLE_FILES, progress, dest)


def download_vi(progress=None, dest: Path | None = None) -> list[str]:
    return download_files(VI_FILES, progress, dest)
