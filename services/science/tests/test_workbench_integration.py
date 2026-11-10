"""RES-620 integration: controller + result document + main window gates (real private snapshots, isolated copy)."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402

from test_workbench_results import app, real  # noqa: E402,F401  (shared fixtures)

from dynamis_science.desktop.main_window import MainWindow  # noqa: E402
from dynamis_science.desktop.services import DynamisAppService  # noqa: E402
from dynamis_science.desktop.workbench.spec import AnalysisSpec  # noqa: E402


def _pump(app, predicate, timeout=120.0):
    end = time.time() + timeout
    while not predicate() and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


def _open_study(app, window, study_id):
    parent = window.navigator.topLevelItem(1)
    item = next(parent.child(i) for i in range(parent.childCount())
                if (parent.child(i).data(0, Qt.ItemDataRole.UserRole) or {}).get("id") == study_id)
    window._navigation_activated(item, 0)
    _pump(app, lambda: window.current_study_id == study_id and window.data_pane.variables())
    _pump(app, lambda: not window.runner.active)


@pytest.fixture()
def window(app, real):  # noqa: F811
    window = MainWindow(DynamisAppService())
    _pump(app, lambda: window.navigator.topLevelItemCount() == 4)
    yield window
    window.close()


def _assign_mixed(window):
    window.workbench.select_analysis("mixed_models")
    for role, name in (("outcome", "cmj_height_cm"), ("subject", "subject_id"), ("occasion", "occasion")):
        window.options_pane.slots[role].box.dropped.emit([name])


def test_run_stale_rerun_and_study_switch(app, window):
    _open_study(app, window, "STUDY-REAL-001")
    _assign_mixed(window)
    shell, doc = window.workbench, window.results_doc
    assert not shell.action_promote.isEnabled()  # nothing to promote yet

    shell.action_run.trigger()
    _pump(app, lambda: doc.run is not None and not window.runner.active)
    assert doc.state["kind"] == "qualified" and not doc.stale
    assert shell.run_label.text() == "Results up to date"
    assert shell.action_promote.isEnabled() and shell.action_add_to_report.isEnabled()
    assert shell.stale_bar.isHidden()  # the one stale bar lives in the shell
    assert not hasattr(doc, "stale_bar")

    window.options_pane.option_changed.emit("alpha", 0.1)  # specification change
    assert doc.stale and shell.run_label.text() == "Specification changed"
    assert not shell.stale_bar.isHidden() and not shell.action_promote.isEnabled()

    window.options_pane.option_changed.emit("alpha", 0.05)  # back to the run's spec
    assert not doc.stale and shell.run_label.text() == "Results up to date"

    window.options_pane.option_changed.emit("alpha", 0.1)
    shell.action_run.trigger()  # rerun
    _pump(app, lambda: doc.run_spec_hash == window.controller.current_spec().spec_hash() and not window.runner.active)
    assert not doc.stale and shell.run_label.text() == "Results up to date" and shell.action_promote.isEnabled()

    _open_study(app, window, "STUDY-REAL-002")  # study switch: nothing outlives its data
    assert doc.run is None and not doc.blocks and not doc.promotable
    assert shell.run_label.text() == "No results yet" and not shell.action_promote.isEnabled()


def test_not_qualified_kind_is_stated_and_not_promotable(app, window):
    _open_study(app, window, "STUDY-REAL-001")
    spec = AnalysisSpec("ttest", {"outcome": ["cmj_height_cm"], "subject": ["subject_id"], "occasion": ["occasion"]},
                        table="cmj_occasions",
                        variable_types={"cmj_height_cm": "numerical", "subject_id": "identifier", "occasion": "ordinal"})
    window._run_spec(spec)
    doc = window.results_doc
    assert doc.state["kind"] == "not_qualified" and doc.blocks and doc.run is None
    assert not doc.promotable and not window.workbench.action_promote.isEnabled()
    assert not window.workbench.action_add_to_report.isEnabled()


def test_reference_occasion_change_reruns(app, window):
    """Regression: reference_occasion=2 made Nelder-Mead stall for ~3 minutes, so the rerun looked hung."""
    _open_study(app, window, "STUDY-REAL-001")
    _assign_mixed(window)
    shell, doc = window.workbench, window.results_doc
    shell.action_run.trigger()
    _pump(app, lambda: doc.run is not None and not window.runner.active)
    first = doc.run["id"]

    window.options_pane.option_changed.emit("reference_occasion", 2)
    assert doc.stale
    started = time.time()
    shell.action_run.trigger()
    _pump(app, lambda: doc.run is not None and doc.run["id"] != first and not window.runner.active, timeout=60)
    assert time.time() - started < 60
    assert doc.run["result"]["reference_occasion"] == 2 and not doc.stale
    assert shell.run_label.text() == "Results up to date"
    # the status bar names the digest and it is the new run's recorded result digest, not the previous one
    assert f"result digest {doc.run['result_digest'][:8]}" in shell.provenance_label.text()
    assert doc.run["result_digest"][:8] != "519fe130" and doc.run["id"] in shell.provenance_label.text()


def test_descriptive_kinds_render_blocks_and_never_promote(app, window):
    from dynamis_science.desktop.workbench.descriptive import AthleteChangeBlock, DescriptivesBlock

    _open_study(app, window, "STUDY-REAL-001")
    shell, doc, drop = window.workbench, window.results_doc, window.options_pane
    shell.select_analysis("descriptives")
    drop.slots["outcome"].box.dropped.emit(["cmj_height_cm"])
    drop.slots["factors"].box.dropped.emit(["occasion"])
    shell.action_run.trigger()
    _pump(app, lambda: doc.blocks and not window.runner.active)
    assert isinstance(doc.blocks[0], DescriptivesBlock) and doc.state["kind"] == "descriptive"
    assert not doc.promotable and not shell.action_promote.isEnabled() and doc.run is None
    assert shell.run_label.text() == "Results up to date"
    assert shell.syntax.toPlainText().endswith(doc.blocks[0].syntax)

    shell.select_analysis("athlete_change")
    for role, name in (("outcome", "cmj_height_cm"), ("subject", "subject_id"), ("occasion", "occasion")):
        drop.slots[role].box.dropped.emit([name])
    shell.action_run.trigger()
    _pump(app, lambda: doc.blocks and isinstance(doc.blocks[0], AthleteChangeBlock) and not window.runner.active)
    assert "1 → 4" in doc.blocks[0].title.text() and not doc.promotable
    window.options_pane.option_changed.emit("contrast_occasion", 3)
    assert doc.stale and shell.run_label.text() == "Specification changed"


def test_mixed_model_trajectories_link_with_by_athlete(app, window):
    _open_study(app, window, "STUDY-REAL-001")
    _assign_mixed(window)
    doc, data = window.results_doc, window.data_pane
    window.workbench.action_run.trigger()
    _pump(app, lambda: doc.trajectory_plot is not None and not window.runner.active)
    data.set_view("By athlete")
    doc.trajectory_plot.athlete_selected.emit("MEN-03")  # a click in the plot
    assert data.selected_athlete() == "MEN-03"
    data.select_athlete("")
    row = next(r for r in range(data.athlete_view.model().rowCount())
               if data.athlete_view.model().index(r, 0).data() == "MEN-05")
    data.athlete_view.setCurrentIndex(data.athlete_view.model().index(row, 1))  # a click in the table
    assert doc.trajectory_plot.selected == "MEN-05"
    band = doc.trajectory_plot.model
    assert band and "not the model's Wald band" in band["label"]
    window.trajectory_actions["3D"].trigger()
    assert doc.trajectory_mode == "3D" and doc.trajectory_3d is not None
    assert doc.trajectory_3d.selected == "MEN-05"


def test_signals_in_results_and_perspective_switch(app, window):
    _open_study(app, window, "STUDY-REAL-002")
    window.workbench.select_analysis("signals")
    _pump(app, lambda: window.signals_view is not None and window.signals_view.trials and not window.runner.active)
    assert window.results_stack.currentWidget() is window.signals_view
    window.workbench.select_analysis("reliability")
    assert window.results_stack.currentWidget() is window.results_doc

    titles = [a.text() for a in window.menuBar().actions()]
    assert "Perspective" in titles
    window.show_performance_page("today")
    _pump(app, lambda: not window.runner.active)  # closing with a task running would open a modal prompt
    assert window.perspectives.currentWidget() is window.performance
    assert "Perspective" in [a.text() for a in window.performance_header.menu_button.menu().actions()]
    window.action_research_perspective.trigger()
    assert window.perspectives.currentWidget() is window.workbench
    window.workbench.palette.popup()
    window.workbench.palette.input.setText("Performance OS")
    assert "Performance OS · Today" in window.workbench.palette.commands()
    window.workbench.palette.input.setText("trajectories")
    assert window.workbench.palette.commands() == ["Show 2D trajectories", "Show 3D trajectories"]
    window.workbench.palette.hide()
