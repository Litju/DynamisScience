from __future__ import annotations

import json

import numpy as np
import polars as pl
import pytest

from dynamis_science import realstore, researchanalysis, researchstore
from dynamis_science.generate import generate_data

SNAPSHOT_ID = "DS-REAL-TEST588"


def _fixture_snapshot(root) -> str:
    rng = np.random.default_rng(588)
    subjects = pl.DataFrame(
        {
            "subject_id": [f"T-{index:02d}" for index in range(1, 7)],
            "display_id": [f"P{index:02d}" for index in range(1, 7)],
            "position": ["Athlete"] * 6,
            "age": [21, 22, 23, 24, 25, 26],
            "body_mass_kg": [70.0, 75.0, 80.0, 85.0, 90.0, 95.0],
            "height_cm": [175.0, 178.0, 180.0, 182.0, 184.0, 186.0],
        }
    )
    occasions = []
    for index in range(1, 7):
        baseline = 35.0 + index * 0.8
        for occasion in (1, 2, 3):
            occasions.append(
                {
                    "subject_id": f"T-{index:02d}",
                    "display_id": f"P{index:02d}",
                    "occasion": occasion,
                    "cmj_height_m": (baseline + 1.1 * (occasion - 1) + rng.normal(0, 0.25)) / 100,
                    "cmj_height_cm": baseline + 1.1 * (occasion - 1) + rng.normal(0, 0.25),
                    "isometric_relative_peak_force_n_kg": 25.0 + index + occasion * 0.2,
                    "back_squat_relative_kg_kg": 1.4 + index * 0.02,
                    "sprint_20m_s": 3.4 - occasion * 0.01,
                }
            )
    cmj = pl.DataFrame(occasions)
    signals = []
    for index in range(1, 6):
        for trial in range(1, 4):
            peak = 1400.0 + index * 35.0 + rng.normal(0, 6.0)
            signals.append(
                {
                    "subject_id": f"T-{index:02d}",
                    "display_id": f"P{index:02d}",
                    "trial_id": f"TRIAL-{index}-{trial}",
                    "activity": "Walking",
                    "trial_number": trial,
                    "fz_peak_n": peak,
                    "support_window_mean_n": 760.0 + rng.normal(0, 4.0),
                    "sampling_hz": 1000.0,
                    "force_file_count": 3,
                    "nan_count": 0,
                    "imu_clock_offset_s": -14000.0 + rng.normal(0, 1.0),
                    "metadata_weight_n": 70.0 * index * 9.80665,
                }
            )
    signal_trials = pl.DataFrame(signals)
    imu = pl.DataFrame(
        {
            "subject_id": [f"T-{index:02d}" for index in range(1, 6)],
            "sampling_hz_median": [99.8, 100.1, 100.0, 99.9, 100.2],
            "gravity_mean_g": [1.0, 1.001, 0.999, 1.0, 1.0002],
            "accel_peak_g": [2.1, 2.3, 2.0, 2.4, 2.2],
        }
    )
    tables = {"subjects": subjects, "cmj_occasions": cmj, "signal_trials": signal_trials, "imu_trials": imu}
    assessment = {
        "source_path": "test-fixture.parquet",
        "source_sha256": "a" * 64,
        "source_size_bytes": 1234,
        "status": "ADMITTED_WITH_WARNINGS",
        "checks": [{"check": "schema", "status": "PASS"}, {"check": "units", "status": "PASS"}],
        "warnings": ["Synthetic test snapshot with clearly labelled test participants."],
        "counts": {"subjects": 6, "cmj_occasions": 18, "signal_trials": 15},
    }
    snapshot = realstore.register_snapshot(
        snapshot_id=SNAPSHOT_ID,
        source_id="SRC-MENDELEY-6P99569X66",
        label="Test-only admitted snapshot for RES-588 lifecycle",
        tables=tables,
        row_counts={name: frame.height for name, frame in tables.items()},
        parser_version="test@1.0.0",
        schema_version="test.snapshot@1.0.0",
        assessment=assessment,
        metric_definitions=[],
        extra={"test_fixture": True},
    )
    return snapshot["id"]


@pytest.fixture
def root(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path))
    _fixture_snapshot(tmp_path)
    return tmp_path


def _study(project_id: str, snapshot_id: str = SNAPSHOT_ID, metric: str = "MET-REAL-CMJ-HEIGHT") -> dict:
    return researchstore.create_study(
        project_id,
        {
            "title": "Scientist-authored repeated-measures study",
            "research_question": "Does the outcome change across the deposited testing occasions?",
            "dataset_snapshot_id": snapshot_id,
            "primary_metric_id": metric,
            "design": "OBSERVATIONAL_LONGITUDINAL" if metric == "MET-REAL-CMJ-HEIGHT" else "MEASUREMENT_REPEATED_TRIALS",
            "hypotheses": ["The outcome changes across occasions."],
        },
    )


def test_project_study_cohort_plan_and_run_lifecycle(root):
    project = researchstore.create_project("Repeated measures project", "A test project", ["Estimate change"], [SNAPSHOT_ID])
    detail = _study(project["id"])
    study_id = detail["study"]["id"]
    assert detail["study"]["state"] == "DRAFT"
    assert detail["cohort"]["status"] == "DRAFT"
    assert detail["plan"]["status"] == "DRAFT"
    assert detail["data_health"]["valid_measurements"] == 18
    assert any(method["id"] == "METH-REAL-TREND" for method in detail["methods"])

    cohort = researchstore.freeze_cohort(detail["cohort"]["id"])
    plan = researchstore.freeze_plan(detail["plan"]["id"])
    assert cohort["status"] == "FROZEN"
    assert plan["status"] == "FROZEN"
    assert plan["spec_id"].startswith("SPEC-U-")
    state = researchstore.transition_entity(study_id, "READY")
    assert state["state"] == "READY"

    run = researchanalysis.execute(
        researchstore.get_entity(study_id),
        researchstore.get_cohort(detail["cohort"]["id"]),
        researchstore.get_plan(detail["plan"]["id"]),
        "METH-REAL-TREND",
        "MET-REAL-CMJ-HEIGHT",
        {},
        [],
    )
    assert run["id"] == "RUN-U-0001"
    assert run["plan_alignment"] == "PLANNED"
    assert run["result"]["contrasts"]["occasion_1_to_3"]["estimate"] > 1.5
    assert researchstore.get_entity(study_id)["state"] == "READY"

    promoted = researchanalysis.promote(run["id"])
    assert promoted["evidence_artifact"]["id"] == "EVID-U-0001"
    assert promoted["evidence_artifact"]["evidence_class"] == "PLANNED"
    assert promoted["figure_artifact"]["id"] == "FIG-U-0001"

    researchstore.cite_artifact(study_id, promoted["evidence_artifact"]["id"])
    report = researchstore.report_payload(study_id)
    assert report["evidence_ids"] == ["EVID-U-0001"]
    assert report["research"]["limitations"]
    export = researchstore.export_html(study_id)
    assert "Embedded manifest" not in export
    assert "id=\"manifest\"" in export
    assert "RUN-U-0001" in export
    assert researchstore.lineage("EVID-U-0001")["root"] == "EVID-U-0001"


def test_frozen_objects_are_immutable_and_forked(root):
    project = researchstore.create_project("Immutability project")
    detail = _study(project["id"])
    cohort_id = detail["cohort"]["id"]
    researchstore.freeze_cohort(cohort_id)
    with pytest.raises(researchstore.ResearchConflict):
        researchstore.update_cohort(cohort_id, {"name": "changed"})
    fork = researchstore.fork_cohort(cohort_id)
    assert fork["id"] != cohort_id
    assert fork["status"] == "DRAFT"

    plan_id = detail["plan"]["id"]
    researchstore.freeze_plan(plan_id)
    original = researchstore.get_plan(plan_id)
    with pytest.raises(researchstore.ResearchConflict):
        researchstore.update_plan(plan_id, {"name": "changed"})
    forked = researchstore.fork_plan(plan_id)
    assert forked["id"] != plan_id
    assert researchstore.get_plan(plan_id)["content_hash"] == original["content_hash"]


def test_archiving_never_deletes_historical_artifacts(root):
    project = researchstore.create_project("Archive project")
    detail = _study(project["id"])
    study_id = detail["study"]["id"]
    researchstore.freeze_cohort(detail["cohort"]["id"])
    researchstore.freeze_plan(detail["plan"]["id"])
    run = researchanalysis.execute(
        researchstore.get_entity(study_id),
        researchstore.get_cohort(detail["cohort"]["id"]),
        researchstore.get_plan(detail["plan"]["id"]),
        "METH-REAL-TREND",
        "MET-REAL-CMJ-HEIGHT",
        {},
        [],
    )
    evidence = researchanalysis.promote(run["id"])["evidence_artifact"]
    archived = researchstore.transition_entity(study_id, "ARCHIVED")
    assert archived["state"] == "ARCHIVED"
    assert researchstore.get_run(run["id"]) is not None
    assert researchstore.get_evidence(evidence["id"]) is not None
    assert researchstore.get_cohort(detail["cohort"]["id"])["status"] == "FROZEN"
    with pytest.raises(researchstore.ResearchConflict):
        researchstore.update_entity(study_id, {"title": "cannot edit"})
    restored = researchstore.transition_entity(study_id, "DRAFT")
    assert restored["state"] == "DRAFT"


def test_monitoring_program_keeps_schedule_and_readings_separate(root):
    project = researchstore.create_project("Monitoring project")
    program = researchstore.create_monitoring_program(
        project["id"],
        {
            "title": "Weekly CMJ monitoring",
            "dataset_snapshot_id": SNAPSHOT_ID,
            "primary_metric_id": "MET-REAL-CMJ-HEIGHT",
            "start_week": 5,
            "weeks": 6,
            "frequency": "weekly",
        },
    )
    assert program["kind"] == "MONITORING"
    schedule = program["program"]
    assert schedule["planned_count"] == 6
    assert schedule["observed_count"] == 3
    assert schedule["status"] == "PLANNED_WITH_AVAILABLE_BASELINE"
    assert "not re-labelled" in schedule["observed_note"]
    assert any(block["type"] == "schedule" for block in program["investigation_documents"][0]["blocks"])
    assert program["data_health"]["valid_measurements"] == 18


def test_incompatible_method_is_rejected_before_execution(root):
    project = researchstore.create_project("Eligibility project")
    detail = _study(project["id"])
    eligibility = {item["method_id"]: item["status"] for item in detail["eligibility"]}
    assert eligibility["METH-REAL-RELIABILITY"] == "INELIGIBLE"
    with pytest.raises(researchstore.ResearchValidation):
        researchanalysis.execute(
            researchstore.get_entity(detail["study"]["id"]),
            researchstore.get_cohort(detail["cohort"]["id"]),
            researchstore.get_plan(detail["plan"]["id"]),
            "METH-REAL-RELIABILITY",
            "MET-REAL-CMJ-HEIGHT",
            {},
            [],
        )


def test_restart_and_regeneration_preserve_research_state(root):
    project = researchstore.create_project("Persistence project")
    detail = _study(project["id"])
    before = researchstore.get_project(project["id"])
    # Synthetic regeneration changes data artifacts only, never authored research metadata.
    generate_data()
    after = researchstore.get_project(project["id"])
    assert after["id"] == before["id"]
    assert after["version"] == before["version"]
    assert researchstore.get_entity(detail["study"]["id"]) is not None
    # A fresh process/connection reads the same SQLite state.
    import importlib

    reloaded = importlib.reload(researchstore)
    assert reloaded.get_project(project["id"])["title"] == "Persistence project"




def test_reruns_are_append_only_and_promotion_is_idempotent(root):
    project = researchstore.create_project("Reproduction project")
    detail = _study(project["id"])
    study_id = detail["study"]["id"]
    researchstore.freeze_cohort(detail["cohort"]["id"])
    researchstore.freeze_plan(detail["plan"]["id"])
    entity = researchstore.get_entity(study_id)
    first = researchanalysis.execute(entity, researchstore.get_cohort(detail["cohort"]["id"]), researchstore.get_plan(detail["plan"]["id"]), "METH-REAL-TREND", "MET-REAL-CMJ-HEIGHT", {}, [])
    second = researchanalysis.execute(entity, researchstore.get_cohort(detail["cohort"]["id"]), researchstore.get_plan(detail["plan"]["id"]), "METH-REAL-TREND", "MET-REAL-CMJ-HEIGHT", {}, [])
    assert first["id"] == "RUN-U-0001"
    assert second["id"] == "RUN-U-0002"
    assert first["result_digest"] == second["result_digest"]
    assert first["reproducibility_key"] == second["reproducibility_key"]
    assert len(researchstore.list_runs(study_id)) == 2
    promoted = researchanalysis.promote(first["id"])
    again = researchanalysis.promote(first["id"])
    assert promoted["evidence_artifact"]["id"] == again["evidence_artifact"]["id"]
    assert again["already_promoted"] is True


def test_frozen_report_version_is_stable(root):
    project = researchstore.create_project("Report versions project")
    detail = _study(project["id"])
    study_id = detail["study"]["id"]
    researchstore.freeze_cohort(detail["cohort"]["id"])
    researchstore.freeze_plan(detail["plan"]["id"])
    run = researchanalysis.execute(researchstore.get_entity(study_id), researchstore.get_cohort(detail["cohort"]["id"]), researchstore.get_plan(detail["plan"]["id"]), "METH-REAL-TREND", "MET-REAL-CMJ-HEIGHT", {}, [])
    evidence = researchanalysis.promote(run["id"])["evidence_artifact"]
    researchstore.cite_artifact(study_id, evidence["id"])
    frozen = researchstore.freeze_report(study_id)
    before = researchstore.export_html(study_id, frozen["version"])
    # A second freeze at the same version is idempotent and cannot rewrite history.
    again = researchstore.freeze_report(study_id)
    assert again["content_hash"] == frozen["content_hash"]
    after = researchstore.export_html(study_id, frozen["version"])
    assert "EVID-U-0001" in before and "EVID-U-0001" in after
    assert before == after


def test_archived_project_keeps_children(root):
    project = researchstore.create_project("Project archive")
    detail = _study(project["id"])
    researchstore.set_project_archived(project["id"], True)
    assert researchstore.get_project(project["id"])["status"] == "ARCHIVED"
    assert researchstore.get_entity(detail["study"]["id"]) is not None
    with pytest.raises(researchstore.ResearchConflict):
        researchstore.create_study(project["id"], {"title": "blocked", "research_question": "x", "dataset_snapshot_id": SNAPSHOT_ID, "primary_metric_id": "MET-REAL-CMJ-HEIGHT"})
    restored = researchstore.set_project_archived(project["id"], False)
    assert restored["status"] == "ACTIVE"


def test_dataset_binding_is_snapshot_bound(root):
    project = researchstore.create_project("Bound project")
    detail = _study(project["id"])
    with pytest.raises(researchstore.ResearchValidation):
        researchstore.create_cohort(
            detail["study"]["id"],
            "Wrong snapshot",
            {
                "snapshot_id": "DS-REAL-SOMETHING-ELSE",
                "require_metric_id": "MET-REAL-CMJ-HEIGHT",
                "min_metric_observations": 1,
            },
        )
