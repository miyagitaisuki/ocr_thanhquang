"""Thư mục dữ liệu của ứng dụng (settings.json, logs/): %LOCALAPPDATA%\\OCR-Nhat trên Windows."""
from __future__ import annotations

import os
from pathlib import Path


def app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "OCR-Nhat"
