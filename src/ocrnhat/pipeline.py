"""PDF/ảnh -> .docx (và .txt) chỉ gồm tiếng Nhật."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
_engines: dict = {}


def get_engine(name: str | None = None, device: str = "cpu"):
    from . import engines
    name = engines.resolve(name or engines.DEFAULT)[0]
    key = (name, device)
    if key not in _engines:
        _engines[key] = engines.create(name, device=device)
    return _engines[key]


def _engine_version(name: str) -> str:
    """Phiên bản engine cho khóa cache, lấy không cần nạp model."""
    if name == "ndlocr":
        from .engines.ndlocr import NDL_COMMIT
        return NDL_COMMIT[:8]
    return "0"


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


def default_workers(device: str) -> int:
    """GPU: 2 luồng là đủ (session CUDA đã dùng hết nhân xử lý). CPU: nửa số nhân, 1..4."""
    if device == "cuda":
        return 2
    import os
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def process_file(path: Path, out_dir: Path, dpi: int = 200, pages: list[int] | None = None,
                 write_txt: bool = True, page_marker: bool = True,
                 progress: Callable[[int, int, str], None] | None = None,
                 cancel: Callable[[], bool] | None = None,
                 review: bool = False, conf_threshold: float = 0.8, use_cache: bool = True,
                 engine: str | None = None, ruby: bool = False, device: str = "auto",
                 workers: int | None = None) -> dict:
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
    cache = PageCache(out_dir / ".cache", file_hash(path), dpi, engine, _engine_version(engine)) if use_cache else None
    n_workers = workers or default_workers(dev)
    eng = get_engine(engine, dev) if not (cache and all(cache.has(p) for p in (pages or range(1, total + 1)))) else None

    def ocr_one(pno: int, img):
        """Chạy trong luồng nền: đọc cache hoặc OCR rồi ghi cache. Trả về (pno, Page, ảnh)."""
        page = cache.get(pno) if cache else None
        if page is None:
            page = eng.ocr(img, f"{path.stem}_{pno}.png")
            if cache:
                cache.put(pno, page)
        return pno, page, img

    results, n_tables, done, sections, n_low = [], 0, 0, [], 0
    # Cửa sổ trượt: tối đa 2*n_workers trang đang chờ, để không giữ cả file trong RAM
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        pending = []
        feed = iter_pages(path, dpi, pages)

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
            items = build_page(page, img)
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
    review_path = None
    if review and sections:
        from .review import write_review
        review_path = out_dir / f"{path.stem}_review.html"
        write_review(sections, review_path, path.name)
    return {"file": str(path), "pages": done, "tables": n_tables, "docx": str(docx_path),
            "review": str(review_path) if review_path else None, "low_conf": n_low}
