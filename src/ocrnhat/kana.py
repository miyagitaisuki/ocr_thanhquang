"""Đọc ô bảng chữ kana bằng Tesseract (tùy chọn, chỉ khi máy có lệnh tesseract và dữ liệu jpn).
Engine NDLOCR không đọc đáng tin từng chữ kana trong ô lưới; Tesseract đọc tốt hơn khi chỉ lấy nét đen."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

_THRESH = 185               # nét kana xám khoảng 120–160 trên nền trắng
_CHROMA = 40                # nét hồng của romaji có chroma cao hơn nhiều


def available() -> bool:
    return shutil.which("tesseract") is not None


def _ink_mask(cell_rgb: np.ndarray) -> np.ndarray:
    """Mặt nạ mực của chữ kana trong ô: nửa trái, nét xám không màu, bỏ đường kẻ chạm mép."""
    h, w = cell_rgb.shape[:2]
    crop = np.ascontiguousarray(cell_rgb[8:h - 8, 14:max(15, int(0.6 * w))])
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    rgb = crop.astype(np.int16)
    ink = (gray < _THRESH) & ((rgb.max(axis=2) - rgb.min(axis=2)) < _CHROMA)
    ink[:, ink.mean(axis=0) > 0.6] = False
    ink[ink.mean(axis=1) > 0.6, :] = False
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    h_, w_ = ink.shape
    for i in range(1, n):
        x, y, cw, ch, _a = stats[i]
        if x == 0 or y == 0 or x + cw >= w_ or y + ch >= h_ or cw <= 3 or ch <= 3:
            ink[lab == i] = False   # chạm mép (đường kẻ) hoặc vạch mảnh: không phải nét chữ
    return ink


def _norm(mask: np.ndarray, size: int = 40) -> np.ndarray:
    """Cắt theo hộp bao nét rồi đưa về ô vuông cố định (giữ tỷ lệ), để so khớp không phụ thuộc cỡ chữ."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return np.zeros((size, size), np.float32)
    box = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8) * 255
    h, w = box.shape
    scale = (size - 4) / max(h, w)
    small = cv2.resize(box, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    out = np.zeros((size, size), np.uint8)
    y0 = (size - small.shape[0]) // 2; x0 = (size - small.shape[1]) // 2
    out[y0:y0 + small.shape[0], x0:x0 + small.shape[1]] = small
    return (out > 127).astype(np.float32)


_FONT_PATHS = ["/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/ipafont-gothic/ipag.ttf"]
_TEMPLATES: dict[str, np.ndarray] | None = None
_KANA_SET = [chr(c) for c in range(0x3041, 0x3097)] + [chr(c) for c in range(0x30A1, 0x30FB)]


def font_available() -> bool:
    return any(Path(f).is_file() for f in _FONT_PATHS)


def _templates() -> dict[str, np.ndarray]:
    global _TEMPLATES
    if _TEMPLATES is None:
        from PIL import ImageDraw, ImageFont
        font = ImageFont.truetype(next(f for f in _FONT_PATHS if Path(f).is_file()), 96)
        tpl = {}
        for ch in _KANA_SET:
            im = Image.new("L", (160, 160), 0)
            ImageDraw.Draw(im).text((30, 20), ch, font=font, fill=255)
            mask = np.array(im) > 127
            tpl[ch] = _norm(mask)
        _TEMPLATES = tpl
    return _TEMPLATES


def read_cell_template(cell_rgb: np.ndarray, min_corr: float = 0.6, min_margin: float = 0.02,
                       charset: str = "hiragana") -> str:
    """Đọc một ô kana bằng tương quan mềm với mẫu IPAGothic (làm mờ để chịu được khác biệt font).
    Chỉ nhận khi tương quan đủ cao và tách biệt rõ với ký tự xếp thứ hai."""
    mask = _ink_mask(cell_rgb)
    if mask.sum() < 20:
        return ""
    q = _soft(_norm(mask))
    q = q - q.mean()
    qn = np.sqrt((q * q).sum()) + 1e-9
    scores = []
    for ch, t in _soft_templates().items():
        if charset == "hiragana" and (not ("ぁ" <= ch <= "ゖ") or ch in _SMALL_KANA):
            continue   # bảng chữ hiragana: không đưa katakana và kana nhỏ (ゕ…) vào so khớp
        b = t - t.mean()
        scores.append(((q * b).sum() / (qn * (np.sqrt((b * b).sum()) + 1e-9)), ch))
    scores.sort(reverse=True)
    (best, ch), (second, _) = scores[0], scores[1]
    if best < min_corr or best - second < min_margin:
        return ""
    return _SMALL_TO_FULL.get(ch, ch)


_SMALL_KANA = set("ぁぃぅぇぉゃゅょゎゕゖっ")


def _soft(mask: np.ndarray, sigma: float = 1.5) -> np.ndarray:
    return cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)


_SOFT_TPL: dict[str, np.ndarray] | None = None


def _soft_templates() -> dict[str, np.ndarray]:
    global _SOFT_TPL
    if _SOFT_TPL is None:
        _SOFT_TPL = {ch: _soft(t) for ch, t in _templates().items()}
    return _SOFT_TPL


def read_cell(cell_rgb: np.ndarray) -> str:
    """Trả về đúng một ký tự kana, hoặc chuỗi rỗng nếu không chắc."""
    h, w = cell_rgb.shape[:2]
    # chữ kana nằm ở nửa trái ô, phía trên giữa; romaji hồng nằm bên phải
    crop = cell_rgb[8:h - 8, 14:max(15, int(0.6 * w))]
    if crop.size == 0:
        return ""
    rgb = np.ascontiguousarray(crop).astype(np.int16)
    gray = cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_RGB2GRAY)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)               # chữ kana gần xám; romaji màu hồng có chroma lớn
    ink = (gray < _THRESH) & (chroma < _CHROMA)
    # đường kẻ lưới lọt vào ô: cột/hàng có mật độ mực quá cao không phải chữ
    ink[:, ink.mean(axis=0) > 0.6] = False
    ink[ink.mean(axis=1) > 0.6, :] = False
    # thành phần mực chạm mép ảnh cắt là đường kẻ lọt vào ô, không phải chữ
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    h_, w_ = ink.shape
    for i in range(1, n):
        x, y, cw, ch, _a = stats[i]
        if x == 0 or y == 0 or x + cw >= w_ or y + ch >= h_:
            ink[lab == i] = False
    out = np.where(ink, 0, 255).astype(np.uint8)
    out = cv2.resize(out, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    out = cv2.copyMakeBorder(out, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "cell.png"
        Image.fromarray(out).save(p)
        for psm in ("10", "7"):   # chữ đơn trước; nếu không ra kana thì thử chế độ một dòng
            res = subprocess.run(["tesseract", str(p), "stdout", "-l", "jpn", "--psm", psm],
                                 capture_output=True, text=True, timeout=20)
            text = "".join(ch for ch in res.stdout if ch.strip())
            if _is_kana(text):
                return _SMALL_TO_FULL.get(text, text)
    return ""


# bảng gojūon không có kana nhỏ: 'ぁ' ở đây là 'あ' bị đọc nhỏ
_SMALL_TO_FULL = {c: f for c, f in zip("ぁぃぅぇぉゃゅょァィゥェォャュョ", "あいうえおやゆよアイウエオヤユヨ")}


def _is_kana(ch: str) -> bool:
    return len(ch) == 1 and (0x3040 <= ord(ch) <= 0x30FF)


def write_review(records: list[tuple[int, np.ndarray, str]], out: Path) -> None:
    """File rà soát HTML: ảnh từng ô kana cạnh chữ đã đọc, để đối chiếu với trang gốc."""
    import base64
    import html
    import io

    parts = []
    for pno, crop, text in records:
        buf = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(crop)).save(buf, format="PNG")
        src = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        shown = html.escape(text) if text else "∅"
        cls = "ok" if text else "empty"
        parts.append(f'<figure class="{cls}"><img src="{src}" alt="p{pno}"><figcaption>p.{pno} → <b>{shown}</b></figcaption></figure>')
    page = (
        "<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>Rà soát bảng kana</title>"
        "<style>body{font-family:sans-serif;margin:16px}"
        ".grid{display:flex;flex-wrap:wrap;gap:10px}"
        "figure{margin:0;width:150px;border:1px solid #ccc;padding:4px;background:#fff}"
        "figure.empty{background:#fff4f4}img{width:100%;image-rendering:auto}"
        "figcaption{font-size:14px}</style></head><body>"
        "<h2>Rà soát bảng chữ kana (thử nghiệm)</h2>"
        "<p>Ô có chữ đọc được hiện chữ sau mũi tên; ô nền đỏ nhạt là ô để trống (không chắc). "
        "Đối chiếu từng ô với ảnh trang gốc.</p>"
        f"<div class='grid'>{''.join(parts)}</div></body></html>"
    )
    out.write_text(page, encoding="utf-8")
