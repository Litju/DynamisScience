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
