"""Revision-bound comparison of CMJ session means and matched retest variation."""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from statistics import mean, stdev
from typing import Annotated, Literal

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from scipy.stats import norm, t

from . import admission, importer, researchstore as store
from .analysis import two_way_icc
from .data_root import paths

METHOD = "METH-U-MEASUREMENT-TRUST"
VERSION = "1.1.0"
METRIC = "MET-CMJ-HEIGHT"
TABLE = "cmj_trials"
COLUMN = "jump_height_cm"
FAMILY = "CMJ_FORCE_PLATFORM"
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
EvidenceText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class RetestReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    first_session: ShortText
    second_session: ShortText
    reviewer: ShortText
    population: ShortText
    design_evidence: EvidenceText
    confirmed_stable_and_applicable: Literal[True]


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reference_revision_id: ShortText
    reference_session: ShortText
    comparison_session: ShortText
    retest: RetestReview | None = None


class Trial(BaseModel):
    trial_id: str
    value: float | None
    qc: str
    source_artifact_id: str | None


class Session(BaseModel):
    revision_id: str
    session_id: str
    date: str | None = None
    week: int | None = None
    ambiguous_time: bool = False
    n_trials: int = 0
    missing_values: int = 0
    excluded_trials: int = 0
    mean: float | None = None
    within_session_sd: float | None = None
    trials: list[Trial] = Field(default_factory=list)


class RetestEvidence(BaseModel):
    review: RetestReview
    n_pairs: int
    excluded_subject_ids: list[str]
    pair_scores: dict[str, tuple[float, float]]
    trial_counts_per_session: int
    interval_days: int
    dates: tuple[str, str]
    bias: float
    difference_sd: float
    typical_error: float
    mdc95: float
    icc_3_1: float
    icc_95_ci: tuple[float | None, float | None]
    prediction_95: tuple[float, float]


class MeasurementTrustResult(BaseModel):
    status: Literal["INTERPRETABLE", "SYNTHETIC_DEMONSTRATION", "INCOMPARABLE", "NOT_ESTIMABLE", "UNQUALIFIED"] = "UNQUALIFIED"
    subject_id: str
    outcome_metric_id: str = METRIC
    unit: str = "cm"
    reference: Session
    comparison: Session
    reference_window_days: int | None = None
    observed_change: float | None = None
    relation_to_retest: Literal["BELOW", "WITHIN", "ABOVE"] | None = None
    retest_review: RetestReview | None = None
    retest_evidence: RetestEvidence | None = None
    reasons: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=lambda: [
        "The comparison describes the observed change in session means and its relation to matched retest variation.",
        "The retest range includes short-term biological variation under the reviewed conditions. It provides no estimate of "
        "meaningful change, fatigue, adaptation, readiness, injury risk or a causal effect.",
    ])


def options(revisions: list[dict]) -> list[dict]:
    """Read the recorded session identities for the native pickers."""
    choices = []
    for revision in reversed(revisions):
        snapshot = revision["snapshot"]
        if not snapshot.get("admitted_source") or TABLE not in snapshot["tables"]:
            continue
        try:
            table = store.read_snapshot_table(snapshot["id"], TABLE)
            if not {"session_id", COLUMN} <= set(table.columns):
                continue
            sessions = table.select("session_id", *[column for column in ("date", "week") if column in table.columns])
        except (OSError, ValueError, pl.exceptions.PolarsError, store.ResearchNotFound):
            continue
        for visit in sessions.drop_nulls("session_id").partition_by("session_id"):
            choices.append({"revision_id": revision["id"], "number": revision["number"],
                            "session_id": visit["session_id"][0], "date": _one(visit, "date"), "week": _one(visit, "week")})
    choices.sort(key=lambda row: (-row["number"], row["date"] or "", row["week"] or 0, row["session_id"]))
    return choices


def _bound_revision(revision_id: str, workspace_id: str) -> dict:
    revision = store.get_data_revision(revision_id)
    if not revision or revision["workspace_id"] != workspace_id:
        raise store.ResearchValidation("Select a data revision from this workspace.")
    return revision


def _same_identity_lineage(reference_id: str, comparison: dict) -> bool:
    revision = comparison
    while revision["id"] != reference_id:
        if revision["mode"] == "SEPARATE" or not revision["parent_revision_id"]:
            return False
        revision = _bound_revision(revision["parent_revision_id"], comparison["workspace_id"])
    return True


def _parquet_check(snapshot: dict, table: str = TABLE) -> str:
    root = paths()["research"] / "data" if snapshot.get("workspace_snapshot") else paths()["admitted"]
    path = root / snapshot["id"] / f"{table}.parquet"
    expected = snapshot.get("checksums", {}).get(path.name)
    if not expected or importer._sha256(path) != expected:
        raise ValueError(f"{table} Parquet checksum failed for {snapshot['id']}.")
    return expected


def _load(revision: dict, receipts: list[dict]) -> tuple[pl.DataFrame, dict]:
    snapshot = revision["snapshot"]
    if not snapshot.get("admitted_source") or TABLE not in snapshot["tables"]:
        raise ValueError("This data revision has no admitted CMJ trial summary.")
    note = {"snapshot_id": snapshot["id"], "parquet_sha256": _parquet_check(snapshot),
            "reconciliation": revision.get("reconciliation"), "inputs": {}, "linked_traces": []}
    for item in revision["inputs"]:
        if {"trace_index", "force_signals"} <= set(item["tables"]):
            note["linked_traces"].append({"snapshot_id": item["id"], "checksums": item["checksums"],
                                          "source_id": item["admission"]["source_id"], "rights_status": item["rights_status"]})
        if item.get("measurement_family") != FAMILY:
            continue
        record = item["admission"]
        source = admission.get_source(record["source_id"])
        pinned = item["source"]
        if (not source or source["rights_status"] not in {"VERIFIED", "FIXTURE_ONLY"}
                or source["rights_status"] != item["rights_status"]
                or source["license_or_agreement"] != pinned["license"]["id"]
                or source["privacy_status"] != pinned["privacy"]["classification"]
                or source["redistribution_restrictions"] != pinned["redistribution_restrictions"]
                or "research" not in {str(use).strip().lower() for use in source["permitted_uses"]}):
            raise ValueError(f"Current source rights cannot support research for {item['id']}.")
        artifact_id = record["source_artifact_id"]
        artifact = admission.get_source_artifact(artifact_id)
        if not artifact or importer._sha256(Path(artifact["stored_path"])) != artifact["content_hash_sha256"]:
            raise ValueError(f"Source artifact checksum failed for {item['id']}.")
        raw_files = []
        for receipt in receipts:
            if receipt["source_artifact_id"] != artifact_id:
                continue
            if importer._sha256(Path(receipt["raw_copy"])) != receipt["raw_sha256"]:
                raise ValueError(f"Retained export checksum failed for {item['id']}.")
            raw_files.append({"receipt_id": receipt["id"], "name": receipt["raw_filename"],
                              "sha256": receipt["raw_sha256"], "row_quarantine": receipt["row_quarantine"]})
        note["inputs"][artifact_id] = {
            "snapshot_id": item["id"], "source_id": source["id"], "rights_status": item["rights_status"],
            "artifact_sha256": artifact["content_hash_sha256"], "parquet_sha256": _parquet_check(item),
            "raw_exports": raw_files, "units": item.get("admission_metadata", {}).get("units", {}),
            "qc": admission.get_quality(record["quality_assessment_id"]),
            "instruments": item.get("provenance", {}).get("instrument_metadata", []),
            "protocols": item.get("provenance", {}).get("protocol_metadata", []),
        }
    return store.read_snapshot_table(snapshot["id"], TABLE), note


def locate_trace(run: dict, revision_id: str, session_id: str, trial_id: str) -> str | None:
    """Locate an unambiguous same-athlete, same-session, same-trial recording pinned by the run."""
    if run["method_id"] != METHOD:
        raise store.ResearchValidation("Select a saved measurement trust result.")
    result = run["result"]
    if not any(session["revision_id"] == revision_id and session["session_id"] == session_id
               and any(trial["trial_id"] == trial_id for trial in session["trials"])
               for session in (result["reference"], result["comparison"])):
        raise store.ResearchValidation("The trial is outside the saved measurement trust assessment.")
    candidates = result["provenance"][revision_id].get("linked_traces", [])
    matches = []
    for candidate in candidates:
        snapshot = store.get_snapshot(candidate["snapshot_id"])
        source = admission.get_source(candidate["source_id"])
        if (not snapshot or snapshot["checksums"] != candidate["checksums"] or not source
                or source["rights_status"] not in {"VERIFIED", "FIXTURE_ONLY"}
                or source["rights_status"] != candidate["rights_status"]
                or "research" not in {str(use).strip().lower() for use in source["permitted_uses"]}):
            continue
        _parquet_check(snapshot, "trace_index")
        trials = store.read_snapshot_table(snapshot["id"], "trace_index").filter(pl.col("trial_id") == trial_id)
        if trials.height == 1 and trials["subject_id"][0] == result["subject_id"] and trials["session_id"][0] == session_id:
            _parquet_check(snapshot, "force_signals")
            matches.append(snapshot["id"])
    return matches[0] if len(matches) == 1 else None


def _one(rows: pl.DataFrame, column: str):
    if column not in rows.columns or rows.is_empty():
        return None
    values = rows[column].unique()
    return values[0] if len(values) == 1 else None


def _session(frame: pl.DataFrame, selected: Session, subject: str) -> tuple[Session, pl.DataFrame]:
    visit = frame.filter(pl.col("session_id") == selected.session_id)
    rows = visit.filter(pl.col("subject_id") == subject)
    selected.date = _one(visit, "date")
    selected.ambiguous_time = any(visit[column].n_unique() > 1 for column in ("date", "week") if column in visit.columns)
    week = _one(visit, "week")
    if type(week) in (int, float) and math.isfinite(week) and week == int(week):
        selected.week = int(week)
    return _score(rows.sort("trial_id"), selected), rows


def _score(rows: pl.DataFrame, selected: Session) -> Session:
    values = []
    for row in rows.iter_rows(named=True):
        raw = row.get(COLUMN)
        value = float(raw) if isinstance(raw, (int, float)) and math.isfinite(raw) else None
        qc = row.get("quality_state", "VALID")
        if value is None:
            selected.missing_values += 1
        elif qc == "VALID":
            values.append(value)
        if qc != "VALID":
            selected.excluded_trials += 1
        selected.trials.append(Trial(trial_id=row["trial_id"] or "", value=value, qc=qc or "UNKNOWN",
                                     source_artifact_id=row.get("source_artifact_id")))
    selected.n_trials = len(values)
    selected.mean = mean(values) if values else None
    selected.within_session_sd = stdev(values) if len(values) > 1 else None
    return selected


def _days(first: str | None, second: str | None) -> int | None:
    if first and second:
        try:
            return (date.fromisoformat(second) - date.fromisoformat(first)).days
        except ValueError:
            return None
    return None


def _source_context(rows: pl.DataFrame, note: dict) -> tuple[tuple | None, list[str]]:
    instrument_id, protocol_id, sampling = (_one(rows, column) for column in ("instrument_id", "protocol_id", "sampling_hz"))
    instrument = admission.get_instrument(instrument_id) if instrument_id else None
    protocol = admission.get_protocol(protocol_id) if protocol_id else None
    if not instrument or not protocol or not sampling or protocol["sampling_hz"] != sampling:
        return None, ["Instrument, protocol and sampling rate must be explicit and homogeneous."]
    issues = []
    sources = set(rows["source_artifact_id"]) if "source_artifact_id" in rows.columns else {None}
    rights = {note["inputs"][artifact]["rights_status"] for artifact in sources if artifact in note["inputs"]}
    if len(rights) > 1:
        issues.append("A session score mixes empirical observations and synthetic fixture trials.")
    for artifact_id in sources:
        source = note["inputs"].get(artifact_id)
        if not source or not source["qc"] or source["qc"]["status"] not in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}:
            issues.append("Source admission QC is unavailable or failed.")
        elif (source["instruments"] != [instrument] or
              (source["protocols"] and source["protocols"] != [protocol])):
            issues.append("The registered protocol or instrument differs from captured acquisition metadata.")
        elif (protocol.get("units", {}).get("distance") != "cm" or source["units"].get("distance") != "cm"):
            issues.append("The source and protocol must document canonical jump height in cm.")
        elif any(item["row_quarantine"].get("count", 0) for item in source["raw_exports"]):
            issues.append("Source import quarantined trial rows. Verify their effect on the completeness of the session score.")
        elif instrument["calibration_status"] != ("SIMULATED" if source["rights_status"] == "FIXTURE_ONLY" else "CALIBRATED"):
            issues.append("The instrument calibration has not been established for this source.")
    note.setdefault("acquisition", {})[protocol_id] = {"protocol": protocol, "instrument": instrument, "sampling_hz": sampling}
    return (instrument_id, protocol_id, sampling, tuple(sorted(rights))), sorted(set(issues))


def _bad_trials(session: Session) -> bool:
    ids = [trial.trial_id for trial in session.trials]
    return not all(ids) or len(set(ids)) != len(ids)


def _retest(frame: pl.DataFrame, revision_id: str, note: dict, review: RetestReview, result: MeasurementTrustResult,
            context: tuple) -> RetestEvidence | None:
    first, second = review.first_session, review.second_session
    if len({first, second, result.reference.session_id, result.comparison.session_id}) != 4:
        result.reasons.append("Select separate retest sessions that do not overlap either comparison session.")
        return None
    visits = frame.filter(pl.col("session_id").is_in([first, second]))
    first_date = _one(visits.filter(pl.col("session_id") == first), "date")
    second_date = _one(visits.filter(pl.col("session_id") == second), "date")
    days = _days(first_date, second_date)
    count = result.reference.n_trials
    if days is None or days <= 0 or days != result.reference_window_days or count != result.comparison.n_trials:
        result.reasons.append("Retest and comparison require the same positive recorded day interval and trial count per session.")
        return None
    visit_context, issues = _source_context(visits, note)
    if issues or visit_context[:3] != context[:3]:
        result.reasons.extend(issues or ["Retest acquisition differs from the compared sessions."])
        return None
    if visit_context[3] != context[3]:
        result.reasons.append("Retest and comparison must both be empirical observations or both be synthetic fixtures.")
        return None
    if visits["trial_id"].null_count() or visits["trial_id"].n_unique() != visits.height:
        result.reasons.append("The retest sessions contain missing or reused trial identifiers.")
        return None
    pairs, excluded = {}, []
    by_athlete = visits.filter(pl.col("subject_id").is_not_null() & (pl.col("subject_id") != result.subject_id))
    for rows in by_athlete.sort("subject_id").partition_by("subject_id", maintain_order=True):
        subject = rows["subject_id"][0]
        a = _score(rows.filter(pl.col("session_id") == first), Session(revision_id=revision_id, session_id=first))
        b = _score(rows.filter(pl.col("session_id") == second), Session(revision_id=revision_id, session_id=second))
        if (a.n_trials == b.n_trials == count and len(a.trials) == len(b.trials) == count
                and not _bad_trials(a) and not _bad_trials(b)):
            pairs[subject] = (a.mean, b.mean)
        else:
            excluded.append(subject)
    if len(pairs) < 3:
        result.reasons.append(f"Only {len(pairs)} independent complete matched retest pairs; at least three are required to estimate variation.")
        return None
    values = np.asarray(list(pairs.values()))
    differences = values[:, 1] - values[:, 0]
    bias, sd = float(np.mean(differences)), float(np.std(differences, ddof=1))
    if not math.isfinite(sd) or sd <= 0:
        result.reasons.append("The retest pairs do not estimate positive, finite variation.")
        return None
    n = len(pairs)
    icc = two_way_icc(values)
    radius = float(t.ppf(0.975, n - 1) * sd * math.sqrt(1 + 1 / n))
    return RetestEvidence(review=review, n_pairs=n, excluded_subject_ids=excluded,
                          pair_scores=pairs, trial_counts_per_session=count, interval_days=days,
                          dates=(first_date, second_date),
                          bias=bias, difference_sd=sd, typical_error=sd / math.sqrt(2),
                          mdc95=float(norm.ppf(0.975) * sd), icc_3_1=icc["icc_3_1"],
                          icc_95_ci=(icc["icc_3_1_ci_low"], icc["icc_3_1_ci_high"]),
                          prediction_95=(bias - radius, bias + radius))


def evaluate(workspace_id: str, active_id: str, subject: str, request: ComparisonRequest) -> MeasurementTrustResult:
    comparison = _bound_revision(active_id, workspace_id)
    reference = _bound_revision(request.reference_revision_id, workspace_id)
    result = MeasurementTrustResult(
        subject_id=subject, reference=Session(revision_id=reference["id"], session_id=request.reference_session),
        comparison=Session(revision_id=active_id, session_id=request.comparison_session), retest_review=request.retest,
    )
    receipts = importer.list_receipts()
    try:
        current, note = _load(comparison, receipts)
        earlier, earlier_note = (current, note) if reference["id"] == active_id else _load(reference, receipts)
    except (OSError, ValueError, LookupError, pl.exceptions.PolarsError, store.ResearchNotFound) as error:
        result.reasons.append(f"Source verification failed. {error}")
        return result
    result.provenance = {reference["id"]: earlier_note, active_id: note}
    required = {"session_id", "subject_id", "trial_id", COLUMN}
    if not required <= set(current.columns) or not required <= set(earlier.columns):
        result.reasons.append("CMJ trial, athlete, session and jump-height fields are required on both revisions.")
        return result
    a, a_rows = _session(earlier, result.reference, subject)
    b, b_rows = _session(current, result.comparison, subject)
    result.reference_window_days = _days(a.date, b.date)
    if not _same_identity_lineage(reference["id"], comparison):
        result.reasons.append("The selected revisions do not share a confirmed athlete identity lineage.")
    if a.session_id == b.session_id or set(a_rows["trial_id"]) & set(b_rows["trial_id"]):
        result.reasons.append("Choose two distinct sessions without reused trial identifiers.")
    if _bad_trials(a) or _bad_trials(b):
        result.reasons.append("A selected session has missing or duplicate trial identifiers.")
    if a.ambiguous_time or b.ambiguous_time:
        result.reasons.append("A selected session has conflicting recorded dates or weeks.")
    if result.reference_window_days is not None and result.reference_window_days < 0:
        result.reasons.append("The comparison session precedes the reference session.")
    if result.reference_window_days is None and a.week is not None and b.week is not None and b.week < a.week:
        result.reasons.append("The comparison week precedes the reference week.")
    a_context, a_issues = _source_context(a_rows, earlier_note) if a.trials else (None, [])
    b_context, b_issues = _source_context(b_rows, note) if b.trials else (None, [])
    if a_context and b_context and a_context[:3] != b_context[:3]:
        result.reasons.append("Instrument, protocol or sampling rate changed between the sessions.")
    if a_context and b_context and a_context[3] != b_context[3]:
        result.reasons.append("The compared sessions mix empirical observations and synthetic fixtures.")
    result.reasons.extend(sorted(set(a_issues + b_issues)))
    if result.reasons:
        result.status = "INCOMPARABLE"
        return result
    if a.mean is None or b.mean is None:
        result.status = "NOT_ESTIMABLE"
        result.reasons.append("The selected athlete has no usable jump-height observation in one or both sessions.")
        return result
    if a.missing_values or b.missing_values or a.excluded_trials or b.excluded_trials:
        result.status = "NOT_ESTIMABLE"
        result.reasons.append("The session score is incomplete because a selected trial is missing or failed QC.")
        return result
    result.observed_change = b.mean - a.mean
    if request.retest is None:
        result.status = "NOT_ESTIMABLE"
        result.reasons.append("Between-session error is unknown. Within-session trial variation does not estimate it.")
        return result
    evidence = _retest(current, active_id, note, request.retest, result, b_context)
    if evidence is not None:
        result.status = "SYNTHETIC_DEMONSTRATION" if b_context[3] == ("FIXTURE_ONLY",) else "INTERPRETABLE"
        result.retest_evidence = evidence
        low, high = evidence.prediction_95
        result.relation_to_retest = "BELOW" if result.observed_change < low else "ABOVE" if result.observed_change > high else "WITHIN"
    return result
