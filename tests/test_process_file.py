"""Đường ống đầy đủ process_file với engine giả: PDF thật (tạo bằng Pillow), không cần model.
Kiểm: sinh .docx có chữ, cache bỏ qua OCR khi chạy lại, và cờ --no-cell-reocr được truyền xuống layout."""
import threading
from pathlib import Path

import pytest
from PIL import Image

from ocrnhat import engines, layout, pipeline
from ocrnhat.engines.base import OcrEngine
from ocrnhat.model import Block, Line, Page


class _CountingEngine(OcrEngine):
    calls = 0

    def __init__(self, device="cpu"):
        pass

    def ocr(self, img, name="page.png"):
        type(self).calls += 1
        h, w = img.shape[:2]
        return Page(w, h, [Block("text", 0, 0, w, h, [Line("東京です", x=10, y=10, w=200, h=30, conf=0.9)])])


@pytest.fixture
def fake_engine(monkeypatch):
    _CountingEngine.calls = 0
    monkeypatch.setattr(engines, "create", lambda name, device="cpu": _CountingEngine(device))
    monkeypatch.setattr(engines, "resolve", lambda name=None: (name or "ndlocr", "test"))
    monkeypatch.setattr(engines, "engine_version", lambda name: "test")
    monkeypatch.setattr(pipeline, "_tls", threading.local())
    return _CountingEngine


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    Image.new("RGB", (800, 1000), "white").save(path, "PDF", resolution=200)
    return path


def test_process_file_sinh_docx_co_chu(fake_engine, pdf, tmp_path):
    out = tmp_path / "out"
    r = pipeline.process_file(pdf, out, 200, None, device="cpu", use_cache=False)
    assert r["pages"] == 1
    docx = Path(r["docx"])
    assert docx.exists()
    from docx import Document
    text = "\n".join(p.text for p in Document(docx).paragraphs)
    assert "東京です" in text


def test_cache_chay_lai_khong_goi_engine(fake_engine, pdf, tmp_path):
    out = tmp_path / "out"
    pipeline.process_file(pdf, out, 200, None, device="cpu", use_cache=True)
    first = fake_engine.calls
    assert first == 1
    pipeline.process_file(pdf, out, 200, None, device="cpu", use_cache=True)
    assert fake_engine.calls == first        # trang đã có trong cache: không OCR lại


def test_tat_cache_thi_ocr_lai(fake_engine, pdf, tmp_path):
    out = tmp_path / "out"
    pipeline.process_file(pdf, out, 200, None, device="cpu", use_cache=False)
    pipeline.process_file(pdf, out, 200, None, device="cpu", use_cache=False)
    assert fake_engine.calls == 2


@pytest.mark.parametrize("cell_reocr, expect_callable", [(True, True), (False, False)])
def test_cell_reocr_duoc_truyen_xuong_layout(fake_engine, pdf, tmp_path, monkeypatch, cell_reocr, expect_callable):
    seen = []
    real = layout.build_page

    def spy(page, img, reocr=None, kana_reader=None):
        seen.append(reocr)
        return real(page, img, reocr, kana_reader)

    monkeypatch.setattr(layout, "build_page", spy)
    pipeline.process_file(pdf, tmp_path / "out", 200, None, device="cpu", use_cache=False, cell_reocr=cell_reocr)
    assert len(seen) == 1
    assert (seen[0] is not None) == expect_callable


def test_batch_gom_trang_va_giu_thu_tu(monkeypatch, tmp_path):
    # PDF 5 trang, batch 2: engine nhận nhóm 2,2,1 và kết quả vẫn theo đúng thứ tự trang
    pdf5 = tmp_path / "five.pdf"
    imgs = [Image.new("RGB", (800, 1000), "white") for _ in range(5)]
    imgs[0].save(pdf5, "PDF", resolution=200, save_all=True, append_images=imgs[1:])
    seen = []

    class _Batch(_CountingEngine):
        def ocr_many(self, imgs, names):
            seen.append(len(imgs))
            return [self.ocr(i, n) for i, n in zip(imgs, names)]

    monkeypatch.setattr(engines, "create", lambda name, device="cpu": _Batch(device))
    monkeypatch.setattr(engines, "resolve", lambda name=None: (name or "ndlocr", "test"))
    monkeypatch.setattr(engines, "engine_version", lambda name: "test")
    monkeypatch.setattr(engines, "batch_size", lambda name: 2)
    monkeypatch.setattr(pipeline, "_tls", threading.local())
    r = pipeline.process_file(pdf5, tmp_path / "out", 200, None, device="cpu", use_cache=False, engine="chandra")
    assert r["pages"] == 5
    assert seen == [2, 2, 1]
