from __future__ import annotations

from pathlib import Path

import pytest

from dynamis_science import qualification
from dynamis_science.data_root import data_root, paths
from dynamis_science.desktop.services import DynamisAppService


@pytest.fixture
def service(monkeypatch, tmp_path):
    root = tmp_path / "private"
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


def _register_fixture_source(service: DynamisAppService) -> None:
    service.register_admission_source(
        {
            "id": "SRC-FIXTURE",
            "name": "Fixture source",
            "publisher": "DynamisScience tests",
            "dataset_identity": "fixture-cmj",
            "version": "1.0",
            "acquisition_method": "synthetic fixture",
            "license_or_agreement": "Internal fixture only; not real data",
            "redistribution_restrictions": "Fixture only; do not treat as real measurements",
            "permitted_uses": ["testing"],
            "rights_status": "FIXTURE_ONLY",
            "derived_data_publishable": False,
        }
    )
    service.verify_source_rights("SRC-FIXTURE", "test")


def _register_instrument_protocol(service: DynamisAppService) -> None:
    service.register_admission_instrument(
        {
            "id": "INST-FP-1",
            "measurement_family": "CMJ_FORCE_PLATFORM",
            "manufacturer": "Fixture",
            "model": "FP",
            "serial_number": "1",
            "calibration_status": "CALIBRATED",
            "calibration_date": "2026-01-01",
            "sampling_capabilities_hz": [1000.0],
        }
    )
    service.register_admission_protocol(
        {
            "id": "PROT-FP-1",
            "measurement_family": "CMJ_FORCE_PLATFORM",
            "name": "Fixture CMJ",
            "version": "1.0",
            "sampling_hz": 1000.0,
            "units": {"body_mass": "kg", "time": "s", "distance": "cm"},
            "coordinate_convention": "vertical z up",
            "processing_method": "trapezoidal",
        }
    )


def _cmj_csv() -> str:
    return (
        "subject_id,session_id,trial_id,instrument_id,protocol_id,sampling_hz,week,body_mass_kg,jump_height_cm,concentric_impulse_n_s_kg\n"
        "SUB-1,S-1,T-1,INST-FP-1,PROT-FP-1,1000,1,80,40,1.7\n"
        "SUB-2,S-2,T-2,INST-FP-1,PROT-FP-1,1000,1,75,38,1.6\n"
    )


def _ingest(service: DynamisAppService, tmp_path: Path, filename: str, content: bytes):
    source_file = tmp_path / filename
    source_file.write_bytes(content)
    return service.ingest_local_source_file("SRC-FIXTURE", source_file)


def test_admission_rejects_source_ids_that_could_escape_storage(service, tmp_path):
    with pytest.raises(ValueError, match="Source id"):
        service.register_admission_source(
            {
                "id": "../outside",
                "name": "Fixture source",
                "publisher": "DynamisScience tests",
                "dataset_identity": "fixture-cmj",
                "version": "1.0",
                "acquisition_method": "synthetic fixture",
                "license_or_agreement": "Internal fixture only",
                "redistribution_restrictions": "Fixture only",
            }
        )
    assert not (data_root() / "artifacts" / "admission_sources.json").exists()


def test_fixture_rights_still_require_permitted_uses(service):
    service.register_admission_source({
        "id": "SRC-INCOMPLETE", "name": "Fixture", "publisher": "Tests",
        "dataset_identity": "fixture", "version": "1", "acquisition_method": "synthetic",
        "license_or_agreement": "Test only", "redistribution_restrictions": "No redistribution",
        "rights_status": "FIXTURE_ONLY", "permitted_uses": [],
    })
    result = service.verify_source_rights("SRC-INCOMPLETE", "test")
    assert result["rights_status"] == "UNVERIFIED"
    assert "missing permitted uses" in result["problems"]


def test_admission_valid_csv(service, tmp_path):
    _register_fixture_source(service)
    _register_instrument_protocol(service)
    artifact = _ingest(service, tmp_path, "cmj.csv", _cmj_csv().encode())
    metadata = {"units": {"body_mass": "kg", "time": "s", "distance": "cm"}}
    validation = service.validate_source_artifact(
        artifact["id"], "CMJ_FORCE_PLATFORM", metadata
    )
    assert validation["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
    admitted = service.admit_source_artifact(
        artifact["id"], "CMJ_FORCE_PLATFORM", metadata
    )
    assert admitted["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
    assert admitted["dataset_snapshot_id"] is not None
    assert any(
        item["id"] == admitted["dataset_snapshot_id"] for item in service.list_datasets()
    )
    assert data_root() == service.root
    assert Path(artifact["stored_path"]).is_relative_to(service.root)
    assert (
        paths()["admitted"]
        / admitted["dataset_snapshot_id"]
        / "cmj_trials.parquet"
    ).exists()
    assert (paths()["artifacts"] / "admission_records.json").exists()


@pytest.mark.parametrize(
    "filename,content,metadata",
    [
        (
            "missing.csv",
            b"subject_id,trial_id\nSUB-1,T-1\n",
            {"units": {"body_mass": "kg"}},
        ),
        (
            "units.csv",
            _cmj_csv().encode(),
            {"units": {"body_mass": "stones"}},
        ),
        (
            "duplicate.csv",
            (
                "subject_id,session_id,trial_id,instrument_id,protocol_id,sampling_hz,week,body_mass_kg,jump_height_cm\n"
                "SUB-1,S-1,T-1,INST-FP-1,PROT-FP-1,1000,1,80,40\n"
                "SUB-2,S-2,T-1,INST-FP-1,PROT-FP-1,1000,1,75,38\n"
            ).encode(),
            {"units": {"body_mass": "kg"}},
        ),
        (
            "sampling.csv",
            (
                "subject_id,session_id,trial_id,instrument_id,protocol_id,sampling_hz,week,body_mass_kg,jump_height_cm\n"
                "SUB-1,S-1,T-1,INST-FP-1,PROT-FP-1,0,1,80,40\n"
            ).encode(),
            {"units": {"body_mass": "kg"}},
        ),
        ("corrupt.csv", b"\x00\xff\xfe not csv", {"units": {"body_mass": "kg"}}),
    ],
)
def test_invalid_admission_data_is_rejected(
    service, tmp_path, filename, content, metadata
):
    _register_fixture_source(service)
    _register_instrument_protocol(service)
    artifact = _ingest(service, tmp_path, filename, content)
    validation = service.validate_source_artifact(
        artifact["id"], "CMJ_FORCE_PLATFORM", metadata
    )
    assert validation["status"] == "REJECTED"
    assert validation["errors"]


def test_admission_is_idempotent_and_rejected_inputs_never_create_snapshots(
    service, tmp_path
):
    _register_fixture_source(service)
    _register_instrument_protocol(service)
    artifact = _ingest(service, tmp_path, "idem.csv", _cmj_csv().encode())
    repeated = service.ingest_local_source_file(
        "SRC-FIXTURE", tmp_path / "idem.csv"
    )
    assert artifact["id"] == repeated["id"]
    metadata = {"units": {"body_mass": "kg", "time": "s", "distance": "cm"}}
    first = service.admit_source_artifact(
        artifact["id"], "CMJ_FORCE_PLATFORM", metadata
    )
    before = len(service.list_admission_records())
    second = service.admit_source_artifact(
        artifact["id"], "CMJ_FORCE_PLATFORM", metadata
    )
    assert second["dataset_snapshot_id"] == first["dataset_snapshot_id"]
    assert len(service.list_admission_records()) == before

    rejected = _ingest(service, tmp_path, "reject.csv", b"foo,bar\n1,2\n")
    result = service.admit_source_artifact(
        rejected["id"], "CMJ_FORCE_PLATFORM", {"units": {"body_mass": "kg"}}
    )
    assert result["status"] == "REJECTED"
    assert result["dataset_snapshot_id"] is None


def test_sprint_modality_is_admitted_with_its_own_contract(service, tmp_path):
    _register_fixture_source(service)
    service.register_admission_instrument(
        {
            "id": "INST-TIME-1",
            "measurement_family": "SPRINT_TIMING",
            "manufacturer": "Fixture",
            "model": "Gates",
            "serial_number": "2",
            "calibration_status": "CALIBRATED",
        }
    )
    service.register_admission_protocol(
        {
            "id": "PROT-SPRINT-1",
            "measurement_family": "SPRINT_TIMING",
            "name": "Sprint",
            "version": "1.0",
            "sampling_hz": 1000.0,
            "units": {"distance": "m", "time": "s"},
            "coordinate_convention": "track lane",
        }
    )
    csv = (
        "subject_id,session_id,trial_id,instrument_id,protocol_id,distance_m,time_s\n"
        "SUB-1,S-1,T-1,INST-TIME-1,PROT-SPRINT-1,30,4.2\n"
    ).encode()
    artifact = _ingest(service, tmp_path, "sprint.csv", csv)
    result = service.admit_source_artifact(
        artifact["id"],
        "SPRINT_TIMING",
        {"units": {"distance": "m", "time": "s"}, "coordinate_system": "track"},
    )
    assert result["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}


def test_qualification_records_are_native_python_calls(service):
    records = qualification.run_qualification()
    assert len(records) == 3
    statuses = {record["id"]: record["status"] for record in records}
    assert statuses["QUAL-CMJ-METRICS"] == "QUALIFIED"
    assert statuses["QUAL-RELIABILITY"] == "QUALIFIED"
    assert statuses["QUAL-LONGITUDINAL"] == "PARTIALLY_QUALIFIED"
