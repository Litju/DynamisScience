from __future__ import annotations

import json
from pathlib import Path

import pytest

from dynamis_science import performance
from dynamis_science.data_root import data_root
from dynamis_science.desktop.services import DynamisAppService


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DynamisAppService:
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


def test_today_is_composed_from_the_admitted_snapshot(service: DynamisAppService):
    payload = performance.today()
    assert payload["pulse"]["roster_active"] == 28
    assert payload["pulse"]["readiness"] == pytest.approx(7.091, abs=0.001)
    assert payload["pulse"]["load_ratio"] == pytest.approx(1.189, abs=0.001)
    assert payload["pulse"]["cmj_height_cm"] == pytest.approx(42.343, abs=0.001)
    assert payload["data_quality"]["valid_trials"] == 883
    assert payload["data_quality"]["present_trials"] == 884
    assert payload["data_quality"]["missing_slots"] == 12
    assert payload["readiness_bands"] == {"l1": 1, "l2": 2, "l3": 16, "l4": 9}
    assert payload["attention"][0]["athlete_id"] == "ATH-003"
    assert len(payload["attention"]) == 5
    assert payload["triage_count"] > 5
    for row in payload["attention"]:
        assert row["flag"]["unit"]
        assert row["flag"]["threshold"] is not None
    assert payload["study"]["snapshot_id"] == "DS-SYNTH-001"
    assert (data_root() / "performance").is_dir()
    movement = performance.movement()
    assert movement["players"][0]["distance_m"] == pytest.approx(215.9, abs=0.1)
    assert movement["players"][0]["hsr_m"] == pytest.approx(81.3, abs=0.1)
    assert movement["quality"]["position_resets_total"] >= 2


def test_performance_store_ignores_legacy_path_override(service, monkeypatch, tmp_path):
    override = tmp_path.parent / "legacy-performance-store"
    monkeypatch.setenv("DYNAMISSCIENCE_PERFORMANCE_STORE", str(override))

    assert performance._store_dir() == data_root() / "performance"
    assert not override.exists()


def test_availability_is_explicitly_roster_only(service: DynamisAppService):
    context = performance.context()
    assert context["availability"]["injury_table"] is False
    assert context["availability"]["status"] == "ROSTER_ONLY"
    assert "injury or exposure table" in context["availability"]["message"]
    movement = performance.movement()
    assert movement["scope"] == "SEGMENT_ONLY"
    assert "not full-match distance" in movement["quality"]["note"]


def test_athlete_360_uses_one_identity_and_keeps_missing_visible(service: DynamisAppService):
    detail = service.performance_athlete("ATH-003")
    assert detail["subject"]["display_id"] == "ATH-003"
    assert len(detail["weeks"]) == 16
    assert detail["current"]["week"] == 16
    assert detail["baseline_weeks"] == [1, 2, 3, 4]
    assert detail["availability"]["status"] == "ROSTER_ONLY"
    assert detail["force_trial_id"] == "CMJ-003-16-1"
    assert detail["force_trial"]["quality_state"] == "VALID"
    assert detail["force_trial"]["sample_rate_hz"] == 1000
    assert any(week["cmj_missing"] is False for week in detail["weeks"])
    assert detail["individual_change"]["baseline_mean"] is not None
    assert "No causal" in detail["individual_change"]["limitations"]


def test_squad_weeks_cover_every_athlete_and_week(service: DynamisAppService):
    payload = performance.squad_weeks()
    assert payload["weeks"] == list(range(1, 17))
    assert len(payload["athletes"]) == 28
    assert all(len(athlete["weeks"]) == 16 for athlete in payload["athletes"])
    assert all(athlete["availability"]["status"] == "ROSTER_ONLY" for athlete in payload["athletes"])


def test_plan_is_separate_from_measurements_and_persists(service: DynamisAppService):
    plan = performance.get_plan()
    assert plan["status"] == "DRAFT"
    assert plan["source"] == "BASELINE_DERIVED_TEMPLATE"
    assert plan["current_week"] == 16
    assert plan["microcycles"][0]["actual_load_au"] == pytest.approx(264.7, abs=0.01)
    next_microcycle = plan["microcycles"][1]
    assert next_microcycle["week"] == 17
    assert next_microcycle["sessions"]
    assert next_microcycle["status"] == "DRAFT"

    sessions = next_microcycle["sessions"]
    sessions[0]["planned_load_au"] = 50
    updated = service.performance_update_plan(
        {
            "week": 17,
            "focus": "Build 4 · updated",
            "testing_window": "Weekly CMJ",
            "sessions": sessions,
            "publish": True,
            "actor": "Test coach",
        }
    )
    assert updated["status"] == "PUBLISHED"
    assert updated["version"] >= 2
    again = performance.get_plan()
    assert again["microcycles"][1]["sessions"][0]["planned_load_au"] == 50
    assert again["status"] == "PUBLISHED"
    assert any(entry["action"] == "PUBLISHED" for entry in again["audit"])


def test_coach_entered_session_log_is_separate_and_computes_srpe(service: DynamisAppService):
    record = service.performance_log_session(
        {
            "date": "2026-11-06",
            "session_type": "Field",
            "duration_min": 75,
            "session_rpe": 6,
            "attendance": 28,
            "notes": "Normal field session",
            "author_role": "Head of Performance",
        }
    )
    assert record["srpe_load_au"] == 450
    assert record["source"] == "COACH_ENTERED"
    today = performance.today()
    assert today["session_logs"][-1]["id"] == record["id"]


def test_testing_reliability_is_computed_and_assessment_is_append_only(service: DynamisAppService):
    payload = performance.tests()
    assert payload["window"]["trials"] == 56
    assert payload["window"]["valid"] == 56
    assert len(payload["reliability"]) == 4
    for metric in payload["reliability"]:
        assert metric["status"] == "COMPUTED"
        assert metric["icc"] is not None
        assert metric["typical_error"] is not None
        assert metric["n_subjects"] == 28
        assert metric["trials_per_subject"] == 2
    created = service.performance_run_reliability()
    assert created["status"] == "COMPUTED"
    assert created["provenance"]["snapshot_id"] == "DS-SYNTH-001"
    again = performance.tests()
    assert again["assessments"][-1]["id"] == created["id"]
    assert len(again["assessments"]) == 1


def test_performance_reports_are_audience_specific_and_frozen(service: DynamisAppService, tmp_path):
    coach = service.performance_create_report(
        {"audience": "coach", "role": "Head of Performance"}
    )
    assert coach["status"] == "DRAFT"
    assert coach["version"] == 1
    assert coach["sections"]
    assert coach["provenance"]["snapshot_id"] == "DS-SYNTH-001"
    assert coach["content_hash"]

    medical = service.performance_create_report({"audience": "medical", "role": "Physio"})
    text = json.dumps(medical)
    assert "No injury" in text or "no injury" in text or "not admitted" in text.lower()
    assert "diagnosis" in text.lower()

    athlete = service.performance_create_report(
        {"audience": "athlete", "athlete_id": "ATH-003", "role": "Head of Performance"}
    )
    assert "ATH-003" in athlete["title"]

    frozen = service.performance_freeze_report(coach["id"])
    assert frozen["status"] == "FROZEN"
    assert frozen["frozen_at"]
    assert frozen["content_hash"] == coach["content_hash"] or len(frozen["content_hash"]) == 64
    checklist = performance.today()["checklist"]
    assert next(item for item in checklist if item["id"] == "report")["done"] is True

    output = service.performance_export_report(coach["id"], tmp_path / "coach-report.html")
    export = output.read_text(encoding="utf-8")
    assert "DS-SYNTH-001" in export
    assert "Limitations" in export


def test_performance_workspaces_never_mix_real_research_data(service: DynamisAppService):
    context = performance.context()
    assert context["snapshot"]["id"] == "DS-SYNTH-001"
    assert context["snapshot"]["synthetic"] is True
    today = performance.today()
    assert today["study"]["snapshot_id"] == "DS-SYNTH-001"
    assert all("REAL" not in str(item) for item in today["weekly"])
    movement = performance.movement()
    assert "DS-SYNTH-001" in movement["source"]
    plan = performance.get_plan()
    assert plan["club"]["id"] == "NORTHSIDE-FC"
    assert plan["as_of"].startswith("2026-09-24")
    report = service.performance_create_report({"audience": "board", "role": "Director"})
    assert report["provenance"]["snapshot_id"] == "DS-SYNTH-001"
    assert report["provenance"]["report_engine"] == "dynamis-performance.report@1.0.0"
    assert "DS-REAL" not in json.dumps(report["provenance"])


def test_units_and_thresholds_are_first_class(service: DynamisAppService):
    payload = performance.units()
    assert len(payload["units"]) == 24
    symbols = {unit["symbol"] for unit in payload["units"]}
    for symbol in ("cm", "N", "N·s·kg⁻¹", "AU", "m·s⁻¹", "%", "h", "per 1000 h"):
        assert symbol in symbols
    for threshold in payload["thresholds"]:
        assert threshold["owner"]
        assert threshold["set_at"]
        assert threshold["unit"]
    assert any(rule.startswith("No value without a unit") for rule in payload["design_rules"])


def test_research_link_exposes_evidence_with_units(service: DynamisAppService):
    payload = performance.research_link()
    assert payload["synthetic"] is True
    assert payload["study"]["id"] == "STUDY-001"
    assert payload["evidence"]
    assert all(item["unit"] for item in payload["evidence"])
    assert payload["report"]["study_id"] == "STUDY-001"
