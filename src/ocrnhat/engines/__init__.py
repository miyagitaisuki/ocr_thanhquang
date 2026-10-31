"""Đăng ký engine OCR. Thêm engine mới: viết lớp kế thừa OcrEngine, thêm tên vào _NAMES và nhánh vào _cls."""
from __future__ import annotations

from .base import OcrEngine

DEFAULT = "auto"      # tiếng Nhật -> ndlocr (GPU được dùng qua --device, không đổi engine)
FALLBACK = "ndlocr"
_NAMES = ("ndlocr", "paddle", "ocr_vi", "yomitoku")   # paddle: tiếng Anh + Trung; ocr_vi: tiếng Việt; yomitoku: tiếng Nhật, tùy chọn (CC BY-NC-SA)


def available() -> list[str]:
    return ["auto"] + list(_NAMES)


def _cls(name: str):
    # import tường minh (không dùng importlib) để PyInstaller đưa đủ module vào exe; import vẫn lười
    if name == "ndlocr":
        from .ndlocr import NdlocrEngine
        return NdlocrEngine
    if name == "paddle":
        from .paddle import PaddleEngine
        return PaddleEngine
    if name == "ocr_vi":
        from .viet import VietnameseEngine
        return VietnameseEngine
    if name == "yomitoku":
        from .yomitoku import YomitokuEngine
        return YomitokuEngine
    raise KeyError(name)


def engine_version(name: str) -> str:
    """Phiên bản engine cho khóa cache, lấy từ thuộc tính lớp (không nạp model)."""
    return _cls(name).version


def resolve(name: str = DEFAULT) -> tuple[str, str]:
    """'auto' -> tên engine cụ thể + lý do (để in cho người dùng). Tên khác trả nguyên."""
    if name != "auto":
        return name, "chọn thủ công"
    return FALLBACK, "tiếng Nhật"


# engine nào dùng được cho ngôn ngữ nào (lang của --lang); auto chọn engine mặc định của ngôn ngữ
LANG_ENGINES = {"ja": ("ndlocr", "yomitoku"), "en": ("paddle",), "zh": ("paddle",), "vi": ("ocr_vi",)}
DEFAULT_FOR_LANG = {"en": "paddle", "zh": "paddle", "vi": "ocr_vi"}


def resolve_for_lang(name: str, lang: str) -> tuple[str, str]:
    """Engine dùng cho (name, lang). Ném ValueError nếu engine không hỗ trợ ngôn ngữ đó."""
    if name == "auto" and lang in DEFAULT_FOR_LANG:
        return DEFAULT_FOR_LANG[lang], "theo ngôn ngữ"
    eng, why = resolve(name)
    if eng not in LANG_ENGINES.get(lang, ()):
        raise ValueError(f"Ngôn ngữ '{lang}' không dùng được với engine '{eng}'. Dùng: {', '.join(LANG_ENGINES[lang])}.")
    return eng, why


def create(name: str = DEFAULT, **kw) -> OcrEngine:
    if name == "auto":
        name = resolve(name)[0]
    if name not in _NAMES:
        raise ValueError(f"Engine không có: {name}. Có: {', '.join(_NAMES)}")
    return _cls(name)(**kw)
