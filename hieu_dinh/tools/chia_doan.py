#!/usr/bin/env python3
"""Chia file OCR (.docx / .txt / .md) thành các đoạn có đánh số dòng Lxxxx để dán vào Gem.

Dùng:
  python chia_doan.py input.docx output.txt
  python chia_doan.py input.txt output.txt --size 2200 --max 3200
  python chia_doan.py input.docx output.txt --heading "^(第\\d+課|問題\\d)"

--size    : độ dài (ký tự) tối thiểu trước khi được phép cắt ở dòng "tiêu đề"   (mặc định 2200)
--max     : độ dài tối đa, quá mức này thì cắt ở bất kỳ dòng nào                 (mặc định 3200)
--heading : regex nhận diện dòng nên bắt đầu một đoạn mới (mặc định: dòng bắt đầu bằng số/số vòng,
            ★, 問題, まとめ, 第..課...)
Chỉ dùng thư viện chuẩn + python-docx (chỉ khi đọc .docx).
"""
import argparse, re, sys

def read_lines(path):
    if path.lower().endswith(".docx"):
        import docx
        from docx.oxml.ns import qn
        d = docx.Document(path)

        def ptext(p):
            out = []
            for e in p.iter():
                if e.tag == qn("w:t"):
                    out.append(e.text or "")
                elif e.tag in (qn("w:br"), qn("w:cr")):
                    out.append("\n")
                elif e.tag == qn("w:tab"):
                    out.append(" ")
            return "".join(out)

        lines = []
        for el in d.element.body:
            if el.tag == qn("w:p"):
                lines.extend(ptext(el).split("\n"))
            elif el.tag == qn("w:tbl"):
                for tc in el.iter(qn("w:tc")):
                    for p in tc.iter(qn("w:p")):
                        lines.extend(ptext(p).split("\n"))
        return lines
    with open(path, encoding="utf-8", errors="strict") as f:
        return f.read().splitlines()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--size", type=int, default=2200)
    ap.add_argument("--max", type=int, default=3200)
    ap.add_argument("--heading", default=r"^(\d{1,3}\s?\S|[①-⑳]|★|大|問題|まとめ|第\d+課|できること)")
    a = ap.parse_args()

    lines = [l.rstrip() for l in read_lines(a.inp) if l.strip()]
    head = re.compile(a.heading)
    chunks, cur, n = [], [], 0
    for i, l in enumerate(lines, 1):
        if cur and ((n >= a.size and head.match(l)) or n >= a.max):
            chunks.append(cur); cur, n = [], 0
        cur.append((i, l)); n += len(l)
    if cur:
        chunks.append(cur)

    total = len(chunks)
    out = []
    for k, c in enumerate(chunks, 1):
        out.append(f"===== ĐOẠN {k:03d}/{total:03d} | dòng L{c[0][0]:04d}–L{c[-1][0]:04d} | {len(c)} dòng =====")
        out += [f"L{i:04d}| {l}" for i, l in c]
        out.append(f"===== HẾT ĐOẠN {k:03d} =====\n")
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"{len(lines)} dòng, {sum(len(l) for l in lines)} ký tự -> {total} đoạn: {a.out}")

if __name__ == "__main__":
    main()
