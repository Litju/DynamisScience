import base64
import io

import polars as pl
import pytest
from fastapi.testclient import TestClient

from dynamis_science.admission import ADMITTED_DIR, ADMISSION_RECORDS_PATH
from dynamis_science.api import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _register_fixture_source(client: TestClient) -> None:
    client.post("/admission/sources", json={
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
    })
    client.post("/admission/sources/SRC-FIXTURE/verify-rights", json={"verifier": "test"})


def _register_instrument_protocol(client: TestClient) -> None:
    client.post("/admission/instruments", json={
        "id": "INST-FP-1",
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "manufacturer": "Fixture",
        "model": "FP",
        "serial_number": "1",
        "calibration_status": "CALIBRATED",
        "calibration_date": "2026-01-01",
        "sampling_capabilities_hz": [1000.0],
    })
    client.post("/admission/protocols", json={
        "id": "PROT-FP-1",
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "name": "Fixture CMJ",
        "version": "1.0",
        "sampling_hz": 1000.0,
        "units": {"body_mass": "kg", "time": "s", "distance": "cm"},
        "coordinate_convention": "vertical z up",
        "processing_method": "trapezoidal",
    })


def _cmj_csv() -> str:
    return (
        "subject_id,session_id,trial_id,instrument_id,protocol_id,sampling_hz,week,body_mass_kg,jump_height_cm,concentric_impulse_n_s_kg\n"
        "SUB-1,S-1,T-1,INST-FP-1,PROT-FP-1,1000,1,80,40,1.7\n"
        "SUB-2,S-2,T-2,INST-FP-1,PROT-FP-1,1000,1,75,38,1.6\n"
    )


def test_admission_valid_csv(client: TestClient):
    _register_fixture_source(client)
    _register_instrument_protocol(client)
    content = _cmj_csv().encode()
    artifact = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "cmj.csv",
        "content_base64": base64.b64encode(content).decode(),
    }).json()
    validation = client.post("/admission/validate", json={
        "artifact_id": artifact["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg", "time": "s", "distance": "cm"}},
    }).json()
    assert validation["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
    admitted = client.post("/admission/admit", json={
        "artifact_id": artifact["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg", "time": "s", "distance": "cm"}},
    }).json()
    assert admitted["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
    assert admitted["dataset_snapshot_id"] is not None
    snapshots = client.get("/admission/snapshots").json()
    assert any(s["id"] == admitted["dataset_snapshot_id"] for s in snapshots)


def test_admission_missing_required_fields(client: TestClient):
    _register_fixture_source(client)
    _register_instrument_protocol(client)
    content = b"subject_id,trial_id\nSUB-1,T-1\n"
    artifact = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "bad.csv",
        "content_base64": base64.b64encode(content).decode(),
    }).json()
    validation = client.post("/admission/validate", json={
        "artifact_id": artifact["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg"}},
    }).json()
    assert validation["status"] == "REJECTED"
    assert validation["errors"]


def test_admission_incorrect_units(client: TestClient):
    _register_fixture_source(client)
    _register_instrument_protocol(client)
    content = _cmj_csv().encode()
    artifact = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "units.csv",
        "content_base64": base64.b64encode(content).decode(),
    }).json()
    validation = client.post("/admission/validate", json={
        "artifact_id": artifact["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "stones"}},
    }).json()
    assert validation["status"] == "REJECTED"


def test_admission_duplicate_trials(client: TestClient):
    _register_fixture_source(client)
    _register_instrument_protocol(client)
    csv = (
        "subject_id,session_id,trial_id,instrument_id,protocol_id,sampling_hz,week,body_mass_kg,jump_height_cm\n"
        "SUB-1,S-1,T-1,INST-FP-1,PROT-FP-1,1000,1,80,40\n"
        "SUB-2,S-2,T-1,INST-FP-1,PROT-FP-1,1000,1,75,38\n"
    )
    artifact = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "dup.csv",
        "content_base64": base64.b64encode(csv.encode()).decode(),
    }).json()
    validation = client.post("/admission/validate", json={
        "artifact_id": artifact["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg"}},
    }).json()
    assert validation["status"] == "REJECTED"


def test_admission_invalid_sampling(client: TestClient):
    _register_fixture_source(client)
    _register_instrument_protocol(client)
    csv = (
        "subject_id,session_id,trial_id,instrument_id,protocol_id,sampling_hz,week,body_mass_kg,jump_height_cm\n"
        "SUB-1,S-1,T-1,INST-FP-1,PROT-FP-1,0,1,80,40\n"
    )
    artifact = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "samp.csv",
        "content_base64": base64.b64encode(csv.encode()).decode(),
    }).json()
    validation = client.post("/admission/validate", json={
        "artifact_id": artifact["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg"}},
    }).json()
    assert validation["status"] == "REJECTED"


def test_admission_corrupted_file(client: TestClient):
    _register_fixture_source(client)
    artifact = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "corrupt.csv",
        "content_base64": base64.b64encode(b"\x00\xff\xfe not csv").decode(),
    }).json()
    validation = client.post("/admission/validate", json={
        "artifact_id": artifact["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg"}},
    }).json()
    assert validation["status"] == "REJECTED"


def test_admission_idempotency(client: TestClient):
    _register_fixture_source(client)
    _register_instrument_protocol(client)
    content = _cmj_csv().encode()
    a1 = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "idem.csv",
        "content_base64": base64.b64encode(content).decode(),
    }).json()
    a2 = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "idem.csv",
        "content_base64": base64.b64encode(content).decode(),
    }).json()
    assert a1["id"] == a2["id"]
    client.post("/admission/admit", json={
        "artifact_id": a1["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg", "time": "s", "distance": "cm"}},
    })
    rec1 = client.get("/admission/records").json()
    before = len(rec1)
    client.post("/admission/admit", json={
        "artifact_id": a1["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg", "time": "s", "distance": "cm"}},
    })
    after = client.get("/admission/records").json()
    assert len(after) == before


def test_admission_rejected_no_snapshot(client: TestClient):
    _register_fixture_source(client)
    content = b"foo,bar\n1,2\n"
    artifact = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "reject.csv",
        "content_base64": base64.b64encode(content).decode(),
    }).json()
    admitted = client.post("/admission/admit", json={
        "artifact_id": artifact["id"],
        "measurement_family": "CMJ_FORCE_PLATFORM",
        "metadata": {"units": {"body_mass": "kg"}},
    }).json()
    assert admitted["status"] == "REJECTED"
    assert admitted["dataset_snapshot_id"] is None


def test_sprint_modality(client: TestClient):
    _register_fixture_source(client)
    client.post("/admission/instruments", json={
        "id": "INST-TIME-1",
        "measurement_family": "SPRINT_TIMING",
        "manufacturer": "Fixture",
        "model": "Gates",
        "serial_number": "2",
        "calibration_status": "CALIBRATED",
    })
    client.post("/admission/protocols", json={
        "id": "PROT-SPRINT-1",
        "measurement_family": "SPRINT_TIMING",
        "name": "Sprint",
        "version": "1.0",
        "sampling_hz": 1000.0,
        "units": {"distance": "m", "time": "s"},
        "coordinate_convention": "track lane",
    })
    csv = (
        "subject_id,session_id,trial_id,instrument_id,protocol_id,distance_m,time_s\n"
        "SUB-1,S-1,T-1,INST-TIME-1,PROT-SPRINT-1,30,4.2\n"
    )
    artifact = client.post("/admission/artifacts", json={
        "source_id": "SRC-FIXTURE",
        "original_filename": "sprint.csv",
        "content_base64": base64.b64encode(csv.encode()).decode(),
    }).json()
    admitted = client.post("/admission/admit", json={
        "artifact_id": artifact["id"],
        "measurement_family": "SPRINT_TIMING",
        "metadata": {"units": {"distance": "m", "time": "s"}, "coordinate_system": "track"},
    }).json()
    assert admitted["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}


def test_qualification_endpoint(client: TestClient):
    records = client.post("/qualification/run").json()
    assert len(records) == 3
    statuses = {r["id"]: r["status"] for r in records}
    assert statuses["QUAL-CMJ-METRICS"] == "QUALIFIED"
    assert statuses["QUAL-RELIABILITY"] == "QUALIFIED"
    assert statuses["QUAL-LONGITUDINAL"] == "PARTIALLY_QUALIFIED"