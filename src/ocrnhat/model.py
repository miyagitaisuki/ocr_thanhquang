"""Mô hình dữ liệu trung gian chung cho mọi engine OCR: Page -> Block -> Line (tọa độ pixel)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Line:
    text: str
    x: float
    y: float
    w: float
    h: float
    conf: float = 0.0
    type: str = ""
    order: int = 0

    @property
    def x1(self): return self.x + self.w
    @property
    def y1(self): return self.y + self.h
    @property
    def cx(self): return self.x + self.w / 2
    @property
    def cy(self): return self.y + self.h / 2
    @property
    def vertical(self): return self.h > 1.5 * self.w and len(self.text) > 1
    @property
    def size(self):  # cỡ chữ ước lượng
        return self.w if self.vertical else self.h


@dataclass
class Block:
    kind: str                     # text | table | ruby | header | folio | figure | other
    x: float
    y: float
    w: float
    h: float
    lines: list[Line] = field(default_factory=list)
    label: str = ""

    @property
    def order(self):
        return min((l.order for l in self.lines), default=10 ** 9)


@dataclass
class Page:
    width: int
    height: int
    blocks: list[Block]


def page_to_dict(p: Page) -> dict:
    """Page -> dict thuần (JSON được). Dùng khi gửi kết quả OCR qua tiến trình con GPU."""
    from dataclasses import asdict
    return asdict(p)


def page_from_dict(d: dict) -> Page:
    return Page(
        width=d["width"], height=d["height"],
        blocks=[Block(kind=b["kind"], x=b["x"], y=b["y"], w=b["w"], h=b["h"],
                      lines=[Line(**l) for l in b["lines"]], label=b.get("label", ""))
                for b in d["blocks"]])
