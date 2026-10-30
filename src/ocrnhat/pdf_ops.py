"""Công cụ PDF: xoay trang, nén file và tự động xử lý file trong thư mục (pypdf, Pillow; đều giấy phép BSD/HPND).

Thư mục tự động dùng vòng lặp quét (không cần thư viện theo dõi hệ thống). File mới được xử lý sau khi kích thước
không đổi giữa hai lần quét, để không đọc file đang được ghi. Kết quả đi vào thư mục con "da_xu_ly".
"""
from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path
from typing import Callable

from pypdf import PdfReader, PdfWriter

from .pdf_extract import ExtractOptions, _check_version, _finish, _open, _target, parse_page_spec

log = logging.getLogger("ocrnhat.pdf_ops")
ROTATIONS = (90, 180, 270)
OUT_SUBDIR = "da_xu_ly"


def rotate_pdf(src: Path, angle: int, pages: str = "", out_dir: Path | None = None,
               opts: ExtractOptions | None = None) -> Path:
    """Xoay các trang (mặc định: tất cả) theo chiều kim đồng hồ: 90, 180 hoặc 270 độ. Ghi ra file *_xoay.pdf."""
    opts = opts or ExtractOptions()
    _check_version(opts)
    if angle not in ROTATIONS:
        raise ValueError("Góc xoay phải là 90, 180 hoặc 270")
    src = Path(src)
    reader = _open(src)
    total = len(reader.pages)
    chosen = {p for g in parse_page_spec(pages, total) for p in g} if pages.strip() else set(range(1, total + 1))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages, 1):
        writer.add_page(page)
        if i in chosen:
            writer.pages[-1].rotate(angle)
    return _finish(writer, f"{src.stem}_xoay", Path(out_dir) if out_dir else src.parent, opts)


def compress_pdf(src: Path, image_quality: int | None = 75, out_dir: Path | None = None,
                 opts: ExtractOptions | None = None) -> Path:
    """Nén: gộp đối tượng trùng, nén nội dung trang và (nếu image_quality) nén lại ảnh JPEG.
    image_quality = None chỉ làm nén không mất dữ liệu. Ghi ra file *_nen.pdf."""
    opts = opts or ExtractOptions(compress=True)
    _check_version(opts)
    if image_quality is not None and not 1 <= image_quality <= 95:
        raise ValueError("Chất lượng ảnh phải từ 1 đến 95")
    src = Path(src)
    reader = _open(src)
    writer = PdfWriter(clone_from=reader)
    if image_quality is not None:
        _recompress_images(writer, image_quality)
    for page in writer.pages:
        page.compress_content_streams()
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    writer.pdf_header = f"%PDF-{opts.pdf_version}"
    out_dir = Path(out_dir) if out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    target = _target(out_dir, f"{src.stem}_nen", opts.overwrite)
    with open(target, "wb") as f:
        writer.write(f)
    return target


def _recompress_images(writer: PdfWriter, quality: int) -> None:
    """Ảnh RGB không trong suốt được ghi lại dạng JPEG. Ảnh lỗi hoặc có kênh alpha thì giữ nguyên."""
    from PIL import Image
    for page in writer.pages:
        for img in page.images:
            try:
                pil = img.image
                if pil is None or pil.mode not in ("RGB", "L"):
                    continue
                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=quality)
                if buf.tell() >= len(img.data):   # không nhỏ hơn thì giữ ảnh cũ
                    continue
                buf.seek(0)
                img.replace(Image.open(buf).copy(), quality=quality)
            except Exception:
                log.debug("Không nén được một ảnh, giữ nguyên", exc_info=True)


def watch_folder(folder: Path, process: Callable[[Path], Path | None], stop: threading.Event,
                 interval: float = 2.0, on_result: Callable[[Path, Path | None, Exception | None], None] | None = None) -> None:
    """Quét `folder` mỗi `interval` giây. File PDF mới (kích thước ổn định qua hai lần quét) được đưa vào
    process(file). Chạy đến khi `stop` được đặt. Thư mục con (kể cả da_xu_ly) không được quét."""
    folder = Path(folder)
    seen: dict[Path, tuple[int, float]] = {}   # file -> (kích thước, thời điểm sửa) lần quét trước
    done: set[Path] = set()
    while not stop.is_set():
        current: dict[Path, tuple[int, float]] = {}
        try:
            with os.scandir(folder) as it:
                for entry in it:
                    if entry.is_file() and entry.name.lower().endswith(".pdf"):
                        st = entry.stat()
                        current[Path(entry.path)] = (st.st_size, st.st_mtime)
        except OSError as e:
            log.warning("Không quét được thư mục %s: %s", folder, e)
        for path, sig in current.items():
            if path in done or seen.get(path) != sig:
                continue   # chưa xử lý, hoặc vừa thay đổi: đợi lần quét sau
            done.add(path)
            try:
                result, err = process(path), None
            except Exception as e:
                result, err = None, e
                log.exception("Lỗi khi xử lý %s", path)
            if on_result:
                on_result(path, result, err)
        seen = current
        done &= set(current)   # file đã bị xóa khỏi thư mục thì quên đi
        stop.wait(interval)


def output_dir(folder: Path) -> Path:
    return Path(folder) / OUT_SUBDIR
