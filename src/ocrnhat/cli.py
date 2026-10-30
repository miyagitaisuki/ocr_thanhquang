"""Dòng lệnh: ocrnhat file1.pdf anh.png thu_muc/ -o ketqua --pages 1-10"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import engines, pipeline
from . import gpu as gpu_mod


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
    from . import gpupack
    gpupack.activate()   # gói GPU đã cài (Chandra, torch CUDA) thì đưa vào đường dẫn import
    for st in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="ocrnhat", description="OCR PDF/ảnh, chỉ lấy tiếng Nhật, xuất Word (.docx).")
    ap.add_argument("inputs", nargs="*", help="PDF, ảnh hoặc thư mục")
    ap.add_argument("-o", "--out", default=None, help="thư mục kết quả (mặc định: thư mục chứa file gốc)")
    ap.add_argument("--pages", default="", help="ví dụ 1-5,8 (chỉ áp dụng cho PDF)")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--no-txt", action="store_true", help="không ghi kèm file .txt")
    ap.add_argument("--no-page-marker", action="store_true", help="không ghi dòng 【原本 p.N】 đầu mỗi trang")
    ap.add_argument("--review", action="store_true", help="xuất thêm *_review.html: ảnh trang cạnh text, tô đỏ chỗ độ tin cậy thấp")
    ap.add_argument("--conf", type=float, default=0.8, help="ngưỡng độ tin cậy cho --review (mặc định 0.8)")
    ap.add_argument("--engine", default=engines.DEFAULT, choices=engines.available(), help="engine OCR (mặc định auto)")
    ap.add_argument("--keep-pages", action="store_true", help="giữ nguyên từng trang (mặc định: gộp các trang thành một khối liền mạch)")
    ap.add_argument("--lang", default="ja", choices=["ja", "en", "zh", "vi", "all"], help="ja: tiếng Nhật (mặc định, NDLOCR/Chandra); en: tiếng Anh, zh: tiếng Trung (PaddleOCR); vi: tiếng Việt (VietOCR); all: mọi ngôn ngữ (chỉ Chandra)")
    ap.add_argument("--ruby", action="store_true", help="giữ furigana thành ruby thật của Word (mặc định: bỏ furigana)")
    ap.add_argument("--device", default="auto", choices=gpu_mod.DEVICES, help="auto | cpu | cuda (GPU NVIDIA, cần onnxruntime-gpu)")
    ap.add_argument("--no-cell-reocr", action="store_true", help="không nhận dạng lại các ô bảng có dòng vượt đường kẻ")
    ap.add_argument("--crop", default="", help="cắt vùng trang trước khi OCR: x0,y0,x1,y1 (pixel)")
    ap.add_argument("--upscale", type=float, default=1.0, help="phóng to ảnh trước khi OCR, ví dụ 2 cho ảnh chữ nhỏ")
    ap.add_argument("--suspect", action="store_true", help="dò chữ nghi nhận sai bằng BERT tiếng Nhật, ghi *_suspect.txt (chỉ đánh dấu; cần pip install \".[suspect]\")")
    ap.add_argument("--kana-reader", default="", choices=["", "tesseract", "template"], help="thử nghiệm: đọc ô bảng chữ kana bằng tesseract (cần lệnh tesseract + dữ liệu jpn) hoặc template (so khớp mẫu với IPAGothic); ô không chắc để trống, xuất file rà soát *_kana_review.html")
    ap.add_argument("--gpu-info", action="store_true", help="in thông tin GPU và engine sẽ được chọn rồi thoát")
    ap.add_argument("--no-cache", action="store_true", help="không dùng cache kết quả OCR theo hash file")
    ap.add_argument("--check-gpu-pack", action="store_true", help="kiểm tra pip đóng gói sẵn có cài được gói GPU không rồi thoát (dùng trong CI)")
    a = ap.parse_args(argv)
    if a.check_gpu_pack:
        try:
            gpupack.check_pip()
        except Exception as e:
            print(f"pip đóng gói lỗi: {e}")
            return 1
        print("pip đóng gói: OK")
        return 0
    if a.gpu_info:
        from . import gpu
        for g in gpu.detect():
            print(f"GPU: {g.name} | VRAM {g.vram_mb or '?'} MB | backend={g.backend}")
        print("Engine sẽ dùng: %s (%s)" % engines.resolve(a.engine))
        print("Thiết bị sẽ dùng: %s (%s)" % gpu_mod.resolve_device(a.device))
        print("onnxruntime CUDA:", "có" if gpu_mod.ort_cuda_available() else "không")
        return 0
    if not a.inputs:
        ap.error("cần ít nhất một file PDF/ảnh hoặc thư mục (xem --help)")
    try:
        crop = pipeline.parse_crop(a.crop)
    except ValueError as e:
        ap.error(str(e))
    files = collect(a.inputs)
    if not files:
        return 1
    pages = pipeline.parse_pages(a.pages)
    for f in files:
        r = pipeline.process_file(
            f, Path(a.out) if a.out else None, a.dpi, pages if f.suffix.lower() == ".pdf" else None,
            write_txt=not a.no_txt, page_marker=not a.no_page_marker,
            review=a.review, conf_threshold=a.conf, use_cache=not a.no_cache, engine=a.engine, lang=a.lang, merge_pages=not a.keep_pages, ruby=a.ruby, device=a.device, cell_reocr=not a.no_cell_reocr, crop=crop, upscale=a.upscale, suspect=a.suspect, kana_reader=a.kana_reader,
            progress=lambda d, t, m: print(f"[{d}/{t}] {m}", flush=True))
        print(f"-> {r['docx']}  ({r['pages']} trang, {r['tables']} bảng)")
        if r.get("suspect"):
            print(f"-> {r['suspect']}  ({r['suspect_lines']} dòng có chữ nghi ngờ)")
        if r.get("kana_review"):
            print(f"-> {r['kana_review']}  (rà soát ô kana)")
        if r["review"]:
            print(f"-> {r['review']}  ({r['low_conf']} mục độ tin cậy thấp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
