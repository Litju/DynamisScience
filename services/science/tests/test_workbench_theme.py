from __future__ import annotations

import pytest

from dynamis_science.desktop import theme


@pytest.mark.parametrize("name", sorted(theme.THEMES))
def test_text_tokens_meet_wcag_aa_on_their_surfaces(name):
    failures = [
        f"{fg} on {bg}: {theme.contrast_ratio(a, b):.2f}"
        for fg, bg, a, b in theme.text_pairs(name)
        if theme.contrast_ratio(a, b) < 4.5
    ]
    assert not failures, failures


def test_frozen_tokens_match_the_design_source():
    assert theme.LIGHT["accent"] == "#1F6B5A" and theme.DARK["desk"] == "#0B0C0E"
    # Text variants only ever move toward the ink; the frozen hues stay for marks and borders.
    assert theme.THEMES["light"]["hyp"] == theme.LIGHT["hyp"]
    assert theme.THEMES["light"]["hyp_text"] != theme.LIGHT["hyp"]


def test_stylesheet_is_fully_generated_for_both_themes():
    for name in theme.THEMES:
        sheet = theme.build_stylesheet(theme.tokens(name))
        assert "$" not in sheet
        for kinds in theme.CHIP_AXES.values():
            for kind in kinds:
                assert f'[chip="{kind}"]' in sheet
        assert "QToolBar#WorkbenchRibbon QToolButton:checked" in sheet
        assert "QFrame#StaleBar" in sheet and "QLabel#Toast" in sheet
        assert "QPushButton#PerformanceRailItem:checked" in sheet


def test_chip_axes_are_separate(qapp):
    kinds = [kind for kinds in theme.CHIP_AXES.values() for kind in kinds]
    assert len(kinds) == len(set(kinds))
    with pytest.raises(ValueError):
        theme.chip("x", "unknown")

