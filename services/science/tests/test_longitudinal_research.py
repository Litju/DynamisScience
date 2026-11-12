"""RES-647 cohort and individual longitudinal research in one persistent workspace."""

from __future__ import annotations

import math

import numpy as np
import pytest

from dynamis_science import importer, longitudinal, researchstore
from dynamis_science.desktop.services import DynamisAppService
from test_importer import FIXTURE, _ready

PARTICIPANTS = [f"P{number:02d}" for number in range(1, 13)]
# Missing follow-ups: (participant, week) pairs that were never measured.
MISSING = {("P03", 3), ("P03", 5), ("P07", 6), ("P11", 2), ("P11", 3), ("P11", 4), ("P11", 5), ("P11", 6)}


def value(index: int, week: int, trial: int) -> float:
    return round(30 + index + 0.4 * week + ((trial * 7 + index * 3 + week) % 5 - 2) * 0.3, 2)


def study_file(tmp_path, weeks: range, name: str):
    """Deterministic CMJ weekly trials: 12 pseudonymous participants, 2–3 repeated trials, missing follow-ups."""
    lines = ["Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N),week"]
    for index, participant in enumerate(PARTICIPANTS, start=1):
        for week in weeks:
            if (participant, week) in MISSING:
                continue
            for trial in range(1, 3 + (index % 2)):
                lines.append(f"{participant},{participant}-W{week}-T{trial},{value(index, week, trial)},{70 + index},{1600 + 10 * index},{week}")
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n")
    return path


def admit(path, context):
    staged = importer.stage(_ready(path), context)
    assert staged["eligible"], staged
    return importer.admit(staged)["dataset_snapshot_id"]


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


@pytest.fixture
def study(service, tmp_path):
    context = importer.build_context(FIXTURE)
    identity = service.create_workspace("Squad longitudinal study")["study"]["id"]
    baseline = admit(study_file(tmp_path, range(1, 4), "weeks1-3.csv"), context)
    follow_up = admit(study_file(tmp_path, range(4, 7), "weeks4-6.csv"), context)
    rev1 = service.attach_workspace_data(identity, baseline)["active_data_revision_id"]
    return {"id": identity, "rev1": rev1, "follow_up": follow_up}


def run(service, identity, revision, method="METH-U-DESC", scope=None):
    return service.execute_analysis_run(identity, {"method_id": method, "outcome_metric_id": "MET-CMJ-HEIGHT",
                                                   "parameters": {}, "data_revision_id": revision, "scope": scope})


def test_cohort_and_individual_investigations_share_one_workspace(service, study, tmp_path):
    identity, rev1 = study["id"], study["rev1"]
    cohort_run = run(service, identity, rev1)
    assert cohort_run["scope"] == {"kind": "COHORT"} and cohort_run["result"]["n_subjects"] == 12

    catalogue = service.participant_catalogue(identity)
    assert len(catalogue["participants"]) == 12 and catalogue["occasions"] == [1, 2, 3]
    p03 = next(item for item in catalogue["participants"] if item["subject_id"] == "P03")
    assert p03["sessions"] == 2 and p03["missing_occasions"] == [3] and p03["latest"] == 2
    assert [item["subject_id"] for item in service.participant_catalogue(identity, "p1")["participants"]] == ["P10", "P11", "P12"]

    a = service.create_individual_investigation(identity, "P01", "Jump height trajectory", "How did P01's jump height change?")
    b = service.create_individual_investigation(identity, "P02", "Off-season tracking")
    a_scope = {"kind": "INDIVIDUAL", "investigation_id": a["id"], "subject_id": "P01"}
    a_first = run(service, identity, rev1, "METH-U-INDIVIDUAL", a_scope)
    assert a_first["scope"]["subject_id"] == "P01" and a_first["investigation_id"] == a["id"]
    assert a_first["execution"]["cohort"]["subject_ids"] == ["P01"]
    # Individual analyses never replace the workspace's cohort selection.
    entity = researchstore.get_entity(identity)
    assert entity["cohort_id"] == cohort_run["cohort_id"] and entity["selected_run_id"] == cohort_run["id"]
    # Cohort methods are not offered for a single participant, nor the individual method for the cohort.
    with pytest.raises(researchstore.ResearchValidation, match="Cohort-level method"):
        run(service, identity, rev1, "METH-U-DESC", a_scope)
    with pytest.raises(researchstore.ResearchValidation, match="Individual-scope method"):
        run(service, identity, rev1, "METH-U-INDIVIDUAL")
    b_run = run(service, identity, rev1, "METH-U-INDIVIDUAL", {"kind": "INDIVIDUAL", "investigation_id": b["id"]})
    assert b_run["scope"]["subject_id"] == "P02"
    with pytest.raises(researchstore.ResearchConflict, match="participant changed"):
        run(service, identity, rev1, "METH-U-INDIVIDUAL", {**a_scope, "subject_id": "P02"})

    # Further measurements arrive as a new revision; earlier individual results stay untouched.
    original = researchstore.get_run(a_first["id"])
    rev2 = service.attach_workspace_data(identity, study["follow_up"], append=True, confirm_participant_ids=True,
                                         base_revision=rev1)["active_data_revision_id"]
    assert service.participant_catalogue(identity)["occasions"] == [1, 2, 3, 4, 5, 6]
    a_second = run(service, identity, rev2, "METH-U-INDIVIDUAL", a_scope)
    assert a_second["data_revision_id"] == rev2 and a_first["data_revision_id"] == rev1
    assert a_second["result"]["last"] == 6 and a_first["result"]["last"] == 3
    assert researchstore.get_run(a_first["id"]) == original
    assert [item["id"] for item in longitudinal.investigation_runs(a["id"])] == [a_first["id"], a_second["id"]]
    with pytest.raises(researchstore.ResearchConflict):
        run(service, identity, rev1, "METH-U-INDIVIDUAL", a_scope)

    # P11 has one remaining measured week: the individual method is unavailable, with the reason shown.
    p11 = service.create_individual_investigation(identity, "P11", "Sparse follow-up")
    with pytest.raises(researchstore.ResearchValidation, match="at least two are required"):
        run(service, identity, rev2, "METH-U-INDIVIDUAL", {"kind": "INDIVIDUAL", "investigation_id": p11["id"]})

    # Reports: individual, cohort and combined with separate labeled sections.
    cohort_rev2 = run(service, identity, rev2)
    individual_html = service.export_workspace_report(identity, a_second["id"], str(tmp_path / "a.html")).read_text(encoding="utf-8")
    assert "Individual investigation · participant P01" in individual_html and a_second["id"] in individual_html
    assert researchstore.get_entity(identity)["cohort_id"] == cohort_rev2["cohort_id"]
    combined = service.export_workspace_report(identity, [cohort_rev2["id"], a_second["id"]], str(tmp_path / "combined.html"))
    text = combined.read_text(encoding="utf-8")
    assert "<h3>Cohort research</h3>" in text and "Individual investigation · participant P01" in text
    latest = researchstore.get_report_version(identity, researchstore.report_versions(identity)[0]["version"])
    assert [section["label"] for section in latest["frozen_content"]["research_sections"]][0] == "Cohort research"

    # Reopen: investigations, their runs and every report version are recovered from the store.
    reopened = DynamisAppService()
    assert {item["id"] for item in reopened.individual_investigations(identity)} == {a["id"], b["id"], p11["id"]}
    assert len(researchstore.report_versions(identity)) == 2
    assert reopened.individual_research(a["id"])["runs"][0]["result_digest"] == a_first["result_digest"]


def test_individual_trajectory_independent_recomputation(service, study):
    identity, rev1 = study["id"], study["rev1"]
    investigation = service.create_individual_investigation(identity, "P03", "Missing follow-up")
    saved = run(service, identity, rev1, "METH-U-INDIVIDUAL", {"kind": "INDIVIDUAL", "investigation_id": investigation["id"]})
    result = saved["result"]
    index = 3
    weeks = {week: [value(index, week, trial) for trial in range(1, 3 + index % 2)] for week in (1, 2)}
    assert result["observed_occasions"] == [1, 2] and result["missing_occasions"] == [3]
    assert result["change_first_to_last"] == pytest.approx(np.mean(weeks[2]) - np.mean(weeks[1]))
    variances = [np.var(values, ddof=1) for values in weeks.values()]
    pooled = math.sqrt(sum((len(values) - 1) * var for values, var in zip(weeks.values(), variances)) / sum(len(v) - 1 for v in weeks.values()))
    assert result["within_session_sd"] == pytest.approx(pooled)
    assert result["change_trial_noise_se"] == pytest.approx(pooled * math.sqrt(1 / len(weeks[1]) + 1 / len(weeks[2])))
    assert "not a personalized causal estimate" in result["limitations"][0]


def test_protocol_scenarios_and_cohort_comparison(service, study):
    identity, rev1 = study["id"], study["rev1"]
    investigation = service.create_individual_investigation(identity, "P04", "Plyometric block")
    observational = service.save_protocol(investigation["id"], {
        "design": "OBSERVATIONAL_TRACKING",
        "periods": [{"kind": "BASELINE", "label": "Baseline", "start": 1, "end": 1},
                    {"kind": "INTERVENTION", "label": "Plyometrics", "start": 2, "end": 3}],
        "changes": [{"at": 2, "description": "Added depth jumps"}],
        "adherence": [{"period": "Plyometrics", "adherence_percent": 80, "deviations": "Missed one session"}],
    }, investigation["version"])
    assert observational["protocol"]["design_label"].startswith("Retrospective observational")
    periods = longitudinal.protocol_observations(investigation["id"])
    assert periods[1]["occasions"] == [2, 3] and periods[1]["trials"] == 4
    # A repeated-measurement history alone is not an N-of-1 experiment.
    with pytest.raises(researchstore.ResearchValidation, match="Not an experimental design"):
        service.save_protocol(investigation["id"], {**observational["protocol"], "design": "N_OF_1_EXPERIMENT"}, observational["version"])
    with pytest.raises(researchstore.ResearchValidation, match="overlap"):
        service.save_protocol(investigation["id"], {"periods": [{"kind": "BASELINE", "start": 1, "end": 2},
                                                               {"kind": "INTERVENTION", "start": 2, "end": 3}]}, observational["version"])
    experiment = service.save_protocol(investigation["id"], {
        "design": "N_OF_1_EXPERIMENT", "assignment": "Randomized ABAB sequence", "prespecified": True,
        "periods": [{"kind": "BASELINE", "start": 1, "end": 1}, {"kind": "INTERVENTION", "start": 2, "end": 2},
                    {"kind": "COMPARISON", "start": 3, "end": 3}, {"kind": "INTERVENTION", "start": 4, "end": 4}],
    }, observational["version"])
    assert experiment["protocol"]["design"] == "N_OF_1_EXPERIMENT"

    with pytest.raises(researchstore.ResearchValidation, match="adverse outcome"):
        service.save_scenario(investigation["id"], {"kind": "WORST_CASE", "title": "Detraining", "assumptions": ["No training"],
                                                    "parameter_bounds": [{"name": "weekly change", "lower": -2, "upper": 0, "unit": "cm"}],
                                                    "horizon": {"value": 4, "unit": "weeks"}}, experiment["version"])
    with pytest.raises(researchstore.ResearchValidation, match="recorded in cm"):
        service.save_scenario(investigation["id"], {"kind": "REFERENCE", "title": "x", "assumptions": ["a"], "unit": "m",
                                                    "parameter_bounds": [{"name": "p", "lower": 0, "upper": 1}],
                                                    "horizon": {"value": 1, "unit": "weeks"}}, experiment["version"])
    saved = service.save_scenario(investigation["id"], {
        "kind": "WORST_CASE", "title": "Four-week detraining", "assumptions": ["No jump training", "Same test protocol"],
        "parameter_bounds": [{"name": "weekly change", "lower": -2, "upper": 0, "unit": "cm/week"}],
        "horizon": {"value": 4, "unit": "weeks"}, "adverse_outcome": "Jump height below the week 1 value"}, experiment["version"])
    scenario = saved["scenarios"][-1]
    assert scenario["designation"] == "HYPOTHETICAL" and scenario["numerical_result"] is None
    assert scenario["qualification"]["message"] == "NOT QUALIFIED — Numerical forecast unavailable."
    assert scenario["data_revision_id"] == rev1 and scenario["unit"] == "cm"
    revised = service.save_scenario(investigation["id"], {**scenario, "title": "Six-week detraining",
                                                          "horizon": {"value": 6, "unit": "weeks"}}, saved["version"])
    assert [item["version"] for item in revised["scenarios"]] == [1, 2]
    assert longitudinal.current_scenarios(revised)[0]["title"] == "Six-week detraining"
    history = researchstore.investigation_versions(investigation["id"])
    assert history[0]["protocol"]["periods"] == [] and len(history) == 5

    comparison = service.compare_with_cohort(identity, "P04")
    assert comparison["cohort_definition"].startswith("Other participants in the revision (n = 11)")
    week1 = comparison["rows"][0]
    assert week1["individual_trials"] == 2 and week1["cohort_n"] == 11 and week1["comparable"]
    assert comparison["hypothetical_scenarios"][0]["designation"] == "HYPOTHETICAL"
    assert not comparison["modeled_estimates"]

    service.select_research_scope(identity, "INDIVIDUAL", investigation["id"])
    assert DynamisAppService().get_study_detail(identity)["study"]["id"] == identity
    assert researchstore.get_entity(identity)["research_context"] == {"scope": "INDIVIDUAL", "subject_id": "P04", "investigation_id": investigation["id"]}


def test_native_individual_research_workflow(service, study, tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from dynamis_science.desktop.individual_research import IndividualsExplorer
    from dynamis_science.desktop.main_window import MainWindow

    identity = study["id"]
    window = MainWindow(service)
    qtbot.addWidget(window)
    idle = lambda: qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    idle()
    window._show_study(identity, service.get_study_detail(identity))
    idle()
    assert "Squad longitudinal study · Data revision 1" in window.context_title.text()
    assert window.scope_picker.isEnabled() and not window.investigation_picker.isEnabled()
    explorer = IndividualsExplorer(service, window.run_task, identity, window)
    idle()
    assert explorer.table.rowCount() == 12 and explorer.table.item(2, 5).text() == "3"
    explorer.search.setText("P0")
    idle()
    assert explorer.table.rowCount() == 9
    a = service.create_individual_investigation(identity, "P01", "Trajectory A")
    b = service.create_individual_investigation(identity, "P02", "Trajectory B")
    window.investigations = service.individual_investigations(identity)
    window._select_scope("INDIVIDUAL", a["id"])
    idle()
    panel = window.research.individual
    assert window.research.tabs.currentWidget() is panel and "Participant P01" in panel.header.text()
    assert panel.data_table.rowCount() == 3 and panel.run_button.isEnabled()
    panel.execute()
    idle()
    assert panel.run_picker.count() == 1 and "Trial-noise SE" in panel.result_view.toPlainText()

    # Switching participant clears A's measurements at once; a late completion for A is ignored.
    callbacks = []
    submit = window.runner.submit
    monkeypatch.setattr(window.runner, "submit", lambda operation, done, failed: callbacks.append(done))
    panel.set_investigation(identity, a["id"])
    window._select_scope("INDIVIDUAL", b["id"])
    assert panel.data_table.rowCount() == 0 and panel.run_picker.count() == 0
    callbacks[0](service.individual_research(a["id"]))
    assert "P01" not in panel.header.text()
    monkeypatch.setattr(window.runner, "submit", submit)
    panel.reload()
    idle()
    assert "Participant P02" in panel.header.text() and panel.run_picker.count() == 0

    # Protocol, scenario and cohort comparison through the native forms.
    window._select_scope("INDIVIDUAL", a["id"])
    idle()
    panel._add_period({"kind": "BASELINE", "label": "Baseline", "start": 1, "end": 1})
    panel._add_period({"kind": "INTERVENTION", "label": "Block", "start": 2, "end": 3}, {"adherence_percent": 90, "deviations": ""})
    panel.save_protocol()
    idle()
    assert [item["label"] for item in panel.payload["investigation"]["protocol"]["periods"]] == ["Baseline", "Block"]
    assert "Block (intervention): occasions 2, 3" in panel.period_view.toPlainText()
    panel.scenario_kind.setCurrentIndex(panel.scenario_kind.findData("WORST_CASE"))
    panel.scenario_title.setText("Detraining stress test")
    panel.adverse.setText("Below baseline")
    panel.assumptions.setPlainText("No jump training")
    for column, text in enumerate(("weekly change", "-2", "0", "cm/week")):
        from PySide6.QtWidgets import QTableWidgetItem
        panel.bounds.setItem(0, column, QTableWidgetItem(text))
    panel.save_scenario()
    idle()
    assert "HYPOTHETICAL · Worst-case" in panel.scenario_view.toPlainText()
    assert "NOT QUALIFIED — Numerical forecast unavailable." in panel.scenario_view.toPlainText()
    panel.compare()
    idle()
    assert panel.compare_table.rowCount() == 3 and "cohort descriptive summaries" in panel.compare_notes.toPlainText()

    # Individual and combined exports from the ordinary actions.
    target = tmp_path / "individual.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    window.research.export_report()
    idle()
    assert "Individual investigation · participant P01" in target.read_text(encoding="utf-8")
    run(service, identity, study["rev1"])
    window._show_study(identity, service.get_study_detail(identity))
    idle()
    assert window.research.individual.investigation_id == a["id"] and window.research.latest_run["scope"]["kind"] == "COHORT"
    target = tmp_path / "combined.html"
    window._export_combined_report()
    idle()
    assert "<h3>Cohort research</h3>" in target.read_text(encoding="utf-8")
    window.close()

    # A fresh window restores the persisted scope and investigation.
    reopened = MainWindow(DynamisAppService())
    qtbot.addWidget(reopened)
    qtbot.waitUntil(lambda: not reopened.runner.active, timeout=30000)
    reopened._show_study(identity, service.get_study_detail(identity))
    qtbot.waitUntil(lambda: not reopened.runner.active, timeout=30000)
    assert reopened.scope_picker.currentData() == "INDIVIDUAL" and reopened.investigation_picker.currentData() == a["id"]
    assert "Participant P01" in reopened.research.individual.header.text()
    reopened.close()
