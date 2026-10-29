"""Dòng lệnh: ocrnhat file1.pdf anh.png thu_muc/ -o ketqua --pages 1-10"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import core


def collect(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(f for f in p.iterdir() if f.suffix.lower() == ".pdf" or f.suffix.lower() in core.IMAGE_EXT)
        elif p.exists():
            out.append(p)
        else:
            print(f"Không thấy: {p}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252, tránh lỗi khi in tiếng Nhật
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="ocrnhat", description="OCR PDF/ảnh, chỉ lấy tiếng Nhật.")
    ap.add_argument("inputs", nargs="+", help="PDF, ảnh hoặc thư mục")
    ap.add_argument("-o", "--out", default="ocr_output", help="thư mục kết quả")
    ap.add_argument("--pages", default="", help="ví dụ 1-5,8 (chỉ áp dụng cho PDF)")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--keep-furigana", action="store_true", help="không loại furigana")
    ap.add_argument("--no-denoise", action="store_true", help="tắt làm sạch nền")
    a = ap.parse_args(argv)
    files = collect(a.inputs)
    if not files:
        return 1
    pages = core.parse_pages(a.pages)
    for f in files:
        def prog(d, t, msg):
            print(f"[{d}/{t}] {msg}", flush=True)
        r = core.process_file(f, Path(a.out), a.dpi, pages if f.suffix.lower() == ".pdf" else None,
                              not a.no_denoise, drop_furigana=not a.keep_furigana, progress=prog)
        print(f"-> {r['txt']}  ({r['lines']} dòng)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
