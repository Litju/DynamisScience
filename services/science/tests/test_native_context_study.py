"""Twelve-week research journey through the native timeline and frozen workspace history."""

from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
import os
import sqlite3

import pytest
from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox

from dynamis_science import admission, context_timeline as timeline, importer, reconciliation
from dynamis_science import researchstore as store, training_context as context
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService
from dynamis_science.desktop.study_home import _NODES
from dynamis_science.desktop.training_context import ContextSourceDialog
from dynamis_science.qa_cleanup import read_marker
from test_reconciliation import FIELDS, declaration, decide, revise, write_export
from test_importer import FIXTURE
from test_training_context import export, training, wellness

START = date(2026, 8, 3)
TRAINING, WELLNESS = "TRAIN-724", "WELL-724"
DATED = FIELDS + ["Date"]
ATHLETES = [f"A{index:02d}" for index in range(1, 21)]
METRIC = "MET-CMJ-HEIGHT"


def day(week, weekday):
    return START + timedelta(weeks=week - 1, days=weekday)


def stamp(week, weekday, hour):
    return f"{day(week, weekday)}T{hour:02d}:00:00-03:00"


def measures(index, week):
    code = f"A{index:02d}-W{week:02d}"
    return [[f"A{index:02d}", code, f"{code}-T{trial}", week, 1000,
             round(28 + index * 0.4 + (week - 1) * 0.25 + offset, 3),
             65 + index, 1500 + index, day(week, index % 4).isoformat()]
            for trial, offset in enumerate((-0.3, 0.3) if (index, week) != (20, 12) else (-0.3,), 1)]


def exposure_rows():
    rows = []
    for index, subject in enumerate(ATHLETES, 1):
        external = "EXT-07" if subject == "A07" else subject
        for week in range(1, 13):
            for weekday in (1, 3, 5)[:1 + index % 3]:
                row = training(participant=external, record_id=f"TR-{subject}-{week}-{weekday}",
                               scheduled_at=stamp(week, weekday, 17), occurred_at=stamp(week, weekday, 17),
                               duration=str(30 + index + weekday), duration_unit="min", rpe=str(3 + week % 5),
                               adherence="AS_PLANNED", recorded_at=stamp(week, weekday, 17))
                if (index + 2 * week + weekday) % 17 == 0:
                    row.update(status="OMITTED", occurred_at=None, duration=None, rpe=None,
                               adherence="OMITTED", reason="Session cancelled", recorded_at=stamp(week, weekday, 19))
                elif (index + week + weekday) % 7 == 0:
                    row.update(occurred_at=stamp(week, weekday + 1, 17), recorded_at=stamp(week, weekday + 1, 19),
                               adherence="MODIFIED", deviation="Adjusted schedule")
                if row["status"] == "OBSERVED" and (index + week * 3 + weekday) % 19 == 0:
                    row.update(rpe=None, rpe_scale=None)
                if row["duration"] and week % 2 == 0:
                    row.update(duration=str(int(row["duration"]) * 60), duration_unit="s")
                rows.append(row)
    return rows


def wellness_rows():
    rows = []
    for index, subject in enumerate(ATHLETES, 1):
        for week in range(1, 13):
            for weekday in (0, 4)[:1 + index % 2]:
                row = wellness(participant=subject, record_id=f"WE-{subject}-{week}-{weekday}",
                               scheduled_at=stamp(week, weekday, 8), questionnaire_version="1" if week < 7 else "2")
                if (index + week + weekday) % 5:
                    row.update(status="OBSERVED", occurred_at=stamp(week, weekday, 8), reason=None,
                               value=str(6 + (week + weekday + index) % 5 / 2))
                rows.append(row)
    return rows


def _source(identity, label):
    return admission.register_source({
        "id": identity, "name": label, "dataset_identity": identity, "publisher": "Synthetic research lab",
        "version": "2026.1", "acquisition_method": "Deterministic fixture", "license_or_agreement": "Internal synthetic fixture",
        "redistribution_restrictions": "Internal", "permitted_uses": ["research"],
        "privacy_status": "TEST_FIXTURE", "rights_status": "FIXTURE_ONLY",
    })


def _append(workspace, path, rows, sessions):
    proposal = reconciliation.propose(workspace, write_export(path, rows, DATED))
    reviewed = revise(proposal, sessions={name: name for name in sessions}, declared=declaration(proposal))
    assert reviewed["ready"], reviewed["discrepancies"]
    return decide(reviewed, "APPROVED")["decision"]["revision_id"]


def _protocol(periods, occasions, reason=""):
    return {"outcome_metric_id": METRIC, "unit": "cm", "prospective": True, "prespecified": True,
            "question": "How does measured CMJ performance vary over the documented periods?",
            "assignment": "Prespecified coach sequence", "amendment_reason": reason,
            "testing_occasions": occasions,
            "periods": [dict(kind=kind, label=label, start=first, end=last)
                        for kind, label, first, last in periods]}


def _study(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    workspace = service.create_workspace("RES-724 Twenty athletes over twelve weeks")["study"]["id"]
    rows = [row for index in range(1, 21) for row in measures(index, 1)]
    initial = write_export(tmp_path / "baseline.csv", rows, DATED)
    staged = importer.stage(importer.probe_file(initial), importer.build_context(FIXTURE))
    assert staged["eligible"], staged["quality"]
    first = service.attach_workspace_data(workspace, importer.admit(staged)["dataset_snapshot_id"])
    revision = first["active_data_revision_id"]
    investigation = service.create_individual_investigation(workspace, "A01", "Prespecified training sequence")
    phases = [("BASELINE", "Baseline", 2, 2), ("INTERVENTION", "Block A", 3, 4),
              ("COMPARISON", "Comparator A", 5, 6), ("INTERVENTION", "Block B", 7, 9),
              ("COMPARISON", "Comparator B", 10, 12)]
    investigation = service.save_protocol(investigation["id"], _protocol(phases, [2, 4, 6, 8, 12]), investigation["version"])
    amended = _protocol(phases, [2, 4, 6, 9, 12], "Documented travel changed the future week 8 testing slot")
    investigation = service.save_protocol(investigation["id"], amended, investigation["version"])
    assessments = {1: (4, 7, 12), **{i: (4 + i % 3, 8 + i % 2, 12) for i in range(2, 21)}}
    rows = [row for index, weeks in assessments.items() for week in weeks for row in measures(index, week)]
    updated = _append(workspace, tmp_path / "follow-up.csv", rows, sorted({row[1] for row in rows}))
    for scheduled, observed in ((4, 4), (6, 7)):
        investigation = service.record_experimental_visit(investigation["id"], {
            "protocol_version": 2, "scheduled_occasion": scheduled, "occasion": observed,
            "occurred_at": stamp(observed, 1, 14), "data_revision_id": updated, "measurement_status": "MEASURED",
            "adherence_percent": 80 if scheduled != observed else 100, "exposure": "Researcher's recorded conduct",
            "deviations": "Visit delayed by one week" if scheduled != observed else "",
        }, investigation["version"])
    snapshot = store.get_data_revision(updated)["snapshot_id"]
    metric = next(row for row in store.dataset_metrics(snapshot) if row["id"] == METRIC)
    definition = store._default_cohort_definition(metric, snapshot)
    definition["include_subject_ids"] = ATHLETES[:10]
    cohort = store.create_cohort(workspace, "First ten athletes", definition)
    result = service.execute_analysis_run(workspace, {
        "data_revision_id": updated, "method_id": "METH-U-DESC", "outcome_metric_id": METRIC, "parameters": {},
    })
    report = service.export_workspace_report(workspace, result["id"], str(tmp_path / "historical.html"))
    _source(TRAINING, "Training session log")
    _source(WELLNESS, "Morning wellness questionnaire")
    return service, workspace, revision, updated, investigation, cohort, report


def test_native_twenty_athlete_twelve_week_context(qtbot, monkeypatch, tmp_path):
    service, workspace, baseline, revision, investigation, cohort, report = _study(monkeypatch, tmp_path)
    report_bytes = report.read_bytes()
    report_hashes = [row["content_hash"] for row in store.report_versions(workspace)]
    training_data, wellness_data = exposure_rows(), wellness_rows()
    exports = {"file": export(tmp_path / "training-v1.csv", training_data)}
    wellness_file = export(tmp_path / "wellness-v1.csv", wellness_data)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(exports["file"]), ""))
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("A01 · August to October", True))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(QMessageBox, "exec", lambda box: warnings.append(box.text()))

    def show_window(app):
        window = MainWindow(app)
        qtbot.addWidget(window)
        window.resize(1440, 900)
        window.show()
        wait(window)
        window._show_study(workspace, app.get_study_detail(workspace))
        wait(window)
        return window

    def wait(window):
        qtbot.waitUntil(lambda: not window.runner.active, timeout=30_000)

    def capture(widget, name):
        scratch = os.environ.get("DYNAMISSCIENCE_QA_RUN_ROOT")
        if scratch and read_marker(scratch)["issue_id"] == "RES-724":
            assert widget.grab().save(str(Path(scratch) / name))

    window = show_window(service)
    window._go_research_stage("Training context")
    wait(window)
    panel = window.research.training_context

    def attach_source(source_id, alias=None, expected_change=None):
        def review():
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, ContextSourceDialog)
            try:
                if expected_change:
                    assert dialog.sources.currentData() == source_id
                    assert "EXT-07 → A07" in dialog.details.toPlainText()
                else:
                    dialog.sources.setCurrentIndex(dialog.sources.findData(source_id))
                if alias:
                    external, athlete = alias
                    assert not dialog.preview_button.isEnabled()
                    dialog.aliases[external].setCurrentText(athlete)
                dialog.preview_button.click()
                assert dialog.attach_button.isEnabled(), dialog.details.toPlainText()
                if expected_change:
                    assert expected_change in dialog.details.toPlainText()
                dialog.attach_button.click()
                assert dialog.result() == 1, dialog.details.toPlainText()
            finally:
                if dialog.isVisible():
                    dialog.reject()
        QTimer.singleShot(0, review)
        panel.add_source.click()
        wait(window)

    attach_source(TRAINING, ("EXT-07", "A07"))
    exports["file"] = wellness_file
    attach_source(WELLNESS)
    panel.week_one.setText(START.isoformat())
    panel.offset.setText("-03:00")
    panel._query(save_calendar=True)
    wait(window)
    if panel.comparison is None:
        panel.compare_button.click()
    assert panel.view["subject_ids"] == ["A01"]
    assert {row["kind"] for row in panel.view["events"]} == set(timeline.KINDS)
    plans = [row for row in panel.view["events"] if row["kind"] == "PLAN"]
    assert len(plans) == 5 and all(row["protocol_version"] == 2 for row in plans)
    assert plans[0]["date"] == "2026-08-10" and plans[-1]["end_date"] == "2026-10-25"
    late = next(row for row in panel.view["events"] if row["kind"] == "VISIT" and row["visit"]["occasion"] == 7)
    assert late["period"]["label"] == "Comparator A" and late["observed_period"]["label"] == "Block B"
    assert late["visit"]["adherence_percent"] == 80
    assert late["visit"]["data_revision_id"] == revision
    point = panel.chart.getViewBox().mapViewToScene(QPointF(late["axis_time"], 2))
    qtbot.mouseClick(panel.chart.viewport(), Qt.MouseButton.LeftButton, pos=panel.chart.mapFromScene(point))
    evidence = panel.evidence.details.toPlainText()
    assert "Comparator A" in evidence and "Block B" in evidence and "80% adherence" in evidence
    panel.evidence.picker.setFocus()
    qtbot.keyClick(panel.evidence.picker, Qt.Key.Key_Home)
    assert panel.evidence.picker.currentIndex() == 0
    panel.evidence.picker.setCurrentIndex(next(i for i, row in enumerate(panel.visible_rows) if row["kind"] == "ASSESSMENT"))
    comparison = panel.comparison
    assert comparison["status"] == "DESCRIPTIVE"
    assert comparison["change"] == pytest.approx(11 * 0.25)
    assert "+2.75 cm" in panel.finding.text()
    assert "Meaningful change has not been established" in panel.comparison_summary.text()
    assert "LIVE · Revision 2" == panel.mode.text()
    assert not window.scope_picker.isVisible()
    assert not window.research.tabs.tabBar().isVisible()
    assert "Jump height" in panel.evidence.details.toPlainText()
    assert window.investigate_button.isChecked() and window.study_button.isVisible()
    window.study_button.click()
    study_home = window.study_home
    assert study_home.isVisible() and window.study_button.isChecked()
    assert not window.stage_picker.isVisible() and not window.research.tabs.tabBar().isVisible()
    instrument = study_home.instrument
    original_projection = instrument._project(_NODES[1])[0]
    instrument.setFocus()
    qtbot.keyClick(instrument, Qt.Key.Key_Right)
    assert instrument._project(_NODES[1])[0] != original_projection
    qtbot.keyClick(instrument, Qt.Key.Key_Home)
    pos = instrument._project(_NODES[1] * 1.17)[0].toPoint()
    qtbot.mouseClick(instrument, Qt.MouseButton.LeftButton, pos=pos)
    wait(window)
    assert window.location.text() == "Sources & quality"
    sources = window.research.source_overview
    assert "Training session log" in sources.context_sources.text()
    assert "Morning wellness questionnaire" in sources.context_sources.text()
    assert "Synthetic fixture" in sources.quality.text()
    assert not window.research.table.isVisible()
    window.investigate_button.click()
    wait(window)
    assert panel.scope.currentData() == "A01" and panel.comparison is comparison

    def check_task(title, verify):
        opened = []
        current = panel.comparison

        def review():
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, QDialog)
            try:
                task_panel = window.research.individual
                assert title in dialog.windowTitle()
                assert not task_panel.tabs.tabBar().isVisible()
                qtbot.waitUntil(lambda: task_panel.payload.get("investigation", {}).get("id") == investigation["id"], timeout=20000)
                verify(task_panel)
                opened.append(True)
            finally:
                dialog.reject()

        QTimer.singleShot(50, review)
        panel.evidence.followup.click()
        wait(window)
        assert opened and panel.comparison is current and window._investigation_visible()

    first_plan = next(i for i, row in enumerate(panel.visible_rows) if row["kind"] == "PLAN")
    panel.evidence.picker.setCurrentIndex(first_plan)

    def planned(task_panel):
        qtbot.waitUntil(lambda: task_panel.protocol_sections.currentIndex() == 2, timeout=15000)
        assert task_panel.period_table.item(task_panel.period_table.currentRow(), 1).text() == "Baseline"

    check_task("A01 · Protocol", planned)
    visit_index = next(i for i, row in enumerate(panel.visible_rows)
                       if row.get("visit", {}).get("id") == late["visit"]["id"])
    panel.evidence.picker.setCurrentIndex(visit_index)

    def recorded(task_panel):
        qtbot.waitUntil(lambda: task_panel.visit_editor.isVisible(), timeout=15000)
        assert task_panel.visit_supersedes.currentData() == late["visit"]["id"]
        assert task_panel.visit_adherence.text() == "80"

    check_task("A01 · Visits", recorded)
    assert panel.evidence.picker.currentIndex() == visit_index
    assert panel.plots.findText("Jump height (cm)") > 0
    panel.plots.setCurrentText("Jump height (cm)")
    assert panel.values_chart.isVisible()
    exposure_source = next(row for row in panel.view["sources"] if row["source"]["id"] == TRAINING)
    relevant = [row for row in training_data if row["participant"] == "A01" and
                day(1, 1).isoformat() < (row["occurred_at"] or row["scheduled_at"])[:10] < day(12, 1).isoformat()]
    independently_computed = sum(float(row["duration"]) * float(row["rpe"]) /
                                (60 if row["duration_unit"] == "s" else 1)
                                for row in relevant if row["duration"] and row["rpe"])
    context_summary = comparison["between_exclusive_dates_by_source"][exposure_source["id"]]
    assert context_summary["recorded_load_sum_au"] == pytest.approx(independently_computed)
    assert context_summary["counts"]["TRAINING OBSERVED"] == sum(row["status"] == "OBSERVED" for row in relevant)
    incompatible_calendar = timeline.build(workspace, revision,
        timeline.TimelineQuery(subject_id="A01", week_one=START + timedelta(days=7), local_offset="-03:00"))
    assert not any(row["kind"] == "PLAN" for row in incompatible_calendar["events"])
    assert "conflicts with recorded assessment weeks" in " ".join(incompatible_calendar["notes"])
    capture(panel, "724-live-timeline.png")
    panel.save_view.click()
    wait(window)
    frozen = panel.saved
    assert frozen and not panel.add_source.isEnabled()
    assert "FROZEN · Revision 2" == panel.mode.text()
    capture(panel, "724-frozen-context.png")
    def unexpected_comparison(*args):
        pytest.fail("Returning to the unchanged live view reran the comparison")

    with monkeypatch.context() as patch:
        patch.setattr(timeline, "compare", unexpected_comparison)
        panel.live_view.click()
        wait(window)
    assert panel.comparison is comparison and panel.scope.currentData() == "A01"
    assert "LIVE · Revision 2" == panel.mode.text()

    panel.scope.setCurrentIndex(panel.scope.findData(f"cohort:{cohort['id']}"))
    wait(window)
    assert panel.view["subject_ids"] == ATHLETES[:10]
    panel.scope.setCurrentIndex(0)
    wait(window)
    all_events = panel.view["events"]
    counts = Counter(row["kind"] for row in all_events)
    assert counts == {"TRAINING": len(training_data), "WELLNESS": len(wellness_data),
                      "ASSESSMENT": 80, "PLAN": 5, "VISIT": 2}
    assert {row["subject_id"] for row in all_events} == set(ATHLETES)
    for event in all_events:
        if event["kind"] == "ASSESSMENT":
            assert all(trial["trial_id"].startswith(event["subject_id"] + "-") for trial in event["trials"])
        if event["kind"] == "TRAINING" and event["external_id"] == "EXT-07":
            assert event["subject_id"] == "A07"
        if event["kind"] in {"TRAINING", "WELLNESS"}:
            assert event["record_id"].split("-")[1] == event["subject_id"]
    observed_exposures = [row for row in all_events if row["kind"] == "TRAINING"]
    assert any("AFTER_SCHEDULE" in row["qc"] and "RECORDED_LATER" in row["qc"] for row in observed_exposures)
    assert any(row["status"] == "OMITTED" and row["session_load_au"] is None for row in observed_exposures)
    assert any(row["status"] == "OBSERVED" and row["session_load_au"] is None for row in observed_exposures)
    responses = [row for row in all_events if row["kind"] == "WELLNESS"]
    assert any(row["status"] == "MISSING" and row["value"] is None for row in responses)
    assert {row["questionnaire_version"] for row in responses} == {"1", "2"}
    window.study_button.click()
    window.study_home.buttons["people"].click()
    tile = next(tile for tile in window.squad.board.tiles() if "A20" in tile.accessibleName())
    tile.click()
    wait(window)
    assert window._investigation_visible() and panel.scope.currentData() == "A20"
    assert panel.comparison["status"] == "INCOMPARABLE" and panel.comparison["change"] is None
    assert "different numbers of trials" in panel.comparison_summary.text()

    panel.scope.setCurrentIndex(panel.scope.findData("A01"))
    wait(window)
    target = next(row for row in training_data if row["record_id"].startswith("TR-A01-2-") and row["rpe"])
    corrected = [{**row, "rpe": str(float(row["rpe"]) + 1)} if row["record_id"] == target["record_id"] else row
                 for row in training_data]
    exports["file"] = export(tmp_path / "training-v2.csv", corrected)
    attach_source(TRAINING, expected_change="160 AU → 192 AU")
    assert "3,334 → 3,366 AU" in panel.import_outcome.text()
    assert panel.comparison["change"] == pytest.approx(2.75)
    context_history = context.source_history(workspace, revision)
    assert [row["version"] for row in context_history if row["source"]["id"] == TRAINING] == [1, 2]
    old = measures(1, 12)[0]
    old[5] += 2
    correction = _append(workspace, tmp_path / "cmj-correction.csv", [old], [])
    assert store.get_data_revision(correction)["mode"] == "CORRECTION"
    panel.scope.setCurrentIndex(panel.scope.findData("A01"))
    wait(window)
    panel.open_saved(frozen["id"])
    wait(window)
    window.research.set_study(workspace, service.get_study_detail(workspace))
    wait(window)
    assert "FROZEN · Revision 2" == panel.mode.text()
    assert panel.comparison["change"] == pytest.approx(2.75)
    panel.live_view.click()
    wait(window)
    assert panel.comparison is None and panel.scope.currentData() == "A01"
    assert "data revision changed" in panel.comparison_summary.text().lower()
    assert panel.compare_button.isVisible()
    panel.compare_button.click()
    assert panel.comparison["change"] == pytest.approx(3.75)
    panel.evidence.picker.setCurrentIndex(next(i for i, row in enumerate(panel.visible_rows)
                                               if row.get("visit", {}).get("id") == late["visit"]["id"]))
    check_task("A01 · Visits", recorded)
    window.study_button.click()
    window.study_home.buttons["design"].click()
    assert "20" in window.research.overview.toPlainText() or "Twenty" in window.research.overview.toPlainText()
    assert "workspace_id" not in window.research.overview.toPlainText()
    assert [row["id"] for row in store.data_revisions(workspace)] == [baseline, revision, correction]
    window.close()

    restarted = show_window(DynamisAppService())
    restarted._go_research_stage("Reports / history")
    wait(restarted)
    history_panel = restarted.research.history_panel
    history_panel.kind.setCurrentText("Contextual views")
    assert history_panel.picker.currentData()[1]["id"] == frozen["id"]
    history_panel.open_context.click()
    wait(restarted)
    reopened = restarted.research.training_context
    assert reopened.saved == frozen
    assert reopened.comparison["change"] == pytest.approx(2.75)
    assert context.roster(store.get_data_revision(correction)) == ATHLETES
    assert store.get_entity(workspace)["active_data_revision_id"] == correction
    assert report.read_bytes() == report_bytes
    assert [row["content_hash"] for row in store.report_versions(workspace)] == report_hashes
    reopened.live_view.click()
    wait(restarted)
    reopened.scope.setCurrentIndex(reopened.scope.findData("A01"))
    wait(restarted)
    assert "LIVE · Revision 3" == reopened.mode.text()
    assert reopened.comparison["change"] == pytest.approx(3.75)
    assert warnings == []
    with sqlite3.connect(store._db_path()) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    print(f"RES-724 native 20×12: {dict(counts)}; omitted training {sum(r['status']=='OMITTED' for r in observed_exposures)}; "
          f"missing wellness {sum(r['status']=='MISSING' for r in responses)}; A01 +2.75 cm, "
          f"{independently_computed:g} recorded AU in the open interval; A20 incomparable; corrected A01 +3.75 cm. "
          f"Frozen view {frozen['id']} SHA-256 {frozen['content_hash']}; historical HTML SHA-256 {sha256(report_bytes).hexdigest()}; "
          f"protocol {investigation['id']} v2; measurement revisions {baseline}, {revision}, {correction}.")
