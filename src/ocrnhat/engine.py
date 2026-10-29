"""Engine OCR: NDLOCR-Lite (Thư viện Quốc hội Nhật Bản, CC BY 4.0), chạy ONNX trên CPU.

Mã NDLOCR-Lite không nằm trong repo này: CI/`scripts/fetch_ndlocr.py` tải đúng phiên bản đã ghim vào
`vendor/ndlocr-lite`. Xem NOTICE.md để biết nguồn và giấy phép.
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

NDL_COMMIT = "e57f7c6bd9cfb3de5f12f008e71ad2122bd44bfd"


def find_ndl_src() -> Path:
    cands = []
    if os.environ.get("OCRNHAT_NDL_SRC"):
        cands.append(Path(os.environ["OCRNHAT_NDL_SRC"]))
    if getattr(sys, "_MEIPASS", None):
        cands.append(Path(sys._MEIPASS) / "ndlocr_src")
    here = Path(__file__).resolve()
    cands += [here.parents[2] / "vendor" / "ndlocr-lite" / "src", Path.cwd() / "vendor" / "ndlocr-lite" / "src"]
    frozen = bool(getattr(sys, "_MEIPASS", None))
    for c in cands:
        # bản exe: mã `ocr.py` đã nằm trong gói, chỉ cần thư mục model/config
        if (c / "model").is_dir() and ((c / "ocr.py").is_file() or (frozen and str(c).startswith(sys._MEIPASS))):
            return c
    raise FileNotFoundError(
        "Không thấy NDLOCR-Lite. Chạy `python scripts/fetch_ndlocr.py` hoặc đặt OCRNHAT_NDL_SRC.")


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


_KIND = {"表組": "table", "ルビ": "ruby", "柱": "header", "ノンブル": "folio", "図版": "figure", "広告": "other"}


def parse_page_xml(page_xml: str, width: int, height: int) -> Page:
    root = ET.fromstring(page_xml)
    blocks: list[Block] = []

    def mk_line(e):
        return Line(e.get("STRING", ""), float(e.get("X")), float(e.get("Y")), float(e.get("WIDTH")),
                    float(e.get("HEIGHT")), float(e.get("CONF", 0) or 0), e.get("TYPE", ""), int(e.get("ORDER", 0) or 0))

    for ch in root:
        if ch.tag == "TEXTBLOCK":
            ls = [mk_line(e) for e in ch.findall("LINE")]
            if ls:
                xs0 = min(l.x for l in ls); ys0 = min(l.y for l in ls)
                blocks.append(Block("text", xs0, ys0, max(l.x1 for l in ls) - xs0, max(l.y1 for l in ls) - ys0, ls))
        elif ch.tag == "BLOCK":
            t = ch.get("TYPE", "")
            blocks.append(Block(_KIND.get(t, "other"), float(ch.get("X", 0)), float(ch.get("Y", 0)),
                                float(ch.get("WIDTH", 0)), float(ch.get("HEIGHT", 0)),
                                [mk_line(e) for e in ch.findall("LINE")], t))
        elif ch.tag == "LINE":
            l = mk_line(ch)
            blocks.append(Block("text", l.x, l.y, l.w, l.h, [l]))
    return Page(width, height, blocks)


class Engine:
    def __init__(self, device: str = "cpu"):
        src = find_ndl_src()
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        import ocr as ndl  # noqa: WPS433 (mã NDLOCR-Lite)

        self.ndl = ndl
        m, c = src / "model", src / "config"
        args = Namespace(
            det_weights=str(m / "deim-s-1024x1024.onnx"), det_classes=str(c / "ndl.yaml"),
            det_score_threshold=0.2, det_conf_threshold=0.25, det_iou_threshold=0.2,
            rec_weights30=str(next(m.glob("parseq-ndl-24x256-*.onnx"))),
            rec_weights50=str(next(m.glob("parseq-ndl-24x384-*.onnx"))),
            rec_weights=str(next(m.glob("parseq-ndl-24x768-*.onnx"))),
            rec_classes=str(c / "NDLmoji.yaml"), device=device, enable_tcy=False)
        self.detector = ndl.get_detector(args)
        self.r30 = ndl.get_recognizer(args, args.rec_weights30)
        self.r50 = ndl.get_recognizer(args, args.rec_weights50)
        self.r100 = ndl.get_recognizer(args, args.rec_weights)

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:
        r = self.ndl._run_ocr_on_image_array(self.detector, self.r30, self.r50, self.r100, name, img_rgb, "", False)
        return parse_page_xml(r["page_xml"], r["img_width"], r["img_height"])
