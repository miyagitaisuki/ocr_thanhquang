"""Tách chữ của một trang từ file .txt kết quả (dùng cho khung xem trước trong GUI)."""
from __future__ import annotations

import re

_HDR = re.compile(r"^=== Trang (\d+) ===$", re.M)


def page_text(txt: str, pno: int) -> str | None:
    """Chữ của trang pno trong nội dung file .txt; None nếu không có trang đó."""
    parts = _HDR.split(txt)          # [đầu, số trang, nội dung, số trang, nội dung, ...]
    for i in range(1, len(parts), 2):
        if int(parts[i]) == pno:
            return parts[i + 1].strip("\n")
    return None
