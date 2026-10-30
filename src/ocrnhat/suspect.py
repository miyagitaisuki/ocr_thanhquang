"""Dò chữ có thể bị nhận sai bằng mô hình BERT tiếng Nhật (cl-tohoku, Apache-2.0).

Chỉ ĐÁNH DẤU để người duyệt xem lại, KHÔNG tự sửa văn bản. Mỗi ký tự được che lần lượt; nếu mô hình
thấy ký tự thật rất khó xảy ra trong ngữ cảnh (xác suất thấp và không nằm trong top-k) thì ghi nhận.
Ngữ cảnh ngắn (dòng vài chữ) dễ cho dương tính giả; ngưỡng chỉ là điểm bắt đầu để duyệt.

Phụ thuộc tùy chọn: `pip install ".[suspect]"` (torch, transformers, fugashi, unidic-lite). Không đóng gói vào exe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MODEL = "cl-tohoku/bert-base-japanese-char-v3"
_JP = re.compile(r"[぀-ヿ㐀-䶿一-鿿々〇]")   # chỉ kiểm tra kana/kanji; chữ khác bỏ qua
MAX_LEN = 300                                # dòng dài hơn được cắt để giới hạn thời gian


@dataclass
class Suspect:
    index: int          # vị trí ký tự trong dòng
    char: str           # ký tự nhận được
    prob: float         # xác suất mô hình gán cho ký tự này
    alternatives: str   # vài ký tự mô hình thấy hợp lý hơn


_state: dict = {}


def _load():
    """Nạp tokenizer và mô hình một lần (import lười để không kéo torch khi không dùng)."""
    if "model" not in _state:
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForMaskedLM, AutoTokenizer
        except ImportError as e:
            raise RuntimeError('Cần cài tùy chọn: pip install ".[suspect]"') from e
        _state["tok"] = AutoTokenizer.from_pretrained(MODEL)
        _state["model"] = AutoModelForMaskedLM.from_pretrained(MODEL).eval()
    return _state["tok"], _state["model"]


def scan_line(text: str, threshold: float = 0.001, topk: int = 5) -> list[Suspect]:
    """Trả về các ký tự nghi ngờ trong một dòng, sắp theo xác suất tăng dần (đáng ngờ nhất trước)."""
    import torch

    tok, model = _load()
    text = text[:MAX_LEN]
    if not text:
        return []
    toks = tok.tokenize(text)
    if len(toks) != len(text):          # tokenizer không tách 1:1 theo ký tự: bỏ qua dòng này
        return []
    ids = tok.convert_tokens_to_ids(toks)
    positions = [i for i, c in enumerate(text) if _JP.match(c) and ids[i] != tok.unk_token_id]
    out: list[Suspect] = []
    batch = 32
    for s in range(0, len(positions), batch):
        chunk = positions[s:s + batch]
        x = torch.tensor([[tok.cls_token_id] + ids + [tok.sep_token_id]] * len(chunk))
        for row, i in enumerate(chunk):
            x[row, i + 1] = tok.mask_token_id
        with torch.no_grad():
            logits = model(input_ids=x).logits
        for row, i in enumerate(chunk):
            p = logits[row, i + 1].softmax(-1)
            pa = p[ids[i]].item()
            top = p.topk(topk).indices.tolist()
            if pa < threshold and ids[i] not in top:
                alts = "".join(tok.convert_ids_to_tokens(t) for t in top[:3])
                out.append(Suspect(i, text[i], pa, alts))
    return sorted(out, key=lambda s: s.prob)


def mark(text: str, suspects: list[Suspect]) -> str:
    """Dòng văn bản với ký tự nghi ngờ được đánh dấu 〔?〕 ngay sau ký tự đó."""
    marks = {s.index for s in suspects}
    return "".join(c + ("〔?〕" if i in marks else "") for i, c in enumerate(text))
