"""Tải mô hình PaddleOCR và VietOCR (ONNX, Apache-2.0) vào thư mục models/ và kiểm SHA-256.

Chạy: python scripts/fetch_models.py [--dir DUONG_DAN]. Mặc định ghi vào models/ ở gốc repo (đã gitignore).
Cùng logic với nút "Tải model OCR" trong GUI. Tải cả mô hình VietOCR (tiếng Việt) từ assets/vi-ocr/.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ocrnhat.engines.models import download_paddle, download_vi  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "models"))
    a = ap.parse_args()

    def show(i, n, name, frac):
        print(f"[{i}/{n}] {name} {round(100 * frac)}%", end="\r" if frac < 1 else "\n", flush=True)

    try:
        download_paddle(progress=show, dest=Path(a.dir))
        download_vi(progress=show, dest=Path(a.dir))
    except RuntimeError as e:
        print("LỖI:", e)
        return 1
    print("Đã có đủ mô hình PaddleOCR và VietOCR trong", a.dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
