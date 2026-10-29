"""Đăng ký engine OCR. Thêm engine mới: viết lớp kế thừa OcrEngine rồi thêm vào _LOADERS."""
from __future__ import annotations

from .base import OcrEngine

DEFAULT = "auto"      # có GPU rời đủ VRAM và Chandra dùng được -> chandra, ngược lại ndlocr
FALLBACK = "ndlocr"


def _ndlocr(**kw):
    from .ndlocr import NdlocrEngine
    return NdlocrEngine(**kw)


def _chandra(**kw):
    from .chandra import ChandraEngine
    return ChandraEngine(**kw)


_LOADERS = {"ndlocr": _ndlocr, "chandra": _chandra}   # import chậm: engine nặng chỉ nạp khi được chọn


def available() -> list[str]:
    return ["auto"] + list(_LOADERS)


def _cls(name: str):
    if name == "chandra":
        from .chandra import ChandraEngine
        return ChandraEngine
    from .ndlocr import NdlocrEngine
    return NdlocrEngine


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
    try:
        return _LOADERS[name](**kw)
    except KeyError:
        raise ValueError(f"Engine không có: {name}. Có: {', '.join(_LOADERS)}") from None
