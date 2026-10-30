"""Engine Chandra OCR 2 (datalab-to/chandra-ocr-2, VLM ~4-5B, cần GPU).

Giấy phép: mã Apache-2.0; trọng số theo OpenRAIL-M sửa đổi (xem NOTICE.md). Trọng số không được đóng vào exe;
máy người dùng tự cài `pip install ".[chandra]"` và mô hình được tải về lần đầu dùng.
Mô hình chạy cục bộ bằng HuggingFace (mặc định) hoặc qua máy chủ vLLM (method="vllm")."

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


_HEAD_LABELS = ("Section-Header", "Title")
_HEAD_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_TITLE_TYPE = "タイトル本文"    # nhãn tiêu đề của NDLOCR; layout.py nhận tiêu đề theo nhãn này


def _text_groups(div, x: float, y: float, w: float, h: float) -> list[list[Line]]:
    """Khối văn bản -> các dòng có khoảng cách giống sách in.

    Chandra không cho tọa độ dòng, nên ước lượng: cỡ chữ từ diện tích khối và số ký tự; mỗi đoạn được chia
    thành các dòng đủ dài theo bề ngang; khoảng cách giữa hai đoạn lớn hơn khoảng cách trong một đoạn.
    Tiêu đề (h1..h6 hoặc nhãn Section-Header/Title) là một dòng có nhãn tiêu đề.
    Mỗi đoạn (và mỗi tiêu đề) là một nhóm dòng riêng, để layout.py không nối nhầm hai đoạn.
    """
    label = div.get("data-label", "")
    parts: list[tuple[str, bool]] = []
    for el in div.xpath(".//p|.//li|.//h1|.//h2|.//h3|.//h4|.//h5|.//h6"):
        t = " ".join(el.text_content().split())
        if t:
            parts.append((t, el.tag in _HEAD_TAGS or label in _HEAD_LABELS))
    if not parts:
        t = " ".join(div.text_content().split())
        if t:
            parts.append((t, label in _HEAD_LABELS))
    if not parts:
        return []
    chars = sum(len(t) for t, head in parts if not head)
    n_head = sum(1 for _, head in parts if head)
    # cỡ chữ ước lượng: diện tích khối (70% lấp đầy) chia cho số ký tự
    lh = (w * h * 0.7 / chars) ** 0.5 if chars else h / max(1, n_head) / 1.5
    cpl = max(1, int(w / lh))
    # đơn vị: (chữ, là tiêu đề, bắt đầu đoạn mới?)
    units: list[tuple[str, bool, bool]] = []
    for t, head in parts:
        if head:
            units.append((t, True, True))
            continue
        for i in range(0, len(t), cpl):
            units.append((t[i:i + cpl], False, i == 0))
    # độ dài theo đơn vị: dòng thân 1.0, tiêu đề 1.6; khoảng cách giữa đoạn 0.6 (cộng vào trước đoạn mới)
    total = sum(1.6 if head else 1.0 for _, head, _ in units) + 0.6 * sum(1 for i, (_, _, new) in enumerate(units) if new and i > 0)
    scale = h / total
    groups: list[list[Line]] = []
    cur = y
    for i, (t, head, new) in enumerate(units):
        if new or not groups:
            groups.append([])
        if new and i > 0:
            cur += 0.6 * scale
        if head:
            groups[-1].append(Line(t, x, cur, w, 1.2 * scale, CONF, _TITLE_TYPE))
            cur += 1.6 * scale
        else:
            groups[-1].append(Line(t, x, cur, w, 0.85 * scale, CONF, ""))
            cur += 1.0 * scale
    return groups


def parse_chandra_html(html: str, width: int, height: int) -> Page:
    """HTML thô của Chandra (các khối <div data-bbox data-label> ở cấp trên) -> Page với tọa độ pixel."""
    import lxml.html

    root = lxml.html.fromstring(f"<div>{html}</div>")
    blocks: list[Block] = []
    seq = 0   # thứ tự đọc: theo thứ tự khối và đoạn trong HTML
    for div in root.xpath("./div"):
        label = div.get("data-label", "")
        if _KIND.get(label, "text") is None:
            continue
        box = _bbox(div, width, height)
        if box is None:
            continue
        x, y, w, h = box
        if label == "Table" or div.xpath(".//table"):
            table = div.xpath(".//table")
            groups = [_table_lines(table[0], x, y, w, h)] if table else []
            kind = "table" if groups and groups[0] else _KIND.get(label, "text")
        else:
            groups = _text_groups(div, x, y, w, h)
            kind = _KIND.get(label, "text")
        for g in groups:
            if not g:
                continue
            for l in g:
                l.order = seq
                seq += 1
            gx = min(l.x for l in g); gy = min(l.y for l in g)
            blocks.append(Block(kind, gx, gy, max(l.x1 for l in g) - gx, max(l.y1 for l in g) - gy, g, label))
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

    def __init__(self, method: str = "hf", **_):
        ok, why = self.is_available()
        if not ok:
            raise RuntimeError(f"Engine Chandra {why}.")
        from chandra.model import InferenceManager   # import lười: chỉ khi thật sự dùng
        self.manager = InferenceManager(method=method)

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:
        from chandra.model.schema import BatchInputItem

        img = Image.fromarray(img_rgb.astype(np.uint8))
        out = self.manager.generate([BatchInputItem(image=img, prompt_type="ocr_layout")])[0]
        if out.error:
            raise RuntimeError(f"Chandra lỗi khi xử lý {name}")
        return parse_chandra_html(out.raw, img.width, img.height)
