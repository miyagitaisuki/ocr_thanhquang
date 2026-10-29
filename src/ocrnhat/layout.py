"""Dựng đoạn văn, tiêu đề và bảng từ kết quả bố cục/tọa độ của NDLOCR-Lite. Chỉ giữ tiếng Nhật."""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

import numpy as np

from .model import Block, Line, Page

_JP = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")
_KANJI = re.compile(r"[㐀-䶿一-鿿]")
_KANA_ONLY = re.compile(r"^[぀-ヿー・、。\s]+$")
_LATIN_WORD = re.compile(r"[A-Za-zÀ-ỹ]{3,}")
_SENT_END = re.compile(r"[。！？!?」』）)]$")
_BULLET = re.compile(r"^([◆◇●○■□※❖・·]|\d+[\.)）]|[(（]\d+[)）]|[①-⑳])")


def jp_ratio(text: str) -> float:
    chars = [c for c in text if c.isalnum() or _JP.match(c)]
    return (sum(1 for c in chars if _JP.match(c)) / len(chars)) if chars else 0.0


@dataclass
class Para:
    text: str
    kind: str = "body"            # body | heading
    x: float = 0
    y: float = 0
    x1: float = 0
    y1: float = 0
    size: float = 0
    conf: float = 1.0
    ruby: list = field(default_factory=list)   # [(bắt đầu, kết thúc, cách đọc)] theo chỉ số ký tự của text


@dataclass
class Cell:
    r: int
    c: int
    rs: int = 1
    cs: int = 1
    text: str = ""
    conf: float = 1.0


@dataclass
class Table:
    n_rows: int
    n_cols: int
    cells: list[Cell] = field(default_factory=list)


# ---------- lọc dòng ----------

def _inside(l: Line, b: Block, m: float = 4) -> bool:
    return b.x - m <= l.cx <= b.x + b.w + m and b.y - m <= l.cy <= b.y + b.h + m


class _Filter:
    def __init__(self, page: Page):
        self.rubies = [b for b in page.blocks if b.kind == "ruby"]
        self.ruby: dict[int, list[tuple[float, float, str]]] = {}
        sizes = sorted(l.size for b in page.blocks if b.kind in ("text", "table") for l in b.lines
                       if _KANJI.search(l.text) and l.conf >= 0.5)
        self.ref = sizes[int(len(sizes) * 0.8)] if sizes else 0
        self.kanji_lines = [l for b in page.blocks if b.kind in ("text", "table") for l in b.lines
                            if _KANJI.search(l.text) and l.conf >= 0.5]

    def _base_below(self, l: Line, strict: bool = True) -> Line | None:
        """Dòng chữ Hán nằm ngay dưới dòng kana `l` (chồng lấn ngang) và lớn hơn: dòng gốc của furigana."""
        best, best_gap = None, 1e9
        for k in self.kanji_lines:
            if k is l or k.vertical: continue
            ov = min(l.x1, k.x1) - max(l.x, k.x)
            gap = k.y - l.y1
            if ov >= (0.5 if strict else 0.3) * l.w and -0.7 * k.size <= gap <= 0.9 * k.size and l.cy < k.cy - 0.2 * k.size \
                    and l.size < 0.95 * k.size and gap < best_gap:
                best, best_gap = k, gap
        return best

    def _above_kanji(self, l: Line) -> bool:
        return self._base_below(l) is not None

    def collect_ruby(self, page: Page) -> None:
        """Gắn mỗi dòng furigana (trong khối ルビ hoặc nhận ra bằng kích thước/vị trí) vào dòng chữ Hán bên dưới."""
        self.ruby: dict[int, list[tuple[float, float, str]]] = {}
        for b in page.blocks:
            for l in b.lines:
                t = l.text.replace(" ", "")
                if b.kind == "ruby":
                    pass
                elif b.kind in ("text", "table") and _KANA_ONLY.match(t) and len(t) <= 30 and self.furigana(l):
                    pass
                else:
                    continue
                if not _KANA_ONLY.match(t) or l.vertical:
                    continue
                base = self._base_below(l, strict=False)
                if base is not None:
                    self.ruby.setdefault(id(base), []).append((l.x, l.x1, t))

    def furigana(self, l: Line) -> bool:
        if not _KANA_ONLY.match(l.text.replace(" ", "")): 
            return False
        if any(_inside(l, b) for b in self.rubies):
            return True
        if len(l.text) <= 30 and self._above_kanji(l):
            return True
        return bool(self.ref and l.size < 0.78 * self.ref and len(l.text) <= 20)

    def keep(self, l: Line, table: bool = False) -> bool:
        t = l.text.strip()
        if not t or self.furigana(l) or _LATIN_WORD.search(t):
            return False
        if _JP.search(t):
            return jp_ratio(t) >= 0.6
        return (table and l.conf >= 0.7 and (not self.ref or l.size >= 0.85 * self.ref)
                and bool(re.fullmatch(r"[\d０-９.,・\-～~:：/／()（）%％]+", t)))


# ---------- đoạn văn ----------

_KANJI_RUN = re.compile(r"[㐀-䶿一-鿿々〇]+")


def _line_ruby(l: Line, anns: list[tuple[float, float, str]], off: int) -> list[tuple[int, int, str]]:
    """Đổi vị trí ngang của furigana thành khoảng ký tự trong dòng (ký tự chia đều theo bề ngang dòng)."""
    n = len(l.text)
    if not n or l.w <= 0:
        return []
    out = []
    for x, x1, reading in anns:
        lo = (x - l.x) / l.w * n
        hi = (x1 - l.x) / l.w * n
        runs = [m for m in _KANJI_RUN.finditer(l.text) if m.end() > lo + 0.3 and m.start() < hi - 0.3]
        if not runs:
            continue
        total = sum(m.end() - m.start() for m in runs)
        pos = 0
        for i, m in enumerate(runs):   # nhiều cụm Hán: chia cách đọc theo số chữ Hán (gần đúng)
            k = len(reading) - pos if i == len(runs) - 1 else max(1, round(len(reading) * (m.end() - m.start()) / total))
            part = reading[pos:pos + k]; pos += k
            if part:
                out.append((off + m.start(), off + m.end(), part))
    return out


def _mk(ls: list[Line], kind: str = "body", flt: "_Filter | None" = None) -> Para:
    ruby, off = [], 0
    for l in ls:
        if flt is not None and id(l) in flt.ruby:
            ruby += _line_ruby(l, flt.ruby[id(l)], off)
        off += len(l.text)
    return Para("".join(l.text for l in ls), kind, min(l.x for l in ls), min(l.y for l in ls),
                max(l.x1 for l in ls), max(l.y1 for l in ls), statistics.median(l.size for l in ls),
                min(l.conf for l in ls), ruby)


def _merge_paras(items: list[tuple[int, "Para | Table"]]) -> list[tuple[int, "Para | Table"]]:
    """Nối đoạn bị tách giữa hai khối: đoạn trước chưa kết câu, đoạn sau cùng cột, sát bên dưới."""
    out: list[tuple[int, "Para | Table"]] = []
    for o, it in items:
        if out and isinstance(it, Para) and isinstance(out[-1][1], Para):
            a: Para = out[-1][1]
            if (a.kind == "body" and it.kind == "body" and not _SENT_END.search(a.text) and not _BULLET.match(it.text)
                    and abs(it.x - a.x) < 1.2 * a.size and -0.5 * a.size < it.y - a.y1 < 1.6 * a.size):
                a.ruby += [(s + len(a.text), e + len(a.text), r) for s, e, r in it.ruby]; a.text += it.text; a.x1 = max(a.x1, it.x1); a.y1 = it.y1; a.conf = min(a.conf, it.conf)
                continue
        out.append((o, it))
    return out


def _paragraphs(block: Block, flt: _Filter) -> list[Para]:
    ls = sorted((l for l in block.lines if flt.keep(l)), key=lambda l: l.order)
    if not ls:
        return []
    H = statistics.median(l.size for l in ls) or 1
    # tiêu đề: khối ngắn, nhãn tiêu đề hoặc chữ lớn, không kết thúc bằng 。
    text_all = "".join(l.text for l in ls)
    big = flt.ref and statistics.median(l.size for l in ls) > 1.25 * flt.ref
    labelled = all(l.type == "タイトル本文" for l in ls)
    if (len(ls) <= 2 and len(text_all) <= 30 and not text_all.endswith("。") and (big or labelled)
            and not re.search(r"[をにはがでとのへもや、,]$", text_all)):
        return [_mk(ls, "heading", flt)]
    left = min(l.x for l in ls); right = max(l.x1 for l in ls)
    paras: list[list[Line]] = []
    for l in ls:
        new = not paras
        if paras:
            p = paras[-1][-1]
            if not l.vertical and not p.vertical:
                if l.x - left > 0.6 * H: new = True
                elif _SENT_END.search(p.text) and p.x1 < right - 1.5 * H: new = True
                elif _BULLET.match(l.text): new = True
        if new: paras.append([l])
        else: paras[-1].append(l)
    return [_mk(g, "body", flt) for g in paras]


# ---------- bảng ----------

def _runs(mask1d: np.ndarray, thresh: float) -> list[float]:
    hit = mask1d > thresh
    pos, i, n = [], 0, len(hit)
    while i < n:
        if hit[i]:
            j = i
            while j + 1 < n and hit[j + 1]: j += 1
            pos.append((i + j) / 2); i = j + 1
        else:
            i += 1
    return pos


def _merge_close(v: list[float], tol: float) -> list[float]:
    out: list[float] = []
    for x in sorted(v):
        if out and x - out[-1] < tol: out[-1] = (out[-1] + x) / 2
        else: out.append(x)
    return out


def _detect_grid(gray: np.ndarray, box: Block):
    import cv2
    x, y, w, h = int(box.x), int(box.y), int(box.w), int(box.h)
    x = max(0, x - 6); y = max(0, y - 6)
    crop = gray[y:y + h + 12, x:x + w + 12]
    if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
        return None
    paper = float(np.median(crop))                     # độ sáng nền giấy
    b = (crop < paper - 40).astype(np.uint8) * 255   # bắt cả đường kẻ xám mờ
    H, W = b.shape
    hor = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, W // 10), 1)))
    ver = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, H // 10))))
    ys = _merge_close(_runs((hor > 0).sum(axis=1) / W, 0.35), 8)
    xs = _merge_close(_runs((ver > 0).sum(axis=0) / H, 0.30), 8)
    if len(ys) < 2 or len(xs) < 2:
        return None
    return dict(ys=[v + y for v in ys], xs=[v + x for v in xs], hor=hor, ver=ver, ox=x, oy=y)


def _sep_present(mask: np.ndarray, axis_pos: float, a0: float, a1: float, vertical: bool, off: tuple[int, int]) -> bool:
    ox, oy = off
    p = int(round(axis_pos - (ox if vertical else oy)))
    lo, hi = int(a0 - (oy if vertical else ox)), int(a1 - (oy if vertical else ox))
    if hi <= lo: return True
    if vertical:
        strip = mask[max(0, lo):hi, max(0, p - 3):p + 4]
        return strip.size > 0 and (strip.max(axis=1) > 0).mean() >= 0.5
    strip = mask[max(0, p - 3):p + 4, max(0, lo):hi]
    return strip.size > 0 and (strip.max(axis=0) > 0).mean() >= 0.5


def _grid_cells(g) -> tuple[list[float], list[float], list[Cell]]:
    ys, xs = g["ys"], g["xs"]
    nr, nc = len(ys) - 1, len(xs) - 1
    off = (g["ox"], g["oy"])
    # vsep[r][k]: có vạch dọc ở xs[k] trong hàng r;  hsep[k][c]: có vạch ngang ở ys[k] trong cột c
    vsep = [[_sep_present(g["ver"], xs[k], ys[r], ys[r + 1], True, off) for k in range(nc + 1)] for r in range(nr)]
    hsep = [[_sep_present(g["hor"], ys[k], xs[c], xs[c + 1], False, off) for c in range(nc)] for k in range(nr + 1)]
    used = [[False] * nc for _ in range(nr)]
    cells = []
    for r in range(nr):
        for c in range(nc):
            if used[r][c]: continue
            c2 = c
            while c2 + 1 < nc and not vsep[r][c2 + 1] and not used[r][c2 + 1]: c2 += 1
            r2 = r
            while r2 + 1 < nr and all(not hsep[r2 + 1][k] and not used[r2 + 1][k] for k in range(c, c2 + 1)): r2 += 1
            for rr in range(r, r2 + 1):
                for cc in range(c, c2 + 1): used[rr][cc] = True
            cells.append(Cell(r, c, r2 - r + 1, c2 - c + 1))
    return ys, xs, cells


def _idx(v: float, edges: list[float]) -> int:
    for i in range(len(edges) - 1):
        if edges[i] <= v < edges[i + 1]: return i
    return 0 if v < edges[0] else len(edges) - 2


def _cell_text(lines: list[Line]) -> str:
    out, last = [], None
    for l in sorted(lines, key=lambda l: (round(l.cy / max(l.size, 1)), l.x)):
        if last is not None and abs(l.cy - last.cy) < 0.5 * max(l.size, 1): out[-1] += l.text
        else: out.append(l.text)
        last = l
    return "\n".join(out)


def _table(block: Block, flt: _Filter, gray: np.ndarray | None) -> Table | None:
    ls = [l for l in block.lines if flt.keep(l, table=True)]
    if not ls: return None
    g = _detect_grid(gray, block) if gray is not None else None
    if g:
        ys, xs, cells = _grid_cells(g)
        buckets: dict[tuple[int, int], list[Line]] = {}
        for l in ls:
            r, c = _idx(l.cy, ys), _idx(l.cx, xs)
            for cell in cells:                      # đưa về ô gốc của vùng gộp
                if cell.r <= r < cell.r + cell.rs and cell.c <= c < cell.c + cell.cs:
                    r, c = cell.r, cell.c; break
            buckets.setdefault((r, c), []).append(l)
        for cell in cells:
            cl = buckets.get((cell.r, cell.c), [])
            if len(cl) > 1:   # số lẻ nằm cạnh chữ khác trong cùng ô thường là furigana đọc sai
                cl = [l for l in cl if not re.fullmatch(r"[\d０-９.,]{1,3}", l.text.strip())] or cl
            cell.text = _cell_text(cl)
            cell.conf = min((l.conf for l in cl), default=1.0)
        return Table(len(ys) - 1, len(xs) - 1, cells)
    return _table_by_clustering(ls)


def _table_by_clustering(ls: list[Line]) -> Table | None:
    """Dự phòng khi bảng không có đường kẻ: hàng theo dải y, cột theo cụm x."""
    H = statistics.median(l.size for l in ls) or 1
    cols: list[list[Line]] = []
    for l in sorted(ls, key=lambda l: l.x):
        for c in cols:
            if abs(statistics.mean(m.x for m in c) - l.x) < 1.5 * H: c.append(l); break
        else: cols.append([l])
    cols.sort(key=lambda c: statistics.mean(m.x for m in c))
    rows: list[list[Line]] = []
    for l in sorted(ls, key=lambda l: l.cy):
        if rows and abs(l.cy - statistics.mean(m.cy for m in rows[-1])) < 0.6 * H: rows[-1].append(l)
        else: rows.append([l])
    t = Table(len(rows), len(cols))
    for ri, rw in enumerate(rows):
        for ci, col in enumerate(cols):
            mine = [l for l in rw if l in col]
            t.cells.append(Cell(ri, ci, 1, 1, _cell_text(mine), min((l.conf for l in mine), default=1.0)))
    return t


# ---------- trang ----------

def build_page(page: Page, img_rgb: np.ndarray | None = None) -> list[Para | Table]:
    gray = None
    if img_rgb is not None:
        import cv2
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY) if img_rgb.ndim == 3 else img_rgb
    flt = _Filter(page)
    flt.collect_ruby(page)
    items: list[tuple[int, Para | Table]] = []
    for b in page.blocks:
        if b.kind == "table":
            t = _table(b, flt, gray)
            if t: items.append((b.order, t))
        elif b.kind in ("text", "other", "figure"):
            for p in _paragraphs(b, flt): items.append((b.order, p))
    items.sort(key=lambda it: it[0])
    return [it for _, it in _merge_paras(items)]
