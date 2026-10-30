"""Gói GPU tùy chọn: torch CUDA + Chandra, tải về sau khi người dùng bấm nút trong GUI.

Exe CPU không chứa torch. Khi người dùng bấm "Cài gói GPU", pip (đóng gói sẵn trong exe) cài vào
thư mục riêng (`%LOCALAPPDATA%\\OCR-Nhat\\gpu`). Lần khởi động sau, `activate()` đưa thư mục đó vào
đường dẫn import trước khi nạp torch. Trọng số Chandra vẫn tải riêng từ Hugging Face.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request
from pathlib import Path

CU_INDEX = "https://download.pytorch.org/whl/cu126"
PYPI_INDEX = "https://pypi.org/simple"
CHANDRA_SPEC = "chandra-ocr[hf]==0.2.0"
MARKER = ".installed"


def pack_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "OCR-Nhat" / "gpu"


def installed() -> bool:
    d = pack_dir()
    return (d / MARKER).is_file() and (d / "torch").is_dir() and (d / "chandra").is_dir()


def activate() -> bool:
    """Đưa gói GPU vào đường dẫn import (gọi trước khi nạp torch hoặc chandra). Trả về có kích hoạt không."""
    if not installed():
        return False
    d = pack_dir()
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        # DLL của torch và CUDA nằm trong torch/lib và nvidia/*/bin
        for sub in [d / "torch" / "lib", *sorted((d / "nvidia").glob("*/bin"))]:
            if sub.is_dir():
                os.add_dll_directory(str(sub))
    return True


_WHEEL = r"{pkg}-(\d+\.\d+\.\d+)(?:%2B|\+)cu126-cp312-cp312-win_amd64\.whl"


def _latest_cu126(pkg: str, minor_prefix: str | None = None) -> str:
    """Phiên bản cu126 mới nhất có wheel Windows cp312 trên chỉ mục PyTorch (tùy chọn: lọc theo minor)."""
    from pip._vendor.packaging.version import Version

    with urllib.request.urlopen(f"{CU_INDEX}/{pkg}/", timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    found = {m.group(1) for m in re.finditer(_WHEEL.format(pkg=re.escape(pkg)), html)}
    if minor_prefix:
        found = {v for v in found if v.startswith(minor_prefix)}
    if not found:
        raise RuntimeError(f"Không thấy wheel {pkg} cu126 cho Windows cp312 trên {CU_INDEX}")
    return max(found, key=Version)


def cuda_pins() -> list[str]:
    """Ghim torch và torchvision cu126 khớp nhau: torch 2.X đi với torchvision 0.(X+15)."""
    torch_v = _latest_cu126("torch")
    minor = int(torch_v.split(".")[1])
    tv_v = _latest_cu126("torchvision", minor_prefix=f"0.{minor + 15}.")
    return [f"torch=={torch_v}+cu126", f"torchvision=={tv_v}+cu126"]


def pip_args(pins: list[str], target: Path) -> list[str]:
    return ["install", "--no-input", "--disable-pip-version-check", "--upgrade", "--target", str(target),
            "--index-url", PYPI_INDEX, "--extra-index-url", CU_INDEX, *pins, CHANDRA_SPEC]


def install(progress=print) -> None:
    """Cài gói GPU bằng pip trong cùng tiến trình (pip đóng gói sẵn trong exe). Ném lỗi nếu thất bại."""
    from pip._internal.cli.main import main as pip_main

    d = pack_dir()
    d.mkdir(parents=True, exist_ok=True)
    progress("Đang chọn phiên bản torch CUDA…")
    pins = cuda_pins()
    progress(f"Đang tải {', '.join(pins)} và Chandra (có thể mất nhiều phút)…")
    code = pip_main(pip_args(pins, d))
    if code != 0:
        raise RuntimeError(f"pip thoát với mã {code}")
    (d / MARKER).write_text("\n".join(pins), encoding="utf-8")
    activate()
