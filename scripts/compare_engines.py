"""Đối chiếu kết quả OCR của dự án (.txt) với một engine khác (ví dụ YomiToku, xuất .md theo trang).

Chỉ so ký tự tiếng Nhật (kana, kanji), bỏ tiếng Việt, chữ Latin, số, dấu markdown và thẻ <br>.
Dùng cho mục đích đối chiếu nội bộ. KHÔNG đưa YomiToku vào sản phẩm: giấy phép CC BY-NC-SA 4.0 (phi thương mại).

Cách dùng:
  python scripts/compare_engines.py ours.txt yomi_dir/ --pages 9-12 -o report.md
  (yomi_dir chứa file *_p<N>.md do `yomitoku ... -f md --pages N` tạo ra)
"""
from __future__ import annotations

import argparse
import re
from difflib import SequenceMatcher
from pathlib import Path

_JP = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ々〇]")
_PAGE = re.compile(r"^=== Trang (\d+) ===$")


def jp_only(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "", text)
    return "".join(c for c in text if _JP.match(c))


def read_ours(path: Path) -> dict[int, str]:
    pages: dict[int, list[str]] = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _PAGE.match(line)
        if m:
            cur = int(m.group(1)); pages[cur] = []
        elif cur is not None:
            pages[cur].append(line)
    return {p: jp_only("\n".join(ls)) for p, ls in pages.items()}


def read_theirs(dirpath: Path) -> dict[int, str]:
    out = {}
    for f in dirpath.glob("*_p*.md"):
        m = re.search(r"_p(\d+)\.md$", f.name)
        if m:
            out[int(m.group(1))] = jp_only(f.read_text(encoding="utf-8"))
    return out


def diffs(a: str, b: str, ctx: int = 8, limit: int = 20):
    sm = SequenceMatcher(None, a, b, autojunk=False)
    rows = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        rows.append((tag, a[max(0, i1 - ctx):i1], a[i1:i2], b[j1:j2], a[i2:i2 + ctx]))
    return sm.ratio(), rows[:limit], len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ours", type=Path, help="file .txt của dự án")
    ap.add_argument("theirs_dir", type=Path, help="thư mục chứa *_p<N>.md của engine khác")
    ap.add_argument("--pages", default="", help="ví dụ 9-12; để trống = các trang có trong cả hai")
    ap.add_argument("-o", "--out", type=Path, help="ghi báo cáo markdown ra file")
    a = ap.parse_args()

    ours, theirs = read_ours(a.ours), read_theirs(a.theirs_dir)
    if a.pages:
        lo, hi = (int(x) for x in a.pages.split("-")) if "-" in a.pages else (int(a.pages),) * 2
        keep = set(range(lo, hi + 1))
    else:
        keep = set(ours) & set(theirs)
    lines = ["# Đối chiếu OCR (chỉ ký tự tiếng Nhật)", "",
             "| Trang | Độ giống | Số đoạn khác nhau | Số ký tự (dự án / engine khác) |", "|---|---|---|---|"]
    details = []
    for p in sorted(keep & set(ours) & set(theirs)):
        ratio, rows, n = diffs(ours[p], theirs[p])
        lines.append(f"| {p} | {ratio:.3f} | {n} | {len(ours[p])} / {len(theirs[p])} |")
        for tag, pre, x, y, post in rows:
            details.append(f"- **Trang {p}** ({tag}): …{pre}[**{x or '∅'}**]{post}… → engine khác: [**{y or '∅'}**]")
    if details:
        lines += ["", "## Đoạn khác nhau (tối đa 20 mỗi trang)", ""] + details
    report = "\n".join(lines) + "\n"
    if a.out:
        a.out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
