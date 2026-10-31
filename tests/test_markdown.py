"""Test xuất Markdown có đánh dấu (không cần model)."""
from ocrnhat.layout import Cell, Para, Table
from ocrnhat.markdown_out import RULES_MD, to_markdown, write_md, write_rules


def _pages():
    t = Table(2, 2, [Cell(0, 0, rs=2, text="見出し", conf=0.3), Cell(0, 1, text="a|b"), Cell(1, 1, text="x\ny")])
    return [(3, [
        Para("第一章", kind="heading"),
        Para("本文です。", conf=0.95),
        Para("怪しい文", conf=0.4),
        Para("項目", bullet=True),
        Para("漢字です", ruby=[(0, 2, "かんじ")]),
        t,
    ])]


def test_markdown_dau_hieu():
    md = to_markdown(_pages(), ruby=True)
    assert md.startswith("<!-- trang 3 -->")
    assert "## 第一章" in md
    assert "\n\n本文です。\n\n" in md
    assert "⟦?怪しい文⟧" in md
    assert "- 項目" in md
    assert "{漢字|かんじ}です" in md
    assert "| ⟦?見出し⟧ | a\\|b |" in md and "x<br>y" in md
    assert "<!-- gộp ô: r1c1 2x1 -->" in md


def test_markdown_khong_ruby_va_khong_trang():
    md = to_markdown(_pages(), page_marker=False, conf=0.0)
    assert "<!--" in md and "trang 3" not in md
    assert "{漢字" not in md and "⟦?" not in md


def test_ghi_file_va_quy_tac(tmp_path):
    write_md(_pages(), tmp_path / "a.md"); write_rules(tmp_path / "r.md")
    assert (tmp_path / "a.md").read_text(encoding="utf-8").strip()
    r = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert r == RULES_MD and "⟦?" in r and "{漢字|かんじ}" in r
