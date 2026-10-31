#!/usr/bin/env python3
"""So bản OCR gốc của một đoạn với PHẦN 1 mà Gem trả về, báo chữ nào bị MẤT hoặc bị THÊM.

Dùng:
  python kiem_tra_mat_chu.py doan_goc.txt gem_tra_ve.txt

  doan_goc.txt   : đoạn đã dán vào Gem (có mã Lxxxx| hoặc không đều được)
  gem_tra_ve.txt : toàn bộ câu trả lời của Gem (script tự cắt lấy PHẦN 1)

Cách làm: đếm số lần xuất hiện từng ký tự có nghĩa (kana, Hán tự, chữ số, chữ Latin) ở hai bên, rồi so.
Dấu câu, khoảng trắng, mã dòng, ký hiệu ⟦?⟧ / <!-- --> bị bỏ qua.
Lưu ý: dòng bị XÓA hợp lệ (có trong Nhật ký) sẽ hiện là "mất" - đối chiếu với Nhật ký.
"""
import re, sys
from collections import Counter

KEEP = re.compile(r"[぀-ヿ㐀-鿿Ａ-Ｚａ-ｚ０-９A-Za-z0-9]")

def clean_source(t):
    return re.sub(r"(?m)^(=====.*|L\d{4}\|\s?)", lambda m: "" if m.group(0).startswith("=====") else "", t)

def part1(t):
    m1 = re.search(r"PH[ẦA]N\s*1[^\n]*\n", t)
    m2 = re.search(r"PH[ẦA]N\s*2\b", t)
    if m1 and m2 and m2.start() > m1.end():
        return t[m1.end():m2.start()]
    if m1:
        return t[m1.end():]
    return t

def strip_marks(t):
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"⟦(?:MẤT CHỮ|THỨ TỰ\?)⟧", "", t)
    t = re.sub(r"⟦(?:\?|★\?:|FURIGANA lạc:)\s*", "", t)
    t = t.replace("⟧", "")
    return t

def count(t):
    return Counter(KEEP.findall(t))

def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(1)
    src = open(sys.argv[1], encoding="utf-8").read()
    gem = open(sys.argv[2], encoding="utf-8").read()
    # chuẩn hoá chữ toàn độ rộng -> bán độ rộng cho số / Latin để khỏi báo oan
    def norm(t):
        return t.translate({ord(c): ord(c) - 0xFEE0 for c in
                            list(map(chr, range(0xFF21, 0xFF3B))) + list(map(chr, range(0xFF41, 0xFF5B))) + list(map(chr, range(0xFF10, 0xFF1A)))})
    cs = count(norm(clean_source(src)))
    cg = count(norm(strip_marks(part1(gem))))
    missing = {c: cs[c] - cg[c] for c in cs if cs[c] > cg[c]}
    added = {c: cg[c] - cs[c] for c in cg if cg[c] > cs[c]}
    print(f"Ký tự có nghĩa: gốc={sum(cs.values())}  Gem={sum(cg.values())}  chênh={sum(cg.values())-sum(cs.values())}")
    print(f"\nMẤT ({sum(missing.values())} ký tự, {len(missing)} loại):")
    print("  " + "  ".join(f"{c}×{n}" for c, n in sorted(missing.items(), key=lambda x: -x[1])) if missing else "  (không)")
    print(f"\nTHÊM ({sum(added.values())} ký tự, {len(added)} loại):")
    print("  " + "  ".join(f"{c}×{n}" for c, n in sorted(added.items(), key=lambda x: -x[1])) if added else "  (không)")
    print("\nGợi ý: chữ MẤT lớn bất thường -> Gem đã lược; chữ THÊM lớn -> Gem đã tự thêm/bịa. "
          "Chênh nhỏ nằm trong Nhật ký (dòng XÓA, sửa B) là bình thường.")

if __name__ == "__main__":
    main()
