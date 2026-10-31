"""Xuất Markdown có đánh dấu theo quy tắc cố định, để nhờ mô hình ngôn ngữ lớn (LLM) hiệu đính.

Quy tắc đánh dấu (`RULES_MD`) có thể xuất riêng để người dùng dán vào file chỉ dẫn (instruction) của LLM.
"""
from __future__ import annotations

from pathlib import Path

from .layout import Para, Table

LOW_OPEN, LOW_CLOSE = "⟦?", "⟧"

RULES_MD = """\
# Quy tắc đọc file Markdown do OCR-Nhat tạo ra

File `.md` này là kết quả OCR (tiếng Nhật) tự động, KHÔNG phải bản gốc. Bạn là người hiệu đính (proofreader).
Mục tiêu: sửa lỗi nhận dạng chữ để ra bản cuối đúng với tài liệu gốc.

## Ký hiệu đánh dấu
- `<!-- trang N -->`: bắt đầu nội dung từ trang N của file gốc (đối chiếu với sách). Giữ nguyên.
- `## Tiêu đề`: dòng được nhận là tiêu đề.
- `- ` đầu dòng: mục liệt kê (ký hiệu đầu dòng của sách).
- Đoạn cách nhau bằng dòng trống: mỗi đoạn là một khối văn bản liền mạch; các dòng ngắt cứng trong trang đã được gộp.
- `⟦?văn bản⟧`: đoạn hoặc ô bảng có độ tin cậy OCR thấp, cần đối chiếu bản gốc. Kiểm tra kỹ các chữ này trước.
- Ký hiệu đặc thù khác (chỉ dùng khi bộ hướng dẫn đầy đủ `hieu_dinh/1_GEM_INSTRUCTIONS.md` yêu cầu): `⟦MẤT CHỮ⟧`, `⟦★?: …⟧`, `⟦FURIGANA lạc: …⟧`, `⟦THỨ TỰ?⟧`.
- `{漢字|かんじ}`: ruby (furigana) gắn trên chữ Hán; chỉ có khi người dùng bật tùy chọn ruby.
- Bảng dạng `| a | b |` (GFM): hàng đầu chỉ là hàng đầu tiên của bảng, chưa chắc là hàng tiêu đề; `\|` là dấu gạch đứng trong ô; `<br>` là xuống dòng trong ô.
- `<!-- gộp ô: r2c1 2x3 -->`: ô gộp, hàng 2 cột 1 (đếm từ 1) trải 2 hàng × 3 cột; các ô bị gộp để trống.

## Lỗi OCR thường gặp (tiếng Nhật)
- Nhầm chữ Hán gần giống nhau (ví dụ 私見→私覚, 稟議書→實識書), nhầm 0/O, 1/l/I, ー (trường âm)/一/－.
- Số khoanh tròn ①②③ có thể thành `(1`, `19`, `O1`.
- Dấu câu và ngoặc nhật 「」『』（）bị nhầm hoặc mất; khoảng trắng thừa giữa chữ Nhật.
- Thứ tự dòng có thể đảo; chữ dọc được xuất theo chiều ngang.
- Furigana còn sót trong ô bảng.

## Cách làm việc
1. Chỉ sửa khi lỗi rõ ràng theo ngữ cảnh. Không viết lại, không diễn đạt lại, không "làm mượt" câu, không dịch.
2. Giữ nguyên cấu trúc: tiêu đề, danh sách, bảng, thứ tự đoạn. Không tự thêm hoặc bớt nội dung ngoài mục 3.
3. Với `⟦?…⟧` mà chữ bị lỗi hoặc không đọc được (rối, sai nghĩa, rỗng): hãy điền một cách đọc hợp lý nhất theo ngữ cảnh xung quanh (câu, mục, bảng). Không cần chính xác từng chữ, chỉ cần hợp nghĩa với tài liệu. Giữ nguyên cặp `⟦?` `⟧` quanh phần điền để người dùng nhận ra đó là phỏng đoán. Nếu không đoán nổi thì giữ nguyên.
4. Chỗ không chắc khác (không phải không đọc được): giữ nguyên và gắn thêm `<!-- ? lý do ngắn -->`.
5. Ưu tiên các đoạn có `⟦?…⟧`, nhưng vẫn đọc cả các đoạn không đánh dấu.
6. Cuối cùng liệt kê hai nhóm: (a) các chỗ đã sửa dạng `trang N: 「cũ」→「mới」`; (b) các chỗ đã điền phỏng đoán dạng `trang N: 「cũ」→「điền」`. Người dùng sẽ đối chiếu nhóm (b) với bản scan.
"""


def _esc_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _ruby_text(p: Para, ruby: bool) -> str:
    if not (ruby and p.ruby):
        return p.text
    out, pos = [], 0
    for s, e, reading in sorted(p.ruby):
        if s < pos:
            continue
        out.append(p.text[pos:s])
        out.append("{%s|%s}" % (p.text[s:e], reading))
        pos = e
    out.append(p.text[pos:])
    return "".join(out)


def _mark(text: str, conf: float, threshold: float) -> str:
    return f"{LOW_OPEN}{text}{LOW_CLOSE}" if text and conf < threshold else text


def _table_md(t: Table, threshold: float) -> str:
    grid = [[""] * t.n_cols for _ in range(t.n_rows)]
    for c in t.cells:
        grid[c.r][c.c] = _mark(_esc_cell(c.text), c.conf, threshold) if c.text else ""
    rows = ["| " + " | ".join(r) + " |" for r in grid]
    rows.insert(1, "|" + "|".join([" --- "] * t.n_cols) + "|")
    merged = [f"r{c.r + 1}c{c.c + 1} {c.rs}x{c.cs}" for c in t.cells if c.rs > 1 or c.cs > 1]
    if merged:
        rows.append("<!-- gộp ô: " + "; ".join(merged) + " -->")
    return "\n".join(rows)


def to_markdown(pages: list[tuple[int, list]], page_marker: bool = True, conf: float = 0.8, ruby: bool = False) -> str:
    """pages: [(số trang, [Para | Table])] -> chuỗi Markdown theo `RULES_MD`."""
    blocks: list[str] = []
    for pno, items in pages:
        if page_marker:
            blocks.append(f"<!-- trang {pno} -->")
        for it in items:
            if isinstance(it, Table):
                blocks.append(_table_md(it, conf))
                continue
            text = _mark(_ruby_text(it, ruby), it.conf, conf)
            if not text.strip():
                continue
            if it.kind == "heading":
                blocks.append("## " + text.replace("\n", " "))
            elif it.bullet:
                blocks.append("- " + text)
            else:
                blocks.append(text)
    return "\n\n".join(blocks) + "\n"


def write_md(pages, out: Path, page_marker: bool = True, conf: float = 0.8, ruby: bool = False) -> None:
    Path(out).write_text(to_markdown(pages, page_marker, conf, ruby), encoding="utf-8")


def write_rules(out: Path) -> None:
    Path(out).write_text(RULES_MD, encoding="utf-8")
