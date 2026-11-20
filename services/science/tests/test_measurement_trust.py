from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from statistics import mean, stdev

import polars as pl
import pytest

from dynamis_science import admission, importer, measurement_trust as trust, reconciliation, researchstore as store
from dynamis_science.desktop.services import DynamisAppService
from test_reconciliation import FIELDS, FIXTURE, declaration, decide, revise, write_export

DATES = ["2026-08-01", "2026-08-08", "2026-08-15", "2026-08-22", "2026-09-01"]
SESSIONS = ["Retest first", "Retest second", "Reference", "Assessment", "Sparse"]
DATED_FIELDS = FIELDS + ["Date"]
RETEST = {
    "first_session": SESSIONS[0], "second_session": SESSIONS[1], "reviewer": "Fixture researcher",
    "population": "Synthetic roster under the same acquisition conditions",
    "design_evidence": "Synthetic testing log confirms stable reference conditions and a seven-day test–retest design.",
    "confirmed_stable_and_applicable": True,
}


def visit(index, subjects=range(1, 21), n_trials=2):
    return [
        [f"A{i:02d}", SESSIONS[index], f"V{index}-{i:02d}-{trial}", index + 1, 1000,
         30 + i * 0.25 + (trial - 1.5) + (0.2 + (i - 11) / 10 if index == 1 else 3 if index == 3 else 0),
         72 + i, 1600 + i, DATES[index]]
        for i in subjects for trial in range(1, n_trials + 1)
    ]


def attach(service, workspace, path, fields=FIXTURE, **kwargs):
    stage = importer.stage(importer.probe_file(path), importer.build_context(fields))
    assert stage["eligible"], stage["quality"]
    return service.attach_workspace_data(workspace, importer.admit(stage)["dataset_snapshot_id"], **kwargs)


@pytest.fixture
def assessment(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    workspace = service.create_workspace("RES-723 synthetic cohort")["study"]["id"]
    initial = write_export(tmp_path / "baseline.csv", visit(0) + visit(1) + visit(2), DATED_FIELDS)
    base = attach(service, workspace, initial)["active_data_revision_id"]
    rows = visit(3) + visit(4, n_trials=1)
    source = write_export(tmp_path / "followup.csv", rows, DATED_FIELDS)
    proposal = reconciliation.propose(workspace, source)
    mapped = revise(proposal, sessions={name: name for name in SESSIONS[3:]}, declared=declaration(proposal))
    assert mapped["ready"], mapped["discrepancies"]
    approval = decide(mapped, "APPROVED")
    current = approval["decision"]["revision_id"]
    investigation = service.create_individual_investigation(workspace, "A01", "Review jump-height change")
    return service, workspace, base, current, investigation, approval


def request_for(revision, *, source=None, target=SESSIONS[3], retest=RETEST):
    return {"reference_revision_id": source or revision, "reference_session": SESSIONS[2],
            "comparison_session": target, **({"retest": retest} if retest else {})}


def run_assessment(service, workspace, investigation, revision, parameters):
    return service.execute_analysis_run(workspace, {
        "method_id": trust.METHOD, "method_version": trust.VERSION, "outcome_metric_id": trust.METRIC,
        "data_revision_id": revision, "parameters": parameters,
        "scope": {"kind": "INDIVIDUAL", "subject_id": "A01", "investigation_id": investigation["id"],
                  "investigation_version": investigation["version"]},
    })


def test_matched_retest_arithmetic_and_persistence(assessment):
    service, workspace, base, revision, investigation, approval = assessment
    run = run_assessment(service, workspace, investigation, revision, request_for(revision, source=base))
    result = trust.MeasurementTrustResult.model_validate(run["result"])
    if result.status != "SYNTHETIC_DEMONSTRATION":
        pytest.fail(result.model_dump_json())
    assert result.observed_change == pytest.approx(3)
    assert result.reference.mean == pytest.approx(30.25)
    assert result.comparison.mean == pytest.approx(33.25)
    assert result.reference_window_days == 7
    assert result.relation_to_retest == "ABOVE"
    evidence = result.retest_evidence
    assert evidence.n_pairs == 19 and "A01" not in evidence.pair_scores
    differences = [0.2 + (i - 11) / 10 for i in range(2, 21)]
    sd = stdev(differences)
    assert evidence.bias == pytest.approx(mean(differences))
    assert evidence.difference_sd == pytest.approx(sd)
    assert evidence.typical_error == pytest.approx(sd / math.sqrt(2))
    assert evidence.mdc95 == pytest.approx(1.959963984540054 * sd)
    radius = 2.10092204024096 * sd * math.sqrt(20 / 19)
    assert evidence.prediction_95 == pytest.approx([mean(differences) - radius, mean(differences) + radius])
    first_scores = [30 + i * 0.25 for i in range(2, 21)]
    athlete_means = [score + difference / 2 for score, difference in zip(first_scores, differences, strict=True)]
    subject_ms = 2 * stdev(athlete_means) ** 2
    residual_ms = sd**2 / 2
    assert evidence.icc_3_1 == pytest.approx((subject_ms - residual_ms) / (subject_ms + residual_ms))
    assert result.provenance[revision]["reconciliation"]["id"] == approval["id"]
    assert result.provenance[revision]["parquet_sha256"] == store.get_data_revision(revision)["snapshot"]["checksums"]["cmj_trials.parquet"]
    assert set(run["execution"]["method_binding"]["measurement_trust"]["revisions"]) == {base, revision}
    assert DynamisAppService().individual_research(investigation["id"])["runs"][0] == run
    with sqlite3.connect(store._db_path()) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_sparse_missing_and_inapplicable_error_are_distinct(assessment):
    service, workspace, _, revision, investigation, _ = assessment
    sparse = run_assessment(service, workspace, investigation, revision,
                            request_for(revision, target=SESSIONS[4], retest=None))["result"]
    assert sparse["status"] == "NOT_ESTIMABLE" and sparse["observed_change"] == pytest.approx(-0.5)
    assert sparse["comparison"]["n_trials"] == 1 and sparse["retest_evidence"] is None
    assert "Within-session" in sparse["reasons"][0]
    mismatch = run_assessment(service, workspace, investigation, revision,
                              request_for(revision, target=SESSIONS[4]))["result"]
    assert mismatch["status"] == "UNQUALIFIED" and mismatch["observed_change"] is not None
    assert "trial count" in mismatch["reasons"][0]
    missing = run_assessment(service, workspace, investigation, revision,
                             request_for(revision, target="Absent", retest=None))["result"]
    assert missing["status"] == "NOT_ESTIMABLE" and missing["observed_change"] is None
    with pytest.raises(store.ResearchConflict, match="revision changed"):
        run_assessment(service, workspace, investigation, "Stale", request_for(revision))


def test_protocol_and_unconfirmed_athlete_lineage_block_change(assessment, tmp_path):
    service, workspace, _, revision, investigation, _ = assessment
    changed = write_export(tmp_path / "changed-protocol.csv", visit(3), DATED_FIELDS)
    current = attach(service, workspace, changed, {**FIXTURE, "protocol_version": "2.0"},
                     base_revision=revision)["active_data_revision_id"]
    result = run_assessment(service, workspace, investigation, current,
                            request_for(current, source=revision, retest=None))["result"]
    assert result["status"] == "INCOMPARABLE"
    assert any("protocol" in reason for reason in result["reasons"])
    assert any("identity" in reason for reason in result["reasons"])
    assert result["observed_change"] is None and result["retest_evidence"] is None


def test_units_and_duplicate_trials_fail_closed(assessment, monkeypatch):
    _, workspace, _, revision, _, _ = assessment
    request = trust.ComparisonRequest.model_validate(request_for(revision))
    load = trust._load

    def wrong_unit(*args):
        frame, provenance = load(*args)
        for source in provenance["inputs"].values():
            source["units"] = {}
        return frame, provenance

    with monkeypatch.context() as patch:
        patch.setattr(trust, "_load", wrong_unit)
        result = trust.evaluate(workspace, revision, "A01", request)
        assert result.status == "INCOMPARABLE" and any("canonical jump height" in reason for reason in result.reasons)
        assert result.observed_change is None

    def duplicate(*args):
        frame, provenance = load(*args)
        copied = frame.filter(pl.col("trial_id") == "V3-01-1")
        return pl.concat([frame, copied]), provenance

    with monkeypatch.context() as patch:
        patch.setattr(trust, "_load", duplicate)
        result = trust.evaluate(workspace, revision, "A01", request)
        assert result.status == "INCOMPARABLE" and any("duplicate trial" in reason for reason in result.reasons)
        assert result.observed_change is None


def test_actual_missing_trial_values_and_unverified_source(assessment, tmp_path):
    service, workspace, _, revision, investigation, _ = assessment
    rows = visit(2) + visit(3)
    rows[0][5] = None
    current = attach(service, workspace, write_export(tmp_path / "missing.csv", rows, DATED_FIELDS),
                     base_revision=revision)["active_data_revision_id"]
    result = run_assessment(service, workspace, investigation, current, request_for(current, retest=None))["result"]
    assert result["status"] == "NOT_ESTIMABLE" and result["observed_change"] is None
    assert result["reference"]["missing_values"] == 1
    artifact = store.get_data_revision(current)["snapshot"]["admission"]["source_artifact_id"]
    receipt = next(item for item in importer.list_receipts() if item["source_artifact_id"] == artifact)
    Path(receipt["raw_copy"]).write_text("corrupt retained source", encoding="utf-8")
    blocked = run_assessment(service, workspace, investigation, current, request_for(current, retest=None))["result"]
    assert blocked["status"] == "UNQUALIFIED" and "checksum" in blocked["reasons"][0]
    assert blocked["observed_change"] is None
