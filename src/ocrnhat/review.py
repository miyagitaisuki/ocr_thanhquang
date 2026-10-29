"""Chế độ rà soát: ảnh trang (khung đỏ quanh dòng độ tin cậy thấp) cạnh văn bản nhận dạng, ra HTML tự chứa."""
from __future__ import annotations

import base64
import html
import io
from pathlib import Path

import numpy as np

from .model import Page
from .layout import Para, Table

_CSS = """body{font-family:'Yu Gothic','Meiryo',sans-serif;margin:0;background:#f4f4f4}
.pg{display:flex;gap:16px;padding:16px;border-bottom:4px solid #999;background:#fff}
.pg img{width:48%;height:auto;align-self:flex-start;position:sticky;top:8px}
.tx{flex:1;font-size:15px;line-height:1.7}.tx h3{margin:.4em 0}.low{background:#ffd6d6;border-bottom:2px solid #d00}
table{border-collapse:collapse;margin:8px 0}td{border:1px solid #888;padding:2px 6px;white-space:pre-wrap}
.meta{color:#666;font-size:12px}"""


def _overlay(img: np.ndarray, page: Page, thr: float) -> str:
    from PIL import Image, ImageDraw
    im = Image.fromarray(img).convert("RGB")
    d = ImageDraw.Draw(im)
    for b in page.blocks:
        for l in b.lines:
            if l.conf < thr and l.text.strip():
                d.rectangle([l.x, l.y, l.x1, l.y1], outline=(220, 0, 0), width=3)
    im.thumbnail((1100, 1600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


def _cls(conf: float, thr: float) -> str:
    return ' class="low"' if conf < thr else ""


def render_page(pno: int, items: list, page: Page, img: np.ndarray, thr: float) -> tuple[str, int]:
    low = 0
    parts = []
    for it in items:
        if isinstance(it, Table):
            grid = {(c.r, c.c): c for c in it.cells}
            rows = []
            for r in range(it.n_rows):
                tds = []
                for c in range(it.n_cols):
                    cell = grid.get((r, c))
                    if cell is None:
                        continue
                    low += cell.conf < thr
                    span = (f' rowspan="{cell.rs}"' if cell.rs > 1 else "") + (f' colspan="{cell.cs}"' if cell.cs > 1 else "")
                    tds.append(f"<td{span}{_cls(cell.conf, thr)}>{html.escape(cell.text)}</td>")
                rows.append("<tr>" + "".join(tds) + "</tr>")
            parts.append("<table>" + "".join(rows) + "</table>")
        else:
            low += it.conf < thr
            tag = "h3" if it.kind == "heading" else "p"
            parts.append(f"<{tag}{_cls(it.conf, thr)} title=\"conf={it.conf:.2f}\">{html.escape(it.text)}</{tag}>")
    b64 = _overlay(img, page, thr)
    sec = (f'<section class="pg"><img src="data:image/jpeg;base64,{b64}"><div class="tx">'
           f'<div class="meta">Trang {pno} - {low} mục độ tin cậy thấp (&lt; {thr})</div>{"".join(parts)}</div></section>')
    return sec, low


def write_review(sections: list[str], out: Path, title: str) -> None:
    out.write_text(f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title><style>{_CSS}</style>"
                   + "".join(sections), encoding="utf-8")
