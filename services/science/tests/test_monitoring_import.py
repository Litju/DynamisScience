"""RES-647 athlete monitoring import (load, sleep, wellness, roster) linked to CMJ in one workspace revision."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from dynamis_science import importer, researchstore, squad
from test_importer import FIXTURE, service  # noqa: F401  (service is a fixture)
from test_longitudinal_research import PARTICIPANTS, admit, study_file

POSITIONS = ["Forward", "Midfield", "Defence"]
START = date(2026, 9, 1)


def load(index: int, day: int) -> float:
    spike = 1.6 if index == 3 and day >= 35 else 1.0  # P03: load spike in the final week
    return round((400 + 20 * index + 60 * (day % 7 == 2)) * spike, 1)


def monitoring_file(tmp_path, days: range, name: str, header: str = "Athlete,Date,Position,sRPE Load (AU),Sleep (h),Wellness"):
    lines = [header]
    for index, participant in enumerate(PARTICIPANTS, start=1):
        for day in days:
            tired = index == 3 and day >= 35
            lines.append(f"{participant},{START + timedelta(days=day)},{POSITIONS[index % 3]},{load(index, day)},"
                         f"{6.0 if tired else 7.5 + (index % 3) * 0.25},{12 if tired else 20 + index % 4}")
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n")
    return path


def monitoring_context():
    return importer.build_context({**FIXTURE, "dataset_identity": "fixture-monitoring", "manufacturer": "Questionnaire app",
                                   "model": "Daily wellness", "protocol_name": "Morning wellness + sRPE"})


def test_monitoring_file_is_detected_mapped_and_admitted(tmp_path):
    plan = importer.probe_file(monitoring_file(tmp_path, range(0, 7), "week1.csv"))
    assert plan["mapping"]["family"] == "ATHLETE_MONITORING" and plan["state"] == "READY", plan["needs"]
    columns = plan["mapping"]["columns"]
    assert {"subject_id", "date", "position", "training_load_au", "sleep_hours", "wellness_score"} <= set(columns)
    snapshot_id = admit(plan["path"] and monitoring_file(tmp_path, range(0, 7), "week1b.csv"), monitoring_context())
    frame = researchstore.read_snapshot_table(snapshot_id, "monitoring")
    assert frame.height == 84 and frame["date"].min() == "2026-09-01"
    subjects = researchstore.read_snapshot_table(snapshot_id, "subjects")
    assert dict(zip(subjects["subject_id"], subjects["position"]))["P02"] == "Defence"
    assert {m["id"] for m in researchstore.dataset_metrics(snapshot_id)} == {"MET-MON-LOAD", "MET-MON-SLEEP", "MET-MON-WELLNESS"}
    # No time axis: blocked, never assumed.
    blocked = importer.probe_file(monitoring_file(tmp_path, range(0, 2), "noaxis.csv", "Athlete,X,Position,sRPE Load (AU),Sleep (h),Wellness"))
    assert blocked["state"] == "REVIEW" and any("date, day or week" in need for need in blocked["needs"])


def test_link_cmj_and_monitoring_then_flag_and_simulate_across_measures(service, tmp_path):
    identity = service.create_workspace("Squad monitoring")["study"]["id"]
    cmj = admit(study_file(tmp_path, range(1, 7), "cmj.csv"), importer.build_context(FIXTURE))
    rev1 = service.attach_workspace_data(identity, cmj)["active_data_revision_id"]
    first = admit(monitoring_file(tmp_path, range(0, 28), "weeks1-4.csv"), monitoring_context())
    with pytest.raises(researchstore.ResearchValidation, match="Confirm"):
        service.attach_workspace_data(identity, first, link=True, base_revision=rev1)
    rev2 = service.attach_workspace_data(identity, first, link=True, confirm_participant_ids=True, base_revision=rev1)["active_data_revision_id"]
    revision = researchstore.get_data_revision(rev2)
    assert revision["mode"] == "LINK" and revision["compatibility"]["linked"] and not revision["compatibility"]["pooled"]
    assert set(revision["snapshot"]["tables"]) == {"cmj_trials", "monitoring", "subjects"}
    entity = researchstore.get_entity(identity)
    assert entity["outcomes"]["primary"][0]["id"] == "MET-CMJ-HEIGHT"  # the studied outcome is unchanged
    with pytest.raises(researchstore.ResearchValidation, match="already has monitoring"):
        service.attach_workspace_data(identity, first, link=True, confirm_participant_ids=True, base_revision=rev2)

    # Later monitoring weeks are appended; CMJ stays in the revision.
    later = admit(monitoring_file(tmp_path, range(28, 42), "weeks5-6.csv"), monitoring_context())
    rev3 = service.attach_workspace_data(identity, later, append=True, confirm_participant_ids=True, base_revision=rev2)["active_data_revision_id"]
    snapshot = researchstore.get_data_revision(rev3)["snapshot"]
    assert snapshot["row_counts"]["monitoring"] == 12 * 42 and snapshot["row_counts"]["cmj_trials"] == researchstore.read_snapshot_table(cmj, "cmj_trials").height
    linked = researchstore.get_snapshot(rev3)
    assert linked["source"]["id"] == "LINKED_INPUTS"
    assert len(linked["measurement_sources"]["cmj_trials"]) == 1
    assert len(linked["measurement_sources"]["monitoring"]) == 2
    assert all(s["checksum"] and s["source"] for values in linked["measurement_sources"].values() for s in values)
    metrics = {m["id"] for m in researchstore.dataset_metrics(rev3)}
    assert {"MET-CMJ-HEIGHT", "MET-MON-LOAD", "MET-MON-SLEEP", "MET-MON-WELLNESS"} <= metrics
    with pytest.raises(researchstore.ResearchValidation, match="Overlapping"):
        service.attach_workspace_data(identity, admit(monitoring_file(tmp_path, range(40, 42), "dup.csv"), monitoring_context()),
                                      append=True, confirm_participant_ids=True, base_revision=rev3)

    # The researcher's own multi-measure rule: load spike (ACWR) AND falling wellness.
    squad.save_rules(identity, [{"name": "Load spike with poor wellness", "category": "In danger", "tone": "negative", "match": "all",
                                 "conditions": [
                                     {"metric_id": "MET-MON-LOAD", "measure": "acute_chronic_ratio", "acute": 7, "chronic": 28, "operator": ">", "value": 1.3},
                                     {"metric_id": "MET-MON-WELLNESS", "measure": "change_from_baseline_pct", "operator": "<", "value": -20}]}])
    board = squad.squad_board(identity, "position")
    flagged = {a["subject_id"] for g in board["groups"] for a in g["athletes"] if a["flags"]}
    assert flagged == {"P03"}
    assert {g["name"] for g in board["groups"]} == set(POSITIONS)
    acwr = next(a for g in board["groups"] for a in g["athletes"] if a["subject_id"] == "P03")["flags"][0]["evidence"][0]["value"]
    recent = [load(3, d) for d in range(35, 42)]
    chronic = [load(3, d) for d in range(14, 42)]
    assert acwr == pytest.approx((sum(recent) / 7) / (sum(chronic) / 28))

    # "Load +20%/step" with an assumed CMJ effect: researcher-defined driver and effect.
    result = squad.simulate(identity, {"name": "Load push", "steps": 2, "outcome_metric_id": "MET-CMJ-HEIGHT",
                                       "drivers": [{"metric_id": "MET-MON-LOAD", "change_pct_per_step": {"best": 10, "expected": 20, "worst": 30}}],
                                       "effects": [{"driver_metric_id": "MET-MON-LOAD", "outcome_pct_per_driver_pct": {"best": 0.05, "expected": -0.05, "worst": -0.1}}]})
    assert result["numerical_result"] is None and result["athletes"] == []
    assert result["qualification"]["status"] == "NOT_QUALIFIED"
    assert pl.DataFrame(researchstore.read_snapshot_table(rev3, "subjects"))["position"].null_count() == 0


def test_events_feed_reports_flag_changes_between_revisions_and_follow_ups(service, tmp_path):
    identity = service.create_workspace("Events")["study"]["id"]
    rev1 = service.attach_workspace_data(identity, admit(study_file(tmp_path, range(1, 7), "cmj.csv"), importer.build_context(FIXTURE)))["active_data_revision_id"]
    rev2 = service.attach_workspace_data(identity, admit(monitoring_file(tmp_path, range(0, 28), "a.csv"), monitoring_context()),
                                         link=True, confirm_participant_ids=True, base_revision=rev1)["active_data_revision_id"]
    service.attach_workspace_data(identity, admit(monitoring_file(tmp_path, range(28, 42), "b.csv"), monitoring_context()),
                                  append=True, confirm_participant_ids=True, base_revision=rev2)
    squad.save_rules(identity, [{"name": "Load spike with poor wellness", "category": "In danger", "tone": "negative",
                                 "conditions": [{"metric_id": "MET-MON-LOAD", "measure": "acute_chronic_ratio", "acute": 7, "chronic": 28, "operator": ">", "value": 1.3},
                                                {"metric_id": "MET-MON-WELLNESS", "measure": "change_from_baseline_pct", "operator": "<", "value": -20}]}])
    feed = squad.events(identity)
    titles = [item["title"] for item in feed["events"]]
    assert titles.count("Retrospective: P03 entered In danger") == 1  # only when the final weeks arrive (revision 3)
    entered = next(item for item in feed["events"] if item["title"] == "Retrospective: P03 entered In danger")
    assert entered["revision"] == 3 and "record mean ratio (7 vs 28 records)" in entered["detail"]
    assert {"New data attached · revision 1", "New kind of measurement linked · revision 2", "New measurements appended · revision 3"} <= set(titles)
    assert [item["subject_id"] for item in feed["attention"]] == ["P03"]
    service.create_individual_investigation(identity, "P03", "Load spike follow-up")
    assert not squad.events(identity)["attention"]


def test_native_events_screen_opens_athletes_and_starts_follow_ups(service, tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QPushButton

    from dynamis_science.desktop.main_window import MainWindow

    identity = service.create_workspace("Native events")["study"]["id"]
    rev1 = service.attach_workspace_data(identity, admit(study_file(tmp_path, range(1, 7), "cmj.csv"), importer.build_context(FIXTURE)))["active_data_revision_id"]
    service.attach_workspace_data(identity, admit(monitoring_file(tmp_path, range(0, 42), "m.csv"), monitoring_context()),
                                  link=True, confirm_participant_ids=True, base_revision=rev1)
    squad.save_rules(identity, [{"name": "Load spike with poor wellness", "category": "In danger", "tone": "negative",
                                 "conditions": [{"metric_id": "MET-MON-LOAD", "measure": "acute_chronic_ratio", "acute": 7, "chronic": 28, "operator": ">", "value": 1.3},
                                                {"metric_id": "MET-MON-WELLNESS", "measure": "change_from_baseline_pct", "operator": "<", "value": -20}]}])
    window = MainWindow(service)
    qtbot.addWidget(window)
    idle = lambda: qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    idle()
    window._show_study(identity, service.get_study_detail(identity))
    idle()
    window._show_events_mode()
    idle()
    feed = window.events_view
    assert window.perspectives.currentWidget() is feed and "1 need attention" in feed.title.text()
    attention = feed.cards()[0]
    assert "P03" in attention.findChild(type(feed.title)).text()
    feed.filter.setCurrentIndex(feed.filter.findData("flag"))
    feed._render()
    assert all("entered" in card.findChild(type(feed.title)).text() or "no longer" in card.findChild(type(feed.title)).text()
               for card in feed.cards()[1:])
    next(b for b in feed.cards()[0].findChildren(QPushButton) if b.text() == "Open athlete").click()
    idle()
    assert window.perspectives.currentWidget() is window.squad and "P03" in window.squad.athlete_page.header.text()
    window._show_events_mode()
    idle()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Load spike follow-up", True))
    next(b for b in feed.cards()[0].findChildren(QPushButton) if b.text() == "Start follow-up").click()
    idle()
    assert "Participant P03" in window.research.individual.header.text()
    assert window.squad.athlete_page.branch_picker.currentText() == "Branch · Load spike follow-up"
    window._show_events_mode()
    idle()
    assert "0 need attention" in feed.title.text()
    window.close()


def test_mixed_file_has_targeted_explicit_family_recovery(service, tmp_path, qtbot):
    from dynamis_science.desktop.import_review import MappingEditor
    path = tmp_path / "mixed.csv"
    path.write_text("Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N),week,Training Load (AU)\nP01,T1,40,80,1800,1,300\n")
    plan = importer.probe_file(path)
    assert plan["mapping"]["family"] is None and "Edit mapping" in " ".join(plan["needs"])
    dialog = MappingEditor(plan)
    qtbot.addWidget(dialog)
    dialog.family.setCurrentIndex(dialog.family.findData("ATHLETE_MONITORING"))
    mon = importer.edit_mapping(plan, dialog.edits())
    assert mon["mapping"]["family"] == "ATHLETE_MONITORING"
    assert "jump_height_cm" not in mon["mapping"]["columns"]
    dialog.family.setCurrentIndex(dialog.family.findData("CMJ_FORCE_PLATFORM"))
    cmj = importer.edit_mapping(plan, dialog.edits(), {"session_id": "S1", "sampling_hz": 1000})
    assert cmj["mapping"]["family"] == "CMJ_FORCE_PLATFORM"
    assert not any(importer.COLUMNS[c][0] == "MON" for c in cmj["mapping"]["columns"])


def test_monitoring_requires_explicit_choice_between_measured_axes(service, tmp_path):
    path = tmp_path / "axes.csv"
    path.write_text("Athlete,Date,week,Training Load (AU)\nP01,2026-01-01,1,300\n")
    plan = importer.probe_file(path)
    assert "multiple monitoring time axes" in " ".join(plan["needs"])
    recovered = importer.edit_mapping(plan, {"week": None})
    assert recovered["state"] == "READY"
