"""PDF/ảnh -> .docx (và .txt) chỉ gồm tiếng Nhật."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
# Mỗi luồng giữ engine riêng: engine NDLOCR không an toàn khi nhiều luồng dùng chung một instance
# (nhận dạng lại ô bảng và OCR trang nền từng gọi cùng lúc -> kết quả trang bị rỗng, không ổn định).
_tls = threading.local()


def get_engine(name: str | None = None, device: str = "cpu"):
    from . import engines
    name = engines.resolve(name or engines.DEFAULT)[0]
    cache = getattr(_tls, "engines", None)
    if cache is None:
        cache = _tls.engines = {}
    key = (name, device)
    if key not in cache:
        cache[key] = engines.create(name, device=device)
    return cache[key]


def parse_pages(spec: str | None) -> list[int] | None:
    """'1-5,8,10-12' -> [1,2,3,4,5,8,10,11,12]"""
    if not spec or not spec.strip():
        return None
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def page_count(path: Path) -> int:
    if Path(path).suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(path)); n = len(pdf); pdf.close()
        return n
    return 1


def iter_pages(path: Path, dpi: int = 200, pages: Iterable[int] | None = None) -> Iterator[tuple[int, np.ndarray]]:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(path))
        n = len(pdf)
        for p in (sorted(set(pages)) if pages else range(1, n + 1)):
            if 1 <= p <= n:
                yield p, np.array(pdf[p - 1].render(scale=dpi / 72).to_pil().convert("RGB"))
        pdf.close()
    else:
        from PIL import Image
        yield 1, np.array(Image.open(path).convert("RGB"))


def parse_crop(spec: str | None) -> tuple[int, int, int, int] | None:
    """'x0,y0,x1,y1' (pixel, theo ảnh gốc hoặc trang đã render ở --dpi) -> bộ 4 số."""
    if not spec or not spec.strip():
        return None
    x0, y0, x1, y1 = (int(v) for v in spec.split(","))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("cần x1 > x0 và y1 > y0")
    return x0, y0, x1, y1


def preprocess(img: np.ndarray, crop=None, upscale: float = 1.0) -> np.ndarray:
    """Cắt vùng rồi phóng to. Áp dụng cho cả ảnh OCR lẫn ảnh dựng docx/rà soát (cùng hệ tọa độ)."""
    if crop:
        x0, y0, x1, y1 = crop
        img = img[max(0, y0):y1, max(0, x0):x1]
    if upscale and upscale != 1.0:
        from PIL import Image
        h, w = img.shape[:2]
        img = np.array(Image.fromarray(img).resize((round(w * upscale), round(h * upscale)), Image.LANCZOS))
    return np.ascontiguousarray(img)


def default_workers(device: str) -> int:
    """GPU: 2 luồng là đủ (session CUDA đã dùng hết nhân xử lý). CPU: nửa số nhân, 1..4."""
    if device == "cuda":
        return 2
    import os
    return max(1, min(4, (os.cpu_count() or 2) // 2))


SUSPECT_MIN_LEN = 12   # dòng ngắn (ô bảng, nhãn) thiếu ngữ cảnh nên cho nhiều dương tính giả


def _suspect_rows(items, threshold: float) -> list[str]:
    """Dòng nào có ký tự nghi ngờ thì trả về một dòng báo cáo (chỉ đánh dấu, không sửa)."""
    from .layout import Para, Table
    from .suspect import mark, scan_line

    texts = []
    for it in items:
        if isinstance(it, Table):
            texts += [c.text for c in it.cells if c.text]
        else:
            texts.append(it.text)
    rows = []
    for t in texts:
        for line in t.split("\n"):
            if len(line) < SUSPECT_MIN_LEN:
                continue
            sus = scan_line(line, threshold)
            if sus:
                detail = ", ".join(f"{x.char} ({x.prob:.4f}; gợi ý {x.alternatives})" for x in sus[:5])
                rows.append(f"{mark(line, sus)}  ← {detail}")
    return rows


def process_file(path: Path, out_dir: Path, dpi: int = 200, pages: list[int] | None = None,
                 write_txt: bool = True, page_marker: bool = True,
                 progress: Callable[[int, int, str], None] | None = None,
                 cancel: Callable[[], bool] | None = None,
                 review: bool = False, conf_threshold: float = 0.8, use_cache: bool = True,
                 engine: str | None = None, ruby: bool = False, device: str = "auto",
                 workers: int | None = None, cell_reocr: bool = True,
                 crop: tuple[int, int, int, int] | None = None, upscale: float = 1.0,
                 suspect: bool = False, suspect_threshold: float = 0.0005,
                 kana_ocr: bool = False) -> dict:
    from .docx_out import write_docx, write_txt as _txt
    from .cache import PageCache, file_hash
    from .layout import Table, build_page
    from concurrent.futures import ThreadPoolExecutor

    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(pages) if pages else page_count(path)
    from . import engines
    engine, why = engines.resolve(engine or engines.DEFAULT)
    from .gpu import resolve_device
    dev, dev_why = resolve_device(device)
    if progress:
        progress(0, total, f"Engine: {engine} ({why}); thiết bị: {dev} ({dev_why})")
    pre_tag = f"c{','.join(map(str, crop))}" if crop else ""
    if upscale and upscale != 1.0:
        pre_tag += f"u{upscale:g}"
    cache = PageCache(out_dir / ".cache", file_hash(path), f"{dpi}{pre_tag}", engine, engines.engine_version(engine)) if use_cache else None
    n_workers = workers or default_workers(dev)
    from . import kana as _kana
    kana_reader = _kana.read_cell if kana_ocr and _kana.available() else None   # thử nghiệm, cần tesseract + jpn

    def reocr(crop):
        """Nhận dạng lại một ô bảng (engine của luồng gọi, lấy lười)."""
        return get_engine(engine, dev).ocr(crop, "cell.png")

    def ocr_one(pno: int, img):
        """Chạy trong luồng nền: đọc cache hoặc OCR (engine riêng của luồng) rồi ghi cache. Trả về (pno, Page, ảnh)."""
        page = cache.get(pno) if cache else None
        if page is None:
            page = get_engine(engine, dev).ocr(img, f"{path.stem}_{pno}.png")
            if cache:
                cache.put(pno, page)
        return pno, page, img

    results, n_tables, done, sections, n_low = [], 0, 0, [], 0
    suspect_rows: list[tuple[int, str]] = []
    # Cửa sổ trượt: tối đa 2*n_workers trang đang chờ, để không giữ cả file trong RAM
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        pending = []
        feed = ((pno, preprocess(img, crop, upscale)) for pno, img in iter_pages(path, dpi, pages))

        def submit_next() -> bool:
            if cancel and cancel():
                return False
            nxt = next(feed, None)
            if nxt is None:
                return False
            pending.append(pool.submit(ocr_one, nxt[0], nxt[1]))
            return True

        for _ in range(2 * n_workers):
            if not submit_next():
                break
        while pending:
            fut = pending.pop(0)               # giữ thứ tự trang
            pno, page, img = fut.result()
            submit_next()
            items = build_page(page, img, reocr if cell_reocr else None, kana_reader)
            if suspect:
                suspect_rows.extend((pno, row) for row in _suspect_rows(items, suspect_threshold))
            if review:
                from .review import render_page
                sec, low = render_page(pno, items, page, img, conf_threshold)
                sections.append(sec); n_low += low
            n_tables += sum(isinstance(i, Table) for i in items)
            results.append((pno, items))
            done += 1
            if progress:
                progress(done, total, f"{path.name} - trang {pno}")
    docx_path = out_dir / f"{path.stem}.docx"
    if results:
        write_docx(results, docx_path, title=None, page_marker=page_marker, ruby=ruby)
        if write_txt:
            _txt(results, out_dir / f"{path.stem}.txt")
    suspect_path = None
    if suspect_rows:
        suspect_path = out_dir / f"{path.stem}_suspect.txt"
        suspect_path.write_text("\n".join(f"Trang {p} | {row}" for p, row in suspect_rows) + "\n", encoding="utf-8")
    review_path = None
    if review and sections:
        from .review import write_review
        review_path = out_dir / f"{path.stem}_review.html"
        write_review(sections, review_path, path.name)
    return {"file": str(path), "pages": done, "tables": n_tables, "docx": str(docx_path),
            "review": str(review_path) if review_path else None, "low_conf": n_low,
            "suspect": str(suspect_path) if suspect_path else None, "suspect_lines": len(suspect_rows)}
