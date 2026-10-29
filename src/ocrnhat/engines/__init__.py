"""Đăng ký engine OCR. Thêm engine mới: viết lớp kế thừa OcrEngine, thêm tên vào _NAMES và nhánh vào _cls."""
from __future__ import annotations

from .base import OcrEngine

DEFAULT = "auto"      # có GPU rời đủ VRAM và Chandra dùng được -> chandra, ngược lại ndlocr
FALLBACK = "ndlocr"
_NAMES = ("ndlocr", "chandra")


def available() -> list[str]:
    return ["auto"] + list(_NAMES)


def _cls(name: str):
    # import tường minh (không dùng importlib) để PyInstaller đưa đủ module vào exe; import vẫn lười
    if name == "ndlocr":
        from .ndlocr import NdlocrEngine
        return NdlocrEngine
    if name == "chandra":
        from .chandra import ChandraEngine
        return ChandraEngine
    raise KeyError(name)


def engine_version(name: str) -> str:
    """Phiên bản engine cho khóa cache, lấy từ thuộc tính lớp (không nạp model)."""
    return _cls(name).version


def resolve(name: str = DEFAULT) -> tuple[str, str]:
    """'auto' -> tên engine cụ thể + lý do (để in cho người dùng). Tên khác trả nguyên."""
    if name != "auto":
        return name, "chọn thủ công"
    from .. import gpu
    g = gpu.best_gpu()
    if g is None:
        return FALLBACK, "mặc định"
    ok, why = _cls("chandra").is_available()
    if not ok:
        return FALLBACK, f"có GPU {g.name} nhưng Chandra {why}"
    return "chandra", f"GPU {g.name} ({g.vram_mb} MB, {g.backend})"


def create(name: str = DEFAULT, **kw) -> OcrEngine:
    if name == "auto":
        name = resolve(name)[0]
    if name not in _NAMES:
        raise ValueError(f"Engine không có: {name}. Có: {', '.join(_NAMES)}")
    return _cls(name)(**kw)
