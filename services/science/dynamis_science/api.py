from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import polars as pl
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .analysis import _group_longitudinal, _individual_change, _reliability, simulate_training_response
from .generate import ARTIFACT_DIR, PARQUET_DIR, ROOT, SNAPSHOT_ID, generate_data

app = FastAPI(title="DynamisScience Local Science Service", version="0.1.0")
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
        "MET-CMJ-POWER": {"column": "peak_power_w_kg", "label": "Peak power", "unit": "W·kg⁻¹", "id": "cmj.peak_power"},
    }


@app.on_event("startup")
def startup() -> None:
    _ensure_data()


@app.get("/health")
def health() -> dict[str, Any]:
    _ensure_data()
    return {"status": "ok", "service": "dynamis-science", "snapshot_id": SNAPSHOT_ID, "mode": "local-synthetic"}


@app.get("/overview")
def overview() -> dict[str, Any]:
    _ensure_data()
    snapshot = _json("dataset_snapshot.json", {})
    study = _json("study.json", {})
    runs = _json("analysis_runs.json", [])
    evidence = _json("evidence.json", [])
    trials = _parquet("cmj_trials")
    subjects = _parquet("subjects")
    valid = int((trials["quality_state"] == "VALID").sum()) if trials.height else 0
    excluded = int((trials["quality_state"] == "EXCLUDED").sum()) if trials.height else 0
    expected = 28 * 16 * 2
    missing_slots = _json("missing_observations.json", [])
    missing = max(0, expected - valid - excluded)
    return {
        "snapshot": snapshot,
        "study": study.get("study", {}),
        "research_question": study.get("question", {}),
        "recent_analyses": runs[-3:][::-1],
        "evidence_artifacts": evidence,
        "data_health": {"valid_measurements": valid, "excluded_measurements": excluded, "missing_observations": missing, "missing_slots": missing_slots, "provenance_completeness": 100.0, "total_subjects": subjects.height},
        "longitudinal_signal": _json("overview_signal.json", []),
        "registries": _json("registry.json", {}),
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
    return {**study, "snapshot": _json("dataset_snapshot.json", {}), "runs": _json("analysis_runs.json", []), "evidence": _json("evidence.json", [])}


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
    metric = _metric_columns().get(metric_id, _metric_columns()["MET-CMJ-IMPULSE"])
    column = metric["column"]
    subject_trials = [row for row in trials if row["subject_id"] == subject_id and row["trial_number"] == 1]
    load = _find(_rows("training_load"), "subject_id", subject_id)
    wellness = {row["week"]: row for row in _rows("wellness") if row["subject_id"] == subject_id}
    observations = []
    for week in range(1, 17):
        week_rows = [row for row in subject_trials if row["week"] == week and row["quality_state"] == "VALID"]
        values = [float(row[column]) for row in week_rows]
        value = float(np.mean(values)) if values else None
        prior = [float(row[column]) for row in subject_trials if row["week"] < week and row["quality_state"] == "VALID"]
        prior_recent = prior[-4:]
        rolling_mean = float(np.mean(prior_recent)) if prior_recent else None
        rolling_sd = float(np.std(prior_recent, ddof=1)) if len(prior_recent) > 1 else None
        typical_error = rolling_sd / math.sqrt(2) if rolling_sd else None
        baseline = [float(row[column]) for row in subject_trials if row["week"] in (1, 2) and row["quality_state"] == "VALID"]
        baseline_mean = float(np.mean(baseline)) if baseline else None
        observations.append({
            "week": week,
            "value": round(value, 6) if value is not None else None,
            "n_trials": len(values),
            "rolling_mean": round(rolling_mean, 6) if rolling_mean is not None else None,
            "rolling_sd": round(rolling_sd, 6) if rolling_sd is not None else None,
            "z_score": round((value - rolling_mean) / rolling_sd, 3) if value is not None and rolling_mean is not None and rolling_sd else None,
            "percent_change_from_baseline": round((value - baseline_mean) / baseline_mean * 100, 2) if value is not None and baseline_mean else None,
            "coefficient_of_variation": round(rolling_sd / rolling_mean * 100, 2) if rolling_mean and rolling_sd else None,
            "typical_error": round(typical_error, 6) if typical_error is not None else None,
            "phase": "Strength block" if 3 <= week <= 10 and subject["intervention_arm"] == "INTERVENTION" else ("Match week" if week in {4, 8, 12, 15} else "Build / recovery"),
            "load": next((row for row in _rows("training_load") if row["subject_id"] == subject_id and row["week"] == week), None),
            "wellness": wellness.get(week),
        })
    return {"subject": subject, "metric": metric, "observations": observations, "typical_error": _individual_change(subject_trials, column).get("typical_error"), "provenance": {"snapshot_id": SNAPSHOT_ID, "source": "cmj_trials.parquet", "quality_rule": "Excluded trials remain visible in registry"}}


@app.get("/subjects/{subject_id}/longitudinal")
def subject_longitudinal(subject_id: str, metric_id: str = "MET-CMJ-IMPULSE") -> dict[str, Any]:
    _ensure_data()
    return _longitudinal_for(subject_id, metric_id)


@app.get("/force/trials")
def force_trials(subject_id: str | None = None, week: int | None = None, quality_state: str | None = None) -> list[dict[str, Any]]:
    _ensure_data()
    frame = _parquet("cmj_trials")
    if subject_id:
        frame = frame.filter(pl.col("subject_id") == subject_id)
    if week:
        frame = frame.filter(pl.col("week") == week)
    if quality_state:
        frame = frame.filter(pl.col("quality_state") == quality_state)
    return frame.sort(["week", "subject_id", "trial_number"], descending=[True, False, False]).to_dicts()


@app.get("/force/trials/{trial_id}")
def force_trial(trial_id: str) -> dict[str, Any]:
    _ensure_data()
    trial = _find(_rows("cmj_trials"), "trial_id", trial_id)
    if trial is None:
        raise HTTPException(status_code=404, detail="Trial not found")
    trace = _parquet("force_traces").filter(pl.col("trial_id") == trial_id)
    boundaries = json.loads(trial.get("phase_boundaries", "{}")) if isinstance(trial.get("phase_boundaries"), str) else trial.get("phase_boundaries", {})
    return {"trial": trial, "boundaries": boundaries, "trace": trace.to_dicts(), "trace_available": bool(trace.height), "method": {"algorithm": "cmj-metrics@1.0.0", "sample_rate_hz": 1000, "integration": "trapezoidal net-force integration", "phase_detection": "deterministic phase template"}}


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
    if athlete_id:
        frame = frame.filter(pl.col("athlete_id") == athlete_id)
    if frame.is_empty():
        raise HTTPException(status_code=404, detail="Pose stream not found")
    frames = []
    for group in frame.group_by("frame", maintain_order=True):
        first = group[1].to_dicts()[0]
        frames.append({"frame": int(first["frame"]), "time_s": float(first["time_s"]), "athlete_id": str(first["athlete_id"]), "joints": group[1].select(["joint", "x_m", "y_m", "z_m", "confidence"]).to_dicts()})
    return {"match_id": match_id, "sample_rate_hz": 10, "frame_count": len(frames), "frames": frames, "topology": ["hip", "left_hip", "right_hip", "knee", "left_knee", "right_knee", "ankle", "left_ankle", "right_ankle", "shoulder", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"]}


@app.get("/registry/metrics")
def registry_metrics() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("registry.json", {}).get("metrics", [])


@app.get("/registry/protocols")
def registry_protocols() -> list[dict[str, Any]]:
    _ensure_data()
    return _json("registry.json", {}).get("protocols", [])


@app.get("/registry")
def registry() -> dict[str, Any]:
    _ensure_data()
    return _json("registry.json", {})


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
    return {**run, "lineage": _json("lineage.json", []), "evidence": [item for item in _json("evidence.json", []) if item.get("analysis_run_id") == run_id]}


@app.post("/analyses/execute")
def execute_analysis(request: AnalysisRequest) -> dict[str, Any]:
    _ensure_data()
    all_runs = _json("analysis_runs.json", [])
    trial_rows = _rows("cmj_trials")
    if request.subject_ids:
        selected = set(request.subject_ids)
        trial_rows = [row for row in trial_rows if row["subject_id"] in selected]
    metric = _metric_columns().get(request.outcome_metric_id, _metric_columns()["MET-CMJ-IMPULSE"])
    if request.method_id == "METH-REL":
        result = _reliability(trial_rows, metric["column"])
    elif request.method_id == "METH-IND":
        result = _individual_change(trial_rows, metric["column"])
    else:
        result = _group_longitudinal(trial_rows, metric["column"])
    next_number = max([int(row["id"].split("-")[-1]) for row in all_runs if row.get("id", "").startswith("RUN-")], default=0) + 1
    run = {
        "id": f"RUN-{next_number:04d}",
        "analysis_spec_id": f"SPEC-EXECUTED-{next_number:04d}",
        "study_id": "STUDY-001",
        "snapshot_id": SNAPSHOT_ID,
        "cohort_id": "COHORT-001",
        "method_id": request.method_id,
        "status": "COMPLETED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 91.4,
        "software_versions": {"service": "dynamis-science@0.1.0"},
        "seed": 20260924,
        "result": result,
        "diagnostics": {"model_status": result.get("model_status", "DESCRIPTIVE")},
        "output_artifact_ids": [],
        "reproducibility_key": f"{SNAPSHOT_ID}:{request.method_id}:{metric['id']}:{json.dumps(request.parameters, sort_keys=True)}",
    }
    all_runs.append(run)
    (ARTIFACT_DIR / "analysis_runs.json").write_text(json.dumps(all_runs, indent=2, sort_keys=True), encoding="utf-8")
    return run


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
    return {**item, "lineage": _json("lineage.json", []), "source_runs": _json("analysis_runs.json", [])}


@app.get("/lineage/{artifact_id}")
def lineage(artifact_id: str) -> dict[str, Any]:
    _ensure_data()
    edges = _json("lineage.json", [])
    return {"artifact_id": artifact_id, "nodes": [
        {"id": "GEN-001", "kind": "generator", "label": "Synthetic generator", "metadata": "dynamis-synthetic@1.0.0"},
        {"id": "RAW-CMJ-001", "kind": "measurement", "label": "Raw CMJ force signal", "metadata": "1000 Hz synthetic trace"},
        {"id": "TRIAL-001", "kind": "trial", "label": "Trial", "metadata": "CMJ-001-01-01"},
        {"id": "METRIC-CMJ-IMPULSE", "kind": "metric", "label": "CMJ / Concentric Impulse", "metadata": "cmj-metrics@1.0.0"},
        {"id": SNAPSHOT_ID, "kind": "snapshot", "label": SNAPSHOT_ID, "metadata": "immutable analytical snapshot"},
        {"id": "COHORT-001", "kind": "cohort", "label": "Elite football longitudinal cohort", "metadata": "FROZEN"},
        {"id": "RUN-0001", "kind": "run", "label": "RUN-0001", "metadata": "METH-LONG"},
        {"id": artifact_id, "kind": "artifact", "label": artifact_id, "metadata": "select to inspect"},
        {"id": "FIG-0001", "kind": "figure", "label": "FIG-0001", "metadata": "computed figure"},
        {"id": "REPORT-001", "kind": "report", "label": "Interim scientific report", "metadata": "DRAFT"},
    ], "edges": edges}


@app.get("/models/training-response")
def model_training_response() -> dict[str, Any]:
    _ensure_data()
    return {"spec": _json("model_spec.json", {}), "run": _json("model_run.json", {}), "snapshot": _json("dataset_snapshot.json", {})}


@app.post("/models/training-response/simulate")
def model_simulate(request: SimulationRequest) -> dict[str, Any]:
    _ensure_data()
    if not request.load_values:
        raise HTTPException(status_code=422, detail="At least one weekly load value is required")
    return simulate_training_response(request.load_values, request.parameters)
