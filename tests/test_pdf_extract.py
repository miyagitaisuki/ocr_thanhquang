"""Trích xuất trang PDF (pypdf). Không cần model OCR: file PDF được tạo ngay trong test."""
import pytest

pypdf = pytest.importorskip("pypdf")
from pypdf import PdfReader, PdfWriter  # noqa: E402
from pypdf.generic import NameObject, NumberObject  # noqa: E402

from ocrnhat import pdf_extract as pe  # noqa: E402


def _make_pdf(path, n, outline=None):
    w = PdfWriter()
    for _ in range(n):
        w.add_blank_page(width=200, height=200)
    if outline:
        for title, page in outline:
            w.add_outline_item(title, page)
    with open(path, "wb") as f:
        w.write(f)
    return path


def test_parse_single_range_and_open_ended():
    assert pe.parse_page_spec("2", 10) == [[2]]
    assert pe.parse_page_spec("5-7", 10) == [[5, 6, 7]]
    assert pe.parse_page_spec("2, 5-7, 9-", 10) == [[2], [5, 6, 7], [9, 10]]
    assert pe.parse_page_spec("-3", 10) == [[1, 2, 3]]


@pytest.mark.parametrize("spec", ["", " , ", "0", "11", "3-2", "4-12", "a-b", "1.5"])
def test_parse_rejects_bad_spec(spec):
    with pytest.raises(ValueError):
        pe.parse_page_spec(spec, 10)


def test_label():
    assert pe._label([2]) == "2"
    assert pe._label([1, 2, 5, 6, 7]) == "1-2_5-7"
    assert pe._label([3, 1]) == "3_1"


def test_extract_single_file_keeps_order_and_dedupes(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 6)
    out = pe.extract_pages(src, "5-6, 2, 5", tmp_path / "out")
    assert [p.name for p in out] == ["doc_trang_5-6_2.pdf"]
    assert len(PdfReader(str(out[0])).pages) == 3


def test_extract_separate_files_per_group(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 6)
    opts = pe.ExtractOptions(separate=True)
    out = pe.extract_pages(src, "1, 3-4, 6-", tmp_path / "out", opts)
    assert [p.name for p in out] == ["doc_trang_1.pdf", "doc_trang_3-4.pdf", "doc_trang_6.pdf"]
    assert [len(PdfReader(str(p)).pages) for p in out] == [1, 2, 1]


def test_no_overwrite_adds_suffix_and_overwrite_replaces(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 3)
    out_dir = tmp_path / "out"
    first = pe.extract_pages(src, "1", out_dir)[0]
    second = pe.extract_pages(src, "1", out_dir)[0]
    assert first.name == "doc_trang_1.pdf"
    assert second.name == "doc_trang_1 (2).pdf"
    again = pe.extract_pages(src, "1", out_dir, pe.ExtractOptions(overwrite=True))[0]
    assert again == first
    assert not (out_dir / "doc_trang_1 (3).pdf").exists()


def test_default_output_is_next_to_source(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 2)
    out = pe.extract_pages(src, "2")
    assert out[0].parent == tmp_path


def test_pdf_version_header(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 2)
    out = pe.extract_pages(src, "1", tmp_path / "out", pe.ExtractOptions(pdf_version="1.7"))[0]
    assert out.read_bytes().startswith(b"%PDF-1.7")
    with pytest.raises(ValueError):
        pe.extract_pages(src, "1", tmp_path / "out", pe.ExtractOptions(pdf_version="2.0"))


def test_bookmarks_kept_for_selected_pages_only(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 6, outline=[("Một", 0), ("Ba", 2), ("Năm", 4)])
    out = pe.extract_pages(src, "3-5", tmp_path / "out")[0]
    titles = [o.title for o in PdfReader(str(out)).outline]
    assert titles == ["Ba", "Năm"]


def test_discard_bookmarks(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 3, outline=[("Một", 0)])
    out = pe.extract_pages(src, "1", tmp_path / "out", pe.ExtractOptions(keep_bookmarks=False))[0]
    assert not PdfReader(str(out)).outline


def test_cli_reports_error_for_bad_pages(tmp_path, capsys):
    src = _make_pdf(tmp_path / "doc.pdf", 2)
    assert pe.main([str(src), "--pages", "9", "-o", str(tmp_path / "out")]) == 1
    assert "nằm ngoài" in capsys.readouterr().err


def test_cli_success(tmp_path, capsys):
    src = _make_pdf(tmp_path / "doc.pdf", 4)
    assert pe.main([str(src), "--pages", "1,3-", "--separate", "-o", str(tmp_path / "out")]) == 0
    assert "doc_trang_1.pdf" in capsys.readouterr().out


def test_split_by_pages(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 5)
    out = pe.split_pdf(src, "pages", 2, tmp_path / "out")
    assert [p.name for p in out] == ["doc_phan_01.pdf", "doc_phan_02.pdf", "doc_phan_03.pdf"]
    assert [len(PdfReader(str(p)).pages) for p in out] == [2, 2, 1]


def test_split_by_pages_default_one_page_each(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 3)
    out = pe.split_pdf(src, "pages", None, tmp_path / "out")
    assert len(out) == 3 and all(len(PdfReader(str(p)).pages) == 1 for p in out)


def test_split_by_bookmark_uses_top_level_marks(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 6, outline=[("Chương 1", 1), ("Chương 2", 4)])
    out = pe.split_pdf(src, "bookmark", None, tmp_path / "out")
    assert [p.name for p in out] == ["doc_phan_dau.pdf", "doc_Chương 1.pdf", "doc_Chương 2.pdf"]
    assert [len(PdfReader(str(p)).pages) for p in out] == [1, 3, 2]
    assert [o.title for o in PdfReader(str(out[1])).outline] == ["Chương 1"]


def test_split_by_bookmark_needs_outline(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 2)
    with pytest.raises(ValueError, match="bookmark"):
        pe.split_pdf(src, "bookmark", None, tmp_path / "out")


def test_split_by_size_keeps_each_file_under_limit(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 6)
    one_page = pe._build(PdfReader(str(src)), [1], pe.ExtractOptions())
    import io
    buf = io.BytesIO(); one_page.write(buf)
    limit_mb = (buf.tell() * 2.5) / 1024 / 1024   # khoảng 2 trang mỗi file
    out = pe.split_pdf(src, "size", limit_mb, tmp_path / "out")
    assert sum(len(PdfReader(str(p)).pages) for p in out) == 6
    assert all(p.stat().st_size <= limit_mb * 1024 * 1024 for p in out)
    assert len(out) >= 3


def test_split_size_rejects_bad_limit(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 2)
    with pytest.raises(ValueError):
        pe.split_pdf(src, "size", 0, tmp_path / "out")
    with pytest.raises(ValueError, match="lớn hơn giới hạn"):
        pe.split_pdf(src, "size", 0.0001, tmp_path / "out")


def test_cli_split(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf", 4)
    assert pe.main([str(src), "--split", "pages", "--every", "2", "-o", str(tmp_path / "out")]) == 0
    assert len(list((tmp_path / "out").glob("*.pdf"))) == 2


def test_merge_keeps_order_pages_and_bookmarks(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", 2, outline=[("Mục A", 0)])
    b = _make_pdf(tmp_path / "b.pdf", 3)
    out = pe.merge_pdfs([b, a], "ghep", tmp_path / "out")
    r = PdfReader(str(out))
    assert out.name == "ghep.pdf" and len(r.pages) == 5
    assert [o.title for o in r.outline if not isinstance(o, list)] == ["b", "a"]


def test_merge_without_bookmarks(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", 1, outline=[("Mục A", 0)])
    b = _make_pdf(tmp_path / "b.pdf", 1)
    out = pe.merge_pdfs([a, b], "ghep", tmp_path / "out", pe.ExtractOptions(keep_bookmarks=False))
    assert len(PdfReader(str(out)).pages) == 2 and not PdfReader(str(out)).outline


def test_merge_overwrite_and_empty(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", 1)
    out1 = pe.merge_pdfs([a], "ghep", tmp_path / "out")
    out2 = pe.merge_pdfs([a], "ghep", tmp_path / "out")
    assert out2.name == "ghep (2).pdf" and out1 != out2
    assert pe.merge_pdfs([a], "ghep", tmp_path / "out", pe.ExtractOptions(overwrite=True)) == out1
    with pytest.raises(ValueError):
        pe.merge_pdfs([], "ghep", tmp_path / "out")


def test_cli_merge(tmp_path, capsys):
    a = _make_pdf(tmp_path / "a.pdf", 1)
    b = _make_pdf(tmp_path / "b.pdf", 2)
    assert pe.main([str(a), str(b), "--merge", "--name", "tong", "-o", str(tmp_path / "out")]) == 0
    assert len(PdfReader(str(tmp_path / "out" / "tong.pdf")).pages) == 3
