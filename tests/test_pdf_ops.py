"""Xoay trang, nén và thư mục tự động (pypdf, Pillow). Không cần model OCR."""
import threading
import time

import pytest

pypdf = pytest.importorskip("pypdf")
from pypdf import PdfReader, PdfWriter  # noqa: E402

from ocrnhat import pdf_ops  # noqa: E402
from ocrnhat.pdf_extract import ExtractOptions  # noqa: E402


def _sized_pdf(path, widths, height=100):
    w = PdfWriter()
    for width in widths:
        w.add_blank_page(width=width, height=height)
    with open(path, "wb") as f:
        w.write(f)
    return path


def _rotations(path):
    return [int(p.get("/Rotate", 0)) % 360 for p in PdfReader(str(path)).pages]


def test_rotate_all_pages(tmp_path):
    src = _sized_pdf(tmp_path / "a.pdf", [1, 2, 3])
    out = pdf_ops.rotate_pdf(src, 90, "", tmp_path / "out")
    assert out.name == "rotate_a.pdf"
    assert _rotations(out) == [90, 90, 90]


def test_rotate_selected_pages_only(tmp_path):
    src = _sized_pdf(tmp_path / "a.pdf", [1, 2, 3, 4])
    out = pdf_ops.rotate_pdf(src, 180, "2,4-", tmp_path / "out")
    assert _rotations(out) == [0, 180, 0, 180]


def test_rotate_rejects_bad_angle_and_range(tmp_path):
    src = _sized_pdf(tmp_path / "a.pdf", [1, 2])
    with pytest.raises(ValueError):
        pdf_ops.rotate_pdf(src, 45, "", tmp_path / "out")
    with pytest.raises(ValueError):
        pdf_ops.rotate_pdf(src, 90, "5", tmp_path / "out")


def test_compress_lossless_keeps_pages(tmp_path):
    src = _sized_pdf(tmp_path / "a.pdf", [1, 2, 3])
    out = pdf_ops.compress_pdf(src, image_quality=None, out_dir=tmp_path / "out")
    assert out.name == "compress_a.pdf"
    assert len(PdfReader(str(out)).pages) == 3


def test_compress_with_images_reduces_size(tmp_path):
    from PIL import Image
    img = Image.effect_noise((800, 800), 60).convert("RGB")   # ảnh nhiễu: JPEG chất lượng thấp nhỏ hơn rõ rệt
    w = PdfWriter()
    w.add_blank_page(width=800, height=800)
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject as N, NumberObject
    raw_rgb = img.tobytes()
    xobj = DecodedStreamObject()
    xobj.set_data(raw_rgb)
    xobj.update({N("/Type"): N("/XObject"), N("/Subtype"): N("/Image"), N("/Width"): NumberObject(800),
                 N("/Height"): NumberObject(800), N("/ColorSpace"): N("/DeviceRGB"), N("/BitsPerComponent"): NumberObject(8)})
    res = DictionaryObject({N("/XObject"): DictionaryObject({N("/Im1"): w._add_object(xobj)})})
    w.pages[0][N("/Resources")] = res
    content = DecodedStreamObject()
    content.set_data(b"q 800 0 0 800 0 0 cm /Im1 Do Q")
    w.pages[0][N("/Contents")] = w._add_object(content)
    src = tmp_path / "img.pdf"
    with open(src, "wb") as f:
        w.write(f)
    out_big = pdf_ops.compress_pdf(src, image_quality=None, out_dir=tmp_path / "out")
    out_small = pdf_ops.compress_pdf(src, image_quality=40, out_dir=tmp_path / "out2")
    assert out_small.stat().st_size < out_big.stat().st_size
    assert len(PdfReader(str(out_small)).pages) == 1


def test_compress_rejects_bad_quality(tmp_path):
    src = _sized_pdf(tmp_path / "a.pdf", [1])
    with pytest.raises(ValueError):
        pdf_ops.compress_pdf(src, image_quality=0, out_dir=tmp_path / "out")


def test_watch_processes_new_pdf_once_when_stable(tmp_path):
    folder = tmp_path / "watch"
    folder.mkdir()
    seen = []
    stop = threading.Event()
    t = threading.Thread(target=pdf_ops.watch_folder,
                         args=(folder, lambda p: seen.append(p.name) or p, stop, 0.05))
    t.start()
    _sized_pdf(folder / "new.pdf", [1])
    deadline = time.time() + 5
    while not seen and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.3)   # chờ thêm vài vòng để xác nhận không xử lý lặp
    stop.set(); t.join(2)
    assert seen == ["new.pdf"]


def test_watch_ignores_subfolder_outputs(tmp_path):
    folder = tmp_path / "watch"
    (folder / pdf_ops.OUT_SUBDIR).mkdir(parents=True)
    _sized_pdf(folder / pdf_ops.OUT_SUBDIR / "x.pdf", [1])
    seen = []
    stop = threading.Event()
    t = threading.Thread(target=pdf_ops.watch_folder, args=(folder, lambda p: seen.append(p) or p, stop, 0.05))
    t.start(); time.sleep(0.4); stop.set(); t.join(2)
    assert seen == []


def test_watch_reports_errors_and_continues(tmp_path):
    folder = tmp_path / "watch"
    folder.mkdir()
    results = []
    stop = threading.Event()

    def boom(p):
        raise ValueError("hỏng")

    t = threading.Thread(target=pdf_ops.watch_folder,
                         args=(folder, boom, stop, 0.05, lambda p, r, e: results.append((p.name, str(e)))))
    t.start()
    _sized_pdf(folder / "bad.pdf", [1])
    deadline = time.time() + 5
    while not results and time.time() < deadline:
        time.sleep(0.05)
    stop.set(); t.join(2)
    assert results == [("bad.pdf", "hỏng")]
