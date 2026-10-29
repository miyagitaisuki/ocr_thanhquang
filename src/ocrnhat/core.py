"""Lõi OCR tiếng Nhật: PDF/ảnh -> văn bản chỉ gồm tiếng Nhật."""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

_JP = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")
_KANA = re.compile(r"^[぀-ヿー・、。\s]+$")
_KANJI = re.compile(r"[㐀-䶿一-鿿]")
_KANA_CH = re.compile(r"[\u3040-\u30ff\u30fc・、。]")
_LATIN_WORD = re.compile(r"[A-Za-z\u00c0-\u1ef9]{3,}")


@dataclass
class Line:
    text: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def h(self) -> float:
        return min(self.y1 - self.y0, self.x1 - self.x0) if self.vertical else self.y1 - self.y0

    @property
    def vertical(self) -> bool:
        return (self.y1 - self.y0) > 2.0 * (self.x1 - self.x0) and len(self.text) > 1

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2


_engine = None


def get_engine():
    """Tạo RapidOCR (model tiếng Nhật) một lần duy nhất."""
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR, LangRec

        _engine = RapidOCR(params={"Rec.lang_type": LangRec.JAPAN, "Global.log_level": "error"})
    return _engine


def jp_ratio(text: str) -> float:
    """Tỉ lệ ký tự tiếng Nhật trên tổng số ký tự chữ/số (bỏ khoảng trắng, dấu câu)."""
    chars = [c for c in text if c.isalnum() or _JP.match(c)]
    if not chars:
        return 0.0
    return sum(1 for c in chars if _JP.match(c)) / len(chars)


def preprocess(img: np.ndarray, denoise: bool = True) -> np.ndarray:
    """Làm sạch nền xám/nhiễu của ảnh scan trước khi OCR."""
    import cv2

    if img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img
    if denoise:
        # chuẩn hóa nền: chia cho nền ước lượng bằng blur lớn, giúp loại nền xám loang
        bg = cv2.medianBlur(gray, 31)
        gray = cv2.divide(gray, bg, scale=255)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


def _run(img: np.ndarray) -> list[Line]:
    r = get_engine()(img)
    if r is None or r.boxes is None or r.txts is None:
        return []
    out = []
    for box, txt, sc in zip(r.boxes, r.txts, r.scores):
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append(Line(txt.strip(), float(sc), float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))))
    return [l for l in out if l.text]


def filter_japanese(lines: list[Line], min_ratio: float = 0.7, drop_furigana: bool = True,
                    min_score: float = 0.5) -> list[Line]:
    """Chỉ giữ dòng tiếng Nhật; bỏ furigana (dòng kana nhỏ nằm sát phía trên chữ lớn)."""
    jp = [l for l in lines if jp_ratio(l.text) >= min_ratio and l.score >= min_score and _JP.search(l.text)
          and not _LATIN_WORD.search(l.text)]
    if not jp:
        return []
    if drop_furigana:
        hs = sorted(l.h for l in jp)
        ref = hs[min(len(hs) - 1, int(len(hs) * 0.8))]  # chiều cao chữ thân bài (phân vị 80)
        kept = []
        for l in jp:
            kana_ratio = sum(1 for c in l.text if _KANA_CH.match(c)) / max(1, len(l.text))
            if l.h < 0.70 * ref and (kana_ratio >= 0.8 or len(l.text) <= 4):
                continue  # furigana
            if l.h < 0.78 * ref and bool(_KANA.match(l.text)):
                continue
            kept.append(l)
        jp = kept
    return jp


def reading_order(lines: list[Line]) -> list[Line]:
    """Sắp xếp trên->dưới; các dòng cùng hàng thì trái->phải (hợp với bảng)."""
    if not lines:
        return []
    ls = sorted(lines, key=lambda l: l.yc)
    rows: list[list[Line]] = []
    for l in ls:
        if rows:
            ref = rows[-1]
            ry = statistics.mean(x.yc for x in ref)
            rh = statistics.mean(x.y1 - x.y0 for x in ref)
            if abs(l.yc - ry) < 0.5 * rh:
                ref.append(l)
                continue
        rows.append([l])
    out = []
    for r in rows:
        out.extend(sorted(r, key=lambda l: l.x0))
    return out


def ocr_image(img: np.ndarray, denoise: bool = True, min_ratio: float = 0.7,
              drop_furigana: bool = True) -> list[Line]:
    lines = _run(preprocess(img, denoise))
    return reading_order(filter_japanese(lines, min_ratio, drop_furigana))


def iter_pages(path: Path, dpi: int = 200, pages: Iterable[int] | None = None) -> Iterator[tuple[int, np.ndarray]]:
    """Sinh (số trang, ảnh RGB). Hỗ trợ PDF và file ảnh."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        n = len(pdf)
        want = sorted(set(pages)) if pages else range(1, n + 1)
        for p in want:
            if 1 <= p <= n:
                bmp = pdf[p - 1].render(scale=dpi / 72).to_numpy()
                yield p, bmp[:, :, :3][:, :, ::-1].copy() if bmp.shape[2] == 4 and False else _to_rgb(bmp)
        pdf.close()
    else:
        from PIL import Image

        yield 1, np.array(Image.open(path).convert("RGB"))


def _to_rgb(bmp: np.ndarray) -> np.ndarray:
    # pypdfium2 trả BGR(A) mặc định
    return bmp[:, :, [2, 1, 0]].copy()


def page_count(path: Path) -> int:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        n = len(pdf)
        pdf.close()
        return n
    return 1


def parse_pages(spec: str | None) -> list[int] | None:
    """'1-5,8,10-12' -> [1,2,3,4,5,8,10,11,12]"""
    if not spec or not spec.strip():
        return None
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def process_file(path: Path, out_dir: Path, dpi: int = 200, pages: list[int] | None = None,
                 denoise: bool = True, min_ratio: float = 0.7, drop_furigana: bool = True,
                 progress: Callable[[int, int, str], None] | None = None,
                 cancel: Callable[[], bool] | None = None) -> dict:
    """OCR một file, ghi <tên>.txt và <tên>.jsonl vào out_dir. Trả về thống kê."""
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(pages) if pages else page_count(path)
    txt_path, jsonl_path = out_dir / f"{path.stem}.txt", out_dir / f"{path.stem}.jsonl"
    n_lines = 0
    done = 0
    with open(txt_path, "w", encoding="utf-8") as ft, open(jsonl_path, "w", encoding="utf-8") as fj:
        for pno, img in iter_pages(path, dpi, pages):
            if cancel and cancel():
                break
            lines = ocr_image(img, denoise, min_ratio, drop_furigana)
            ft.write(f"=== Trang {pno} ===\n")
            ft.write("\n".join(l.text for l in lines) + "\n\n")
            fj.write(json.dumps({"page": pno, "lines": [
                {**asdict(l), "score": round(l.score, 3)} for l in lines]}, ensure_ascii=False) + "\n")
            ft.flush(); fj.flush()
            n_lines += len(lines)
            done += 1
            if progress:
                progress(done, total, f"{path.name} - trang {pno}")
    return {"file": str(path), "pages": done, "lines": n_lines, "txt": str(txt_path), "jsonl": str(jsonl_path)}
