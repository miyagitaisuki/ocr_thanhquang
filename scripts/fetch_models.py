"""Tải model PaddleOCR (ONNX, Apache-2.0) vào thư mục models/ và kiểm tra SHA-256.

Chạy: python scripts/fetch_models.py [--dir DUONG_DAN]. Mặc định ghi vào models/ ở gốc repo (đã gitignore).
Model VietOCR không tải ở đây: chạy scripts/export_vi.py.
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "ch_PP-OCRv4_det_infer.onnx": ("https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv4/ch_PP-OCRv4_det_infer.onnx",
                                   "d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9"),
    "ch_PP-OCRv4_rec_infer.onnx": ("https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv4/ch_PP-OCRv4_rec_infer.onnx",
                                   "48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b"),
    "ppocr_keys_v1.txt": ("https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/release/2.7/ppocr/utils/ppocr_keys_v1.txt",
                          "28b2362ad4ab2dc38769aa72feb535e3a9ddb3fd2a7585a05920e6393b1dc7f7"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "models"))
    a = ap.parse_args()
    out = Path(a.dir)
    out.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, (url, want) in FILES.items():
        dst = out / name
        if not (dst.is_file() and sha256(dst) == want):
            print(f"tải {name} ...")
            tmp = dst.with_suffix(dst.suffix + ".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.replace(dst)
        got = sha256(dst)
        ok = got == want
        bad += not ok
        print(("OK   " if ok else "SAI  ") + name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
