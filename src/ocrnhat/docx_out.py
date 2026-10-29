"""Ghi kết quả ra Word (.docx) và text thuần."""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .layout import Para, Table

FONT = "Yu Mincho"


def _font(run, size=None, bold=None, gray=False):
    run.font.name = FONT
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    if size: run.font.size = Pt(size)
    if bold is not None: run.bold = bold
    if gray: run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)


def _new_doc(title: str | None):
    d = Document()
    st = d.styles["Normal"]
    st.font.name = FONT; st.font.size = Pt(10.5)
    st.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    for s in ("Heading 1", "Heading 2"):
        hs = d.styles[s]; hs.font.name = FONT; hs.font.color.rgb = RGBColor(0, 0, 0)
        hs.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    sec = d.sections[0]; sec.left_margin = sec.right_margin = Cm(2.2)
    if title:
        d.add_heading(title, level=1)
    return d


def _add_table(d, t: Table):
    tb = d.add_table(rows=t.n_rows, cols=t.n_cols)
    tb.style = "Table Grid"
    for c in t.cells:
        cell = tb.cell(c.r, c.c)
        if c.rs > 1 or c.cs > 1:
            try: cell = cell.merge(tb.cell(c.r + c.rs - 1, c.c + c.cs - 1))
            except Exception: pass
        cell.text = ""
        _font(cell.paragraphs[0].add_run(c.text), 9.5)
    d.add_paragraph()


def write_docx(pages: list[tuple[int, list[Para | Table]]], out: Path, title: str | None = None,
               page_marker: bool = True) -> None:
    d = _new_doc(title)
    for i, (pno, items) in enumerate(pages):
        if i:
            d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        if page_marker:
            p = d.add_paragraph(); _font(p.add_run(f"【原本 p.{pno}】"), 8, gray=True)
        for it in items:
            if isinstance(it, Table): _add_table(d, it)
            elif it.kind == "heading":
                h = d.add_heading(level=2); _font(h.add_run(it.text), 12, True)
            else:
                p = d.add_paragraph(); p.paragraph_format.space_after = Pt(4); _font(p.add_run(it.text))
    d.save(str(out))


def write_txt(pages, out: Path) -> None:
    with open(out, "w", encoding="utf-8") as f:
        for pno, items in pages:
            f.write(f"=== Trang {pno} ===\n")
            for it in items:
                if isinstance(it, Table):
                    grid = [[""] * it.n_cols for _ in range(it.n_rows)]
                    for c in it.cells: grid[c.r][c.c] = c.text.replace("\n", " / ")
                    f.write("\n".join("\t".join(r) for r in grid) + "\n")
                else:
                    f.write(it.text + "\n")
            f.write("\n")
