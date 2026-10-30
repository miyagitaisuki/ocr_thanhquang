"""Bảng chữ kana (layout._read_kana_chart) với lưới tổng hợp và bộ đọc giả; không cần Tesseract."""
import numpy as np

from ocrnhat.layout import KANA_NOTE, build_page
from ocrnhat.model import Block, Line, Page


def _grid_image(rows=4, cols=6, cw=150, ch=70):
    h, w = rows * ch + 40, cols * cw + 40
    img = np.full((h, w, 3), 255, np.uint8)
    for r in range(rows + 1):
        img[20 + r * ch, 20:20 + cols * cw] = 0
    for c in range(cols + 1):
        img[20:20 + rows * ch, 20 + c * cw] = 0
    return img


def _page(img, rows=4, cols=6, cw=150, ch=70):
    lines = []
    for r in range(rows):
        for c in range(cols):
            x = 20 + c * cw + cw // 2
            y = 20 + r * ch + ch // 2
            lines.append(Line(["a", "ka", "sa", "ta", "na", "ha"][r], x=x - 10, y=y - 8, w=30, h=16, conf=0.9))
    return Page(img.shape[1], img.shape[0], [Block("table", 0, 0, img.shape[1], img.shape[0], lines)])


def test_bang_kana_dung_bo_doc_va_co_ghi_chu():
    img = _grid_image()
    page = _page(img)
    seen = []

    def reader(crop):
        seen.append(crop.shape)
        return "か"

    items = build_page(page, img, None, reader)
    tables = [i for i in items if hasattr(i, "cells")]
    assert tables and tables[0].kana is True
    assert len(seen) == 24                              # mọi ô đều được đọc
    assert all(c.text == "か" for c in tables[0].cells)
    assert any(getattr(i, "text", "") == KANA_NOTE for i in items)


def test_khong_co_bo_doc_thi_khong_thanh_bang_kana():
    img = _grid_image()
    items = build_page(_page(img), img, None, None)
    tables = [i for i in items if hasattr(i, "cells")]
    assert not any(t.kana for t in tables)
