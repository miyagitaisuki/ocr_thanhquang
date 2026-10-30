"""Tương phản màu của giao diện Qt (WCAG): không cần cửa sổ."""
import pytest

from ocrnhat.gui_qt_style import PALETTES, PILLS, contrast, stylesheet

TEXT_PAIRS = [("text", "page"), ("text", "card"), ("muted", "page"), ("muted", "card"), ("accent_dark", "accent_soft"),
              ("accent", "card"), ("accent", "field"), ("danger", "card"), ("pdf_fg", "pdf_bg"), ("btn_fg", "btn_hi"),
              ("btn_fg", "btn_lo"), ("btn_fg", "btn_hover_hi"), ("btn_fg", "btn_hover_lo"), ("nav_text", "card")]
CONTROL_PAIRS = [("ctl_border", "field"), ("ctl_border", "card"), ("accent", "field")]


@pytest.mark.parametrize("theme", list(PALETTES))
def test_text_contrast(theme):
    pal = PALETTES[theme]
    for fg, bg in TEXT_PAIRS:
        assert contrast(pal[fg], pal[bg]) >= 4.5, (theme, fg, bg)


@pytest.mark.parametrize("theme", list(PALETTES))
def test_control_contrast(theme):
    pal = PALETTES[theme]
    for fg, bg in CONTROL_PAIRS:
        assert contrast(pal[fg], pal[bg]) >= 3.0, (theme, fg, bg)


@pytest.mark.parametrize("theme", list(PALETTES))
def test_pill_contrast(theme):
    for key, (bg, fg) in PILLS[theme].items():
        assert contrast(fg, bg) >= 4.5, (theme, key)


def test_stylesheet_has_no_placeholder_and_scales():
    for theme in PALETTES:
        assert "@" not in stylesheet(theme)
    assert "font-size: 16pt" in stylesheet("sáng", 12)   # tiêu đề = cỡ chữ + 4
