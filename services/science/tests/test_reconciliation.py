from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from dynamis_science import admission, importer, reconciliation as reconcile, researchstore as store
from dynamis_science.desktop.services import DynamisAppService
from test_importer import FIXTURE


FIELDS = ["Athlete", "Session", "Trial", "week", "Sampling Frequency (Hz)",
          "Jump Height (cm)", "Body Mass (kg)", "Peak Force (N)"]
FOLLOWUP_FIELDS = ["Player", "Test Session", "Trial", "week", "Sampling Frequency (Hz)",
                   "Jump Height (mm)", "Body Mass (kg)", "Peak Force (N)", "Export tag"]
ACTOR = {"reviewer": "Fixture researcher", "reason": "Verified against the synthetic testing log."}


def write_export(path, rows, fields=FIELDS):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)
    return path


def baseline_rows():
    return [[f"A{i:02d}", "Baseline", f"B{i:02d}", 1, 1000, 30 + i / 2, 72 + i, 1600 + i]
            for i in range(1, 21)]


def followup_rows():
    return [["A07-renamed" if i == 7 else f"A{i:02d}", "Week 12 export", f"F{i:02d}", 12, 1000,
             320 + 5 * i, 72 + i, 1650 + i, "v2"] for i in range(1, 21)]


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    service.ensure_initialized()
    entity = service.create_workspace("RES-722 synthetic cohort")["study"]["id"]
    original = write_export(tmp_path / "baseline.csv", baseline_rows())
    staged = importer.stage(importer.probe_file(original), importer.build_context(FIXTURE))
    baseline_id = importer.admit(staged)["dataset_snapshot_id"]
    first = service.attach_workspace_data(entity, baseline_id)
    return service, entity, original, first


def revise(entry, **kwargs):
    return reconcile.revise(entry["workspace_id"], entry["id"], entry["version"], **kwargs)


def decide(entry, action):
    return reconcile.decide(entry["workspace_id"], entry["id"], entry["version"], action, **ACTOR)


def declaration(entry):
    return {key: entry["context"][key] for key in reconcile.CONTEXT_FIELDS}


def kinds(entry):
    return {item["kind"] for item in entry["discrepancies"]}


def test_reconcile_followup_correction_reopen_and_run(setup, tmp_path):
    service, workspace, original, first = setup
    baseline = first["snapshot"]
    original_parquet = Path(baseline["path"]) / "cmj_trials.parquet"
    original_bytes = original_parquet.read_bytes()
    run_spec = {"method_id": "METH-U-DESC", "outcome_metric_id": "MET-CMJ-HEIGHT", "parameters": {}}
    initial = service.execute_analysis_run(workspace, {**run_spec, "data_revision_id": first["active_data_revision_id"]})
    assert initial["status"] == "COMPLETED"
    original_report = service.export_workspace_report(workspace, initial["id"], str(tmp_path / "original.html"))
    frozen_bytes = original_report.read_bytes()
    frozen_version = store.get_report_version(workspace, 1)
    duplicate_path = tmp_path / "renamed_duplicate.csv"
    duplicate_path.write_bytes(original.read_bytes())
    duplicate = reconcile.propose(workspace, duplicate_path)
    assert "duplicate_file" in kinds(duplicate) and not duplicate["ready"]
    assert decide(duplicate, "REJECTED")["decision"]["proposal_version"] == 1
    rows = followup_rows()
    rows.extend([["A01", "Initial amended", "B01", 1, 1000, 310, 73, 1601, "v2"],
                 ["A02", "Initial amended", "B02", 1, 1000, 310, 74, 1602, "v2"]])
    followup = write_export(tmp_path / "followup.csv", rows, FOLLOWUP_FIELDS)
    proposed = reconcile.propose(workspace, followup)
    assert {"source_schema", "unit_change", "athlete_identity", "session_identity"} <= kinds(proposed)
    assert not proposed["ready"]
    with pytest.raises(importer.ImportBlocked, match="Approval requires"):
        decide(proposed, "APPROVED")
    mapped = revise(proposed, athletes={"A07-renamed": "A07"},
                    sessions={"Initial amended": "Baseline", "Week 12 export": "Follow-up"},
                    declared=declaration(proposed))
    assert mapped["ready"], mapped["discrepancies"]
    assert mapped["counts"] == {"new": 20, "duplicate": 1, "correction": 1}
    assert mapped["corrections"] == ["B01"]
    approved = decide(mapped, "APPROVED")
    assert approved["version"] == 3 and approved["decision"]["proposal_version"] == 2
    reopened = DynamisAppService().get_study_detail(workspace)
    revision_id = reopened["active_data_revision_id"]
    assert revision_id == approved["decision"]["revision_id"]
    assert reopened["data_revisions"][-1]["mode"] == "CORRECTION"
    assert reopened["data_revisions"][-1]["reconciliation"]["id"] == approved["id"]
    frame = store.read_snapshot_table(reopened["snapshot"]["id"], "cmj_trials")
    assert frame.height == 40 and frame["subject_id"].n_unique() == 20
    assert frame.filter(pl.col("trial_id") == "F07").select("subject_id", "session_id", "jump_height_cm").row(0) == ("A07", "Follow-up", 35.5)
    assert frame.filter(pl.col("trial_id") == "B01")["jump_height_cm"][0] == 31
    assert original_parquet.read_bytes() == original_bytes
    assert original_report.read_bytes() == frozen_bytes
    assert store.get_report_version(workspace, 1) == frozen_version
    assert Path(approved["raw_path"]).read_bytes() == followup.read_bytes()
    replay = reconcile.propose(workspace, followup)
    assert replay["repeat_file"] and replay["decision"] == approved["decision"]
    assert len(store.data_revisions(workspace)) == 2
    assert [event["version"] for event in reconcile.history(workspace) if event["id"] == approved["id"]] == [3, 2, 1]
    result = DynamisAppService().execute_analysis_run(workspace, {**run_spec, "data_revision_id": revision_id})
    assert result["status"] == "COMPLETED" and result["data_revision_id"] == revision_id
    process = subprocess.run([sys.executable, "-c", """
import json, sys
from dynamis_science import reconciliation, researchstore
workspace = sys.argv[1]
print(json.dumps([researchstore.get_entity(workspace)["active_data_revision_id"],
                  reconciliation.history(workspace)[0]["state"]]))
""", workspace], capture_output=True, text=True, check=True, timeout=25)
    assert json.loads(process.stdout) == [revision_id, "APPROVED"]
    with sqlite3.connect(store._db_path()) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_blocks_cross_athlete_session_and_acquisition_conflicts(setup, tmp_path):
    _, workspace, _, first = setup
    followup = write_export(tmp_path / "trial.csv", followup_rows(), FOLLOWUP_FIELDS)
    proposed = reconcile.propose(workspace, followup)
    wrong = revise(proposed, athletes={"A07-renamed": "A08"}, sessions={"Week 12 export": "Follow-up"},
                   declared=declaration(proposed))
    assert "athlete_conflict" in kinds(wrong)
    with pytest.raises(store.ResearchConflict):
        decide(proposed, "REJECTED")
    wrong_session = revise(wrong, athletes={"A07-renamed": "A07"}, sessions={"Week 12 export": "Baseline"})
    assert "session_time_conflict" in kinds(wrong_session)
    crossed = followup_rows()
    crossed[0][2] = "B02"
    crossed[0][1], crossed[0][3] = "Initial amended", 1
    conflict = reconcile.propose(workspace, write_export(tmp_path / "cross.csv", crossed, FOLLOWUP_FIELDS))
    mapped = revise(conflict, athletes={"A07-renamed": "A07"}, declared=declaration(conflict),
                    sessions={"Initial amended": "Baseline", "Week 12 export": "Follow-up"})
    assert "trial_identity_conflict" in kinds(mapped)
    drift = followup_rows()
    drift[0][4] = 500
    drift[1][4] = 500
    altered = reconcile.propose(workspace, write_export(tmp_path / "protocol.csv", [row + ["OTHER-PROTOCOL"] for row in drift],
                                                       FOLLOWUP_FIELDS + ["Protocol"]))
    assert {"protocol_drift", "timebase_drift"} <= kinds(altered)
    assert decide(altered, "QUARANTINED")["state"] == "QUARANTINED"
    assert store.get_entity(workspace)["active_data_revision_id"] == first["active_data_revision_id"]
    assert len(admission.list_admitted_snapshots()) == 1


def test_units_rights_tamper_and_malformed_source_fail_closed(setup, tmp_path):
    _, workspace, _, first = setup
    bad = tmp_path / "invalid.csv"
    bad.write_bytes(b"Athlete,Athlete\nA1,A2\n")
    unreadable = reconcile.propose(workspace, bad)
    assert "unreadable" in kinds(unreadable)
    assert Path(unreadable["raw_path"]).read_bytes() == bad.read_bytes()
    assert decide(unreadable, "REJECTED")["state"] == "REJECTED"

    rows = followup_rows()
    path = write_export(tmp_path / "units.csv", rows, FOLLOWUP_FIELDS)
    item = reconcile.propose(workspace, path)
    mismatch = revise(item, edits={"jump_height_cm": {"source": "Jump Height (mm)", "unit": "cm"}})
    assert "unit_conflict" in kinds(mismatch)
    row = revise(mismatch, edits={"jump_height_cm": {"source": "Jump Height (mm)", "unit": "mm"}},
                 athletes={"A07-renamed": "A07"}, sessions={"Week 12 export": "Follow-up"}, declared=declaration(item))
    assert row["ready"]
    raw = Path(row["raw_path"])
    intact = raw.read_bytes()
    raw.write_text("tampered", encoding="utf-8")
    with pytest.raises(importer.ImportBlocked, match="checksum"):
        decide(row, "APPROVED")
    raw.write_bytes(intact)

    source_path = admission._artifact_path("admission_sources.json")
    sources = admission._load_list(source_path)
    source_id = first["snapshot"]["source"]["id"]
    # Check eligibility against current rights at approval time.
    admission._save_list(source_path, [{**value, "rights_status": "UNVERIFIED"} if value["id"] == source_id else value
                                       for value in sources])
    with pytest.raises(importer.ImportBlocked, match="rights"):
        decide(row, "APPROVED")
    assert len(admission.list_admitted_snapshots()) == 1


def test_additive_migration_and_failed_approval_can_retry(setup, tmp_path, monkeypatch):
    service, workspace, _, first = setup
    with store._connect() as connection:
        connection.execute("DROP TABLE reconciliation_events")
        connection.execute("PRAGMA user_version=2")
    assert reconcile.history(workspace) == []
    assert service.get_study_detail(workspace)["active_data_revision_id"] == first["active_data_revision_id"]
    path = write_export(tmp_path / "followup.csv", followup_rows(), FOLLOWUP_FIELDS)
    entry = reconcile.propose(workspace, path)
    ready = revise(entry, athletes={"A07-renamed": "A07"}, sessions={"Week 12 export": "Follow-up"},
                   declared=declaration(entry))
    attach = store.attach_workspace_data

    def fail(*args, **kwargs):
        attach(*args, **kwargs)
        raise RuntimeError("Injected decision write failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "attach_workspace_data", fail)
        with pytest.raises(RuntimeError, match="decision write failure"):
            decide(ready, "APPROVED")
    from dynamis_science.data_root import paths
    assert list((paths()["research"] / "data").iterdir()) == []
    assert reconcile.history(workspace)[0] == ready
    assert len(store.data_revisions(workspace)) == 1
    mapped_id = next(row["dataset_snapshot_id"] for row in admission.list_admission_records()
                     if row.get("dataset_snapshot_id") and row["dataset_snapshot_id"] != first["snapshot"]["id"])
    assert admission.get_admitted_snapshot(mapped_id) is None
    other = service.create_workspace("Other workspace")["study"]["id"]
    with pytest.raises(store.ResearchValidation, match="admitted input"):
        service.attach_workspace_data(other, mapped_id)
    approved = decide(ready, "APPROVED")
    assert len(admission.list_admitted_snapshots()) == 2
    assert len(store.data_revisions(workspace)) == 2
    assert len(list((paths()["research"] / "data").iterdir())) == 1

    later = followup_rows()[6]
    later[1:4] = ["Other visit", "L07", 13]
    next_file = write_export(tmp_path / "alias.csv", [later], FOLLOWUP_FIELDS)
    next_proposal = reconcile.propose(workspace, next_file)
    assert next_proposal["identity_preview"]["athletes"] == [
        {"source": "A07-renamed", "target": "A07", "bound": True, "confirmed": False}]
    bad = revise(next_proposal, athletes={"A07-renamed": "A08"},
                 sessions={"Other visit": "Other visit"}, declared=declaration(next_proposal))
    assert "athlete_conflict" in kinds(bad)
    assert reconcile.propose(workspace, path)["decision"] == approved["decision"]


def test_approved_mapping_cannot_seed_another_workspace(setup, tmp_path):
    service, workspace, _, _ = setup
    path = write_export(tmp_path / "mapped.csv", followup_rows(), FOLLOWUP_FIELDS)
    entry = reconcile.propose(workspace, path)
    approved = decide(revise(entry, athletes={"A07-renamed": "A07"},
                             sessions={"Week 12 export": "Follow-up"},
                             declared=declaration(entry)), "APPROVED")
    other = service.create_workspace("Unrelated IDs")["study"]["id"]
    assert store.get_snapshot(approved["decision"]["snapshot_id"])
    with pytest.raises(store.ResearchValidation, match="workspace-bound"):
        service.attach_workspace_data(other, approved["decision"]["snapshot_id"])
    assert store.data_revisions(other) == []


def test_source_conflict_and_semantic_duplicate(setup, tmp_path):
    _, workspace, _, _ = setup
    baseline = baseline_rows()
    baseline[0][5] = 33.3
    other = write_export(tmp_path / "other_source.csv", baseline)
    alternate = importer.build_context({**FIXTURE, "source_name": "Unrelated lab"})
    assert importer.stage(importer.probe_file(other), alternate)["eligible"]
    assert "source_conflict" in kinds(reconcile.propose(workspace, other))

    rows = [[athlete, session, trial, week, hz, int(height * 10), mass, force, "reformatted"]
            for athlete, session, trial, week, hz, height, mass, force in baseline_rows()]
    file = write_export(tmp_path / "different_bytes.csv", rows, FOLLOWUP_FIELDS)
    entry = reconcile.propose(workspace, file)
    assert "duplicate_measurements" in kinds(entry)
    assert entry["counts"] == {"new": 0, "correction": 0, "duplicate": 20}
    assert not entry["ready"]
    assert not reconcile._changed("jump_height_cm", 33.3, 333 * 0.1)


def test_source_ids_keep_csv_leading_zeroes(tmp_path):
    rows = [["01", "01", "01", 1, 1000, 31, 72, 1600],
            ["1", "1", "1", 1, 1000, 32, 73, 1601]]
    path = write_export(tmp_path / "leading_zeroes.csv", rows)
    data = importer.read_summary(importer.probe_file(path))
    assert data.select("subject_id", "session_id", "trial_id").rows() == [("01", "01", "01"), ("1", "1", "1")]


def test_mixed_row_units_and_ignored_timebase_cannot_be_overridden(setup, tmp_path):
    _, workspace, _, _ = setup
    units = [row + ["cm" if index == 1 else "mm"] for index, row in enumerate(followup_rows())]
    file = write_export(tmp_path / "different_row_units.csv", units, FOLLOWUP_FIELDS + ["Jump Height Unit"])
    assert "unit_conflict" in kinds(reconcile.propose(workspace, file))
    rows = followup_rows()
    for row in rows:
        row[4] = 500
    rate = reconcile.propose(workspace, write_export(tmp_path / "sample_rate.csv", rows, FOLLOWUP_FIELDS))
    override = revise(rate, edits={"sampling_hz": None}, constants={"sampling_hz": 1000})
    assert "timebase_drift" in kinds(override)
    assert not override["ready"]


@pytest.mark.parametrize("suffix", [".xlsx", ".parquet"])
def test_reconcile_existing_excel_and_parquet_support(setup, tmp_path, suffix):
    _, workspace, _, _ = setup
    source = tmp_path / ("followup" + suffix)
    rows = followup_rows()
    if suffix == ".xlsx":
        from openpyxl import Workbook

        workbook = Workbook()
        for row in [FOLLOWUP_FIELDS, *rows]:
            workbook.active.append(row)
        workbook.save(source)
    else:
        pl.DataFrame(rows, schema=FOLLOWUP_FIELDS, orient="row").write_parquet(source)
    entry = reconcile.propose(workspace, source)
    mapped = revise(entry, athletes={"A07-renamed": "A07"}, sessions={"Week 12 export": "Follow-up"},
                    declared=declaration(entry))
    assert mapped["ready"], mapped["discrepancies"]
    assert Path(mapped["raw_path"]).read_bytes() == source.read_bytes()
    assert decide(mapped, "APPROVED")["state"] == "APPROVED"


def test_cannot_reuse_a_session_id_for_a_different_date(setup, tmp_path):
    service, workspace, _, first = setup
    recorded = write_export(tmp_path / "dated.csv", [row + ["2026-10-01"] for row in baseline_rows()], FIELDS + ["date"])
    staged = importer.stage(importer.probe_file(recorded), importer.build_context(FIXTURE))
    snapshot = importer.admit(staged)["dataset_snapshot_id"]
    service.attach_workspace_data(workspace, snapshot, base_revision=first["active_data_revision_id"])
    row = ["A01", "Baseline", "NEW-TRIAL", 1, 1000, 31, 73, 1601, "2026-10-02"]
    path = write_export(tmp_path / "new-date.csv", [row], FIELDS + ["date"])
    proposal = reconcile.propose(workspace, path)
    assert "session_date_conflict" in kinds(proposal)
    assert not proposal["ready"]


def test_recorded_sessions_cannot_be_replaced_with_a_constant(setup, tmp_path):
    _, workspace, _, _ = setup
    rows = [["A01", visit, f"V{index}", 12, 1000, 35, 73, 1700]
            for index, visit in enumerate(("Visit A", "Visit B"))]
    entry = reconcile.propose(workspace, write_export(tmp_path / "two-visits.csv", rows))
    mapped = revise(entry, edits={"session_id": None}, constants={"session_id": "Merged"},
                    sessions={"Merged": "Merged"}, declared=declaration(entry))
    assert "session_identity" in kinds(mapped)
    assert not mapped["ready"]


def test_approval_verifies_retained_reference_export(setup, tmp_path):
    _, workspace, _, first = setup
    rows = [["A01", "Follow-up", "F01", 12, 1000, 35, 73, 1700]]
    entry = reconcile.propose(workspace, write_export(tmp_path / "followup.csv", rows))
    mapped = revise(entry, sessions={"Follow-up": "Follow-up"}, declared=declaration(entry))
    assert mapped["ready"]
    artifact = first["snapshot"]["admission"]["source_artifact_id"]
    receipt = next(row for row in importer.list_receipts() if row["source_artifact_id"] == artifact)
    Path(receipt["raw_copy"]).write_bytes(b"Corrupt retained reference")
    with pytest.raises(importer.ImportBlocked, match="Retained reference export.*checksum"):
        decide(mapped, "APPROVED")


def test_excel_date_is_preserved_and_legacy_cache_is_ignored(setup, tmp_path):
    from openpyxl import Workbook

    from dynamis_science.data_root import paths

    service, workspace, _, first = setup
    fields = FIELDS + ["Date"]
    original = write_export(tmp_path / "dated-baseline.csv", [r + ["2026-09-01"] for r in baseline_rows()], fields)
    staged = importer.stage(importer.probe_file(original), importer.build_context(FIXTURE))
    service.attach_workspace_data(workspace, importer.admit(staged)["dataset_snapshot_id"],
                                  base_revision=first["active_data_revision_id"])
    source = tmp_path / "followup.xlsx"
    rows = [["A01", "Visit A", "F01", 12, 1000, 35, 73, 1700, date(2026, 11, 17)]]
    workbook = Workbook()
    for row in [fields, *rows]:
        workbook.active.append(row)
    workbook.save(source)
    workbook.close()
    entry = reconcile.propose(workspace, source)
    retained = Path(entry["raw_path"])
    digest = hashlib.sha256(
        f"{retained.resolve()}|{retained.stat().st_size}|{retained.stat().st_mtime_ns}".encode()
    ).hexdigest()[:16]
    legacy_cache = paths()["tmp"] / "converted" / f"{digest}.parquet"
    legacy_cache.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame([rows[0][:5] + [49] + rows[0][6:]], schema=fields, orient="row").write_parquet(legacy_cache)
    mapped = revise(entry, sessions={"Visit A": "Visit A"}, declared=declaration(entry))
    assert mapped["ready"], mapped["discrepancies"]
    approved = decide(mapped, "APPROVED")
    result = store.read_snapshot_table(approved["decision"]["revision_id"], "cmj_trials")
    assert result.filter(pl.col("trial_id") == "F01").select("jump_height_cm", "date").row(0) == (35.0, "2026-11-17")
