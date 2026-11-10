from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QAbstractButton, QApplication, QLineEdit, QPlainTextEdit, QWidget

from dynamis_science.desktop import theme
from dynamis_science.desktop.workbench.shell import ANALYSES, PANE_MINIMUM, WorkbenchShell


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


def test_shell_api_layout_keyboard_and_accessibility(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    settings = QSettings(str(tmp_path / "workbench.ini"), QSettings.Format.IniFormat)
    shell = WorkbenchShell(settings)
    qtbot.addWidget(shell)
    shell.resize(1440, 820)
    shell.show()
    qtbot.waitExposed(shell)
    shell.activateWindow()
    qtbot.waitUntil(shell.isActiveWindow)

    assert [shell.ribbon.widgetForAction(a).text() for a in shell.analysis_actions.values()] == [
        label for _key, label, _group in ANALYSES
    ]
    with qtbot.waitSignal(shell.analysis_selected) as selected:
        shell.analysis_actions["mixed_models"].trigger()
    assert selected.args == ["mixed_models"] and shell.current_analysis() == "mixed_models"
    assert shell.panes["options"].title.text() == "Mixed Models"

    data, options, results = QWidget(), QWidget(), QWidget()
    shell.set_data_widget(data)
    shell.set_options_widget(options)
    previous = shell.set_results_widget(results)
    assert previous is not None and shell.panes["results"].content is results
    for key, minimum in PANE_MINIMUM.items():
        assert shell.panes[key].minimumWidth() == minimum

    shell.set_provenance("STD-REAL-101", "RUN-REAL-0005", "519fe130", "descriptive", "real")
    assert not shell.action_promote.isEnabled()
    shell.set_provenance("STD-REAL-101", "RUN-REAL-0005", "519fe130", "qualified", "real")
    assert shell.action_promote.isEnabled()
    assert "digest 519fe130" in shell.provenance_label.text()

    shell.set_run_state("stale")
    assert shell.stale_bar.isVisible()
    shell.set_run_state("current")
    assert not shell.stale_bar.isVisible()
    shell.set_syntax("smf.mixedlm(...)")
    shell.copy_syntax()
    assert QApplication.clipboard().text() == "smf.mixedlm(...)" and shell.toast.isVisible()

    shell.focus_pane(2)
    assert shell.focused_pane() == "results"
    shell.cycle_panes()
    assert shell.focused_pane() == "data"

    unnamed = [
        type(widget).__name__
        for kind in (QAbstractButton, QLineEdit, QPlainTextEdit)
        for widget in shell.findChildren(kind)
        if widget.isVisible() and not widget.accessibleName()
    ]
    assert not unnamed, unnamed

    shell.palette.popup()
    assert "Mixed Models" in shell.palette.commands()
    shell.palette.input.setText("relia")
    assert shell.palette.commands() == ["Reliability"]
    shell.palette._run_current()
    assert shell.current_analysis() == "reliability"

    shell.splitter.setSizes([500, 300, 600])
    expected = shell.splitter.sizes()
    shell.save_state()
    restored = WorkbenchShell(QSettings(str(tmp_path / "workbench.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(restored)
    restored.resize(1440, 820)
    restored.show()
    qtbot.waitExposed(restored)
    assert restored.splitter.sizes() == expected
    assert restored.current_analysis() == "reliability"

    shell.resize(900, 500)
    assert shell._compact and not shell.panes["options"].isVisible()
    shell.focus_pane(1)
    assert shell.panes["options"].isVisible()
    shell.set_theme("light")
