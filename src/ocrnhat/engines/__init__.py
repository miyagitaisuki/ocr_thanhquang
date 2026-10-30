"""Đăng ký engine OCR. Thêm engine mới: viết lớp kế thừa OcrEngine, thêm tên vào _NAMES và nhánh vào _cls."""
from __future__ import annotations

from .base import OcrEngine

DEFAULT = "auto"      # có GPU rời đủ VRAM và Chandra dùng được -> chandra, ngược lại ndlocr
FALLBACK = "ndlocr"
_NAMES = ("ndlocr", "chandra", "paddle", "ocr_vi")   # paddle: tiếng Anh + Trung; ocr_vi: tiếng Việt


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
    if name == "paddle":
        from .paddle import PaddleEngine
        return PaddleEngine
    if name == "ocr_vi":
        from .viet import VietnameseEngine
        return VietnameseEngine
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
        return FALLBACK, "không có GPU rời đủ VRAM"
    ok, why = _cls("chandra").is_available()
    if not ok:
        return FALLBACK, f"có GPU {g.name} nhưng Chandra {why}"
    return "chandra", f"GPU {g.name} ({g.vram_mb} MB, {g.backend})"


# engine nào dùng được cho ngôn ngữ nào (lang của --lang); auto chọn engine mặc định của ngôn ngữ
LANG_ENGINES = {"ja": ("ndlocr", "chandra"), "en": ("paddle", "chandra"), "zh": ("paddle", "chandra"),
                "vi": ("ocr_vi", "chandra"), "all": ("chandra",)}
DEFAULT_FOR_LANG = {"en": "paddle", "zh": "paddle", "vi": "ocr_vi", "all": "chandra"}


def resolve_for_lang(name: str, lang: str) -> tuple[str, str]:
    """Engine dùng cho (name, lang). Ném ValueError nếu engine không hỗ trợ ngôn ngữ đó."""
    if name == "auto" and lang in DEFAULT_FOR_LANG:
        return DEFAULT_FOR_LANG[lang], "theo ngôn ngữ"
    eng, why = resolve(name)
    if eng not in LANG_ENGINES.get(lang, ()):
        raise ValueError(f"Ngôn ngữ '{lang}' không dùng được với engine '{eng}'. Dùng: {', '.join(LANG_ENGINES[lang])}.")
    return eng, why


def batch_size(name: str) -> int:
    """Số trang gom lại mỗi lần OCR. Chỉ Chandra (VLM trên GPU) có batch; theo VRAM của card đang dùng."""
    if name != "chandra":
        return 1
    from .. import gpu
    from .chandra import batch_for_vram
    g = gpu.best_gpu()
    return batch_for_vram(g.vram_mb if g else None)


def create(name: str = DEFAULT, **kw) -> OcrEngine:
    if name == "auto":
        name = resolve(name)[0]
    if name not in _NAMES:
        raise ValueError(f"Engine không có: {name}. Có: {', '.join(_NAMES)}")
    return _cls(name)(**kw)
