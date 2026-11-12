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


def test_native_squad_home_athlete_branches_and_simulation(service, study, tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QInputDialog

    from dynamis_science import squad
    from dynamis_science.desktop.main_window import MainWindow
    from dynamis_science.desktop.squad_view import SimulationDialog

    identity = study["id"]
    squad.save_rules(identity, [{"name": "Low jump height", "category": "In danger", "tone": "negative",
                                 "conditions": [{"metric_id": "MET-CMJ-HEIGHT", "measure": "latest", "operator": "<", "value": 34}]}])
    window = MainWindow(service)
    qtbot.addWidget(window)
    idle = lambda: qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    idle()
    window._show_study(identity, service.get_study_detail(identity))
    idle()
    home = window.squad
    assert window.perspectives.currentWidget() is home and home.currentWidget() is home.board
    assert "Data revision 1" in window.context_title.text()
    tiles = home.board.tiles()
    assert len(tiles) == 12
    danger = [tile for tile in tiles if tile.athlete["flags"]]
    assert {tile.athlete["subject_id"] for tile in danger} == {"P01", "P02", "P03"}
    assert all("In danger" in tile.text() for tile in danger)

    # Tap P01: athlete page on the main line, then a new branch becomes the individual investigation.
    p01 = next(tile for tile in tiles if tile.athlete["subject_id"] == "P01")
    p01.click()
    idle()
    page = home.athlete_page
    assert home.currentWidget() is page and "P01" in page.header.text() and page.branch_picker.currentData() is None
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Plyometric block", True))
    page.new_branch()
    idle()
    panel = window.research.individual
    assert "Participant P01" in panel.header.text() and page.branch_picker.currentText() == "Branch · Plyometric block"
    panel.execute()
    idle()
    assert panel.run_picker.count() == 1

    # Back to the squad and into P02: P01's measurements are cleared, a late P01 completion is ignored.
    callbacks = []
    submit = window.runner.submit
    monkeypatch.setattr(window.runner, "submit", lambda operation, done, failed: callbacks.append(done))
    panel.set_investigation(identity, panel.investigation_id)
    page.back_requested.emit()
    next(tile for tile in home.board.tiles() if tile.athlete["subject_id"] == "P02").click()
    assert panel.data_table.rowCount() == 0 and "P02" in page.header.text()
    callbacks[0](service.individual_research(window.investigations[0]["id"]))
    assert "P01" not in panel.header.text()
    monkeypatch.setattr(window.runner, "submit", submit)

    # Researcher-defined squad simulation through the native dialog.
    dialog = SimulationDialog(service, window.run_task, identity, home.board.board, None, window)
    dialog.trend["worst"].setValue(-3)
    dialog.run(True)
    idle()
    assert dialog.results.rowCount() == 1 and "not a model-based prediction" in dialog.summary.text()
    assert researchstore.get_entity(identity)["simulations"][0]["definition"]["name"] == "Scenario"

    # Individual export from the branch, then reopen restores the athlete and branch.
    window._select_scope("INDIVIDUAL", window.investigations[0]["id"])
    idle()
    target = tmp_path / "individual.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    window.research.export_report()
    idle()
    assert "Individual investigation · participant P01" in target.read_text(encoding="utf-8")
    window.close()
    reopened = MainWindow(DynamisAppService())
    qtbot.addWidget(reopened)
    qtbot.waitUntil(lambda: not reopened.runner.active, timeout=30000)
    reopened._show_study(identity, service.get_study_detail(identity))
    qtbot.waitUntil(lambda: not reopened.runner.active, timeout=30000)
    assert reopened.perspectives.currentWidget() is reopened.squad and reopened.squad.currentWidget() is reopened.squad.athlete_page
    assert "Participant P01" in reopened.research.individual.header.text()
    reopened.close()


@pytest.mark.parametrize("sessions", [
    [[10], [11, 12, 13], [16]],
    [[1, 2], [4, 8, 12, 16], [20, 21, 22]],
    [[3], [], [7]],
    [[1, 9, 17], [], [10, 10.1]],
])
def test_individual_noise_against_independent_pairwise_identity(monkeypatch, sessions):
    from statistics import mean
    import polars as pl
    rows = [{"subject_id": "A", "week": i+1, "height": v, "quality_state": "VALID"}
            for i, values in enumerate(sessions) for v in values]
    # Another participant establishes missing measurement occasions without imputing A.
    rows += [{"subject_id": "B", "week": i+1, "height": 1.0, "quality_state": "VALID"} for i in range(len(sessions))]
    frame = pl.DataFrame(rows)
    monkeypatch.setattr(researchstore, "read_snapshot_table", lambda *args: frame)
    result = longitudinal.individual_trajectory("test", {"table": "cmj_trials", "column": "height", "unit": "cm", "id": "height"}, "A")
    observed = [v for v in sessions if v]
    # SSE identity: sum of all unordered pair differences squared / n.
    sse = sum(sum((x-y)**2 for i, x in enumerate(v) for y in v[i+1:])/len(v) for v in observed)
    df = sum(len(v)-1 for v in observed)
    pooled = math.sqrt(sse/df) if df else None
    assert result["change_first_to_last"] == pytest.approx(mean(observed[-1])-mean(observed[0]))
    assert result["within_session_df"] == df
    assert result["missing_occasions"] == [i+1 for i,v in enumerate(sessions) if not v]
    if df:
        assert result["within_session_sd"] == pytest.approx(pooled)
        assert result["change_trial_noise_se"] == pytest.approx(math.sqrt(sse/df*(1/len(observed[0])+1/len(observed[-1]))))
    else:
        assert result["within_session_sd"] is None and result["change_trial_noise_se"] is None
    assert "common session variance" in " ".join(result["limitations"])


def test_individual_excludes_nonfinite_and_qc_ineligible_trials(monkeypatch):
    import polars as pl
    frame = pl.DataFrame({"subject_id": ["A"]*6, "week": [1,1,1,2,2,3],
                          "height": [10., float("nan"), 999., 14., 16., float("inf")],
                          "quality_state": ["VALID", "VALID", "REJECTED", "VALID", "VALID", "VALID"]})
    monkeypatch.setattr(researchstore, "read_snapshot_table", lambda *args: frame)
    result = longitudinal.individual_trajectory("test", {"table": "cmj_trials", "column": "height", "unit": "cm", "id": "height"}, "A")
    assert result["change_first_to_last"] == 5
    assert result["n_observations"] == 3 and result["missing_occasions"] == [3]
