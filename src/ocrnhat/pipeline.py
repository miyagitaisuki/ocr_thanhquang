"""PDF/ảnh -> .docx (và .txt) chỉ gồm tiếng Nhật."""
from __future__ import annotations

import re
import threading
import unicodedata
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


def ascii_name(name: str) -> str:
    """Tên không dấu, chỉ chữ và số ASCII, nối bằng '_'. Tên không còn chữ nào thì là 'file'."""
    s = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "file"


def output_stem(path: Path, pages: list[int] | None, total: int) -> str:
    """Tiền tố file kết quả: OCR_<tên không dấu>_<trang đầu>_<trang cuối>."""
    nums = sorted(pages) if pages else [1, total]
    return f"OCR_{ascii_name(Path(path).stem)}_{nums[0]}_{nums[-1]}"


def default_out_dir(path: Path) -> Path:
    """Thư mục mặc định của kết quả: thư mục chứa file gốc."""
    return Path(path).parent


def process_file(path: Path, out_dir: Path | None, dpi: int = 200, pages: list[int] | None = None,
                 write_txt: bool = True, page_marker: bool = True,
                 progress: Callable[[int, int, str], None] | None = None,
                 cancel: Callable[[], bool] | None = None,
                 review: bool = False, conf_threshold: float = 0.8, use_cache: bool = True,
                 engine: str | None = None, ruby: bool = False, device: str = "auto", lang: str = "ja",
                 merge_pages: bool = True,
                 workers: int | None = None, cell_reocr: bool = True,
                 crop: tuple[int, int, int, int] | None = None, upscale: float = 1.0,
                 suspect: bool = False, suspect_threshold: float = 0.0005,
                 kana_reader: str = "") -> dict:
    from .docx_out import write_docx, write_txt as _txt
    from .cache import PageCache, file_hash
    from .layout import Table, build_page
    from concurrent.futures import ThreadPoolExecutor

    path = Path(path)
    out_dir = Path(out_dir) if out_dir else default_out_dir(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(pages) if pages else page_count(path)
    stem = output_stem(path, pages, total)
    from . import engines
    engine, why = engines.resolve_for_lang(engine or engines.DEFAULT, lang)
    from .gpu import resolve_device
    dev, dev_why = resolve_device(device)
    if progress:
        progress(0, total, f"Engine: {engine} ({why}); thiết bị: {dev} ({dev_why})")
    pre_tag = f"c{','.join(map(str, crop))}" if crop else ""
    if upscale and upscale != 1.0:
        pre_tag += f"u{upscale:g}"
    cache = PageCache(out_dir / ".cache", file_hash(path), f"{dpi}{pre_tag}", engine, engines.engine_version(engine)) if use_cache else None
    n_workers = workers or default_workers(dev)
    batch = engines.batch_size(engine)   # Chandra: số trang mỗi lần suy luận theo VRAM
    if batch > 1 or engine == "chandra":
        n_workers = 1                    # một bản model trên GPU; các trang gom thành nhóm
    from . import kana as _kana
    kana_log: list[tuple[int, np.ndarray, str]] = []   # thử nghiệm: mỗi ô kana được ghi lại để rà soát
    kana_pno = [0]
    read_one = None
    if kana_reader == "tesseract" and _kana.available():
        read_one = _kana.read_cell
    elif kana_reader == "template" and _kana.font_available():
        read_one = _kana.read_cell_template
    if read_one is not None:
        def kana_fn(crop):
            text = read_one(crop)
            kana_log.append((kana_pno[0], crop.copy(), text))
            return text
    else:
        kana_fn = None

    def reocr(crop):
        """Nhận dạng lại một ô bảng (engine của luồng gọi, lấy lười)."""
        return get_engine(engine, dev).ocr(crop, "cell.png")

    def ocr_batch(items):
        """Chạy trong luồng nền: đọc cache hoặc OCR cả nhóm trang (một lần suy luận nếu engine hỗ trợ).
        Trả về [(pno, Page, ảnh)] đúng thứ tự đầu vào."""
        got = {}
        todo = []
        for pno, img in items:
            page = cache.get(pno) if cache else None
            if page is None:
                todo.append((pno, img))
            else:
                got[pno] = page
        if todo:
            pages = get_engine(engine, dev).ocr_many([img for _, img in todo],
                                                     [f"{path.stem}_{pno}.png" for pno, _ in todo])
            for (pno, _), page in zip(todo, pages):
                if cache:
                    cache.put(pno, page)
                got[pno] = page
        return [(pno, got[pno], img) for pno, img in items]

    results, n_tables, done, sections, n_low = [], 0, 0, [], 0
    page_lines: list[tuple[int, list]] = []   # rà soát trong GUI: tọa độ từng dòng (hệ ảnh đã cắt/phóng to)
    suspect_rows: list[tuple[int, str]] = []
    # Cửa sổ trượt: tối đa 2*n_workers trang đang chờ, để không giữ cả file trong RAM
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        pending = []
        feed = ((pno, preprocess(img, crop, upscale)) for pno, img in iter_pages(path, dpi, pages))

        def groups():
            chunk = []
            for item in feed:
                chunk.append(item)
                if len(chunk) == batch:
                    yield chunk
                    chunk = []
            if chunk:
                yield chunk
        group_feed = groups()

        def submit_next() -> bool:
            if cancel and cancel():
                return False
            nxt = next(group_feed, None)
            if nxt is None:
                return False
            pending.append(pool.submit(ocr_batch, nxt))
            return True

        for _ in range(2 * n_workers):
            if not submit_next():
                break
        while pending:
            fut = pending.pop(0)               # giữ thứ tự trang
            submit_next()
            for pno, page, img in fut.result():
                kana_pno[0] = pno
                items = build_page(page, img, reocr if cell_reocr else None, kana_fn, lang=lang)
                page_lines.append((pno, [(l.x, l.y, l.x1, l.y1, float(l.conf), l.text)
                                         for b in page.blocks for l in b.lines if l.text.strip()]))
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
    docx_path = out_dir / f"{stem}.docx"
    if results:
        if merge_pages:
            from .layout import merge_pages as _merge
            results = _merge(results)
        write_docx(results, docx_path, title=None, page_marker=page_marker, ruby=ruby, page_break=not merge_pages)
        if write_txt:
            _txt(results, out_dir / f"{stem}.txt")
    suspect_path = None
    if suspect_rows:
        suspect_path = out_dir / f"{stem}_suspect.txt"
        suspect_path.write_text("\n".join(f"Trang {p} | {row}" for p, row in suspect_rows) + "\n", encoding="utf-8")
    review_path = None
    if review and sections:
        from .review import write_review
        review_path = out_dir / f"{stem}_review.html"
        write_review(sections, review_path, path.name)
    kana_review = None
    if kana_log:
        kana_review = out_dir / f"{stem}_kana_review.html"
        _kana.write_review(kana_log, kana_review)
    return {"file": str(path), "pages": done, "tables": n_tables, "docx": str(docx_path),
            "kana_review": str(kana_review) if kana_review else None,
            "review": str(review_path) if review_path else None, "low_conf": n_low,
            "suspect": str(suspect_path) if suspect_path else None, "suspect_lines": len(suspect_rows),
            "page_lines": page_lines, "crop": crop, "upscale": upscale, "conf_threshold": conf_threshold}
