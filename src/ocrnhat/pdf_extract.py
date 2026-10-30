"""Công cụ PDF: trích xuất trang và tách file PDF (pypdf, giấy phép BSD-3).

Cú pháp trang: "2", "5-23", "2,5-7,12-" (để trống đầu/cuối = từ trang 1 / đến trang cuối).
Chế độ "file riêng": mỗi nhóm phân cách bằng dấu phẩy là một file.
Tách file (split_pdf): theo số trang, theo bookmark cấp 1, hoặc theo dung lượng tối đa.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

PDF_VERSIONS = ("1.4", "1.5", "1.6", "1.7")
SPLIT_MODES = ("pages", "bookmark", "size")


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


def _target(out_dir: Path, name: str, overwrite: bool) -> Path:
    path = out_dir / f"{name}.pdf"
    n = 2
    while path.exists() and not overwrite:
        path = out_dir / f"{name} ({n}).pdf"
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


def _build(reader: PdfReader, pages: list[int], opts: ExtractOptions) -> PdfWriter:
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
    return writer


def _write_groups(reader: PdfReader, src: Path, groups: list[tuple[str, list[int]]], out_dir: Path | None,
                  opts: ExtractOptions) -> list[Path]:
    """Ghi mỗi nhóm (hậu tố tên file, danh sách trang) thành một file trong out_dir."""
    out_dir = Path(out_dir) if out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for suffix, pages in groups:
        target = _target(out_dir, src.stem + suffix, opts.overwrite)
        with open(target, "wb") as f:
            _build(reader, pages, opts).write(f)
        written.append(target)
    return written


def _check_version(opts: ExtractOptions) -> None:
    if opts.pdf_version not in PDF_VERSIONS:
        raise ValueError(f"Phiên bản PDF không hợp lệ: {opts.pdf_version}")


def extract_pages(src: Path, spec: str, out_dir: Path | None = None, opts: ExtractOptions | None = None) -> list[Path]:
    """Trích xuất các trang của `src` theo `spec`. Trả về danh sách file đã ghi."""
    opts = opts or ExtractOptions()
    _check_version(opts)
    src = Path(src)
    reader = _open(src)
    groups = parse_page_spec(spec, len(reader.pages))
    if not opts.separate:   # gộp mọi nhóm thành một file, bỏ trang trùng, giữ thứ tự nhập
        groups = [list(dict.fromkeys(p for g in groups for p in g))]
    return _write_groups(reader, src, [(f"_trang_{_label(g)}", g) for g in groups], out_dir, opts)


def _safe_name(title: str) -> str:
    """Bỏ ký tự không hợp lệ trong tên file Windows."""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", title).strip()
    return name[:60] or "muc"


def _bookmark_groups(reader: PdfReader) -> list[tuple[str, list[int]]]:
    """Mỗi bookmark cấp 1 mở một file, kéo đến trước bookmark kế tiếp. Trang trước bookmark đầu thành một file riêng."""
    first_title: dict[int, str] = {}
    for item in reader.outline:
        if isinstance(item, list):   # mục con, bỏ qua
            continue
        page = reader.get_destination_page_number(item)
        if page is not None:
            first_title.setdefault(page + 1, item.title)   # trang 1-based
    if not first_title:
        raise ValueError("PDF không có bookmark cấp 1 để tách")
    starts = sorted(first_title.items())
    total = len(reader.pages)
    groups: list[tuple[str, list[int]]] = []
    if starts[0][0] > 1:
        groups.append(("_phan_dau", list(range(1, starts[0][0]))))
    for i, (start, title) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else total
        groups.append((f"_{_safe_name(title)}", list(range(start, end + 1))))
    return groups


def _size_groups(reader: PdfReader, limit: float, opts: ExtractOptions) -> list[tuple[str, list[int]]]:
    """Gộp trang liên tiếp, mỗi file không vượt limit (byte). Dung lượng từng trang đo riêng nên chỉ là ước lượng:
    file thật thường nhỏ hơn vì các trang dùng chung font và tài nguyên."""
    sizes: dict[int, int] = {}
    for p in range(1, len(reader.pages) + 1):
        buf = io.BytesIO()
        _build(reader, [p], opts).write(buf)
        if buf.tell() > limit:
            raise ValueError(f"Trang {p} lớn hơn giới hạn {limit / 1024 / 1024:.1f} MB, không tách được")
        sizes[p] = buf.tell()
    groups: list[list[int]] = []
    cur: list[int] = []
    cur_size = 0
    for p, s in sizes.items():
        if cur and cur_size + s > limit:
            groups.append(cur)
            cur, cur_size = [], 0
        cur.append(p)
        cur_size += s
    if cur:
        groups.append(cur)
    return [(f"_phan_{i:02d}", g) for i, g in enumerate(groups, 1)]


def split_pdf(src: Path, mode: str, value: float | int | None = None, out_dir: Path | None = None,
              opts: ExtractOptions | None = None) -> list[Path]:
    """Tách `src` thành nhiều file.
    mode "pages": value = số trang mỗi file (mặc định 1).
    mode "bookmark": theo bookmark cấp 1 (value không dùng).
    mode "size": value = dung lượng tối đa mỗi file, tính bằng MB.
    """
    opts = opts or ExtractOptions()
    _check_version(opts)
    src = Path(src)
    reader = _open(src)
    total = len(reader.pages)
    if mode == "pages":
        n = int(value or 1)
        if n < 1:
            raise ValueError("Số trang mỗi file phải từ 1 trở lên")
        groups = [(f"_phan_{i:02d}", list(range(a, min(a + n - 1, total) + 1)))
                  for i, a in enumerate(range(1, total + 1, n), 1)]
    elif mode == "bookmark":
        groups = _bookmark_groups(reader)
    elif mode == "size":
        if not value or float(value) <= 0:
            raise ValueError("Dung lượng tối đa phải lớn hơn 0 MB")
        groups = _size_groups(reader, float(value) * 1024 * 1024, opts)
    else:
        raise ValueError(f"Kiểu tách không hợp lệ: {mode}")
    return _write_groups(reader, src, groups, out_dir, opts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ocrnhat-pdf", description="Trích xuất trang hoặc tách file PDF.")
    ap.add_argument("inputs", nargs="+", help="file PDF")
    ap.add_argument("--pages", default="", help="trích xuất: ví dụ 2 hoặc 5-23 hoặc 2,5-7,12-")
    ap.add_argument("--split", choices=SPLIT_MODES, help="tách file thay vì trích xuất: pages | bookmark | size")
    ap.add_argument("--every", type=int, default=1, help="--split pages: số trang mỗi file (mặc định 1)")
    ap.add_argument("--max-mb", type=float, default=10, help="--split size: dung lượng tối đa mỗi file, MB (mặc định 10)")
    ap.add_argument("-o", "--out", default=None, help="thư mục kết quả (mặc định: cạnh file gốc)")
    ap.add_argument("--separate", action="store_true", help="trích xuất: mỗi nhóm trang (phân cách bằng dấu phẩy) thành một file")
    ap.add_argument("--overwrite", action="store_true", help="ghi đè file đã có (mặc định: thêm số (2), (3)...)")
    ap.add_argument("--no-compress", action="store_true", help="không nén lại nội dung trang")
    ap.add_argument("--no-bookmarks", action="store_true", help="bỏ bookmark")
    ap.add_argument("--pdf-version", default="1.5", choices=PDF_VERSIONS, help="phiên bản PDF ghi trong file (mặc định 1.5)")
    a = ap.parse_args(argv)
    if not a.split and not a.pages:
        ap.error("cần --pages (trích xuất) hoặc --split (tách file)")
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    opts = ExtractOptions(separate=a.separate, overwrite=a.overwrite, compress=not a.no_compress,
                          keep_bookmarks=not a.no_bookmarks, pdf_version=a.pdf_version)
    out = Path(a.out) if a.out else None
    code = 0
    for name in a.inputs:
        try:
            if a.split:
                value = {"pages": a.every, "size": a.max_mb, "bookmark": None}[a.split]
                paths = split_pdf(Path(name), a.split, value, out, opts)
            else:
                paths = extract_pages(Path(name), a.pages, out, opts)
            for path in paths:
                print(f"-> {path}")
        except (ValueError, OSError) as e:
            print(f"Lỗi {name}: {e}", file=sys.stderr)
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
