from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from dynamis_science import admission, importer
from dynamis_science.desktop.services import DynamisAppService

from test_importer import FIXTURE, HEADER, ROWS, _file


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


def _plan(path, **constants):
    return importer.edit_mapping(importer.probe_file(path), {}, {"session_id": "S1", "sampling_hz": 1000, **constants})


def test_changed_normalization_creates_a_new_snapshot_and_never_overwrites(service, tmp_path):
    path = _file(tmp_path, "m.csv", HEADER + ROWS)
    ctx = importer.build_context(FIXTURE)
    first = importer.admit(importer.stage(_plan(path), ctx))
    snap = Path(admission.get_admitted_snapshot(first["dataset_snapshot_id"])["path"])
    before = {p.name: p.read_bytes() for p in snap.iterdir()}
    # the researcher now says body mass is kg, not g: different normalization of the same raw bytes
    edited = importer.edit_mapping(_plan(path), {"body_mass_kg": {"source": "Body Mass (kg)", "unit": "g"}})
    second = importer.admit(importer.stage(edited, ctx))
    assert second["dataset_snapshot_id"] != first["dataset_snapshot_id"]
    mass = pl.read_parquet(Path(admission.get_admitted_snapshot(second["dataset_snapshot_id"])["path"]) / "cmj_trials.parquet")["body_mass_kg"]
    assert mass.to_list() == pytest.approx([0.08, 0.075])
    assert {p.name: p.read_bytes() for p in snap.iterdir()} == before  # the historical snapshot is untouched


def test_same_artifact_with_different_metadata_is_refused(service, tmp_path):
    path = _file(tmp_path, "m.csv", HEADER + ROWS)
    staged = importer.stage(_plan(path), importer.build_context(FIXTURE))
    importer.admit(staged)
    receipt = staged["receipt"]
    changed = dict(receipt["admission_metadata"], coordinate_system="x-forward")
    with pytest.raises(ValueError, match="immutable snapshot"):
        admission.admit_artifact(receipt["source_artifact_id"], receipt["family"], changed)


def test_source_artifacts_do_not_collide_across_sources_or_names(service, tmp_path):
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    one = importer.stage(_plan(_file(tmp_path / "a", "same.csv", HEADER + ROWS)), importer.build_context(FIXTURE))
    two = importer.stage(_plan(_file(tmp_path / "b", "same.csv", HEADER + ROWS)), importer.build_context({**FIXTURE, "source_name": "Other"}))
    assert one["artifact"]["id"] != two["artifact"]["id"] and one["artifact"]["stored_path"] != two["artifact"]["stored_path"]


def test_same_athlete_ids_in_two_imports_are_never_merged(service, tmp_path):
    ctx = importer.build_context(FIXTURE)
    a = importer.admit(importer.stage(_plan(_file(tmp_path, "one.csv", HEADER + "A1,T1,40,80,1800\n")), ctx))
    b = importer.admit(importer.stage(_plan(_file(tmp_path, "two.csv", HEADER + "A1,T9,41,80,1810\n")), ctx))
    assert a["dataset_snapshot_id"] != b["dataset_snapshot_id"]
    rows = [pl.read_parquet(Path(admission.get_admitted_snapshot(r["dataset_snapshot_id"])["path"]) / "cmj_trials.parquet") for r in (a, b)]
    assert [f.height for f in rows] == [1, 1]


def test_snapshots_and_receipts_persist_across_restart(service, tmp_path, monkeypatch):
    path = _file(tmp_path, "p.csv", HEADER + ROWS)
    record = importer.admit(importer.stage(_plan(path), importer.build_context(FIXTURE)))
    importer.save_preset("Persisted", _plan(path), importer.build_context(FIXTURE))
    reopened = DynamisAppService()  # a new process would build exactly this from the same root
    reopened.ensure_initialized()
    sid = record["dataset_snapshot_id"]
    assert sid in {d["id"] for d in reopened.list_datasets()}
    assert reopened.query_table(sid, "cmj_trials")["total_rows"] == 2
    assert importer.list_receipts()[0]["decision"].startswith("ADMITTED") and importer.match_preset(importer.probe_file(path))
    assert reopened.dataset_inspector(sid)["receipts"]


def test_raw_values_are_not_replaced_by_derived_values(service, tmp_path):
    # peak_force_n is the file's own column; the importer adds no computed metric
    sid = importer.admit(importer.stage(_plan(_file(tmp_path, "r.csv", HEADER + ROWS)), importer.build_context(FIXTURE)))["dataset_snapshot_id"]
    columns = pl.read_parquet(Path(admission.get_admitted_snapshot(sid)["path"]) / "cmj_trials.parquet").columns
    assert set(columns) <= set(admission.CMJ_METRIC_COLUMNS) | set(admission.CMJ_REQUIRED_COLUMNS) | {"week", "source_artifact_id", "_instrument_default"}
