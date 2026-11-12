from __future__ import annotations

from pathlib import Path

import pytest

from dynamis_science import researchstore
from dynamis_science.desktop.services import DynamisAppService


def test_authored_project_study_cohort_plan_and_report_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    service.ensure_initialized()
    project = service.create_project(
        {
            "title": "Local authoring test",
            "description": "Disposable workflow verification",
            "objectives": ["Verify persistent research lifecycle"],
            "dataset_snapshot_ids": ["DS-SYNTH-001"],
        }
    )
    updated = service.update_project(
        project["id"],
        {"title": "Versioned local authoring test", "base_version": project["version"]},
    )
    assert updated["version"] == 2
    with pytest.raises(researchstore.ResearchConflict):
        service.update_project(project["id"], {"title": "Stale edit", "base_version": 1})

    detail = service.create_study(
        project["id"],
        {
            "title": "Synthetic repeated-measures study",
            "research_question": "Does the stored outcome change over the observed weeks?",
            "dataset_snapshot_id": "DS-SYNTH-001",
            "primary_metric_id": "MET-CMJ-IMPULSE",
            "design": "OBSERVATIONAL_LONGITUDINAL",
        },
    )
    study_id = detail["study"]["id"]
    edited_study = service.update_study(
        study_id,
        {"title": "Scientist-edited repeated-measures study"},
        base_version=detail["study"]["version"],
    )
    assert edited_study["version"] == detail["study"]["version"] + 1
    cohort = service.list_cohorts(study_id)[-1]
    cohort = service.update_cohort(
        cohort["id"],
        {"description": "Updated cohort definition", "base_version": cohort["version"]},
    )
    frozen_cohort = service.freeze_cohort(cohort["id"])
    assert frozen_cohort["status"] == "FROZEN"
    plan = service.list_plans(study_id)[-1]
    updated_plan = service.update_plan(
        plan["id"], {"name": "Pre-specified descriptive plan", "base_version": plan["version"]}
    )
    frozen_plan = service.freeze_plan(updated_plan["id"])
    assert frozen_plan["status"] == "FROZEN" and frozen_plan["content_hash"]
    assert len(service.cohort_history(cohort["id"])) == 3
    assert len(service.plan_history(plan["id"])) == 3
    service.transition_study(study_id, "READY")

    run = service.execute_analysis_run(
        study_id,
        {
            "method_id": frozen_plan["method_id"],
            "outcome_metric_id": frozen_plan["outcome_metric_id"],
            "parameters": frozen_plan["parameters"],
        },
    )
    assert run["plan_alignment"] == "PLANNED"
    evidence = service.promote_run_to_evidence(run["id"])["evidence_artifact"]
    service.cite_report_artifact(study_id, evidence["id"])
    version = service.freeze_report(study_id)["version"]
    report = service.export_report_html(study_id, tmp_path / "report-v1.html", version)
    report_html = report.read_text(encoding="utf-8")
    assert run["id"] in report_html
    assert "Student-t 95% CI for final-point mean (not the change)" in report_html
    assert researchstore.report_versions(study_id)[0]["status"] == "FROZEN"
    first_report = service.get_report_version(study_id, version)
    draft_report = service.update_report(
        study_id,
        {"summary": "Second frozen version for native comparison."},
        base_version=version,
    )
    second_version = service.freeze_report(study_id)["version"]
    second_report = service.get_report_version(study_id, second_version)
    assert draft_report["version"] == second_version == version + 1
    assert first_report["frozen_content"] != second_report["frozen_content"]
    assert any(record["change_type"] == "CREATED" for record in service.project_history(project["id"]))
    assert any(record["change_type"] == "UPDATED" for record in service.study_history(study_id))


def test_investigation_scratchpad_versions_validate_order_and_fork(tmp_path, monkeypatch):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    project = service.create_project(
        {"title": "Investigation test", "dataset_snapshot_ids": ["DS-SYNTH-001"]}
    )
    study = service.create_study(
        project["id"],
        {
            "title": "Investigation study",
            "research_question": "How does the registered outcome vary?",
            "dataset_snapshot_id": "DS-SYNTH-001",
            "primary_metric_id": "MET-CMJ-IMPULSE",
        },
    )["study"]

    investigation = service.create_investigation(
        study["id"],
        "Signal review",
        [
            {"id": "B-COHORT", "type": "cohort", "title": "Cohort", "state": {}},
            {
                "id": "B-EXPLORE",
                "type": "explore",
                "title": "Explore impulse",
                "state": {"cohort_block_id": "B-COHORT"},
            },
        ],
    )
    with pytest.raises(researchstore.ResearchValidation, match="must appear earlier"):
        service.update_investigation(
            investigation["id"],
            [
                {
                    "id": "B-EXPLORE",
                    "type": "explore",
                    "title": "Explore impulse",
                    "state": {"cohort_block_id": "B-COHORT"},
                },
                {"id": "B-COHORT", "type": "cohort", "title": "Cohort", "state": {}},
            ],
            base_version=1,
        )

    updated = service.update_investigation(
        investigation["id"], investigation["blocks"], base_version=1, title="Saved version"
    )
    assert updated["version"] == 2
    with pytest.raises(researchstore.ResearchConflict, match="at version 2"):
        service.update_investigation(
            investigation["id"], investigation["blocks"], base_version=1
        )
    fork = service.fork_investigation(investigation["id"])
    assert fork["parent_id"] == investigation["id"]
    assert fork["blocks"] == updated["blocks"]
    assert len(service.list_investigations(study["id"])) == 3


def test_local_source_admission_streams_checks_rights_and_enters_research_catalogue(
    tmp_path, monkeypatch
):
    root = tmp_path / "private"
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    service = DynamisAppService()
    service.ensure_initialized()
    source = {
        "id": "SRC-LOCAL-TEST",
        "name": "Disposable CMJ source",
        "publisher": "Researcher-provided manifest",
        "dataset_identity": "local-cmj-test-v1",
        "version": "1.0",
        "acquisition_method": "local file",
        "license_or_agreement": "Test fixture licence",
        "redistribution_restrictions": "Local test only",
        "permitted_uses": ["research testing"],
        "privacy_status": "TEST_FIXTURE",
        "rights_status": "UNVERIFIED",
        "derived_data_publishable": False,
    }
    service.register_admission_source(source)
    rights = service.verify_source_rights(source["id"], "test operator")
    assert rights["rights_status"] == "VERIFIED"
    service.register_admission_instrument(
        {
            "id": "INST-LOCAL-TEST",
            "measurement_family": "CMJ_FORCE_PLATFORM",
            "manufacturer": "Test",
            "model": "Plate",
            "serial_number": "TEST-1",
            "calibration_status": "CALIBRATED",
        }
    )
    service.register_admission_protocol(
        {
            "id": "PROT-LOCAL-TEST",
            "measurement_family": "CMJ_FORCE_PLATFORM",
            "name": "Test CMJ protocol",
            "version": "1.0",
            "sampling_hz": 1000,
            "units": {"body_mass": "kg", "time": "s", "distance": "cm"},
        }
    )
    source_file = tmp_path / "cmj.csv"
    content = (
        "subject_id,session_id,trial_id,instrument_id,protocol_id,sampling_hz,week,body_mass_kg,jump_height_cm,concentric_impulse_n_s_kg\n"
        "P01,S01,T01,INST-LOCAL-TEST,PROT-LOCAL-TEST,1000,1,80,38,1.7\n"
        "P01,S02,T02,INST-LOCAL-TEST,PROT-LOCAL-TEST,1000,2,80,39,1.8\n"
        "P02,S01,T03,INST-LOCAL-TEST,PROT-LOCAL-TEST,1000,1,75,35,1.6\n"
        "P02,S02,T04,INST-LOCAL-TEST,PROT-LOCAL-TEST,1000,2,75,36,1.7\n"
    ).encode()
    source_file.write_bytes(content)
    artifact = service.ingest_local_source_file(source["id"], source_file)
    stored = Path(artifact["stored_path"])
    assert stored.read_bytes() == content
    assert artifact["size_bytes"] == len(content)
    metadata = {"units": {"body_mass": "kg", "time": "s", "distance": "cm"}}
    quality = service.validate_source_artifact(
        artifact["id"], "CMJ_FORCE_PLATFORM", metadata
    )
    assert quality["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
    admitted = service.admit_source_artifact(
        artifact["id"], "CMJ_FORCE_PLATFORM", metadata
    )
    assert admitted["dataset_snapshot_id"]
    dataset = service.get_dataset_detail(admitted["dataset_snapshot_id"])
    assert dataset["source"]["license"]["id"] == source["license_or_agreement"]
    assert dataset["source"]["privacy"]["restrictions"] == source["redistribution_restrictions"]
    page = service.read_table_page(admitted["dataset_snapshot_id"], "cmj_trials", limit=2)
    assert len(page["rows"]) == 2
    methods = service.list_methods(admitted["dataset_snapshot_id"])
    assert any(method["id"] == "METH-U-DESC" for method in methods)
    assert any(
        item["id"] == admitted["dataset_snapshot_id"]
        for item in service.list_datasets()
    )
    project = service.create_project(
        {
            "title": "Admitted data project",
            "dataset_snapshot_ids": [admitted["dataset_snapshot_id"]],
        }
    )
    study = service.create_study(
        project["id"],
        {
            "title": "Admitted CMJ study",
            "research_question": "How does CMJ impulse change over measured weeks?",
            "dataset_snapshot_id": admitted["dataset_snapshot_id"],
            "primary_metric_id": "MET-CMJ-IMPULSE",
            "design": "OBSERVATIONAL_LONGITUDINAL",
        },
    )
    assert study["real_data"]
    assert study["snapshot"]["source"]["rights_status"] == "VERIFIED"
