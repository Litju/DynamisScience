from __future__ import annotations

import base64

import openpyxl
import polars as pl
import pytest
from fastapi.testclient import TestClient

from dynamis_science import real_mendeley, real_movesmart, realstore
from dynamis_science.api import app
from dynamis_science.data_root import data_root, paths
from dynamis_science.real_sources import SOURCES


def _write_demo_workbook(path):
    headers = [
        "ID", "COND", "prevspost", "age", "ht", "wt", "sprinttimea", "sprinttimeb", "sprinttimec",
        "isonetpeakforce", "isopeakforce", "isorelativepeakforce", "isoforcea", "isoforceb", "isoforcec",
        "CMJht", "CONmeanforce", "CONphasetime", "meanbrakingforce", "brakingphasetime", "CMdisplacement",
        "RSI", "BS", "BSrel", None,
    ]
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "DATA"
    sheet.append(headers)
    for subject in range(1, 22):
        mass = 70.0 + subject
        height = 175.0 + subject * 0.5
        for occasion in range(1, 5):
            split_a = 1.25 - occasion * 0.005
            split_b = 1.85 - occasion * 0.006
            sheet.append([
                subject, occasion, "pre", 20, height, mass, split_a + split_b, split_a, split_b,
                None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            ])
            if subject in {4, 14} and occasion == 4:
                sheet.append([
                    subject, occasion, "post", 20, height, mass, split_a + split_b, split_a, split_b,
                    2200.0, 3600.0, 3600.0 / mass, 1700.0, 1900.0, 2000.0,
                    None, None, None, None, None, None, None, None, None, None,
                ])
            else:
                jump_m = 0.36 + occasion * 0.012 + subject * 0.001
                sheet.append([
                    subject, occasion, "post", 20, height, mass, split_a + split_b, split_a, split_b,
                    2200.0, 3600.0, 3600.0 / mass, 1700.0, 1900.0, 2000.0,
                    jump_m, 1800.0, 0.22, 1500.0, 0.14, -0.25, 2.4, 100.0, 100.0 / mass, None,
                ])
    workbook.save(path)


@pytest.fixture
def temp_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path))
    return tmp_path


def test_source_assessments_separate_rights_from_admissibility():
    assert len(SOURCES) == 2
    for source in SOURCES:
        assert source["rights_status"] == "VERIFIED"
        assert source["license"]["url"].startswith("https://creativecommons.org/")
        assert source["scientific_admissibility"]["status"] == "ADMISSIBLE_WITH_LIMITATIONS"
        assert source["privacy"]["classification"] in {"PSEUDONYMOUS", "ANONYMOUS"}


def test_mendeley_adapter_preserves_native_and_canonical_values(temp_root):
    path = temp_root / "DATA.xlsx"
    _write_demo_workbook(path)
    tables = real_mendeley.build_tables(path)
    assert tables["measurements_long"].height == 168
    assert tables["cmj_occasions"].height == 82
    assert tables["subjects"].height == 21
    assert tables["sprint_trials"].height == 168
    row = tables["measurements_long"].filter(pl.col("trial_id") == "MEN-01-O1-POST").row(0, named=True)
    assert row["cmj_height_m"] is not None
    assert round(row["cmj_height_cm"], 6) == round(row["cmj_height_m"] * 100, 6)
    sprint_row = tables["sprint_trials"].filter(pl.col("trial_id") == "MEN-01-O1-POST").row(0, named=True)
    assert abs(sprint_row["sprint_split_residual_s"]) < 1e-12
    assessment = real_mendeley.assess(tables, path)
    assert assessment["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
    assert assessment["counts"]["subjects"] == 21
    snapshot = real_mendeley.write_snapshot(tables, assessment)
    snapshot_dir = paths()["snapshots"] / snapshot["id"]
    assert (snapshot_dir / "provenance_manifest.json").exists()
    assert (snapshot_dir / "measurements_long.parquet").exists()
    assert snapshot_dir.is_relative_to(temp_root.resolve())


def test_movesmart_snapshot_writer_uses_private_root(temp_root):
    tables = {
        "subjects": pl.DataFrame({"subject_id": ["SYNTHETIC-01"]}),
        "signal_trials": pl.DataFrame({"trial_id": ["SYNTHETIC-TRIAL"], "fz_peak_n": [1200.0]}),
    }
    assessment = {
        "status": "ADMITTED_WITH_WARNINGS",
        "source_path": "synthetic-movesmart-fixture.zip",
        "source_sha256": "a" * 64,
        "source_size_bytes": 1,
        "checks": [{"check": "fixture", "status": "PASS"}],
        "warnings": [],
    }

    snapshot = real_movesmart.write_snapshot(tables, assessment)
    snapshot_dir = paths()["snapshots"] / snapshot["id"]
    assert (snapshot_dir / "provenance_manifest.json").exists()
    assert (snapshot_dir / "signal_trials.parquet").exists()
    assert snapshot_dir.is_relative_to(temp_root.resolve())


def test_snapshot_is_immutable_and_idempotent(temp_root):
    path = temp_root / "DATA.xlsx"
    _write_demo_workbook(path)
    tables = real_mendeley.build_tables(path)
    assessment = real_mendeley.assess(tables, path)
    first = real_mendeley.write_snapshot(tables, assessment)
    second = real_mendeley.write_snapshot(tables, assessment)
    assert first["id"] == second["id"]
    snapshot_dir = temp_root / "snapshots" / first["id"]
    assert (snapshot_dir / "snapshot.json").exists()
    assert (snapshot_dir / "provenance_manifest.json").exists()
    assert (snapshot_dir / "immutable.json").exists()
    changed = {name: frame.head(10) for name, frame in tables.items()}
    with pytest.raises(realstore.SnapshotConflictError):
        realstore.register_snapshot(
            snapshot_id=first["id"],
            source_id="SRC-MENDELEY-6P99569X66",
            label="changed",
            tables=changed,
            row_counts={name: frame.height for name, frame in changed.items()},
            parser_version="test",
            schema_version="test",
            assessment=assessment,
            metric_definitions=[],
        )


def test_real_endpoints_are_separate_from_synthetic(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path))
    with TestClient(app) as client:
        studies = client.get("/studies").json()
        assert [study["id"] for study in studies] == ["STUDY-001"]
        sources = client.get("/real/sources").json()
        assert len(sources) == 2
        assert all(source["admitted"] is False for source in sources)
        datasets = client.get("/datasets").json()
        assert len(datasets) == 1
        assert datasets[0]["synthetic"] is True


def test_qualification_records_are_real_data_only_when_present(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path))
    assert data_root() == tmp_path
    with TestClient(app) as client:
        assert client.get("/real/qualification").json() == []
