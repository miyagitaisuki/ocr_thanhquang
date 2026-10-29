"""Đăng ký engine OCR. Thêm engine mới: viết lớp kế thừa OcrEngine rồi thêm vào _LOADERS."""
from __future__ import annotations

from .base import OcrEngine

DEFAULT = "ndlocr"


def _ndlocr(**kw):
    from .ndlocr import NdlocrEngine
    return NdlocrEngine(**kw)


def _chandra(**kw):
    from .chandra import ChandraEngine
    return ChandraEngine(**kw)


_LOADERS = {"ndlocr": _ndlocr, "chandra": _chandra}   # import chậm: engine nặng chỉ nạp khi được chọn


def available() -> list[str]:
    return list(_LOADERS)


def create(name: str = DEFAULT, **kw) -> OcrEngine:
    try:
        return _LOADERS[name](**kw)
    except KeyError:
        raise ValueError(f"Engine không có: {name}. Có: {', '.join(_LOADERS)}") from None
