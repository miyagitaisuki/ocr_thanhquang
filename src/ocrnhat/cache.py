"""Cache kết quả OCR từng trang theo hash nội dung file + trang + dpi + phiên bản engine."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .model import Block, Line, Page

_VER = 1


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:20]


class PageCache:
    def __init__(self, root: Path, fhash: str, dpi: int, engine: str, engine_ver: str):
        self.dir = Path(root)
        self.prefix = f"{fhash}_{dpi}_{engine}-{engine_ver}_v{_VER}"

    def _path(self, pno: int) -> Path:
        return self.dir / f"{self.prefix}_p{pno}.json"

    def get(self, pno: int) -> Page | None:
        p = self._path(pno)
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return Page(d["width"], d["height"],
                        [Block(b["kind"], b["x"], b["y"], b["w"], b["h"], [Line(**l) for l in b["lines"]], b["label"])
                         for b in d["blocks"]])
        except Exception:
            return None

    def has(self, pno: int) -> bool:
        return self._path(pno).is_file()

    def put(self, pno: int, page: Page) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._path(pno).write_text(json.dumps(asdict(page), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
