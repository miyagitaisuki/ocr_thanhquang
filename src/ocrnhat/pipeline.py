"""PDF/ảnh -> .docx (và .txt) chỉ gồm tiếng Nhật."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        from .engine import Engine
        _engine = Engine()
    return _engine


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


def process_file(path: Path, out_dir: Path, dpi: int = 200, pages: list[int] | None = None,
                 write_txt: bool = True, page_marker: bool = True,
                 progress: Callable[[int, int, str], None] | None = None,
                 cancel: Callable[[], bool] | None = None,
                 review: bool = False, conf_threshold: float = 0.8, use_cache: bool = True) -> dict:
    from .docx_out import write_docx, write_txt as _txt
    from .cache import PageCache, file_hash
    from .layout import Table, build_page

    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(pages) if pages else page_count(path)
    eng = None
    cache = PageCache(out_dir / ".cache", file_hash(path), dpi) if use_cache else None
    results, n_tables, done, sections, n_low = [], 0, 0, [], 0
    for pno, img in iter_pages(path, dpi, pages):
        if cancel and cancel():
            break
        page = cache.get(pno) if cache else None
        if page is None:
            eng = eng or get_engine()
            page = eng.ocr(img, f"{path.stem}_{pno}.png")
            if cache:
                cache.put(pno, page)
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
        write_docx(results, docx_path, title=None, page_marker=page_marker)
        if write_txt:
            _txt(results, out_dir / f"{path.stem}.txt")
    review_path = None
    if review and sections:
        from .review import write_review
        review_path = out_dir / f"{path.stem}_review.html"
        write_review(sections, review_path, path.name)
    return {"file": str(path), "pages": done, "tables": n_tables, "docx": str(docx_path),
            "review": str(review_path) if review_path else None, "low_conf": n_low}
