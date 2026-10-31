"""Engine yomitoku: đăng ký và chuyển kết quả sang Page, không nạp model thật (không cần torch)."""
import sys
import types

import numpy as np
import pytest

from ocrnhat import engines
from ocrnhat.engines.yomitoku import YomitokuEngine


def test_registered_for_japanese_only():
    assert "yomitoku" in engines.available()
    assert "yomitoku" in engines.LANG_ENGINES["ja"]
    assert "yomitoku" not in engines.LANG_ENGINES["en"]
    assert engines.resolve_for_lang("yomitoku", "ja") == ("yomitoku", "chọn thủ công")


def test_version_is_cache_key():
    assert engines.engine_version("yomitoku").startswith("yomitoku-")


def test_missing_package_reports_reason(monkeypatch):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    ok, why = YomitokuEngine.is_available()
    assert not ok and "yomitoku" in why


class _Word:
    def __init__(self, points, content, rec_score):
        self.points, self.content, self.rec_score = points, content, rec_score


def test_words_become_ordered_page(monkeypatch):
    # OCR giả: hai dòng, dòng dưới được khai báo trước để kiểm tra việc sắp thứ tự đọc
    words = [
        _Word([[10, 100], [200, 100], [200, 130], [10, 130]], "下の行", 0.9),
        _Word([[10, 10], [200, 10], [200, 40], [10, 40]], "上の行", 0.8),
        _Word([[10, 50], [200, 50], [200, 60], [10, 60]], "   ", 0.5),   # khoảng trắng: bỏ
    ]

    class FakeOCR:
        def __init__(self, device="cpu", visualize=False):
            self.device = device

        def __call__(self, img):
            assert img.shape[2] == 3
            return types.SimpleNamespace(words=words), None

    fake = types.ModuleType("yomitoku")
    fake.OCR = FakeOCR
    monkeypatch.setitem(sys.modules, "yomitoku", fake)
    monkeypatch.setattr(YomitokuEngine, "is_available", classmethod(lambda cls: (True, "")))

    eng = YomitokuEngine(device="cuda")
    assert eng.ocr_model.device == "cuda"
    page = eng.ocr(np.full((200, 300, 3), 255, np.uint8))
    texts = [ln.text for b in page.blocks for ln in b.lines]
    assert texts == ["上の行", "下の行"]
    assert page.width == 300 and page.height == 200
