"""RES-716 linked native selector → existing engine → immutable result journeys."""
from statistics import mean

import pytest
from PySide6.QtCore import Qt

from dynamis_science import researchstore
from dynamis_science.desktop.main_window import MainWindow
from test_longitudinal_research import service, study, value  # noqa: F401


def test_cohort_and_individual_native_method_journeys(qtbot, service, study, tmp_path):  # noqa: F811
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.resize(1400, 900)
    window.show()
    def idle():
        qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    idle()
    identity = study["id"]
    window._show_study(identity, service.get_study_detail(identity))
    idle()
    window._analyze_workspace()
    idle()
    panel = window.research
    picker = panel.method_picker
    assert picker.findData("METH-FORECAST") >= 0
    picker.setCurrentIndex(picker.findData("METH-REAL-TREND"))
    assert not panel.execute_button.isEnabled()
    assert "selected outcome is in cmj_trials" in panel.method_details.toPlainText()
    assert "Wald" in panel.method_details.toPlainText()
    picker.setCurrentIndex(picker.findData("METH-FORECAST"))
    assert not panel.execute_button.isEnabled()
    assert "No qualified forecasting model" in panel.method_details.toPlainText()
    before = len(researchstore.list_runs(identity))
    panel._execute()  # Programmatic bypass of the disabled button is also harmless.
    idle()
    assert len(researchstore.list_runs(identity)) == before
    picker.setCurrentIndex(picker.findData("METH-U-DESC"))
    assert panel.execute_button.isEnabled()
    assert "Student-t" in panel.method_details.toPlainText()
    panel.parameters.setPlainText("{invalid")
    panel._method_selected()  # Choosing an old item cannot bypass a pending/invalid preview.
    assert not panel.execute_button.isEnabled()
    panel.parameters.setPlainText("{}")
    idle()
    assert panel.execute_button.isEnabled()
    qtbot.mouseClick(panel.execute_button, Qt.MouseButton.LeftButton)
    idle()
    saved = panel.latest_run
    assert saved["method_id"] == "METH-U-DESC"
    assert saved["result"]["n_subjects"] == 12
    assert saved["execution"]["method_binding"]["data_revision_id"] == study["rev1"]
    assert "implementation_sha256" in panel.run_output.toPlainText()

    inv = service.create_individual_investigation(identity, "P01", "Scientific methods demo")
    individual = panel.individual
    individual.set_investigation(identity, inv["id"])
    idle()
    assert individual.method_picker.currentData()["method_id"] == "METH-U-INDIVIDUAL"
    assert individual.run_button.isEnabled()
    assert "Trial-noise SE" in individual.method_detail.toPlainText()
    individual.execute()
    idle()
    result = individual.run_picker.currentData()
    assert result["method_id"] == "METH-U-INDIVIDUAL"
    assert result["scope"]["subject_id"] == "P01"
    assert result["result"]["change_first_to_last"] == pytest.approx(mean(value(1, 3, t) for t in (1, 2, 3)) - mean(value(1, 1, t) for t in (1, 2, 3)))
    assert "Captured scientific execution contract" in individual.result_view.toPlainText()
    for index in range(individual.method_picker.count()):
        if individual.method_picker.itemData(index)["method_id"] == "METH-REAL-RELIABILITY":
            individual.method_picker.setCurrentIndex(index)
            break
    assert not individual.run_button.isEnabled()
    assert "Cohort-level" in individual.method_detail.toPlainText()
    individual.execute()
    idle()
    assert individual.run_picker.count() == 1
    window.close()


def test_planning_is_read_only_and_exclusions_match_execution(service, study, monkeypatch):  # noqa: F811
    identity, revision = study["id"], study["rev1"]
    original = researchstore.get_entity(identity)
    methods = service.analysis_methods(identity, "MET-CMJ-HEIGHT", revision_id=revision,
                                       excluded_subject_ids=["P01"])
    summary = next(m for m in methods if m["method_id"] == "METH-U-DESC")
    assert summary["status"] == "ELIGIBLE"
    assert summary["population"]["subjects"] == 11
    assert researchstore.get_entity(identity) == original
    with pytest.raises(researchstore.ResearchConflict):
        service.analysis_methods(identity, "MET-CMJ-HEIGHT", revision_id="stale")

    # Authored studies use their saved cohort rules, just as their execution path does.
    metric = researchstore.dataset_metrics(original["dataset_snapshot_id"])[0]
    cohort = researchstore.create_cohort(identity, "Two athletes", {**researchstore._default_cohort_definition(metric, original["dataset_snapshot_id"]),
                                                                 "include_subject_ids": ["P01", "P02"]})
    authored = {**researchstore.get_entity(identity), "workspace": False, "cohort_id": cohort["id"]}
    monkeypatch.setattr(researchstore, "get_entity", lambda _: authored)
    methods = service.analysis_methods(identity, metric["id"])
    assert next(m for m in methods if m["method_id"] == "METH-U-DESC")["population"]["subjects"] == 2
