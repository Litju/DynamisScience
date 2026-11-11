from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl
import pytest

from dynamis_science import admission, importer
from dynamis_science.desktop.services import DynamisAppService

FIXTURE = {"source_name": "Fixture lab", "publisher": "DynamisScience tests", "dataset_identity": "fixture-import",
           "license_or_agreement": "Internal fixture only", "redistribution_restrictions": "Fixture only",
           "privacy_status": "TEST_FIXTURE", "manufacturer": "Fixture", "model": "FP", "serial_number": "1",
           "protocol_name": "Fixture CMJ", "protocol_version": "1.0"}
HEADER = "Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N)\n"
ROWS = "A1,T1,40.0,80,1800\nA2,T2,38.5,75,1700\n"


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


def _file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode())
    return path


def _ready(path: Path, **constants):
    plan = importer.probe_file(path)
    return importer.edit_mapping(plan, {}, {"session_id": "S1", "sampling_hz": 1000, **constants})


def test_detects_headers_units_and_family(tmp_path):
    plan = importer.probe_file(_file(tmp_path, "a.csv", HEADER + ROWS))
    cols = plan["mapping"]["columns"]
    assert plan["mapping"]["family"] == "CMJ_FORCE_PLATFORM"
    assert cols["subject_id"]["source"] == "Athlete" and cols["jump_height_cm"]["unit"] == "cm"
    assert plan["state"] == "REVIEW"  # session and sampling rate are never assumed
    assert any("session_id" in n for n in plan["needs"]) and any("sampling_hz" in n for n in plan["needs"])


def test_bom_semicolon_and_unknown_unit_review(tmp_path):
    text = "﻿Athlete;Trial;Jump Height;Body Mass (stone)\nA1;T1;40;12\n"
    plan = importer.probe_file(_file(tmp_path, "b.csv", text))
    assert plan["delimiter"] == ";" and plan["rows"] == 1
    assert "body_mass_kg" not in plan["mapping"]["columns"]
    assert any("unit is not stated" in a for a in plan["ambiguities"])
    assert any("stone" in a for a in plan["ambiguities"])


@pytest.mark.parametrize("name,content,why", [("empty.csv", "", "empty"), ("x.xlsx", "x", "Unsupported"),
                                              ("dup.csv", "a,a\n1,2\n", "Duplicate")])
def test_unreadable_inputs_are_unsupported(tmp_path, name, content, why):
    plan = importer.probe_file(_file(tmp_path, name, content))
    assert plan["state"] == "UNSUPPORTED" and why in plan["reason"]


def test_ambiguous_duplicate_target_columns_not_guessed(tmp_path):
    plan = importer.probe_file(_file(tmp_path, "c.csv", "Athlete,Trial,Jump Height (cm),jump_height_cm\nA,1,1,2\n"))
    assert "jump_height_cm" not in plan["mapping"]["columns"]
    assert any("several columns match" in a for a in plan["ambiguities"])


def test_import_csv_admits_synthetic_only_and_unit_converts(service, tmp_path):
    text = "Athlete,Trial,Jump Height (m),Body Mass (g)\nA1,T1,0.4,80000\nA2,T2,0.385,75000\n"
    path = _file(tmp_path, "d.csv", text)
    plan = _ready(path)
    staged = importer.stage(plan, importer.build_context(FIXTURE))
    assert staged["eligible"] and staged["synthetic_only"], staged["quality"]
    record = importer.admit(staged)
    assert record["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
    assert record["admission_class"] == "SYNTHETIC_ONLY"
    snap = admission.get_admitted_snapshot(record["dataset_snapshot_id"])
    table = pl.read_parquet(Path(snap["path"]) / "cmj_trials.parquet")
    assert table["jump_height_cm"].to_list() == pytest.approx([40.0, 38.5])
    assert table["body_mass_kg"].to_list() == pytest.approx([80.0, 75.0])
    assert snap["synthetic"] and not snap["real_data"]
    receipt = importer.list_receipts()[0]
    assert receipt["raw_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert Path(receipt["raw_copy"]).read_bytes() == text.encode()  # original preserved apart from the snapshot
    assert snap["admission_metadata"]["import"]["raw_sha256"] == receipt["raw_sha256"]


def test_import_parquet_and_workbench_visibility(service, tmp_path):
    path = tmp_path / "e.parquet"
    pl.DataFrame({"subject_id": ["001", "002"], "session_id": ["S", "S"], "trial_id": ["a", "b"], "sampling_hz": [1000.0, 1000.0],
                  "jump_height_cm": [30.0, 31.0]}).write_parquet(path)
    staged = importer.stage(_ready(path), importer.build_context(FIXTURE))
    record = importer.admit(staged)
    sid = record["dataset_snapshot_id"]
    assert sid in {d["id"] for d in service.list_datasets()}  # visible to the existing workbench catalogue
    detail = service.get_dataset_detail(sid)
    page = service.read_table_page(sid, detail["tables"][0]["name"])
    assert page["total_rows"] == 2 and page["rows"][0]["subject_id"] == "001"
    frame = pl.read_parquet(Path(admission.get_admitted_snapshot(record["dataset_snapshot_id"])["path"]) / "cmj_trials.parquet")
    assert frame["subject_id"].to_list() == ["001", "002"]  # identifiers are not coerced to numbers


def test_idempotent_and_duplicate_protection(service, tmp_path):
    ctx = importer.build_context(FIXTURE)
    first = importer.stage(_ready(_file(tmp_path, "f.csv", HEADER + ROWS)), ctx)
    rec1 = importer.admit(first)
    again = importer.stage(_ready(tmp_path / "f.csv"), ctx)
    assert importer.admit(again)["id"] == rec1["id"]
    assert len(admission.list_admitted_snapshots()) == 1 and len(importer.list_receipts()) == 1
    copy = importer.stage(_ready(_file(tmp_path, "renamed.csv", HEADER + ROWS)), ctx)
    assert copy["duplicate_of"] and not copy["eligible"]
    with pytest.raises(importer.ImportBlocked, match="duplicates"):
        importer.admit(copy)


def test_same_basename_in_different_sources_do_not_collide(service, tmp_path):
    (tmp_path / "x").mkdir(), (tmp_path / "y").mkdir()
    a = importer.stage(_ready(_file(tmp_path / "x", "same.csv", HEADER + ROWS)), importer.build_context(FIXTURE))
    b = importer.stage(_ready(_file(tmp_path / "y", "same.csv", HEADER + ROWS)),
                       importer.build_context({**FIXTURE, "source_name": "Other lab"}))
    assert importer.admit(a)["dataset_snapshot_id"] != importer.admit(b)["dataset_snapshot_id"]


def test_invalid_data_is_rejected_and_quarantined_without_snapshot(service, tmp_path):
    bad = _file(tmp_path, "bad.csv", "Athlete,Trial,Jump Height (cm)\nA1,T1,400\nA2,T1,38\n")
    staged = importer.stage(_ready(bad), importer.build_context(FIXTURE))
    assert not staged["eligible"] and staged["quality"]["status"] == "REJECTED"
    result = importer.quarantine(staged, "duplicate trial ids")
    assert Path(result["quarantine_path"]).read_bytes() == bad.read_bytes()
    assert result["admission_record"]["status"] == "REJECTED" and not admission.list_admitted_snapshots()
    assert importer.list_receipts()[0]["decision"] == "QUARANTINED"


def test_real_claim_needs_rights_and_calibration(service, tmp_path):
    real = {**FIXTURE, "privacy_status": "DEIDENTIFIED", "source_name": "Real lab"}
    path = _file(tmp_path, "r.csv", HEADER + ROWS)
    unreviewed = importer.stage(_ready(path), importer.build_context(real))
    assert not unreviewed["eligible"] and unreviewed["rights_status"] == "UNVERIFIED"
    uncalibrated = importer.stage(_ready(path), importer.build_context(real), rights_reviewed_by="tester")
    assert uncalibrated["rights_status"] == "VERIFIED" and uncalibrated["quality"]["status"] == "QUARANTINED"
    assert not uncalibrated["eligible"]
    calibrated = importer.stage(_ready(path), importer.build_context({**real, "calibration_status": "CALIBRATED"}),
                                rights_reviewed_by="tester")
    assert calibrated["eligible"] and not calibrated["synthetic_only"]
    assert "admission_class" not in importer.admit(calibrated)


def test_registered_records_are_never_silently_changed(service, tmp_path):
    path = _file(tmp_path, "g.csv", HEADER + ROWS)
    importer.stage(_ready(path), importer.build_context(FIXTURE))
    changed = importer.build_context({**FIXTURE, "license_or_agreement": "Different licence"})
    with pytest.raises(importer.ImportBlocked, match="different license_or_agreement"):
        importer.stage(_ready(path), changed)


def test_preset_reuse_and_schema_drift(service, tmp_path):
    ctx = importer.build_context(FIXTURE)
    first = _ready(_file(tmp_path, "p1.csv", HEADER + ROWS))
    preset = importer.save_preset("Lab CMJ export", first, ctx)
    assert importer.save_preset("Lab CMJ export", first, ctx)["version"] == 2
    second = _file(tmp_path, "p2.csv", HEADER + "B1,T9,41,70,1500\n")
    assert importer.match_preset(importer.probe_file(second))["version"] == 2
    staged = importer.import_with_preset(second, preset)
    assert staged["eligible"]
    drifted = _file(tmp_path, "p3.csv", HEADER.replace("(cm)", "(m)").replace("Peak Force (N)", "Peak Force (kN)") + "B1,T9,0.4,70,1.5\n")
    plan = importer.probe_file(drifted)
    assert importer.match_preset(plan) is None  # a unit change in a header is drift, never silent reuse
    assert importer.schema_drift(plan)["missing_columns"] == ["Jump Height (cm)", "Peak Force (N)"]
    renamed = _file(tmp_path, "p4.csv", HEADER.replace("Athlete", "Participant ID") + ROWS)
    with pytest.raises(importer.ImportBlocked, match="Schema differs"):
        importer.import_with_preset(renamed, preset)
    assert importer.match_preset(importer.probe_file(renamed)) is None
    assert importer.schema_drift(importer.probe_file(renamed))["missing_columns"] == ["Athlete"]


def test_folder_import_is_bounded_and_skips_links(service, tmp_path, monkeypatch):
    folder = tmp_path / "batch"
    folder.mkdir()
    for i in range(3):
        _file(folder, f"f{i}.csv", HEADER + f"A{i},T{i},4{i},80,1800\n")
    _file(folder, "notes.txt", "ignore")
    outside = _file(tmp_path, "outside.csv", HEADER + ROWS)
    try:
        (folder / "link.csv").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    monkeypatch.setattr(importer, "MAX_FILES", 2)
    result = importer.probe(folder)
    assert [p["name"] for p in result["files"]] == ["f0.csv", "f1.csv"]
    reasons = {s["name"]: s["reason"] for s in result["skipped"]}
    assert "symbolic link" in reasons["link.csv"] and "batches" in reasons["f2.csv"]


def test_file_changed_after_review_is_refused(service, tmp_path):
    path = _file(tmp_path, "h.csv", HEADER + ROWS)
    plan = _ready(path)
    path.write_bytes((HEADER + ROWS + "A3,T3,1,1,1\n").encode())
    with pytest.raises(importer.ImportBlocked, match="changed"):
        importer.stage(plan, importer.build_context(FIXTURE))


def test_blank_lines_are_not_records(tmp_path):
    plan = importer.probe_file(_file(tmp_path, "blank.csv", HEADER + ROWS + "\n\n"))
    assert plan["rows"] == 2
