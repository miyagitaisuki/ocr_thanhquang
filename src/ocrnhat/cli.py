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
    ap.add_argument("--lang", default="ja", choices=["ja", "en", "zh", "vi"], help="ja: tiếng Nhật (mặc định, NDLOCR); en: tiếng Anh, zh: tiếng Trung (PaddleOCR); vi: tiếng Việt (VietOCR)")
    ap.add_argument("--ruby", action="store_true", help="giữ furigana thành ruby thật của Word (mặc định: bỏ furigana)")
    ap.add_argument("--device", default="auto", choices=gpu_mod.DEVICES, help="auto | cpu | cuda (GPU NVIDIA, cần onnxruntime-gpu)")
    ap.add_argument("--no-vi-fix", action="store_true", help="tắt hậu xử lý tiếng Việt (bỏ nhiễu dấu mộc, sửa dấu theo tần suất)")
    ap.add_argument("--no-cell-reocr", action="store_true", help="không nhận dạng lại các ô bảng có dòng vượt đường kẻ")
    ap.add_argument("--crop", default="", help="cắt vùng trang trước khi OCR: x0,y0,x1,y1 (pixel); nhiều vùng cách bằng \";\"")
    ap.add_argument("--upscale", type=float, default=1.0, help="phóng to ảnh trước khi OCR, ví dụ 2 cho ảnh chữ nhỏ")
    ap.add_argument("--suspect", action="store_true", help="dò chữ nghi nhận sai bằng BERT tiếng Nhật, ghi *_suspect.txt (chỉ đánh dấu; cần pip install \".[suspect]\")")
    ap.add_argument("--kana-reader", default="", choices=["", "tesseract", "template"], help="thử nghiệm: đọc ô bảng chữ kana bằng tesseract (cần lệnh tesseract + dữ liệu jpn) hoặc template (so khớp mẫu với IPAGothic); ô không chắc để trống, xuất file rà soát *_kana_review.html")
    ap.add_argument("--markdown", action="store_true", help="xuất thêm *.md có đánh dấu theo quy tắc (tiêu đề, bảng, ⟦?…⟧ chỗ nghi ngờ) để nhờ LLM hiệu đính, kèm ocr_markdown_rules.md")
    ap.add_argument("--md-conf", type=float, default=0.8, help="ngưỡng độ tin cậy để gắn ⟦?…⟧ trong file .md (mặc định 0.8)")
    ap.add_argument("--md-rules", nargs="?", const="-", default=None, metavar="FILE", help="xuất quy tắc đánh dấu Markdown (để dán vào chỉ dẫn LLM) ra FILE hoặc màn hình rồi thoát")
    ap.add_argument("--gpu-info", action="store_true", help="in thông tin GPU và engine sẽ được chọn rồi thoát")
    ap.add_argument("--gpu-install", action="store_true", help="tải và cài gói GPU (CUDA/cuDNN, ~1,3 GB) rồi thoát")
    ap.add_argument("--gpu-status", action="store_true", help="cho biết gói GPU đã cài chưa rồi thoát")
    ap.add_argument("--no-cache", action="store_true", help="không dùng cache kết quả OCR theo hash file")
    a = ap.parse_args(argv)
    if a.md_rules is not None:
        from .markdown_out import RULES_MD, write_rules
        if a.md_rules == "-":
            print(RULES_MD)
        else:
            write_rules(Path(a.md_rules)); print(f"-> {a.md_rules}")
        return 0
    if a.gpu_status or a.gpu_install:
        from . import gpu_pack
        if a.gpu_install:
            ok, why = gpu_pack.supported()
            if not ok:
                print(f"Không cài được: {why}")
                return 1
            print(gpu_pack.install(progress=lambda t, f: print(f"{t} ({max(0, int(100 * f))}%)", flush=True)))
        print("Gói GPU:", "đã cài" if gpu_pack.installed() else "chưa cài", f"(phiên bản {gpu_pack.M.PACK_VERSION})")
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
        crops = pipeline.parse_crops(a.crop)
        crop = crops[0] if crops and len(crops) == 1 else crops
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
            review=a.review, conf_threshold=a.conf, use_cache=not a.no_cache, engine=a.engine, lang=a.lang, merge_pages=not a.keep_pages, ruby=a.ruby, device=a.device, cell_reocr=not a.no_cell_reocr, vi_fix=not a.no_vi_fix, crop=crop, upscale=a.upscale, suspect=a.suspect, kana_reader=a.kana_reader, markdown=a.markdown, md_conf=a.md_conf,
            progress=lambda d, t, m: print(f"[{d}/{t}] {m}", flush=True))
        print(f"-> {r['docx']}  ({r['pages']} trang, {r['tables']} bảng)")
        if r.get("markdown"):
            print(f"-> {r['markdown']}  (Markdown để hiệu đính; quy tắc: {r['md_rules']})")
        if r.get("suspect"):
            print(f"-> {r['suspect']}  ({r['suspect_lines']} dòng có chữ nghi ngờ)")
        if r.get("kana_review"):
            print(f"-> {r['kana_review']}  (rà soát ô kana)")
        if r["review"]:
            print(f"-> {r['review']}  ({r['low_conf']} mục độ tin cậy thấp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
