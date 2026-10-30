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


def merge_pdfs(srcs: list[Path], name: str = "ghep", out_dir: Path | None = None,
               opts: ExtractOptions | None = None) -> Path:
    """Ghép các file theo đúng thứ tự trong `srcs` thành một file PDF. Mỗi file nguồn có một bookmark cấp 1
    mang tên file (khi giữ bookmark), bookmark gốc của file nằm dưới đó."""
    opts = opts or ExtractOptions()
    _check_version(opts)
    if not srcs:
        raise ValueError("Chưa có file nào để ghép")
    srcs = [Path(s) for s in srcs]
    out_dir = Path(out_dir) if out_dir else srcs[0].parent
    out_dir.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for src in srcs:
        reader = _open(src)
        writer.append(reader, outline_item=src.stem if opts.keep_bookmarks else None,
                      import_outline=opts.keep_bookmarks)
    if opts.compress:
        for page in writer.pages:
            page.compress_content_streams()
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    writer.pdf_header = f"%PDF-{opts.pdf_version}"
    target = _target(out_dir, name, opts.overwrite)
    with open(target, "wb") as f:
        writer.write(f)
    return target


def _finish(writer: PdfWriter, name: str, out_dir: Path, opts: ExtractOptions) -> Path:
    """Nén (nếu bật), đặt phiên bản PDF và ghi ra file mới trong out_dir."""
    if opts.compress:
        for page in writer.pages:
            page.compress_content_streams()
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    writer.pdf_header = f"%PDF-{opts.pdf_version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = _target(out_dir, name, opts.overwrite)
    with open(target, "wb") as f:
        writer.write(f)
    return target


def interleave_pdfs(srcs: list[Path], name: str = "xen_ke", out_dir: Path | None = None,
                    opts: ExtractOptions | None = None, reverse_second: bool = False) -> Path:
    """Ghép xen kẽ: lấy lần lượt trang 1 của file 1, file 2, ..., rồi trang 2 của từng file...
    File hết trang trước thì bỏ qua. Dùng cho bản scan hai mặt: quét mặt trước một lần, mặt sau một lần.
    reverse_second: đảo thứ tự file thứ hai (thường quét mặt sau theo chiều ngược)."""
    opts = opts or ExtractOptions()
    _check_version(opts)
    if len(srcs) < 2:
        raise ValueError("Ghép xen kẽ cần ít nhất hai file")
    srcs = [Path(s) for s in srcs]
    readers = [_open(s) for s in srcs]
    orders = [list(r.pages) for r in readers]
    if reverse_second:
        orders[1] = orders[1][::-1]
    writer = PdfWriter()
    for i in range(max(len(o) for o in orders)):
        for order in orders:
            if i < len(order):
                writer.add_page(order[i])
    return _finish(writer, name, Path(out_dir) if out_dir else srcs[0].parent, opts)


def insert_repeated(main: Path, insert: Path, name: str = "chen_trang", out_dir: Path | None = None,
                    opts: ExtractOptions | None = None, insert_page: int = 1, before: bool = False) -> Path:
    """Chèn lặp lại một trang của file `insert` vào sau (hoặc trước) mỗi trang của file `main`:
    B1 A B2 A B3 A (before=False) hoặc A B1 A B2 A B3 (before=True)."""
    opts = opts or ExtractOptions()
    _check_version(opts)
    main, insert = Path(main), Path(insert)
    mreader = _open(main)
    ireader = _open(insert)
    if not 1 <= insert_page <= len(ireader.pages):
        raise ValueError(f"Trang chèn {insert_page} nằm ngoài khoảng 1–{len(ireader.pages)} của file {insert.name}")
    piece = ireader.pages[insert_page - 1]
    writer = PdfWriter()
    for page in mreader.pages:
        if before:
            writer.add_page(piece)
        writer.add_page(page)
        if not before:
            writer.add_page(piece)
    return _finish(writer, name, Path(out_dir) if out_dir else main.parent, opts)


def _run_watch(a) -> int:
    """--watch: xử lý PDF mới trong thư mục bằng --rotate hoặc --compress, cho đến khi Ctrl+C."""
    import threading
    from . import pdf_ops
    folder = Path(a.watch)
    if not folder.is_dir():
        print(f"Không thấy thư mục: {folder}", file=sys.stderr)
        return 1
    if not (a.rotate or a.compress):
        print("--watch cần --rotate hoặc --compress", file=sys.stderr)
        return 1
    out = pdf_ops.output_dir(folder)
    opts = ExtractOptions(pdf_version=a.pdf_version)

    def process(path: Path) -> Path:
        if a.rotate:
            return pdf_ops.rotate_pdf(path, a.rotate, a.pages, out, opts)
        return pdf_ops.compress_pdf(path, a.image_quality, out, opts)

    def report(path, result, err):
        print(f"{path.name}: {'lỗi: ' + str(err) if err else '-> ' + str(result)}", flush=True)

    print(f"Đang theo dõi {folder} (kết quả vào {out}). Ctrl+C để dừng.", flush=True)
    stop = threading.Event()
    try:
        pdf_ops.watch_folder(folder, process, stop, on_result=report)
    except KeyboardInterrupt:
        stop.set()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ocrnhat-pdf", description="Trích xuất trang hoặc tách file PDF.")
    ap.add_argument("inputs", nargs="+", help="file PDF")
    ap.add_argument("--pages", default="", help="trích xuất: ví dụ 2 hoặc 5-23 hoặc 2,5-7,12-")
    ap.add_argument("--merge", action="store_true", help="ghép các file đầu vào theo thứ tự thành một PDF")
    ap.add_argument("--name", default="ghep", help="--merge, --interleave, --insert: tên file kết quả, không gồm .pdf")
    ap.add_argument("--interleave", action="store_true", help="ghép xen kẽ các file đầu vào (trang 1 của từng file, rồi trang 2...)")
    ap.add_argument("--reverse-second", action="store_true", help="--interleave: đảo thứ tự file thứ hai (scan mặt sau)")
    ap.add_argument("--insert", action="store_true", help="chèn lặp lại: inputs[0] là file chính, inputs[1] là file chứa trang chèn")
    ap.add_argument("--insert-page", type=int, default=1, help="--insert: số trang của file chèn (mặc định 1)")
    ap.add_argument("--insert-before", action="store_true", help="--insert: chèn trước mỗi trang thay vì sau")
    ap.add_argument("--rotate", type=int, choices=(90, 180, 270), help="xoay trang theo chiều kim đồng hồ (dùng với --pages để chọn trang, mặc định tất cả)")
    ap.add_argument("--compress", action="store_true", help="nén file (gộp đối tượng trùng, nén nội dung; kèm ảnh nếu có --image-quality)")
    ap.add_argument("--image-quality", type=int, default=None, help="--compress: nén lại ảnh JPEG ở chất lượng này, 1–95 (ví dụ 75)")
    ap.add_argument("--watch", default=None, metavar="THU_MUC", help="tự động xử lý PDF mới trong thư mục bằng --rotate hoặc --compress; Ctrl+C để dừng")
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
    if a.watch:
        return _run_watch(a)
    if a.rotate or a.compress:
        from . import pdf_ops
        opts = ExtractOptions(overwrite=a.overwrite, compress=not a.no_compress,
                              keep_bookmarks=not a.no_bookmarks, pdf_version=a.pdf_version)
        out = Path(a.out) if a.out else None
        code = 0
        for name in a.inputs:
            try:
                if a.rotate:
                    print(f"-> {pdf_ops.rotate_pdf(Path(name), a.rotate, a.pages, out, opts)}")
                else:
                    print(f"-> {pdf_ops.compress_pdf(Path(name), a.image_quality, out, opts)}")
            except (ValueError, OSError) as e:
                print(f"Lỗi {name}: {e}", file=sys.stderr)
                code = 1
        return code
    if not (a.split or a.merge or a.interleave or a.insert or a.rotate or a.compress or a.watch or a.pages):
        ap.error("cần --pages (trích xuất), --split (tách file) hoặc --merge (ghép file)")
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    opts = ExtractOptions(separate=a.separate, overwrite=a.overwrite, compress=not a.no_compress,
                          keep_bookmarks=not a.no_bookmarks, pdf_version=a.pdf_version)
    out = Path(a.out) if a.out else None
    code = 0
    if a.interleave or a.insert:
        try:
            if a.insert:
                if len(a.inputs) != 2:
                    raise ValueError("--insert cần đúng hai file: file chính rồi file chèn")
                res = insert_repeated(Path(a.inputs[0]), Path(a.inputs[1]), a.name, out, opts, a.insert_page, a.insert_before)
            else:
                res = interleave_pdfs([Path(x) for x in a.inputs], a.name, out, opts, a.reverse_second)
            print(f"-> {res}")
        except (ValueError, OSError) as e:
            print(f"Lỗi: {e}", file=sys.stderr)
            return 1
        return 0
    if a.merge:
        try:
            print(f"-> {merge_pdfs([Path(x) for x in a.inputs], a.name, out, opts)}")
        except (ValueError, OSError) as e:
            print(f"Lỗi ghép: {e}", file=sys.stderr)
            return 1
        return 0
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
