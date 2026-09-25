from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import duckdb
import numpy as np
import polars as pl
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from .analysis import (
    _group_longitudinal,
    _individual_change,
    _reliability,
    _safe_float,
    reproducibility_key,
    result_digest,
    simulate_scenario,
    simulate_training_response,
)
from .generate import ARTIFACT_DIR, PARQUET_DIR, SNAPSHOT_ID, generate_data
from .lineage import build_lineage_graph, scope_lineage_graph


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_data()
    yield


app = FastAPI(title="DynamisScience Local Science Service", version="0.2.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BLOCK_TYPES = {
    "question",
    "dataset",
    "cohort",
    "table",
    "explore",
    "force_trial",
    "match_event",
    "analysis",
    "diagnostics",
    "evidence",
    "model",
    "figure",
    "interpretation",
    "report_section",
}
# A block may only depend on blocks placed before it, which is the only
# ordering constraint the workbench enforces when blocks are reordered.
BLOCK_DEPENDENCY_KEYS = ("cohort_block_id", "analysis_block_id", "evidence_block_id")
REPORT_SECTIONS = ["Intervention result", "Reliability context", "Exploratory results"]


class AnalysisRequest(BaseModel):
    method_id: str = "METH-LONG"
    outcome_metric_id: str = "MET-CMJ-IMPULSE"
    subject_ids: list[str] | None = None
    excluded_subject_ids: list[str] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class PromotionRequest(BaseModel):
    run_id: str


class CitationRequest(BaseModel):
    artifact_id: str
    section: str | None = None


class CohortRequest(BaseModel):
    excluded_subject_ids: list[str] = Field(default_factory=list)


class SimulationRequest(BaseModel):
    load_values: list[float]
    parameters: dict[str, float] = Field(default_factory=dict)


class ScenarioRequest(BaseModel):
    future_load_au: list[float]


class InvestigationBlock(BaseModel):
    id: str
    type: str
    title: str
    state: dict[str, Any] = Field(default_factory=dict)
    collapsed: bool = False


class InvestigationUpdate(BaseModel):
    title: str | None = None
    blocks: list[InvestigationBlock]
    base_version: int | None = None


# --------------------------------------------------------------------------- #
# Local artefact store
# --------------------------------------------------------------------------- #


def _ensure_data() -> None:
    required = [ARTIFACT_DIR / "dataset_snapshot.json", ARTIFACT_DIR / "investigations.json", PARQUET_DIR / "cmj_trials.parquet"]
    if not all(path.exists() for path in required):
        generate_data()


def _json(name: str, default: Any) -> Any:
    path = ARTIFACT_DIR / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(name: str, value: Any) -> None:
    """Atomic replace so a crash mid-write cannot corrupt the artefact store."""
    path = ARTIFACT_DIR / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


@lru_cache(maxsize=32)
def _parquet_cached(name: str, mtime_ns: int) -> pl.DataFrame:
    return pl.read_parquet(PARQUET_DIR / f"{name}.parquet")


def _parquet(name: str) -> pl.DataFrame:
    """Parquet tables are immutable per snapshot, so reads are cached by mtime."""
    path = PARQUET_DIR / f"{name}.parquet"
    if not path.exists():
        return pl.DataFrame()
    return _parquet_cached(name, path.stat().st_mtime_ns)


def _rows(name: str) -> list[dict[str, Any]]:
    return _parquet(name).to_dicts()


def _find(items: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
    return next((item for item in items if str(item.get(key)) == value), None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric_columns() -> dict[str, dict[str, Any]]:
    return {
        "MET-CMJ-IMPULSE": {"column": "concentric_impulse_n_s_kg", "label": "Concentric impulse", "unit": "N·s·kg⁻¹", "id": "cmj.concentric_impulse"},
        "MET-CMJ-HEIGHT": {"column": "jump_height_cm", "label": "Jump height (flight time)", "unit": "cm", "id": "cmj.jump_height.flight_time"},
        "MET-CMJ-BRAKING-DURATION": {"column": "eccentric_braking_duration_s", "label": "Eccentric braking duration", "unit": "s", "id": "cmj.eccentric_braking_duration"},
        "MET-CMJ-BRAKING-IMPULSE": {"column": "eccentric_braking_impulse_n_s_kg", "label": "Eccentric braking impulse", "unit": "N·s·kg⁻¹", "id": "cmj.eccentric_braking_impulse"},
        "MET-CMJ-POWER": {"column": "peak_power_w_kg", "label": "Peak power", "unit": "W·kg⁻¹", "id": "cmj.peak_power"},
        "MET-CMJ-DEPTH": {"column": "countermovement_depth_cm", "label": "Countermovement depth", "unit": "cm", "id": "cmj.countermovement_depth"},
        "MET-CMJ-RSI-MOD": {"column": "rsi_mod", "label": "RSI-mod", "unit": "cm·s⁻¹", "id": "cmj.rsi_mod"},
    }


def _metric(metric_id: str) -> dict[str, Any]:
    metrics = _metric_columns()
    if metric_id not in metrics:
        raise HTTPException(status_code=422, detail=f"Unknown outcome metric: {metric_id}")
    return {**metrics[metric_id], "metric_id": metric_id}


def _study() -> dict[str, Any]:
    return _json("study.json", {})


def _all_subject_ids() -> list[str]:
    return sorted(str(row["subject_id"]) for row in _rows("subjects"))


def _cohort_for(excluded: list[str] | None = None, included: list[str] | None = None) -> dict[str, Any]:
    """Resolve a cohort selection to a stable, typed CohortDefinition.

    The frozen COHORT-001 is returned unchanged when nobody is excluded. Any
    other selection is a DRAFT cohort whose ID is a digest of its membership, so
    the same selection always resolves to the same cohort.
    """
    frozen = _study().get("cohort", {})
    all_ids = _all_subject_ids()
    unknown = sorted((set(excluded or []) | set(included or [])) - set(all_ids))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown subject IDs: {', '.join(unknown)}")
    members = sorted(included) if included else [sid for sid in all_ids if sid not in set(excluded or [])]
    if len(members) < 4:
        raise HTTPException(status_code=422, detail="A cohort needs at least four athletes for group inference")
    if members == sorted(frozen.get("subject_ids", [])):
        return {**frozen, "excluded_subject_ids": []}
    digest = hashlib.sha256(",".join(members).encode("utf-8")).hexdigest()[:8].upper()
    removed = [sid for sid in all_ids if sid not in set(members)]
    return {
        "id": f"COHORT-D-{digest}",
        "study_id": "STUDY-001",
        "name": f"Draft cohort · {len(members)} athletes",
        "description": f"COHORT-001 with {len(removed)} athlete(s) excluded by the scientist.",
        "derived_from": frozen.get("id", "COHORT-001"),
        "subject_ids": members,
        "excluded_subject_ids": removed,
        "exclusion_criteria": [*frozen.get("exclusion_criteria", []), f"Scientist exclusion: {', '.join(removed)}"],
        "snapshot_id": SNAPSHOT_ID,
        "status": "DRAFT",
    }


@lru_cache(maxsize=4)
def _trace_trial_ids_cached(mtime_ns: int) -> frozenset[str]:
    return frozenset(pl.read_parquet(PARQUET_DIR / "force_traces.parquet", columns=["trial_id"])["trial_id"].unique().to_list())


def _trace_trial_ids() -> frozenset[str]:
    path = PARQUET_DIR / "force_traces.parquet"
    return _trace_trial_ids_cached(path.stat().st_mtime_ns) if path.exists() else frozenset()


# --------------------------------------------------------------------------- #
# Health, study, subjects
# --------------------------------------------------------------------------- #


@app.get("/health")
def health() -> dict[str, Any]:
    _ensure_data()
    return {"status": "ok", "service": "dynamis-science", "snapshot_id": SNAPSHOT_ID, "mode": "local-synthetic", "external_services": []}


def _data_health(subject_ids: set[str] | None = None) -> dict[str, Any]:
    """Provenance completeness is computed from stored records, never asserted."""
    trials = _rows("cmj_trials")
    missing_slots = _json("missing_observations.json", [])
    if subject_ids is not None:
        trials = [row for row in trials if row["subject_id"] in subject_ids]
        missing_slots = [slot for slot in missing_slots if slot.get("subject_id") in subject_ids]
    evidence = _json("evidence.json", [])
    n_subjects = len(subject_ids) if subject_ids is not None else 28
    expected_slots = n_subjects * 16 * 2
    valid = sum(1 for row in trials if row.get("quality_state") == "VALID")
    excluded = sum(1 for row in trials if row.get("quality_state") == "EXCLUDED")
    missing = max(0, expected_slots - valid - excluded)
    metric_fields = [
        "jump_height_cm",
        "concentric_impulse_n_s_kg",
        "eccentric_braking_impulse_n_s_kg",
        "eccentric_braking_duration_s",
        "countermovement_depth_cm",
        "peak_force_n",
        "peak_power_w_kg",
        "rsi_mod",
    ]
    complete_trials = 0
    for row in trials:
        has_trace = bool(str(row.get("trace_path") or "").strip())
        has_boundaries = bool(str(row.get("phase_boundaries") or "").strip())
        has_metrics = all(math.isfinite(_safe_float(row.get(field), float("nan"))) for field in metric_fields)
        has_quality = bool(str(row.get("quality_state") or "").strip())
        if has_trace and has_boundaries and has_metrics and has_quality:
            complete_trials += 1
    complete_evidence = sum(
        1
        for item in evidence
        if item.get("dataset_snapshot_id")
        and item.get("analysis_run_id")
        and (item.get("provenance") or {}).get("snapshot_checksum")
        and item.get("metric_id")
    )
    denominator = len(trials) + len(evidence)
    numerator = complete_trials + complete_evidence
    completeness = round(numerator / denominator * 100, 1) if denominator else 0.0
    return {
        "valid_measurements": valid,
        "excluded_measurements": excluded,
        "missing_observations": missing,
        "expected_slots": expected_slots,
        "missing_slots": missing_slots,
        "excluded_trials": [
            {"trial_id": row["trial_id"], "subject_id": row["subject_id"], "display_id": row["display_id"], "week": row["week"], "trial_number": row["trial_number"], "reason": row.get("exclusion_reason", "")}
            for row in trials
            if row.get("quality_state") == "EXCLUDED"
        ],
        "complete_records": numerator,
        "total_records": denominator,
        "provenance_completeness": completeness,
        "total_subjects": len({row["subject_id"] for row in trials}),
    }


@app.get("/overview")
def overview() -> dict[str, Any]:
    _ensure_data()
    study = _study()
    runs = _json("analysis_runs.json", [])
    return {
        "snapshot": _json("dataset_snapshot.json", {}),
        "study": study.get("study", {}),
        "research_question": study.get("question", {}),
        "groups": study.get("groups", {}),
        "plan": study.get("plan", {}),
        "recent_analyses": runs[-3:][::-1],
        "evidence_artifacts": _json("evidence.json", []),
        "data_health": _data_health(),
        "longitudinal_signal": _json("overview_signal.json", []),
        "registries": _json("registry.json", {}),
        "figures": _json("figures.json", []),
    }


def _study_summary(study: dict[str, Any]) -> dict[str, Any]:
    runs = _json("analysis_runs.json", [])
    evidence = _json("evidence.json", [])
    return {
        **study.get("study", {}),
        "plan_status": study.get("plan", {}).get("status"),
        "run_count": len(runs),
        "evidence_count": len(evidence),
        "last_run_at": max((run.get("created_at", "") for run in runs), default=None),
        "investigation_ids": [item["id"] for item in _json("investigations.json", [])],
    }


@app.get("/studies")
def studies() -> list[dict[str, Any]]:
    _ensure_data()
    return [_study_summary(_study())]


@app.get("/studies/{study_id}")
def study_detail(study_id: str) -> dict[str, Any]:
    _ensure_data()
    study = _study()
    if study_id != "STUDY-001":
        raise HTTPException(status_code=404, detail="Study not found")
    subjects = _rows("subjects")
    arms: dict[str, int] = {}
    positions: dict[str, int] = {}
    for subject in subjects:
        arms[subject["intervention_arm"]] = arms.get(subject["intervention_arm"], 0) + 1
        positions[subject["position"]] = positions.get(subject["position"], 0) + 1
    return {
        **study,
        "snapshot": _json("dataset_snapshot.json", {}),
        "runs": _json("analysis_runs.json", []),
        "evidence": _json("evidence.json", []),
        "figures": _json("figures.json", []),
        "arm_counts": arms,
        "position_counts": positions,
        "data_health": _data_health(),
        "investigations": [{"id": item["id"], "title": item["title"], "status": item["status"], "block_count": len(item["blocks"])} for item in _json("investigations.json", [])],
    }


@app.get("/subjects")
def subjects(position: str | None = None, arm: str | None = None) -> list[dict[str, Any]]:
    _ensure_data()
    frame = _parquet("subjects")
    if position:
        frame = frame.filter(pl.col("position") == position)
    if arm:
        frame = frame.filter(pl.col("intervention_arm") == arm)
    return frame.to_dicts()


def _longitudinal_for(subject_id: str, metric_id: str) -> dict[str, Any]:
    trials = _rows("cmj_trials")
    subject = _find(_rows("subjects"), "subject_id", subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    metrics = _metric_columns()
    metric = metrics.get(metric_id, metrics["MET-CMJ-IMPULSE"])
    column = metric["column"]
    subject_trials = [row for row in trials if row["subject_id"] == subject_id]
    load_lookup = {row["week"]: row for row in _rows("training_load") if row["subject_id"] == subject_id}
    wellness = {row["week"]: row for row in _rows("wellness") if row["subject_id"] == subject_id}
    traces = _trace_trial_ids()
    baseline_values = [float(row[column]) for row in subject_trials if row["week"] in (1, 2) and row["quality_state"] == "VALID"]
    baseline_mean = float(np.mean(baseline_values)) if baseline_values else None
    prior_values: list[float] = []
    observations = []
    for week in range(1, 17):
        week_rows = [row for row in subject_trials if row["week"] == week]
        valid_rows = [row for row in week_rows if row["quality_state"] == "VALID"]
        excluded_rows = [row for row in week_rows if row["quality_state"] == "EXCLUDED"]
        values = [float(row[column]) for row in valid_rows]
        value = float(np.mean(values)) if values else None
        recent = prior_values[-4:]
        rolling_mean = float(np.mean(recent)) if recent else None
        rolling_sd = float(np.std(recent, ddof=1)) if len(recent) > 1 else None
        typical_error = rolling_sd / math.sqrt(2) if rolling_sd else None
        if values:
            prior_values.extend(values)
        expected_trials = 2
        observations.append({
            "week": week,
            "value": round(value, 6) if value is not None else None,
            "n_trials": len(values),
            "expected_trials": expected_trials,
            "missing_trials": max(0, expected_trials - len(week_rows)),
            "excluded_trials": len(excluded_rows),
            "quality_state": "MISSING" if not values else ("WARNING" if len(values) < expected_trials or excluded_rows else "VALID"),
            "rolling_mean": round(rolling_mean, 6) if rolling_mean is not None else None,
            "rolling_sd": round(rolling_sd, 6) if rolling_sd is not None else None,
            "z_score": round((value - rolling_mean) / rolling_sd, 3) if value is not None and rolling_mean is not None and rolling_sd else None,
            "percent_change_from_baseline": round((value - baseline_mean) / baseline_mean * 100, 2) if value is not None and baseline_mean else None,
            "coefficient_of_variation": round(rolling_sd / rolling_mean * 100, 2) if rolling_mean and rolling_sd else None,
            "typical_error": round(typical_error, 6) if typical_error is not None else None,
            "phase": "Strength block" if 3 <= week <= 10 and subject["intervention_arm"] == "INTERVENTION" else ("Match week" if week in {4, 8, 12, 15} else "Build / recovery"),
            "load": load_lookup.get(week),
            "wellness": wellness.get(week),
            "trials": [
                {
                    "trial_id": row["trial_id"],
                    "trial_number": row["trial_number"],
                    "quality_state": row["quality_state"],
                    "exclusion_reason": row.get("exclusion_reason", ""),
                    "value": float(row[column]),
                    "trace_available": row["trial_id"] in traces,
                }
                for row in sorted(week_rows, key=lambda item: item["trial_number"])
            ],
        })
    individual = _individual_change(trials, column)
    athlete_record = next((row for row in individual["athletes"] if row["subject_id"] == subject_id), None)
    return {
        "subject": subject,
        "metric": metric,
        "observations": observations,
        "typical_error": individual["typical_error"],
        "individual": {
            "method": individual["method"],
            "baseline_weeks": [1, 2],
            "post_weeks": [9, 10],
            "baseline_mean": athlete_record["baseline"] if athlete_record else None,
            "post_mean": athlete_record["post"] if athlete_record else None,
            "change": athlete_record["change"] if athlete_record else None,
            "percent_change": athlete_record["percent_change"] if athlete_record else None,
            "standardized_change": athlete_record["standardized_change"] if athlete_record else None,
            "exceeds_typical_error": athlete_record["exceeds_typical_error"] if athlete_record else None,
            "typical_error": individual["typical_error"],
            "cohort_change_sd": individual["change_sd"],
            "n_subjects": individual["n_subjects"],
            "limitations": "Descriptive baseline-to-post change; the typical error of a change is derived from the cohort change SD, so this is context, not a causal individual response.",
        },
        "provenance": {
            "snapshot_id": SNAPSHOT_ID,
            "source": "cmj_trials.parquet",
            "quality_rule": "Excluded trials remain visible in the trial registry and are omitted from weekly means.",
        },
    }


@app.get("/subjects/{subject_id}/longitudinal")
def subject_longitudinal(subject_id: str, metric_id: str = "MET-CMJ-IMPULSE") -> dict[str, Any]:
    _ensure_data()
    return _longitudinal_for(subject_id, metric_id)


# --------------------------------------------------------------------------- #
# Cohort and exploration
# --------------------------------------------------------------------------- #


@app.post("/cohorts/resolve")
def resolve_cohort(request: CohortRequest) -> dict[str, Any]:
    _ensure_data()
    cohort = _cohort_for(excluded=request.excluded_subject_ids)
    members = set(cohort["subject_ids"])
    subjects_rows = _rows("subjects")
    trials = [row for row in _rows("cmj_trials") if row["subject_id"] in members]
    health = _data_health(members)
    arm_counts: dict[str, int] = {"INTERVENTION": 0, "COMPARISON": 0}
    athletes = []
    for subject in sorted(subjects_rows, key=lambda item: item["subject_id"]):
        included = subject["subject_id"] in members
        subject_trials = [row for row in _rows("cmj_trials") if row["subject_id"] == subject["subject_id"]]
        if included:
            arm_counts[subject["intervention_arm"]] = arm_counts.get(subject["intervention_arm"], 0) + 1
        athletes.append({
            "subject_id": subject["subject_id"],
            "display_id": subject["display_id"],
            "position": subject["position"],
            "intervention_arm": subject["intervention_arm"],
            "included": included,
            "valid_trials": sum(1 for row in subject_trials if row["quality_state"] == "VALID"),
            "excluded_trials": sum(1 for row in subject_trials if row["quality_state"] == "EXCLUDED"),
            "missing_trials": 32 - len(subject_trials),
        })
    by_arm_missing: dict[str, int] = {}
    for slot in health["missing_slots"]:
        arm = next((row["intervention_arm"] for row in subjects_rows if row["subject_id"] == slot["subject_id"]), "UNKNOWN")
        by_arm_missing[arm] = by_arm_missing.get(arm, 0) + 1
    return {
        "cohort": cohort,
        "n": len(members),
        "arm_counts": arm_counts,
        "inclusion_criteria": [
            "Synthetic athlete enrolled in STUDY-001",
            "Valid baseline CMJ session (week 1)",
            "At least one post-block observation",
        ],
        "exclusion_criteria": cohort.get("exclusion_criteria", []),
        "filters": {"excluded_subject_ids": cohort.get("excluded_subject_ids", [])},
        "trial_quality": {
            "valid": health["valid_measurements"],
            "excluded": health["excluded_measurements"],
            "missing": health["missing_observations"],
            "expected": health["expected_slots"],
            "missing_by_arm": by_arm_missing,
            "excluded_trials": health["excluded_trials"],
            "missing_slots": health["missing_slots"],
        },
        "n_trials": len(trials),
        "athletes": athletes,
        "snapshot_id": SNAPSHOT_ID,
    }


def _t_critical(df: int) -> float:
    from scipy import stats

    return float(stats.t.ppf(0.975, df)) if df > 0 else float("nan")


@app.get("/explore/longitudinal")
def explore_longitudinal(
    metric_id: str = "MET-CMJ-IMPULSE",
    exclude: str = "",
    reference: str = Query(default="RAW", pattern="^(RAW|CHANGE|PERCENT)$"),
) -> dict[str, Any]:
    """Server-side aggregation of the cohort longitudinal signal.

    DuckDB aggregates valid trials to athlete-week means directly from the
    Parquet snapshot; the arm summary is computed across athletes so every
    athlete contributes one value per week (unit of analysis = athlete).
    """
    _ensure_data()
    metric = _metric(metric_id)
    excluded = [value for value in exclude.split(",") if value]
    cohort = _cohort_for(excluded=excluded)
    members = cohort["subject_ids"]
    column = metric["column"]
    connection = duckdb.connect()
    try:
        athlete_weeks = connection.execute(
            f"""
            SELECT subject_id, display_id, intervention_arm, week,
                   avg({column}) FILTER (WHERE quality_state = 'VALID') AS value,
                   count(*) FILTER (WHERE quality_state = 'VALID') AS n_valid,
                   count(*) FILTER (WHERE quality_state = 'EXCLUDED') AS n_excluded,
                   count(*) AS n_recorded
            FROM read_parquet(?)
            WHERE list_contains(?, subject_id)
            GROUP BY ALL
            ORDER BY subject_id, week
            """,
            [str(PARQUET_DIR / "cmj_trials.parquet"), members],
        ).fetchall()
        load_rows = connection.execute(
            """
            SELECT l.week, s.intervention_arm,
                   avg(l.training_impulse_au), avg(l.external_load_au), avg(l.match_minutes), avg(l.session_rpe)
            FROM read_parquet(?) l JOIN read_parquet(?) s USING (subject_id)
            WHERE list_contains(?, l.subject_id)
            GROUP BY ALL
            ORDER BY l.week
            """,
            [str(PARQUET_DIR / "training_load.parquet"), str(PARQUET_DIR / "subjects.parquet"), members],
        ).fetchall()
    finally:
        connection.close()
    athletes: dict[str, dict[str, Any]] = {}
    for subject_id, display_id, arm, week, value, n_valid, n_excluded, n_recorded in athlete_weeks:
        record = athletes.setdefault(subject_id, {"subject_id": subject_id, "display_id": display_id, "intervention_arm": arm, "raw": [None] * 16, "n_valid": [0] * 16, "n_excluded": [0] * 16, "n_missing": [2] * 16})
        index = int(week) - 1
        record["raw"][index] = float(value) if value is not None else None
        record["n_valid"][index] = int(n_valid)
        record["n_excluded"][index] = int(n_excluded)
        record["n_missing"][index] = max(0, 2 - int(n_recorded))
    for record in athletes.values():
        baseline = [value for value in record["raw"][:2] if value is not None]
        base = float(np.mean(baseline)) if baseline else None
        record["baseline"] = base
        if reference == "RAW":
            record["values"] = record["raw"]
        elif reference == "CHANGE":
            record["values"] = [None if value is None or base is None else value - base for value in record["raw"]]
        else:
            record["values"] = [None if value is None or not base else (value - base) / base * 100 for value in record["raw"]]
    unit = metric["unit"] if reference != "PERCENT" else "%"
    summary = []
    for arm in ("INTERVENTION", "COMPARISON"):
        arm_athletes = [record for record in athletes.values() if record["intervention_arm"] == arm]
        for week in range(1, 17):
            values = [record["values"][week - 1] for record in arm_athletes if record["values"][week - 1] is not None]
            n = len(values)
            mean = float(np.mean(values)) if n else None
            sd = float(np.std(values, ddof=1)) if n > 1 else None
            sem = sd / math.sqrt(n) if sd is not None else None
            t_value = _t_critical(n - 1) if n > 1 else None
            summary.append({
                "arm": arm,
                "week": week,
                "n": n,
                "n_athletes": len(arm_athletes),
                "mean": mean,
                "sd": sd,
                "ci_low": mean - t_value * sem if mean is not None and sem is not None and t_value is not None else None,
                "ci_high": mean + t_value * sem if mean is not None and sem is not None and t_value is not None else None,
                "missing_athletes": len(arm_athletes) - n,
                "excluded_trials": sum(record["n_excluded"][week - 1] for record in arm_athletes),
                "missing_trials": sum(record["n_missing"][week - 1] for record in arm_athletes),
            })
    context = []
    for week, arm, impulse, external, match_minutes, rpe in load_rows:
        context.append({"week": int(week), "arm": arm, "training_impulse_au": float(impulse), "external_load_au": float(external), "match_minutes": float(match_minutes), "session_rpe": float(rpe)})
    weekly_load = [float(np.mean([row["training_impulse_au"] for row in context if row["week"] == week])) for week in range(1, 17)]
    load_mean = float(np.mean(weekly_load))
    load_sd = float(np.std(weekly_load, ddof=1))
    load_peaks = [{"week": week, "training_impulse_au": value, "z": (value - load_mean) / load_sd} for week, value in enumerate(weekly_load, start=1) if load_sd and (value - load_mean) / load_sd > 1.5]
    groups = _study().get("groups", {})
    block_weeks = groups.get("intervention", {}).get("block_weeks", [3, 10])
    return {
        "metric": metric,
        "unit": unit,
        "reference": reference,
        "reference_label": {"RAW": "Observed value", "CHANGE": "Change from individual baseline (weeks 1–2)", "PERCENT": "Percent change from individual baseline (weeks 1–2)"}[reference],
        "cohort": {"id": cohort["id"], "status": cohort["status"], "n": len(members), "excluded_subject_ids": cohort.get("excluded_subject_ids", [])},
        "summary": summary,
        "athletes": sorted(athletes.values(), key=lambda item: item["subject_id"]),
        "context": context,
        "annotations": {
            "intervention_block": {"start_week": block_weeks[0], "end_week": block_weeks[1], "source": "study.json groups.intervention.block_weeks"},
            "load_peaks": load_peaks,
            "load_peak_rule": "Cohort mean weekly training impulse more than 1.5 SD above the 16-week mean",
        },
        "method": {
            "unit_of_analysis": "athlete-week mean of valid trials (both trials)",
            "interval": "t-based 95% CI of the arm mean across athletes",
            "engine": f"duckdb {duckdb.__version__} over Parquet",
            "note": "Descriptive exploration. The confirmatory model uses first valid trials only.",
        },
        "provenance": {"snapshot_id": SNAPSHOT_ID, "source": ["cmj_trials.parquet", "training_load.parquet", "subjects.parquet"]},
    }


# --------------------------------------------------------------------------- #
# Force and match measurement
# --------------------------------------------------------------------------- #


@app.get("/force/trials")
def force_trials(
    subject_id: str | None = None,
    week: int | None = None,
    quality_state: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[dict[str, Any]]:
    _ensure_data()
    frame = _parquet("cmj_trials")
    if subject_id:
        frame = frame.filter(pl.col("subject_id") == subject_id)
    if week:
        frame = frame.filter(pl.col("week") == week)
    if quality_state:
        frame = frame.filter(pl.col("quality_state") == quality_state)
    traces = _trace_trial_ids()
    rows = frame.sort(["week", "subject_id", "trial_number"], descending=[True, False, False]).head(limit).to_dicts()
    return [{**row, "trace_available": row["trial_id"] in traces} for row in rows]


@app.get("/force/trials/{trial_id}")
def force_trial(trial_id: str) -> dict[str, Any]:
    _ensure_data()
    trial = _find(_rows("cmj_trials"), "trial_id", trial_id)
    if trial is None:
        raise HTTPException(status_code=404, detail="Trial not found")
    trace = _parquet("force_traces").filter(pl.col("trial_id") == trial_id)
    boundaries = json.loads(trial.get("phase_boundaries", "{}")) if isinstance(trial.get("phase_boundaries"), str) else trial.get("phase_boundaries", {})
    registry = _json("registry.json", {})
    snapshot = _json("dataset_snapshot.json", {})
    subject = _find(_rows("subjects"), "subject_id", str(trial["subject_id"]))
    return {
        "trial": {**trial, "trace_available": bool(trace.height)},
        "subject": subject,
        "boundaries": boundaries,
        "trace": trace.to_dicts(),
        "trace_available": bool(trace.height),
        "method": {
            "algorithm": "cmj-metrics",
            "algorithm_version": "1.0.0",
            "sample_rate_hz": 1000,
            "integration": "trapezoidal net-force integration",
            "phase_detection": "deterministic phase template",
            "protocol_id": "PROT-CMJ",
            "metrics": registry.get("metrics", []),
        },
        "provenance": {
            "snapshot_id": SNAPSHOT_ID,
            "seed": snapshot.get("seed"),
            "generator_version": snapshot.get("generator_version"),
            "source": trial.get("trace_path"),
            "trials_checksum": snapshot.get("checksums", {}).get("cmj_trials.parquet"),
            "traces_checksum": snapshot.get("checksums", {}).get("force_traces.parquet"),
        },
    }


@app.get("/match/{match_id}")
def match_detail(match_id: str) -> dict[str, Any]:
    _ensure_data()
    tracking = _parquet("match_tracking").filter(pl.col("match_id") == match_id)
    if tracking.is_empty():
        raise HTTPException(status_code=404, detail="Match not found")
    pose = _parquet("match_pose").filter(pl.col("match_id") == match_id)
    pose_athletes = sorted(pose["athlete_id"].unique().to_list()) if pose.height else []
    return {
        "match_id": match_id,
        "sample_rate_hz": 10,
        "frame_count": int(tracking["frame"].n_unique()),
        "duration_s": float(tracking["time_s"].max()),
        "player_count": int(tracking.filter(pl.col("player_id") != "BALL")["player_id"].n_unique()),
        "pose_athletes": pose_athletes,
        "pose_sample_rate_hz": 10,
        "events": _rows("match_events"),
        "provenance": {"snapshot_id": SNAPSHOT_ID, "source": ["match_tracking.parquet", "match_pose.parquet", "match_events.parquet"], "mode": "SYNTHETIC"},
    }


@app.get("/match/{match_id}/tracking")
def match_tracking(match_id: str) -> dict[str, Any]:
    _ensure_data()
    frame = _parquet("match_tracking").filter(pl.col("match_id") == match_id)
    if frame.is_empty():
        raise HTTPException(status_code=404, detail="Match not found")
    frames = []
    for group in frame.group_by("frame", maintain_order=True):
        values = group[1].sort("player_id")
        first = values.row(0, named=True)
        frames.append({"frame": int(first["frame"]), "time_s": float(first["time_s"]), "entities": values.select(["player_id", "team", "x_m", "y_m", "vx_m_s", "vy_m_s"]).to_dicts()})
    return {"match_id": match_id, "sample_rate_hz": 10, "frame_count": frame["frame"].n_unique(), "duration_s": float(frame["time_s"].max()), "frames": frames, "events": _rows("match_events")}


@app.get("/match/{match_id}/pose")
def match_pose(match_id: str, athlete_id: str | None = None) -> dict[str, Any]:
    _ensure_data()
    frame = _parquet("match_pose").filter(pl.col("match_id") == match_id)
    if frame.is_empty():
        raise HTTPException(status_code=404, detail="Match not found")
    available = sorted(frame["athlete_id"].unique().to_list())
    if athlete_id:
        frame = frame.filter(pl.col("athlete_id") == athlete_id)
    if athlete_id and frame.is_empty():
        return {
            "match_id": match_id,
            "athlete_id": athlete_id,
            "available": False,
            "pose_athletes": available,
            "sample_rate_hz": 10,
            "frame_count": 0,
            "frames": [],
            "topology": [],
            "message": f"No pose stream is retained for {athlete_id} in this bounded segment.",
        }
    frames = []
    for group in frame.group_by("frame", maintain_order=True):
        first = group[1].row(0, named=True)
        frames.append({"frame": int(first["frame"]), "time_s": float(first["time_s"]), "athlete_id": str(first["athlete_id"]), "joints": group[1].select(["joint", "x_m", "y_m", "z_m", "confidence"]).to_dicts()})
    return {
        "match_id": match_id,
        "athlete_id": athlete_id,
        "available": True,
        "pose_athletes": available,
        "sample_rate_hz": 10,
        "frame_count": len(frames),
        "frames": frames,
        "topology": ["hip", "left_hip", "right_hip", "knee", "left_knee", "right_knee", "ankle", "left_ankle", "right_ankle", "shoulder", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"],
    }


# --------------------------------------------------------------------------- #
# Library and data
# --------------------------------------------------------------------------- #


@app.get("/registry")
def registry() -> dict[str, Any]:
    _ensure_data()
    return _json("registry.json", {})


@app.get("/library")
def library() -> dict[str, Any]:
    """The scientific Library: the same contracts the workbench executes against."""
    _ensure_data()
    content = _json("registry.json", {})
    specs = _study().get("analysis_specs", [])
    runs = _json("analysis_runs.json", [])
    usage: dict[str, list[str]] = {}
    for spec in specs:
        usage.setdefault(spec["outcome_metric_id"], []).append(spec["id"])
    for run in runs:
        spec = (run.get("execution") or {}).get("analysis_spec") or {}
        if spec.get("outcome_metric_id"):
            usage.setdefault(spec["outcome_metric_id"], []).append(run["id"])
    method_runs: dict[str, list[str]] = {}
    for run in runs:
        method_runs.setdefault(run["method_id"], []).append(run["id"])
    return {
        **content,
        "metrics": [{**metric, "usages": sorted(set(usage.get(metric["id"], [])))} for metric in content.get("metrics", [])],
        "methods": [{**method, "runs": method_runs.get(method["id"], []), "specs": [spec["id"] for spec in specs if spec["method_id"] == method["id"]]} for method in content.get("methods", [])],
        "model_spec": _json("model_spec.json", {}),
    }


@app.get("/registry/metrics")
def registry_metrics() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("registry.json", {}).get("metrics", [])


@app.get("/registry/protocols")
def registry_protocols() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("registry.json", {}).get("protocols", [])


TABLE_DESCRIPTIONS = {
    "subjects": ("Synthetic athletes, arm allocation and persistent traits", None),
    "cmj_trials": ("CMJ trial summaries with phase-derived metrics and quality state", None),
    "force_traces": ("Vertical ground reaction force traces for audit trials", "force_traces_hz"),
    "training_load": ("Weekly training-load aggregation per athlete", None),
    "wellness": ("Weekly wellness context per athlete", None),
    "match_tracking": ("Bounded match segment: player and ball positions", "match_tracking_hz"),
    "match_pose": ("3D pose joints for selected tracked players", "match_pose_hz"),
    "match_events": ("Annotated events within the match segment", None),
}


@app.get("/datasets")
def datasets() -> list[dict[str, Any]]:
    _ensure_data()
    snapshot = _json("dataset_snapshot.json", {})
    return [{
        "id": snapshot.get("id"),
        "label": snapshot.get("label"),
        "seed": snapshot.get("seed"),
        "generator_version": snapshot.get("generator_version"),
        "schema_version": snapshot.get("schema_version"),
        "generated_at": snapshot.get("generated_at"),
        "table_count": len(snapshot.get("row_counts", {})),
        "row_total": sum(snapshot.get("row_counts", {}).values()),
        "synthetic": True,
        "used_by_studies": ["STUDY-001"],
    }]


@app.get("/datasets/{snapshot_id}")
def dataset_detail(snapshot_id: str) -> dict[str, Any]:
    _ensure_data()
    snapshot = _json("dataset_snapshot.json", {})
    if snapshot_id != snapshot.get("id"):
        raise HTTPException(status_code=404, detail="Dataset snapshot not found")
    tables = []
    for name in sorted(snapshot.get("row_counts", {})):
        frame = _parquet(name)
        description, rate_key = TABLE_DESCRIPTIONS.get(name, ("", None))
        tables.append({
            "name": name,
            "file": f"{name}.parquet",
            "description": description,
            "rows": frame.height,
            "manifest_rows": snapshot["row_counts"][name],
            "checksum_sha256": snapshot.get("checksums", {}).get(f"{name}.parquet"),
            "sample_rate_hz": snapshot.get("sample_rates", {}).get(rate_key) if rate_key else None,
            "columns": [{"name": column, "dtype": str(dtype), "null_count": int(frame[column].null_count())} for column, dtype in frame.schema.items()],
        })
    return {
        "snapshot": snapshot,
        "tables": tables,
        "quality": _data_health(),
        "disclaimer": "Fully synthetic data generated locally from a fixed seed. No real athletes, clubs, matches or measurements are represented.",
    }


# --------------------------------------------------------------------------- #
# Execution, runs and evidence
# --------------------------------------------------------------------------- #


def _run_view(run: dict[str, Any], runs: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    reproduces = [
        other["id"]
        for other in runs
        if other["id"] != run["id"]
        and other.get("reproducibility_key") == run.get("reproducibility_key")
        and other.get("result_digest") == run.get("result_digest")
        and other["id"] < run["id"]
    ]
    return {
        **run,
        "reproduces": reproduces,
        "evidence_ids": [item["id"] for item in evidence if item.get("analysis_run_id") == run["id"]],
    }


@app.get("/runs")
def runs() -> list[dict[str, Any]]:
    _ensure_data()
    all_runs = _json("analysis_runs.json", [])
    evidence = _json("evidence.json", [])
    return [_run_view(run, all_runs, evidence) for run in all_runs][::-1]


@app.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    _ensure_data()
    all_runs = _json("analysis_runs.json", [])
    run = _find(all_runs, "id", run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    evidence = _json("evidence.json", [])
    return {
        **_run_view(run, all_runs, evidence),
        "lineage": _lineage_for(run_id),
        "evidence": [item for item in evidence if item.get("analysis_run_id") == run_id],
    }


def _resolve_spec(method_id: str, metric_id: str, parameters: dict[str, Any], cohort: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return the frozen spec this execution matches, and the effective parameters."""
    specs = _study().get("analysis_specs", [])
    candidates = [spec for spec in specs if spec["method_id"] == method_id and spec["outcome_metric_id"] == metric_id]
    defaults = {
        "METH-LONG": {"reference_week": 1, "contrast_week": 10, "alpha": 0.05},
        "METH-REL": {"baseline_weeks": [1], "alpha": 0.05},
        "METH-IND": {"baseline_weeks": [1, 2], "post_weeks": [9, 10]},
    }[method_id]
    base = dict(candidates[0]["parameters"]) if candidates else dict(defaults)
    effective = {**base, **parameters}
    frozen = next(
        (spec for spec in candidates if spec.get("status") == "FROZEN" and spec["parameters"] == effective and cohort["id"] == spec["cohort_id"]),
        None,
    )
    return frozen, effective


def _validate_parameters(method_id: str, parameters: dict[str, Any]) -> None:
    if method_id == "METH-LONG":
        reference = parameters.get("reference_week")
        contrast = parameters.get("contrast_week")
        if not isinstance(reference, int) or not isinstance(contrast, int) or not 1 <= reference < contrast <= 16:
            raise HTTPException(status_code=422, detail="reference_week and contrast_week must be integers with 1 ≤ reference < contrast ≤ 16")
    if method_id == "METH-REL":
        weeks = parameters.get("baseline_weeks")
        if not isinstance(weeks, list) or not weeks or not all(isinstance(week, int) and 1 <= week <= 16 for week in weeks):
            raise HTTPException(status_code=422, detail="baseline_weeks must be a non-empty list of weeks 1–16")
    if method_id == "METH-IND" and (parameters.get("baseline_weeks") != [1, 2] or parameters.get("post_weeks") != [9, 10]):
        raise HTTPException(status_code=422, detail="METH-IND v1.1.0 supports only baseline weeks 1–2 and post weeks 9–10")


@app.post("/analyses/execute")
def execute_analysis(request: AnalysisRequest) -> dict[str, Any]:
    """Execute a method and append a new immutable AnalysisRun.

    Completed runs are never mutated and execution does not create evidence:
    an EvidenceArtifact only exists after an explicit promotion of a run.
    """
    _ensure_data()
    if request.method_id not in {"METH-LONG", "METH-REL", "METH-IND"}:
        raise HTTPException(status_code=422, detail=f"Unknown method: {request.method_id}")
    started = time.perf_counter()
    metric = _metric(request.outcome_metric_id)
    cohort = _cohort_for(excluded=request.excluded_subject_ids, included=request.subject_ids)
    frozen_spec, parameters = _resolve_spec(request.method_id, request.outcome_metric_id, request.parameters, cohort)
    _validate_parameters(request.method_id, parameters)
    members = set(cohort["subject_ids"])
    trial_rows = [row for row in _rows("cmj_trials") if row["subject_id"] in members]
    if request.method_id == "METH-REL":
        result = _reliability(trial_rows, metric["column"], tuple(parameters["baseline_weeks"]))
    elif request.method_id == "METH-IND":
        result = _individual_change(trial_rows, metric["column"])
    else:
        result = _group_longitudinal(trial_rows, metric["column"], parameters["reference_week"], parameters["contrast_week"])
    duration_ms = (time.perf_counter() - started) * 1000
    all_runs = _json("analysis_runs.json", [])
    run_number = max([int(row["id"].split("-")[-1]) for row in all_runs if str(row.get("id", "")).startswith("RUN-")], default=0) + 1
    snapshot = _json("dataset_snapshot.json", {})
    run_id = f"RUN-{run_number:04d}"
    if frozen_spec is not None:
        spec = frozen_spec
        plan_alignment = "PLANNED"
    else:
        # Exploratory specs are content-addressed: the same method, outcome,
        # parameters and cohort always resolve to the same specification.
        spec_digest = hashlib.sha256(json.dumps([request.method_id, request.outcome_metric_id, parameters, cohort["id"]], sort_keys=True).encode("utf-8")).hexdigest()[:8].upper()
        spec = {
            "id": f"SPEC-X-{spec_digest}",
            "study_id": "STUDY-001",
            "name": f"Exploratory {request.method_id} on {metric['label']}",
            "method_id": request.method_id,
            "method_version": "1.1.0",
            "cohort_id": cohort["id"],
            "snapshot_id": SNAPSHOT_ID,
            "outcome_metric_id": request.outcome_metric_id,
            "model_formula": result.get("formula", result.get("method", "")),
            "parameters": parameters,
            "planned_contrasts": [result.get("primary_contrast_id", result.get("method", ""))],
            "status": "EXPLORATORY",
            "deviates_from": [item["id"] for item in _study().get("analysis_specs", []) if item["method_id"] == request.method_id],
        }
        plan_alignment = "EXPLORATORY"
    diagnostics = result.get("diagnostics") or {"model_status": result.get("status", "DESCRIPTIVE"), "n_subjects": result.get("n_subjects")}
    run = {
        "id": run_id,
        "analysis_spec_id": spec["id"],
        "study_id": "STUDY-001",
        "snapshot_id": SNAPSHOT_ID,
        "cohort_id": cohort["id"],
        "method_id": request.method_id,
        "outcome_metric_id": request.outcome_metric_id,
        "status": "COMPLETED",
        "plan_alignment": plan_alignment,
        "created_at": _now(),
        "duration_ms": round(duration_ms, 3),
        "software_versions": {"service": "dynamis-science@0.2.0", "python": platform.python_version(), "numpy": np.__version__},
        "seed": snapshot.get("seed"),
        "parameters": parameters,
        "result": result,
        "diagnostics": diagnostics,
        "output_artifact_ids": [],
        "result_digest": result_digest(request.method_id, result),
        "reproducibility_key": reproducibility_key(SNAPSHOT_ID, spec["id"], metric["id"], cohort["subject_ids"], parameters),
        "execution": {"analysis_spec": spec, "cohort": cohort},
    }
    all_runs.append(run)
    _write_json("analysis_runs.json", all_runs)
    return _run_view(run, all_runs, _json("evidence.json", []))


def _evidence_payload(run: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the immutable evidence and figure artefacts for a completed run."""
    method_id = run["method_id"]
    metric_id = run.get("outcome_metric_id") or (run.get("execution") or {}).get("analysis_spec", {}).get("outcome_metric_id", "MET-CMJ-IMPULSE")
    metric = _metric(metric_id)
    result = run["result"].get("primary", run["result"]) if method_id == "METH-LONG" else run["result"]
    cohort = (run.get("execution") or {}).get("cohort") or _study().get("cohort", {})
    snapshot = _json("dataset_snapshot.json", {})
    planned = run.get("plan_alignment") == "PLANNED"
    interval = None
    contrast_id = None
    if method_id == "METH-REL":
        computed = result.get("status") == "COMPUTED"
        kind = "RELIABILITY"
        value = result.get("icc_3_1")
        unit = "ICC(3,1)"
        uncertainty = (result["icc_3_1_ci_high"] - result["icc_3_1_ci_low"]) / 2 if computed else None
        uncertainty_label = "95% CI half-width" if computed else None
        interval = {"low": result.get("icc_3_1_ci_low"), "high": result.get("icc_3_1_ci_high"), "level": 0.95, "kind": "Shrout–Fleiss F-based 95% CI"} if computed else None
        sample_size = result.get("n_subjects", 0)
        effect_size = result.get("mean_cv_percent")
        title = f"Repeated-trial reliability for {metric['label'].lower()}"
        interpretation = (
            f"ICC(3,1) was {_safe_float(result.get('icc_3_1')):.3f}; typical error {_safe_float(result.get('typical_error')):.3f} "
            f"{metric['unit']} and mean within-subject CV {_safe_float(result.get('mean_cv_percent')):.1f}%."
        ) if computed else str(result.get("message", "Insufficient data"))
        quality = "VALID" if computed else "WARNING"
    elif method_id == "METH-IND":
        kind = "CHANGE"
        value = result["standardized_change"]
        unit = "SD"
        uncertainty = result["typical_error"]
        uncertainty_label = "typical error of a change"
        sample_size = result["n_subjects"]
        effect_size = result["standardized_change"]
        title = f"Individual change context for {metric['label'].lower()}"
        interpretation = (
            f"Median individual change was {result['median_change']:.3f} {metric['unit']} "
            f"({result['standardized_change']:.2f} SD) against a typical error of {result['typical_error']:.3f} {metric['unit']}."
        )
        quality = "EXPLORATORY"
    else:
        contrast_id = result["primary_contrast_id"]
        contrast = result["contrasts"][contrast_id]
        kind = "EFFECT"
        value = contrast["estimate"]
        unit = metric["unit"]
        uncertainty = contrast["std_error"]
        uncertainty_label = "SE"
        interval = {"low": contrast["ci_low"], "high": contrast["ci_high"], "level": 0.95, "kind": "Wald 95% CI"}
        sample_size = result["n_observations"]
        effect_size = result.get("effect_size")
        title = f"Intervention × Time effect on {metric['label'].lower()}"
        interpretation = (
            f"From week {result['reference_week']} to week {result['contrast_week']} the intervention arm changed by "
            f"{contrast['estimate']:.4g} {metric['unit']} more than the comparison arm (95% CI {contrast['ci_low']:.4g} to "
            f"{contrast['ci_high']:.4g}; {result['n_subjects']} athletes, {result['n_observations']} observations) using {result['method']}. "
            "Synthetic-data demonstration, not a clinical or performance claim."
        )
        quality = "VALID" if result.get("converged") or result.get("estimator") == "OLS_CLUSTER_ROBUST" else "WARNING"
    evidence_class = ("CONFIRMATORY" if method_id == "METH-LONG" else "PLANNED") if planned else "EXPLORATORY"
    evidence = {
        "title": title,
        "kind": kind,
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "estimate": value,
        "uncertainty": uncertainty,
        "uncertainty_label": uncertainty_label,
        "interval": interval,
        "effect_size": effect_size,
        "contrast_id": contrast_id,
        "population": f"{cohort.get('name', cohort.get('id'))} ({len(cohort.get('subject_ids', []))} synthetic athletes)",
        "sample_size": sample_size,
        "protocol_id": "PROT-CMJ",
        "dataset_snapshot_id": run["snapshot_id"],
        "analysis_run_id": run["id"],
        "analysis_spec_id": run["analysis_spec_id"],
        "cohort_id": run["cohort_id"],
        "diagnostics": run.get("diagnostics", {}),
        "quality": quality,
        "evidence_class": evidence_class,
        "reproducibility_key": run.get("reproducibility_key"),
        "result_digest": run.get("result_digest"),
        "version": 1,
        "state": "CURRENT",
        "provenance": {
            "source": "cmj_trials.parquet",
            "algorithm": result.get("method", "local estimator"),
            "algorithm_version": "1.1.0",
            "snapshot_checksum": snapshot.get("checksums", {}).get("cmj_trials.parquet"),
            "seed": snapshot.get("seed"),
            "estimator": result.get("estimator"),
            "executed_at": run.get("created_at"),
            "promoted_from_run": run["id"],
        },
        "interpretation": interpretation,
    }
    if kind == "EFFECT":
        figure_spec = {"x": "week", "y": metric["label"], "unit": metric["unit"], "series": ["INTERVENTION", "COMPARISON"], "metric_id": metric_id, "cohort_id": run["cohort_id"], "subject_ids": cohort.get("subject_ids", []), "summary": "arm weekly mean ± 95% CI of first valid trials", "source_artifact": "cmj_trials.parquet"}
        figure_kind = "LINE"
        figure_title = f"{metric['label']} response by intervention arm"
    elif kind == "RELIABILITY":
        figure_spec = {"x": "within-subject CV", "unit": "%", "values": [row["cv_percent"] for row in result.get("cv_percent_by_subject", [])], "source_artifact": f"analysis_runs.json#{run['id']}.result.cv_percent_by_subject"}
        figure_kind = "DISTRIBUTION"
        figure_title = f"Within-subject CV · {metric['label'].lower()}"
    else:
        figure_spec = {"x": "baseline", "y": "change", "unit": metric["unit"], "points": [{"subject_id": row["subject_id"], "baseline": row["baseline"], "change": row["change"]} for row in result.get("athletes", [])], "typical_error": result.get("typical_error"), "source_artifact": f"analysis_runs.json#{run['id']}.result.athletes"}
        figure_kind = "SCATTER"
        figure_title = f"Individual change versus baseline · {metric['label'].lower()}"
    figure = {"title": figure_title, "kind": figure_kind, "dataset_snapshot_id": run["snapshot_id"], "analysis_run_id": run["id"], "spec": figure_spec}
    return evidence, figure


def _evidence_view(item: dict[str, Any], evidence: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    reproduces = [
        other["id"]
        for other in evidence
        if other["id"] < item["id"]
        and other.get("reproducibility_key") == item.get("reproducibility_key")
        and other.get("result_digest") == item.get("result_digest")
    ]
    reproduced_by = [
        other["id"]
        for other in evidence
        if other["id"] > item["id"]
        and other.get("reproducibility_key") == item.get("reproducibility_key")
        and other.get("result_digest") == item.get("result_digest")
    ]
    superseded_by = [
        other["id"]
        for other in evidence
        if other["id"] > item["id"]
        and other.get("reproducibility_key") == item.get("reproducibility_key")
        and other.get("result_digest") != item.get("result_digest")
    ]
    return {
        **item,
        "reproduces": reproduces,
        "reproduced_by": reproduced_by,
        "state": "SUPERSEDED" if superseded_by else item.get("state", "CURRENT"),
        "superseded_by": superseded_by,
        "cited_by_report": item["id"] in report.get("evidence_ids", []),
    }


@app.post("/evidence")
def promote_evidence(request: PromotionRequest) -> dict[str, Any]:
    """Explicitly promote a completed run to an immutable EvidenceArtifact."""
    _ensure_data()
    all_runs = _json("analysis_runs.json", [])
    run = _find(all_runs, "id", request.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.get("status") != "COMPLETED":
        raise HTTPException(status_code=409, detail=f"{run['id']} is {run.get('status')}; only completed runs can be promoted")
    if not run.get("diagnostics"):
        raise HTTPException(status_code=422, detail=f"{run['id']} has no diagnostics; a result without diagnostics cannot become evidence")
    all_evidence = _json("evidence.json", [])
    report = _json("report.json", {})
    existing = next((item for item in all_evidence if item.get("analysis_run_id") == run["id"]), None)
    if existing is not None:
        figure = next((figure for figure in _json("figures.json", []) if existing["id"] in figure.get("evidence_ids", [])), None)
        return {"evidence_artifact": _evidence_view(existing, all_evidence, report), "figure_artifact": figure, "already_promoted": True}
    all_figures = _json("figures.json", [])
    evidence, figure = _evidence_payload(run)
    evidence_number = max([int(item["id"].split("-")[-1]) for item in all_evidence if str(item.get("id", "")).startswith("EVID-")], default=0) + 1
    figure_number = max([int(item["id"].split("-")[-1]) for item in all_figures if str(item.get("id", "")).startswith("FIG-")], default=0) + 1
    evidence_id = f"EVID-{evidence_number:04d}"
    figure_id = f"FIG-{figure_number:04d}"
    created_at = _now()
    evidence = {"id": evidence_id, **evidence, "created_at": created_at, "figure_ids": [figure_id]}
    figure = {"id": figure_id, **figure, "evidence_ids": [evidence_id], "created_at": created_at}
    all_evidence.append(evidence)
    all_figures.append(figure)
    _write_json("evidence.json", all_evidence)
    _write_json("figures.json", all_figures)
    return {"evidence_artifact": _evidence_view(evidence, all_evidence, report), "figure_artifact": figure, "already_promoted": False}


@app.get("/evidence")
def evidence() -> list[dict[str, Any]]:
    _ensure_data()
    items = _json("evidence.json", [])
    report = _json("report.json", {})
    return [_evidence_view(item, items, report) for item in items]


@app.get("/evidence/{evidence_id}")
def evidence_detail(evidence_id: str) -> dict[str, Any]:
    _ensure_data()
    items = _json("evidence.json", [])
    item = _find(items, "id", evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    figures = [figure for figure in _json("figures.json", []) if evidence_id in figure.get("evidence_ids", [])]
    report = _json("report.json", {})
    return {
        **_evidence_view(item, items, report),
        "lineage": _lineage_for(evidence_id),
        "source_runs": [run for run in _json("analysis_runs.json", []) if run.get("id") == item.get("analysis_run_id")],
        "figures": figures,
    }


def _figure_data(figure: dict[str, Any]) -> dict[str, Any]:
    spec = figure.get("spec", {})
    if figure.get("kind") == "LINE":
        metric = _metric(spec.get("metric_id", "MET-CMJ-IMPULSE"))
        members = set(spec.get("subject_ids") or _all_subject_ids())
        rows = [row for row in _rows("cmj_trials") if row["subject_id"] in members and row["quality_state"] == "VALID" and row["trial_number"] == 1]
        series = []
        for arm in ("INTERVENTION", "COMPARISON"):
            for week in range(1, 17):
                values = [float(row[metric["column"]]) for row in rows if row["intervention_arm"] == arm and row["week"] == week]
                n = len(values)
                mean = float(np.mean(values)) if n else None
                sd = float(np.std(values, ddof=1)) if n > 1 else None
                half = _t_critical(n - 1) * sd / math.sqrt(n) if sd is not None else None
                series.append({"arm": arm, "week": week, "n": n, "mean": mean, "sd": sd, "ci_low": mean - half if mean is not None and half is not None else None, "ci_high": mean + half if mean is not None and half is not None else None})
        return {"kind": "LINE", "unit": metric["unit"], "metric": metric, "series": series}
    if figure.get("kind") == "DISTRIBUTION":
        return {"kind": "DISTRIBUTION", "unit": spec.get("unit", "%"), "values": spec.get("values", [])}
    return {"kind": figure.get("kind"), "unit": spec.get("unit"), "points": spec.get("points", []), "typical_error": spec.get("typical_error")}


@app.get("/figures")
def figures() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("figures.json", [])


@app.get("/figures/{figure_id}")
def figure_detail(figure_id: str) -> dict[str, Any]:
    _ensure_data()
    figure = _find(_json("figures.json", []), "id", figure_id)
    if figure is None:
        raise HTTPException(status_code=404, detail="Figure not found")
    return {**figure, "data": _figure_data(figure), "cited_by_report": figure_id in _json("report.json", {}).get("figure_ids", [])}


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def _section_for(artifact_id: str) -> str:
    evidence = _find(_json("evidence.json", []), "id", artifact_id)
    figure = _find(_json("figures.json", []), "id", artifact_id)
    if figure is not None and figure.get("evidence_ids"):
        evidence = _find(_json("evidence.json", []), "id", figure["evidence_ids"][0])
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"{artifact_id} is not a stored evidence or figure artifact")
    if evidence.get("evidence_class") == "EXPLORATORY":
        return "Exploratory results"
    return "Intervention result" if evidence.get("kind") == "EFFECT" else "Reliability context"


@app.get("/report")
def report() -> dict[str, Any]:
    _ensure_data()
    report_artifact = _json("report.json", {})
    evidence_items = _json("evidence.json", [])
    figures_items = _json("figures.json", [])
    cited_evidence = [_evidence_view(item, evidence_items, report_artifact) for item in evidence_items if item["id"] in report_artifact.get("evidence_ids", [])]
    cited_figures = [{**figure, "data": _figure_data(figure)} for figure in figures_items if figure["id"] in report_artifact.get("figure_ids", [])]
    runs_by_id = {run["id"]: run for run in _json("analysis_runs.json", [])}
    study = _study()
    return {
        **report_artifact,
        "evidence": cited_evidence,
        "figures": cited_figures,
        "runs": [runs_by_id[item["analysis_run_id"]] for item in cited_evidence if item["analysis_run_id"] in runs_by_id],
        "snapshot": _json("dataset_snapshot.json", {}),
        "study": study.get("study", {}),
        "question": study.get("question", {}),
        "hypotheses": study.get("hypotheses", []),
        "plan": study.get("plan", {}),
        "cohort": study.get("cohort", {}),
        "groups": study.get("groups", {}),
        "data_health": _data_health(),
        "longitudinal_signal": _json("overview_signal.json", []),
    }


@app.post("/report/citations")
def add_citation(request: CitationRequest) -> dict[str, Any]:
    """Cite an immutable evidence or figure artefact in the draft report."""
    _ensure_data()
    report_artifact = _json("report.json", {})
    section = request.section or _section_for(request.artifact_id)
    if section not in REPORT_SECTIONS:
        raise HTTPException(status_code=422, detail=f"Unknown report section: {section}")
    is_figure = request.artifact_id.startswith("FIG-")
    key = "figure_ids" if is_figure else "evidence_ids"
    if request.artifact_id in report_artifact.get(key, []):
        return {"report_id": report_artifact["id"], "artifact_id": request.artifact_id, "section": section, "already_cited": True}
    report_artifact.setdefault(key, []).append(request.artifact_id)
    report_artifact.setdefault("citations", []).append({"artifact_id": request.artifact_id, "section": section, "added_at": _now()})
    report_artifact["updated_at"] = _now()
    _write_json("report.json", report_artifact)
    return {"report_id": report_artifact["id"], "artifact_id": request.artifact_id, "section": section, "already_cited": False}


@app.delete("/report/citations/{artifact_id}")
def remove_citation(artifact_id: str) -> dict[str, Any]:
    _ensure_data()
    report_artifact = _json("report.json", {})
    key = "figure_ids" if artifact_id.startswith("FIG-") else "evidence_ids"
    if artifact_id not in report_artifact.get(key, []):
        raise HTTPException(status_code=404, detail=f"{artifact_id} is not cited in the report")
    report_artifact[key] = [item for item in report_artifact[key] if item != artifact_id]
    report_artifact["citations"] = [item for item in report_artifact.get("citations", []) if item["artifact_id"] != artifact_id]
    report_artifact["updated_at"] = _now()
    _write_json("report.json", report_artifact)
    return {"report_id": report_artifact["id"], "artifact_id": artifact_id, "removed": True}


# --------------------------------------------------------------------------- #
# Investigations (serialisable workbench documents)
# --------------------------------------------------------------------------- #


def _validate_blocks(blocks: list[InvestigationBlock]) -> None:
    seen: set[str] = set()
    for block in blocks:
        if block.type not in BLOCK_TYPES:
            raise HTTPException(status_code=422, detail=f"Unknown block type: {block.type}")
        if block.id in seen:
            raise HTTPException(status_code=422, detail=f"Duplicate block ID: {block.id}")
        for key in BLOCK_DEPENDENCY_KEYS:
            reference = block.state.get(key)
            if reference and reference not in seen:
                raise HTTPException(status_code=422, detail=f"{block.id} depends on {reference}, which must appear earlier in the investigation")
        seen.add(block.id)


@app.get("/investigations")
def investigations(study_id: str = "STUDY-001") -> list[dict[str, Any]]:
    _ensure_data()
    return [item for item in _json("investigations.json", []) if item.get("study_id") == study_id]


@app.get("/investigations/{investigation_id}")
def investigation(investigation_id: str) -> dict[str, Any]:
    _ensure_data()
    item = _find(_json("investigations.json", []), "id", investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return item


@app.put("/investigations/{investigation_id}")
def update_investigation(investigation_id: str, request: InvestigationUpdate) -> dict[str, Any]:
    _ensure_data()
    items = _json("investigations.json", [])
    item = _find(items, "id", investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if request.base_version is not None and request.base_version != item["version"]:
        raise HTTPException(status_code=409, detail=f"Investigation is at version {item['version']}, not {request.base_version}")
    _validate_blocks(request.blocks)
    item["blocks"] = [block.model_dump() for block in request.blocks]
    if request.title:
        item["title"] = request.title
    item["version"] += 1
    item["updated_at"] = _now()
    _write_json("investigations.json", items)
    return item


# --------------------------------------------------------------------------- #
# Lineage
# --------------------------------------------------------------------------- #


def _lineage_for(artifact_id: str) -> dict[str, Any]:
    return build_lineage_graph(
        artifact_id=artifact_id,
        snapshot=_json("dataset_snapshot.json", {}),
        study=_study(),
        registry=_json("registry.json", {}),
        runs=_json("analysis_runs.json", []),
        evidence=_json("evidence.json", []),
        figures=_json("figures.json", []),
        report=_json("report.json", {}),
        model_spec=_json("model_spec.json", {}),
        model_run=_json("model_run.json", {}),
        trial_rows=_rows("cmj_trials") if artifact_id.startswith("CMJ-") else None,
    )


@app.get("/lineage")
def lineage_root() -> dict[str, Any]:
    _ensure_data()
    return _lineage_for("REPORT-001")


@app.get("/lineage/{artifact_id}")
def lineage(
    artifact_id: str,
    scope: str = Query(default="full", pattern="^(full|path)$"),
    depth: int = Query(default=3, ge=1, le=8),
) -> dict[str, Any]:
    _ensure_data()
    graph = _lineage_for(artifact_id)
    return scope_lineage_graph(graph, descendant_depth=depth) if scope == "path" else graph


# --------------------------------------------------------------------------- #
# Mechanistic model
# --------------------------------------------------------------------------- #


@app.get("/models/training-response")
def model_training_response() -> dict[str, Any]:
    _ensure_data()
    return {
        "spec": _json("model_spec.json", {}),
        "run": _json("model_run.json", {}),
        "snapshot": _json("dataset_snapshot.json", {}),
        "load_series": [row["training_impulse_au"] for row in sorted(_rows("training_load"), key=lambda item: (item["week"], item["subject_id"])) if row["subject_id"] == "SUB-001"],
    }


@app.post("/models/training-response/simulate")
def model_simulate(request: SimulationRequest) -> dict[str, Any]:
    _ensure_data()
    if not request.load_values:
        raise HTTPException(status_code=422, detail="At least one weekly load value is required")
    if len(request.load_values) > 52:
        raise HTTPException(status_code=422, detail="Simulation horizon is bounded to 52 weeks")
    return simulate_training_response(request.load_values, request.parameters)


@app.post("/models/training-response/scenario")
def model_scenario(request: ScenarioRequest) -> dict[str, Any]:
    """Forward-simulate the fitted model over a future weekly load scenario."""
    _ensure_data()
    if not 1 <= len(request.future_load_au) <= 24:
        raise HTTPException(status_code=422, detail="A scenario covers between 1 and 24 future weeks")
    if any(not math.isfinite(value) or value < 0 or value > 2000 for value in request.future_load_au):
        raise HTTPException(status_code=422, detail="Scenario load values must be finite and within 0–2000 AU")
    model_run = _json("model_run.json", {})
    result = simulate_scenario(model_run, request.future_load_au)
    digest = hashlib.sha256(json.dumps([model_run.get("id"), request.future_load_au]).encode("utf-8")).hexdigest()[:10].upper()
    return {**result, "scenario_id": f"SCN-{digest}", "persisted": False}
