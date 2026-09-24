from __future__ import annotations

import json
import math
import os
import platform
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import numpy as np
import polars as pl
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .analysis import (
    _group_longitudinal,
    _individual_change,
    _reliability,
    _safe_float,
    simulate_training_response,
)
from .generate import ARTIFACT_DIR, PARQUET_DIR, SNAPSHOT_ID, generate_data
from .lineage import build_lineage_graph

@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_data()
    yield


app = FastAPI(title="DynamisScience Local Science Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    method_id: str = "METH-LONG"
    outcome_metric_id: str = "MET-CMJ-IMPULSE"
    subject_ids: list[str] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class SimulationRequest(BaseModel):
    load_values: list[float]
    parameters: dict[str, float] = Field(default_factory=dict)


def _ensure_data() -> None:
    if not (ARTIFACT_DIR / "dataset_snapshot.json").exists() or not (PARQUET_DIR / "cmj_trials.parquet").exists():
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


def _parquet(name: str) -> pl.DataFrame:
    path = PARQUET_DIR / f"{name}.parquet"
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _rows(name: str) -> list[dict[str, Any]]:
    return _parquet(name).to_dicts()


def _find(items: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
    return next((item for item in items if str(item.get(key)) == value), None)


def _metric_columns() -> dict[str, dict[str, Any]]:
    return {
        "MET-CMJ-IMPULSE": {"column": "concentric_impulse_n_s_kg", "label": "Concentric impulse", "unit": "N·s·kg⁻¹", "id": "cmj.concentric_impulse"},
        "MET-CMJ-HEIGHT": {"column": "jump_height_cm", "label": "Jump height", "unit": "cm", "id": "cmj.jump_height.flight_time"},
        "MET-CMJ-BRAKING-DURATION": {"column": "eccentric_braking_duration_s", "label": "Braking duration", "unit": "s", "id": "cmj.eccentric_braking_duration"},
        "MET-CMJ-BRAKING-IMPULSE": {"column": "eccentric_braking_impulse_n_s_kg", "label": "Braking impulse", "unit": "N·s·kg⁻¹", "id": "cmj.eccentric_braking_impulse"},
        "MET-CMJ-POWER": {"column": "peak_power_w_kg", "label": "Peak power", "unit": "W·kg⁻¹", "id": "cmj.peak_power"},
        "MET-CMJ-DEPTH": {"column": "countermovement_depth_cm", "label": "Countermovement depth", "unit": "cm", "id": "cmj.countermovement_depth"},
        "MET-CMJ-RSI-MOD": {"column": "rsi_mod", "label": "RSI-mod", "unit": "cm·s⁻¹", "id": "cmj.rsi_mod"},
    }


@app.get("/health")
def health() -> dict[str, Any]:
    _ensure_data()
    return {"status": "ok", "service": "dynamis-science", "snapshot_id": SNAPSHOT_ID, "mode": "local-synthetic"}


def _data_health() -> dict[str, Any]:
    """Provenance completeness is computed from stored records, never asserted."""
    trials = _rows("cmj_trials")
    evidence = _json("evidence.json", [])
    expected_slots = 28 * 16 * 2
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
        "missing_slots": _json("missing_observations.json", []),
        "complete_records": numerator,
        "total_records": denominator,
        "provenance_completeness": completeness,
        "total_subjects": len({row["subject_id"] for row in trials}),
    }


@app.get("/overview")
def overview() -> dict[str, Any]:
    _ensure_data()
    snapshot = _json("dataset_snapshot.json", {})
    study = _json("study.json", {})
    runs = _json("analysis_runs.json", [])
    evidence = _json("evidence.json", [])
    return {
        "snapshot": snapshot,
        "study": study.get("study", {}),
        "research_question": study.get("question", {}),
        "groups": study.get("groups", {}),
        "plan": study.get("plan", {}),
        "recent_analyses": runs[-3:][::-1],
        "evidence_artifacts": evidence,
        "data_health": _data_health(),
        "longitudinal_signal": _json("overview_signal.json", []),
        "registries": _json("registry.json", {}),
        "figures": _json("figures.json", []),
    }


@app.get("/studies")
def studies() -> list[dict[str, Any]]:
    _ensure_data()
    study = _json("study.json", {})
    return [study.get("study", {})]


@app.get("/studies/{study_id}")
def study_detail(study_id: str) -> dict[str, Any]:
    _ensure_data()
    study = _json("study.json", {})
    if study_id != "STUDY-001":
        raise HTTPException(status_code=404, detail="Study not found")
    subjects = _rows("subjects")
    arms: dict[str, int] = {}
    for subject in subjects:
        arms[subject["intervention_arm"]] = arms.get(subject["intervention_arm"], 0) + 1
    positions: dict[str, int] = {}
    for subject in subjects:
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
    load_rows = [row for row in _rows("training_load") if row["subject_id"] == subject_id]
    load_lookup = {row["week"]: row for row in load_rows}
    wellness = {row["week"]: row for row in _rows("wellness") if row["subject_id"] == subject_id}
    baseline_values = [
        float(row[column])
        for row in subject_trials
        if row["week"] in (1, 2) and row["quality_state"] == "VALID"
    ]
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
    return frame.sort(["week", "subject_id", "trial_number"], descending=[True, False, False]).head(limit).to_dicts()


@app.get("/force/trials/{trial_id}")
def force_trial(trial_id: str) -> dict[str, Any]:
    _ensure_data()
    trial = _find(_rows("cmj_trials"), "trial_id", trial_id)
    if trial is None:
        raise HTTPException(status_code=404, detail="Trial not found")
    trace = _parquet("force_traces").filter(pl.col("trial_id") == trial_id)
    boundaries = json.loads(trial.get("phase_boundaries", "{}")) if isinstance(trial.get("phase_boundaries"), str) else trial.get("phase_boundaries", {})
    registry = _json("registry.json", {})
    return {
        "trial": trial,
        "boundaries": boundaries,
        "trace": trace.to_dicts(),
        "trace_available": bool(trace.height),
        "method": {
            "algorithm": "cmj-metrics",
            "algorithm_version": "1.0.0",
            "sample_rate_hz": 1000,
            "integration": "trapezoidal net-force integration",
            "phase_detection": "deterministic phase template",
            "metrics": registry.get("metrics", []),
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
        "provenance": {"snapshot_id": SNAPSHOT_ID, "source": ["match_tracking.parquet", "match_pose.parquet"], "mode": "SYNTHETIC"},
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
        first = values.to_dicts()[0]
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
        first = group[1].to_dicts()[0]
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


@app.get("/registry")
def registry() -> dict[str, Any]:
    _ensure_data()
    return _json("registry.json", {})


@app.get("/registry/metrics")
def registry_metrics() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("registry.json", {}).get("metrics", [])


@app.get("/registry/protocols")
def registry_protocols() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("registry.json", {}).get("protocols", [])


@app.get("/runs")
def runs() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("analysis_runs.json", [])[::-1]


@app.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    _ensure_data()
    run = _find(_json("analysis_runs.json", []), "id", run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        **run,
        "lineage": _lineage_for(run_id),
        "evidence": [item for item in _json("evidence.json", []) if item.get("analysis_run_id") == run_id],
    }


@app.post("/analyses/execute")
def execute_analysis(request: AnalysisRequest) -> dict[str, Any]:
    """Execute a frozen method and persist a new immutable run plus its evidence.

    Completed runs are never mutated: the ledger is append-only and the
    configuration that produced a run is captured in its AnalysisSpec reference.
    """
    _ensure_data()
    started = time.perf_counter()
    all_runs = _json("analysis_runs.json", [])
    all_evidence = _json("evidence.json", [])
    all_figures = _json("figures.json", [])
    trial_rows = _rows("cmj_trials")
    selected_subject_ids = sorted(request.subject_ids) if request.subject_ids else []
    if selected_subject_ids:
        selected = set(selected_subject_ids)
        trial_rows = [row for row in trial_rows if row["subject_id"] in selected]
    metrics = _metric_columns()
    if request.outcome_metric_id not in metrics:
        raise HTTPException(status_code=422, detail=f"Unknown outcome metric: {request.outcome_metric_id}")
    metric = metrics[request.outcome_metric_id]
    if request.method_id == "METH-REL":
        result = _reliability(trial_rows, metric["column"])
        evidence_kind = "RELIABILITY"
        value = result.get("icc_3_1")
        unit = "ICC(3,1)"
        uncertainty = (result.get("icc_3_1_ci_high", 0) - result.get("icc_3_1_ci_low", 0)) / 2 if result.get("status") == "COMPUTED" else None
        uncertainty_label = "95% CI half-width" if uncertainty is not None else None
        sample_size = result.get("n_subjects", 0)
        interpretation = (
            f"ICC(3,1) was {_safe_float(result.get('icc_3_1')):.3f}; typical error {_safe_float(result.get('typical_error')):.3f} "
            f"{metric['unit']} and mean within-subject CV {_safe_float(result.get('mean_cv_percent')):.1f}%."
        )
        quality = "VALID" if result.get("status") == "COMPUTED" else "WARNING"
    elif request.method_id == "METH-IND":
        result = _individual_change(trial_rows, metric["column"])
        evidence_kind = "CHANGE"
        value = result["standardized_change"]
        unit = "SD"
        uncertainty = result["typical_error"]
        uncertainty_label = "typical error of a change"
        sample_size = result["n_subjects"]
        interpretation = (
            f"Median individual change was {result['median_change']:.3f} {metric['unit']} "
            f"({result['standardized_change']:.2f} SD) against a typical error of {result['typical_error']:.3f}."
        )
        quality = "EXPLORATORY"
    else:
        result = _group_longitudinal(trial_rows, metric["column"])
        contrast = result["contrasts"][result["primary_contrast_id"]]
        evidence_kind = "EFFECT"
        value = contrast["estimate"]
        unit = metric["unit"]
        uncertainty = contrast["std_error"]
        uncertainty_label = "SE"
        sample_size = result["n_observations"]
        interpretation = (
            f"{contrast['contrast']}: {contrast['estimate']:.3f} {metric['unit']} "
            f"(95% CI {contrast['ci_low']:.3f} to {contrast['ci_high']:.3f}) using {result['method']}."
        )
        quality = "VALID"
    duration_ms = (time.perf_counter() - started) * 1000
    run_number = max([int(row["id"].split("-")[-1]) for row in all_runs if str(row.get("id", "")).startswith("RUN-")], default=0) + 1
    evidence_number = max([int(item["id"].split("-")[-1]) for item in all_evidence if str(item.get("id", "")).startswith("EVID-")], default=0) + 1
    figure_number = max([int(item["id"].split("-")[-1]) for item in all_figures if str(item.get("id", "")).startswith("FIG-")], default=0) + 1
    snapshot = _json("dataset_snapshot.json", {})
    run_id = f"RUN-{run_number:04d}"
    evidence_id = f"EVID-{evidence_number:04d}"
    figure_id = f"FIG-{figure_number:04d}"
    spec_id = f"SPEC-EXEC-{run_number:04d}"
    cohort_id = "COHORT-001" if not selected_subject_ids else f"COHORT-EXEC-{run_number:04d}"
    parameters = {"reference_week": 1, "contrast_week": 10, **request.parameters}
    run = {
        "id": run_id,
        "analysis_spec_id": spec_id,
        "study_id": "STUDY-001",
        "snapshot_id": SNAPSHOT_ID,
        "cohort_id": cohort_id,
        "method_id": request.method_id,
        "status": "COMPLETED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round(duration_ms, 3),
        "software_versions": {"service": "dynamis-science@0.1.0", "python": platform.python_version(), "numpy": np.__version__},
        "seed": snapshot.get("seed"),
        "result": result,
        "diagnostics": result.get("diagnostics", {"model_status": result.get("model_status", "DESCRIPTIVE")}),
        "output_artifact_ids": [evidence_id, figure_id],
        "reproducibility_key": f"{SNAPSHOT_ID}:{spec_id}:{metric['id']}:{json.dumps(parameters, sort_keys=True)}",
        "execution": {
            "analysis_spec": {
                "id": spec_id,
                "study_id": "STUDY-001",
                "name": f"Executed {request.method_id} on {metric['label']}",
                "method_id": request.method_id,
                "method_version": "1.1.0",
                "cohort_id": cohort_id,
                "snapshot_id": SNAPSHOT_ID,
                "outcome_metric_id": request.outcome_metric_id,
                "model_formula": result.get("formula", result.get("method", "")),
                "parameters": parameters,
                "planned_contrasts": ["Intervention × Time at week 10 versus comparison"] if request.method_id == "METH-LONG" else [result.get("method", "")],
                "status": "EXPLORATORY",
            },
            "cohort": {
                "id": cohort_id,
                "study_id": "STUDY-001",
                "name": "Executed cohort selection" if selected_subject_ids else "Elite football longitudinal cohort",
                "description": "Explicit subject subset supplied at execution time." if selected_subject_ids else "Frozen study cohort.",
                "subject_ids": selected_subject_ids or [f"SUB-{index:03d}" for index in range(1, 29)],
                "exclusion_criteria": ["Force trace fails deterministic QC rule"],
                "snapshot_id": SNAPSHOT_ID,
                "status": "DRAFT" if selected_subject_ids else "FROZEN",
            },
        },
    }
    evidence = {
        "id": evidence_id,
        "title": f"{metric['label']} · {request.method_id}",
        "kind": evidence_kind,
        "metric_id": request.outcome_metric_id,
        "value": value,
        "unit": unit,
        "estimate": value,
        "uncertainty": uncertainty,
        "uncertainty_label": uncertainty_label,
        "effect_size": result.get("effect_size"),
        "population": "Explicit subject subset" if selected_subject_ids else "Synthetic elite football cohort, weeks 1–16",
        "sample_size": sample_size,
        "protocol_id": "PROT-CMJ",
        "dataset_snapshot_id": SNAPSHOT_ID,
        "analysis_run_id": run_id,
        "diagnostics": result.get("diagnostics", result),
        "quality": quality,
        "provenance": {
            "source": "cmj_trials.parquet",
            "algorithm": result.get("method", "local estimator"),
            "algorithm_version": "1.1.0",
            "snapshot_checksum": snapshot.get("checksums", {}).get("cmj_trials.parquet"),
            "seed": snapshot.get("seed"),
            "executed_at": run["created_at"],
        },
        "interpretation": interpretation,
    }
    figure = {
        "id": figure_id,
        "title": f"{metric['label']} · {evidence_kind.lower()} output",
        "kind": "LINE" if evidence_kind == "EFFECT" else ("DISTRIBUTION" if evidence_kind == "RELIABILITY" else "SCATTER"),
        "evidence_ids": [evidence_id],
        "dataset_snapshot_id": SNAPSHOT_ID,
        "analysis_run_id": run_id,
        "spec": {"x": "week" if evidence_kind == "EFFECT" else "value", "unit": metric["unit"], "source": "executed run"},
    }
    all_runs.append(run)
    all_evidence.append(evidence)
    all_figures.append(figure)
    _write_json("analysis_runs.json", all_runs)
    _write_json("evidence.json", all_evidence)
    _write_json("figures.json", all_figures)
    return {**run, "evidence_artifact": evidence, "figure_artifact": figure}


@app.get("/evidence")
def evidence() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("evidence.json", [])


@app.get("/evidence/{evidence_id}")
def evidence_detail(evidence_id: str) -> dict[str, Any]:
    _ensure_data()
    item = _find(_json("evidence.json", []), "id", evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    figures = [figure for figure in _json("figures.json", []) if evidence_id in figure.get("evidence_ids", [])]
    report = _json("report.json", {})
    return {
        **item,
        "lineage": _lineage_for(evidence_id),
        "source_runs": [run for run in _json("analysis_runs.json", []) if run.get("id") == item.get("analysis_run_id")],
        "figures": figures,
        "cited_by_report": evidence_id in report.get("evidence_ids", []),
    }


@app.get("/figures")
def figures() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("figures.json", [])


@app.get("/report")
def report() -> dict[str, Any]:
    _ensure_data()
    report_artifact = _json("report.json", {})
    evidence_items = _json("evidence.json", [])
    return {
        **report_artifact,
        "evidence": [item for item in evidence_items if item["id"] in report_artifact.get("evidence_ids", [])],
        "figures": [figure for figure in _json("figures.json", []) if figure["id"] in report_artifact.get("figure_ids", [])],
        "snapshot": _json("dataset_snapshot.json", {}),
        "study": _json("study.json", {}).get("study", {}),
        "data_health": _data_health(),
        "longitudinal_signal": _json("overview_signal.json", []),
    }


def _lineage_for(artifact_id: str) -> dict[str, Any]:
    return build_lineage_graph(
        artifact_id=artifact_id,
        snapshot=_json("dataset_snapshot.json", {}),
        study=_json("study.json", {}),
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
def lineage(artifact_id: str) -> dict[str, Any]:
    _ensure_data()
    return _lineage_for(artifact_id)


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
