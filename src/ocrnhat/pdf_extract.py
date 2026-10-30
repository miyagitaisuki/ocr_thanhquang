"""Công cụ PDF: trích xuất trang ra file PDF mới (pypdf, giấy phép BSD-3).

Cú pháp trang: "2", "5-23", "2,5-7,12-" (để trống đầu/cuối = từ trang 1 / đến trang cuối).
Chế độ "file riêng": mỗi nhóm phân cách bằng dấu phẩy là một file.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

PDF_VERSIONS = ("1.4", "1.5", "1.6", "1.7")


@dataclass
class ExtractOptions:
    separate: bool = False        # mỗi nhóm trang thành một file
    overwrite: bool = False       # ghi đè file đã có; nếu không thì thêm (2), (3)...
    compress: bool = True         # nén nội dung trang và gộp đối tượng trùng
    keep_bookmarks: bool = True   # giữ bookmark trỏ tới trang được trích
    pdf_version: str = "1.5"      # số phiên bản ghi trong tiêu đề %PDF-


def parse_page_spec(spec: str, total: int) -> list[list[int]]:
    """'2, 5-7, 12-' với tổng số trang -> danh sách nhóm trang (1-based), theo thứ tự nhập."""
    groups: list[list[int]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, _, b = part.partition("-")
                first = int(a) if a.strip() else 1
                last = int(b) if b.strip() else total
            else:
                first = last = int(part)
        except ValueError:
            raise ValueError(f"Không hiểu '{part}'. Ví dụ đúng: 2 hoặc 5-23 hoặc 2,5-7,12-") from None
        if not 1 <= first <= last <= total:
            raise ValueError(f"'{part}' nằm ngoài khoảng 1–{total} (file có {total} trang)")
        groups.append(list(range(first, last + 1)))
    if not groups:
        raise ValueError("Chưa nhập trang cần trích xuất")
    return groups


def page_count(path: Path) -> int:
    return len(_open(Path(path)).pages)


def _open(src: Path) -> PdfReader:
    reader = PdfReader(str(src))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF có mật khẩu, không trích xuất được")
    return reader


def _label(pages: list[int]) -> str:
    """[1, 2, 5, 6, 7] -> '1-2_5-7' (tên file)."""
    runs: list[str] = []
    start = prev = pages[0]
    for p in pages[1:] + [None]:
        if p is not None and p == prev + 1:
            prev = p
            continue
        runs.append(str(start) if start == prev else f"{start}-{prev}")
        if p is not None:
            start = prev = p
    return "_".join(runs)


def _target(out_dir: Path, stem: str, pages: list[int], overwrite: bool) -> Path:
    path = out_dir / f"{stem}_trang_{_label(pages)}.pdf"
    n = 2
    while path.exists() and not overwrite:
        path = out_dir / f"{stem}_trang_{_label(pages)} ({n}).pdf"
        n += 1
    return path


def _copy_outline(reader: PdfReader, writer: PdfWriter, index: dict[int, int], items: list, parent=None) -> None:
    """Chép bookmark chỉ tới trang đã chọn. Bookmark bị loại thì mục con của nó chuyển lên cấp trên."""
    prev = parent   # chỗ gắn mục con của mục vừa xét
    for item in items:
        if isinstance(item, list):
            _copy_outline(reader, writer, index, item, prev)
            continue
        page = reader.get_destination_page_number(item)
        if page is not None and page in index:
            prev = writer.add_outline_item(item.title, index[page], parent=parent)
        else:
            prev = parent


def _write(reader: PdfReader, pages: list[int], target: Path, opts: ExtractOptions) -> None:
    writer = PdfWriter()
    index: dict[int, int] = {}   # trang gốc (0-based) -> vị trí mới (0-based)
    for new_i, p in enumerate(pages):
        writer.add_page(reader.pages[p - 1])
        index.setdefault(p - 1, new_i)
    if opts.compress:
        for page in writer.pages:
            page.compress_content_streams()
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    if opts.keep_bookmarks and reader.outline:
        _copy_outline(reader, writer, index, reader.outline)
    writer.pdf_header = f"%PDF-{opts.pdf_version}"
    with open(target, "wb") as f:
        writer.write(f)


def extract_pages(src: Path, spec: str, out_dir: Path | None = None, opts: ExtractOptions | None = None) -> list[Path]:
    """Trích xuất các trang của `src` theo `spec`. Trả về danh sách file đã ghi."""
    opts = opts or ExtractOptions()
    src = Path(src)
    if opts.pdf_version not in PDF_VERSIONS:
        raise ValueError(f"Phiên bản PDF không hợp lệ: {opts.pdf_version}")
    reader = _open(src)
    groups = parse_page_spec(spec, len(reader.pages))
    if not opts.separate:   # gộp mọi nhóm thành một file, bỏ trang trùng, giữ thứ tự nhập
        groups = [list(dict.fromkeys(p for g in groups for p in g))]
    out_dir = Path(out_dir) if out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for group in groups:
        target = _target(out_dir, src.stem, group, opts.overwrite)
        _write(reader, group, target, opts)
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ocrnhat-pdf", description="Trích xuất trang PDF ra file PDF mới.")
    ap.add_argument("inputs", nargs="+", help="file PDF")
    ap.add_argument("--pages", required=True, help="ví dụ 2 hoặc 5-23 hoặc 2,5-7,12-")
    ap.add_argument("-o", "--out", default=None, help="thư mục kết quả (mặc định: cạnh file gốc)")
    ap.add_argument("--separate", action="store_true", help="mỗi nhóm trang (phân cách bằng dấu phẩy) thành một file")
    ap.add_argument("--overwrite", action="store_true", help="ghi đè file đã có (mặc định: thêm số (2), (3)...)")
    ap.add_argument("--no-compress", action="store_true", help="không nén lại nội dung trang")
    ap.add_argument("--no-bookmarks", action="store_true", help="bỏ bookmark")
    ap.add_argument("--pdf-version", default="1.5", choices=PDF_VERSIONS, help="phiên bản PDF ghi trong file (mặc định 1.5)")
    a = ap.parse_args(argv)
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    opts = ExtractOptions(separate=a.separate, overwrite=a.overwrite, compress=not a.no_compress,
                          keep_bookmarks=not a.no_bookmarks, pdf_version=a.pdf_version)
    code = 0
    for name in a.inputs:
        try:
            for path in extract_pages(Path(name), a.pages, Path(a.out) if a.out else None, opts):
                print(f"-> {path}")
        except (ValueError, OSError) as e:
            print(f"Lỗi {name}: {e}", file=sys.stderr)
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
