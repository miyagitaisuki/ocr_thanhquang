"""Hậu xử lý văn bản tiếng Việt (engine ocr_vi): bỏ nhiễu dấu mộc, sửa dấu theo tần suất trong tài liệu.

Chỉ sửa khi cách viết thay thế là âm tiết hợp lệ (có trong từ điển) và xuất hiện nhiều hơn hẳn
trong chính tài liệu, nên tên riêng, số hiệu và từ đúng hiếm khi bị đổi. Từ điển: pyvi (MIT),
`data/vi_words.txt`. Các mục không có đủ bằng chứng giữ nguyên.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import replace
from functools import lru_cache
from importlib import resources

from .layout import Para, Table

_TOK = re.compile(r"^([^\w]*)([^\W\d_]+)([^\w]*)$")
_SPLIT = re.compile(r"(\s+)")
_ARTICLE = re.compile(r"\s+(?=Điều\s+\d+\.(?=\s|[^\W\d_]))")     # "Điều 2." bị gộp vào giữa đoạn trước
_DIGIT_RUN = re.compile(r"(?<!\S)(\d)(?:\s+\1(?!\S)){2,}\s*")   # "3 3 3 3" từ dấu mộc
MIN_COUNT = 3       # số lần tối thiểu cách viết thay thế phải xuất hiện
RATIO = 4           # và phải nhiều hơn gấp RATIO lần cách viết gốc


def _key(s: str) -> str:
    """Bỏ dấu thanh, dấu mũ và đ -> d, để gom các âm tiết cùng chữ cái."""
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=1)
def _lexicon() -> tuple[frozenset, frozenset, dict]:
    """(âm tiết hợp lệ, cặp âm tiết có trong từ điển, nhóm theo khóa không dấu)."""
    text = resources.files("ocrnhat").joinpath("data/vi_words.txt").read_text(encoding="utf8")
    syl: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    for w in text.split("\n"):
        parts = w.strip().lower().split()
        syl.update(parts)
        pairs.update(zip(parts, parts[1:]))
    by_key: dict[str, set[str]] = defaultdict(set)
    for s in syl:
        by_key[_key(s)].add(s)
    return frozenset(syl), frozenset(pairs), by_key


def _is_noise(core: str, valid: frozenset) -> bool:
    """Chữ viết thường, ngắn, không phải âm tiết tiếng Việt: thường là dấu mộc hoặc nhãn bị đọc sai."""
    return len(core) <= 3 and not core.isupper() and core.lower() not in valid


def _tokens(text: str):
    """Các phần tử xen kẽ: (token, None) cho khoảng trắng, (token, match) cho từ."""
    for part in _SPLIT.split(text):
        if not part or part.isspace():
            yield part, None
        else:
            yield part, _TOK.match(part)


def _drop_noise(text: str, valid: frozenset) -> str:
    text = _DIGIT_RUN.sub("", text)
    out = []
    for part, m in _tokens(text):
        if m is None:
            if not re.fullmatch(r"\d{5,}", part):      # dãy số dài từ dấu mộc, số thứ tự thì giữ
                out.append(part)
            continue
        if not _is_noise(m.group(2), valid):
            out.append(part)
    return re.sub(r" {2,}", " ", "".join(out)).strip()


def _case_like(orig: str, new: str) -> str:
    if orig.isupper() and len(orig) > 1:
        return new.upper()
    if orig[0].isupper():
        return new[0].upper() + new[1:]
    return new


def build_stats(texts: list[str]) -> tuple[Counter, Counter]:
    bi: Counter = Counter()
    uni: Counter = Counter()
    for text in texts:
        words = [m.group(2).lower() if m else None for _, m in _tokens(text)]
        words = [w for w in words if w]
        uni.update(words)
        bi.update(zip(words, words[1:]))
    return bi, uni


def _fix_text(text: str, bi: Counter, uni: Counter, lex) -> str:
    valid, pairs, by_key = lex
    toks = [(part, m) for part, m in _tokens(text)]
    words = [m.group(2).lower() if m else None for _, m in toks]
    for i, (part, m) in enumerate(toks):
        if m is None or words[i] is None:
            continue
        s = words[i]
        prev = next((words[j] for j in range(i - 1, -1, -1) if words[j]), None) if i else None
        nxt = next((words[j] for j in range(i + 1, len(words)) if words[j]), None)
        if (prev and (prev, s) in pairs) or (nxt and (s, nxt) in pairs):
            continue

        def score(x: str) -> int:
            return (bi[(prev, x)] if prev else 0) + (bi[(x, nxt)] if nxt else 0)

        base = score(s)
        best, best_score = None, 0
        for x in by_key.get(_key(s), ()):
            if x == s or x not in valid:
                continue
            sc = score(x)
            if sc > best_score:
                best, best_score = x, sc
        if best and best_score >= MIN_COUNT and best_score >= RATIO * (base + 1):
            toks[i] = (m.group(1) + _case_like(m.group(2), best) + m.group(3), m)
            words[i] = best
    return "".join(part for part, _ in toks)


def _split_articles(items: list) -> list:
    """Tách đoạn body có "Điều N." ở giữa thành các đoạn riêng (mỗi Điều một đoạn)."""
    out = []
    for it in items:
        if isinstance(it, Para) and it.kind == "body" and _ARTICLE.search(it.text):
            for part in _ARTICLE.split(it.text):
                if part.strip():
                    out.append(replace(it, text=part.strip()))
        else:
            out.append(it)
    return out


def correct_results(results: list[tuple[int, list]]) -> list[tuple[int, list]]:
    """Áp dụng lên các mục Para và Table của mọi trang, trước khi ghi Word/txt."""
    lex = _lexicon()
    valid = lex[0]
    results = [(pno, _split_articles(items)) for pno, items in results]
    paras = [i for _, items in results for i in items if isinstance(i, Para)]
    cells = [c for _, items in results for i in items if isinstance(i, Table) for c in i.cells]
    for p in paras:
        p.text = _drop_noise(p.text, valid)
    for c in cells:
        c.text = _drop_noise(c.text, valid)
    texts = [p.text for p in paras] + [c.text for c in cells]
    bi, uni = build_stats(texts)
    for p in paras:
        p.text = _fix_text(p.text, bi, uni, lex)
    for c in cells:
        c.text = _fix_text(c.text, bi, uni, lex)
    # đoạn chỉ có nhiễu sau khi lọc thì bỏ hẳn
    return [(pno, [i for i in items if not (isinstance(i, Para) and not i.text.strip())])
            for pno, items in results]
