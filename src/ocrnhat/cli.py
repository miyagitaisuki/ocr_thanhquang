"""Dòng lệnh: ocrnhat file1.pdf anh.png thu_muc/ -o ketqua --pages 1-10"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import engines, pipeline


def collect(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(f for f in p.iterdir() if f.suffix.lower() == ".pdf" or f.suffix.lower() in pipeline.IMAGE_EXT)
        elif p.exists():
            out.append(p)
        else:
            print(f"Không thấy: {p}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="ocrnhat", description="OCR PDF/ảnh, chỉ lấy tiếng Nhật, xuất Word (.docx).")
    ap.add_argument("inputs", nargs="*", help="PDF, ảnh hoặc thư mục")
    ap.add_argument("-o", "--out", default="ocr_output", help="thư mục kết quả")
    ap.add_argument("--pages", default="", help="ví dụ 1-5,8 (chỉ áp dụng cho PDF)")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--no-txt", action="store_true", help="không ghi kèm file .txt")
    ap.add_argument("--no-page-marker", action="store_true", help="không ghi dòng 【原本 p.N】 đầu mỗi trang")
    ap.add_argument("--review", action="store_true", help="xuất thêm *_review.html: ảnh trang cạnh text, tô đỏ chỗ độ tin cậy thấp")
    ap.add_argument("--conf", type=float, default=0.8, help="ngưỡng độ tin cậy cho --review (mặc định 0.8)")
    ap.add_argument("--engine", default=engines.DEFAULT, choices=engines.available(), help="engine OCR (mặc định ndlocr)")
    ap.add_argument("--ruby", action="store_true", help="giữ furigana thành ruby thật của Word (mặc định: bỏ furigana)")
    ap.add_argument("--gpu-info", action="store_true", help="in thông tin GPU và engine sẽ được chọn rồi thoát")
    ap.add_argument("--no-cache", action="store_true", help="không dùng cache kết quả OCR theo hash file")
    a = ap.parse_args(argv)
    if a.gpu_info:
        from . import gpu
        for g in gpu.detect():
            print(f"GPU: {g.name} | VRAM {g.vram_mb or '?'} MB | backend={g.backend}")
        print("Engine sẽ dùng: %s (%s)" % engines.resolve(a.engine))
        return 0
    files = collect(a.inputs)
    if not files:
        return 1
    pages = pipeline.parse_pages(a.pages)
    for f in files:
        r = pipeline.process_file(
            f, Path(a.out), a.dpi, pages if f.suffix.lower() == ".pdf" else None,
            write_txt=not a.no_txt, page_marker=not a.no_page_marker,
            review=a.review, conf_threshold=a.conf, use_cache=not a.no_cache, engine=a.engine, ruby=a.ruby,
            progress=lambda d, t, m: print(f"[{d}/{t}] {m}", flush=True))
        print(f"-> {r['docx']}  ({r['pages']} trang, {r['tables']} bảng)")
        if r["review"]:
            print(f"-> {r['review']}  ({r['low_conf']} mục độ tin cậy thấp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
