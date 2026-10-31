"""Nhãn, ánh xạ nhãn -> khóa và đọc tùy chọn OCR cho giao diện. Không phụ thuộc giao diện, test được không cần cửa sổ.

Giao diện truyền vào hàm get(tên, mặc định) để lấy giá trị ô nhập; hàm trả về dict đúng với pipeline.process_file.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

from . import pipeline
from .appdir import app_dir

SETTINGS = app_dir() / "settings.json"   # dùng chung cho cả hai giao diện
LOG_FILE = app_dir() / "logs" / "app.log"

ENGINE_LABELS = {"auto": "Tự động (công cụ phù hợp)", "ndlocr": "Tiếng Nhật – NDLOCR",
                 "paddle": "Tiếng Anh, Trung – PaddleOCR",
                 "ocr_vi": "Tiếng Việt – VietOCR"}
LANG_LABELS = {"ja": "Tiếng Nhật", "en": "Tiếng Anh", "zh": "Tiếng Trung", "vi": "Tiếng Việt",
               }
# ngôn ngữ được chọn cho từng engine (auto: mọi ngôn ngữ, engine tự chọn theo ngôn ngữ)
ENGINE_LANGS = {"ndlocr": ("ja",), "paddle": ("en", "zh"),
                "ocr_vi": ("vi",), "auto": ("ja", "en", "zh", "vi")}
KANA_LABELS = {"": "Tắt", "template": "Mẫu chữ IPAGothic (thử nghiệm)", "tesseract": "Tesseract (thử nghiệm)"}
MERGE_LABELS = {True: "Gộp trang (mặc định)", False: "Giữ nguyên trang"}


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def open_path(p: Path) -> None:
    """Mở file hoặc thư mục bằng ứng dụng mặc định của hệ điều hành."""
    if os.name == "nt":
        os.startfile(str(p))  # noqa: S606 (chủ ý: mở bằng ứng dụng mặc định)
    else:
        subprocess.Popen(["xdg-open", str(p)])


def dev_labels(cuda: bool) -> dict[str, str]:
    """Nhãn thiết bị. Chỉ có GPU khi onnxruntime có CUDA (bản GPU)."""
    return {"auto": "Tự động", "cpu": "CPU", **({"cuda": "GPU (NVIDIA)"} if cuda else {})}


def key_for(labels: Mapping[Any, str], value: str, default: Any) -> Any:
    """Nhãn hiển thị -> khóa. Nhãn không còn trong bảng (đổi tên, hoặc lưu từ bản cũ) thì trả về mặc định."""
    return next((k for k, v in labels.items() if v == value), default)


def engine_key(value: str) -> str:
    return key_for(ENGINE_LABELS, value, "auto")


def read_options(get: Callable[[str, Any], Any], dev_map: Mapping[str, str] | None = None) -> dict:
    """Đọc và kiểm tra các ô nhập. get(tên, mặc định) trả giá trị hiện tại. Ném ValueError với thông báo tiếng Việt nếu sai."""
    dev_map = dev_map or dev_labels(False)
    try:
        conf = float(get("conf", "0.8"))
    except ValueError:
        raise ValueError("Ngưỡng nghi ngờ phải là số, ví dụ 0.8.") from None
    try:
        upscale = float(get("upscale", "1") or "1")
    except ValueError:
        raise ValueError("Phóng to phải là số, ví dụ 1 hoặc 2.") from None
    if upscale <= 0:
        raise ValueError("Phóng to phải lớn hơn 0.")
    try:
        crops = pipeline.parse_crops(get("crop", ""))
        crop = None if not crops else (crops[0] if len(crops) == 1 else crops)   # một vùng giữ dạng bộ 4 số
    except ValueError:
        raise ValueError("Vùng cắt sai. Nhập theo thứ tự: trái, trên, phải, dưới (pixel).") from None
    return dict(
        write_txt=get("txt", True), page_marker=get("marker", True),
        lang=key_for(LANG_LABELS, get("lang", LANG_LABELS["ja"]), "ja"),
        device=key_for(dev_map, get("dev", dev_map["auto"]), "auto"),
        ruby=get("ruby", False), markdown=get("markdown", False), md_conf=conf, review=get("review", False), conf_threshold=conf,
        engine=engine_key(get("engine", ENGINE_LABELS["auto"])), crop=crop, upscale=upscale,
        merge_pages=get("merge", MERGE_LABELS[True]) == MERGE_LABELS[True],
        cell_reocr=get("cell_reocr", True), use_cache=get("use_cache", True), vi_fix=get("vi_fix", True),
        kana_reader=key_for(KANA_LABELS, get("kana", KANA_LABELS[""]), ""),
        dpi=int(get("dpi", "200")),
    )


def engine_problem(opts: dict, cls_for: Callable[[str], Any]) -> str | None:
    """Lý do công cụ đã chọn chưa dùng được (thiếu model), None nếu chạy được.
    cls_for(khóa) trả lớp engine cần model (paddle, ocr_vi) hoặc None nếu engine không cần model."""
    key, lang = opts["engine"], opts["lang"]
    if lang not in ENGINE_LANGS.get(key, ()):
        return f"{ENGINE_LABELS[key]} không đọc được {LANG_LABELS[lang]}. Hãy chọn công cụ hoặc ngôn ngữ khác."
    if key == "auto":   # auto chỉ kiểm các công cụ cần model; tiếng Nhật và mọi ngôn ngữ để engine tự chọn
        key = {"en": "paddle", "zh": "paddle", "vi": "ocr_vi"}.get(lang)
    cls = cls_for(key) if key else None
    if cls is None:
        return None
    ok, why = cls.is_available()
    return None if ok else f"Chưa dùng được {ENGINE_LABELS[key]} vì {why}"


# ---------- Công cụ PDF ----------

SPLIT_LABELS = {"pages": "Theo số trang", "bookmark": "Theo bookmark cấp 1", "size": "Theo dung lượng tối đa"}
ROTATE_ANGLES = (90, 180, 270)


def split_value(mode: str, raw: str) -> float | int | None:
    """Giá trị cho Tách PDF: số trang (theo trang), MB (theo dung lượng), không dùng (bookmark)."""
    if mode == "bookmark":
        return None
    try:
        return int(raw.strip() or "1") if mode == "pages" else float(raw.strip())
    except ValueError:
        raise ValueError("Số trang hoặc dung lượng (MB) phải là số.") from None


def image_quality(enabled: bool, raw: str) -> int | None:
    """Chất lượng ảnh khi nén (1–95). Tắt nén lại ảnh thì trả None."""
    if not enabled:
        return None
    try:
        q = int(raw.strip())
    except ValueError:
        q = 0
    if not 1 <= q <= 95:
        raise ValueError("Chất lượng ảnh phải là số từ 1 đến 95.")
    return q


def name_or(raw: str, default: str) -> str:
    """Tên file kết quả: để trống thì dùng tên mặc định."""
    return raw.strip() or default
