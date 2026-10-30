"""Engine Chandra OCR 2 (datalab-to/chandra-ocr-2, VLM ~4-5B, cần GPU; trọng số OpenRAIL-M sửa đổi).

Không nằm trong exe và không nằm trong requirements.txt: chỉ dùng khi máy đã cài `pip install chandra-ocr`
(tùy chọn, xem readme). Mô hình chạy qua máy chủ vLLM (mặc định) hoặc HuggingFace cục bộ.

Phần phân tích HTML của Chandra (`parse_chandra_html`) là hàm thuần, không cần model, được test trực tiếp.
Chandra không trả tọa độ từng dòng: mỗi khối có bbox (hệ 0..1000); văn bản trong khối được chia đều theo chiều
cao, bảng được chia lưới đều theo số hàng/cột và có tính colspan/rowspan. Đây là ước lượng; layout.py vẫn
dựng bảng từ đường kẻ trên ảnh, nên bảng chỉ đúng khi lưới ước lượng khớp với ảnh.
"""
from __future__ import annotations

import importlib.util

import numpy as np
from PIL import Image

from ..model import Block, Line, Page
from .base import OcrEngine

BBOX_SCALE = 1000          # hệ tọa độ bbox của Chandra (settings.BBOX_SCALE)
CONF = 0.9                 # Chandra không trả độ tin cậy từng dòng: cố định, không so sánh được với NDLOCR
CHANDRA_VERSION = "chandra-ocr-2"

_KIND = {"Page-Header": "header", "Page-Footer": "folio", "Image": "figure", "Figure": "figure",
         "Table": "table", "Blank-Page": None}


def _bbox(div, width: int, height: int) -> tuple[float, float, float, float] | None:
    raw = div.get("data-bbox", "")
    try:
        x0, y0, x1, y1 = (float(v) for v in raw.split())
    except ValueError:
        return None
    sx, sy = width / BBOX_SCALE, height / BBOX_SCALE
    return x0 * sx, y0 * sy, (x1 - x0) * sx, (y1 - y0) * sy


def _cell_text(el) -> str:
    return " ".join(el.text_content().split())


def _table_lines(table, x: float, y: float, w: float, h: float) -> list[Line]:
    """Chia bảng HTML thành lưới đều trong bbox, tính rowspan/colspan, mỗi ô là một Line."""
    rows = table.xpath(".//tr")
    grid: dict[tuple[int, int], str] = {}
    spans: dict[tuple[int, int], tuple[int, int]] = {}
    occupied: set[tuple[int, int]] = set()
    n_cols = 0
    for r, tr in enumerate(rows):
        c = 0
        for cell in tr.xpath("./td|./th"):
            while (r, c) in occupied:
                c += 1
            rs = int(cell.get("rowspan", "1") or 1)
            cs = int(cell.get("colspan", "1") or 1)
            grid[(r, c)] = _cell_text(cell)
            spans[(r, c)] = (rs, cs)
            for dr in range(rs):
                for dc in range(cs):
                    occupied.add((r + dr, c + dc))
            c += cs
            n_cols = max(n_cols, c)
    n_rows = len(rows)
    if not n_rows or not n_cols:
        return []
    cw, rh = w / n_cols, h / n_rows
    out: list[Line] = []
    for (r, c), text in grid.items():
        if not text:
            continue
        rs, cs = spans[(r, c)]
        cx = x + c * cw
        cy = y + r * rh
        out.append(Line(text, cx, cy, cs * cw, rs * rh, CONF, "", r * n_cols + c))
    return out


def _text_lines(div, x: float, y: float, w: float, h: float) -> list[Line]:
    """Mỗi đoạn (p/li/h*) hoặc mỗi dòng ngắt bằng <br> là một Line; chia đều chiều cao khối."""
    parts = [" ".join(p.text_content().split()) for p in div.xpath(".//p|.//li|.//h1|.//h2|.//h3|.//h4|.//h5|.//h6")]
    if not parts:
        parts = [" ".join(div.text_content().split())]
    parts = [t for t in parts if t]
    if not parts:
        return []
    lh = h / len(parts)
    return [Line(t, x, y + i * lh, w, lh, CONF, "", i) for i, t in enumerate(parts)]


def parse_chandra_html(html: str, width: int, height: int) -> Page:
    """HTML thô của Chandra (các khối <div data-bbox data-label> ở cấp trên) -> Page với tọa độ pixel."""
    import lxml.html

    root = lxml.html.fromstring(f"<div>{html}</div>")
    blocks: list[Block] = []
    for order, div in enumerate(root.xpath("./div")):
        label = div.get("data-label", "")
        if _KIND.get(label, "text") is None:
            continue
        box = _bbox(div, width, height)
        if box is None:
            continue
        x, y, w, h = box
        if label == "Table" or div.xpath(".//table"):
            table = div.xpath(".//table")
            lines = _table_lines(table[0], x, y, w, h) if table else []
            kind = "table" if lines else _KIND.get(label, "text")
        else:
            lines = _text_lines(div, x, y, w, h)
            kind = _KIND.get(label, "text")
        for i, l in enumerate(lines):
            l.order = order * 1000 + i
        if lines:
            blocks.append(Block(kind, x, y, w, h, lines, label))
    return Page(width, height, blocks)


class ChandraEngine(OcrEngine):
    name = "chandra"
    version = CHANDRA_VERSION
    needs_gpu = True

    @classmethod
    def is_available(cls):
        if importlib.util.find_spec("chandra") is None:
            return False, "chưa cài (pip install chandra-ocr)"
        return True, ""

    def __init__(self, method: str = "vllm", **_):
        ok, why = self.is_available()
        if not ok:
            raise RuntimeError(f"Engine Chandra {why}.")
        from chandra.model import InferenceManager   # import lười: chỉ khi thật sự dùng
        self.manager = InferenceManager(method=method)

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:
        from chandra.model.schema import BatchInputItem

        img = Image.fromarray(img_rgb.astype(np.uint8))
        out = self.manager.generate([BatchInputItem(image=img)])[0]
        if out.error:
            raise RuntimeError(f"Chandra lỗi khi xử lý {name}")
        return parse_chandra_html(out.raw, img.width, img.height)
