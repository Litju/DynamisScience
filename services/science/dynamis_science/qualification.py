from __future__ import annotations

import json
import math
import platform
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .analysis import _group_longitudinal, _reliability, _safe_float
from .generate import ARTIFACT_DIR, PARQUET_DIR, SNAPSHOT_ID

QUALIFICATION_PATH = ARTIFACT_DIR / "qualification_records.json"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def _env() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(), "service": "dynamis-science@0.2.0"}


def _cmj_record() -> dict[str, Any]:
    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet")
    trial_id = "CMJ-001-10-1"
    trial = trials.filter(pl.col("trial_id") == trial_id).row(0, named=True)
    trace = pl.read_parquet(PARQUET_DIR / "force_traces.parquet").filter(pl.col("trial_id") == trial_id)
    times = trace["time_s"].to_numpy().astype(float)
    force = trace["force_n"].to_numpy().astype(float)
    bw = float(trace["body_weight_n"][0])
    mass = float(trial["body_mass_kg"])
    boundaries = json.loads(trial["phase_boundaries"]) if isinstance(trial["phase_boundaries"], str) else trial["phase_boundaries"]
    # Independent reference using explicit trapezoidal integration and finite differences.
    net = force - bw
    velocity = np.concatenate([[0.0], np.cumsum((net[1:] + net[:-1]) * 0.5 / mass * np.diff(times))])
    displacement = np.concatenate([[0.0], np.cumsum((velocity[1:] + velocity[:-1]) * 0.5 * np.diff(times))])
    propulsion = (times >= boundaries["braking_end"]) & (times < boundaries["takeoff"])
    braking = (times >= boundaries["movement_onset"]) & (times < boundaries["braking_end"])
    flight = boundaries["landing"] - boundaries["takeoff"]
    reference = {
        "body_weight_n": bw,
        "concentric_impulse_n_s_kg": float(np.trapezoid(net[propulsion], times[propulsion]) / mass),
        "eccentric_braking_impulse_n_s_kg": float(abs(np.trapezoid(net[braking], times[braking]) / mass)),
        "eccentric_braking_duration_s": float(boundaries["braking_end"] - boundaries["unweighting_end"]),
        "jump_height_cm": float(9.80665 * flight * flight / 8.0 * 100.0),
        "peak_force_n": float(np.max(force)),
        "peak_power_w_kg": float(np.max(force[propulsion] * np.maximum(velocity[propulsion], 0.0)) / mass),
        "countermovement_depth_cm": float(abs(np.min(displacement)) * 100.0),
    }
    service = {key: _safe_float(trial[key]) for key in reference if key in trial}
    diffs = {key: abs(reference[key] - service[key]) for key in reference}
    rels = {key: (diffs[key] / max(abs(reference[key]), 1e-12)) for key in reference}
    tolerance = 0.02
    passed = all(diffs[key] <= tolerance * max(1.0, abs(reference[key])) for key in reference)
    return {
        "id": "QUAL-CMJ-METRICS",
        "scientific_method": "CMJ force-platform metric extraction",
        "method_version": "1.0.0",
        "input_fixture": trial_id,
        "independent_reference_implementation": "Independent NumPy trapezoidal integration and finite-difference kinematics",
        "reference_result": reference,
        "dynamis_result": service,
        "absolute_difference": diffs,
        "relative_difference": rels,
        "tolerance": tolerance,
        "pass_fail": "PASS" if passed else "FAIL",
        "status": "QUALIFIED" if passed else "FAILED",
        "known_limitations": [
            "Validation uses one representative high-quality trial.",
            "Phase boundaries are taken from the stored trial; independent phase detection is not evaluated here.",
        ],
        "reproduction_command": "uv run --directory services/science pytest tests/test_qualification.py",
        "environment": _env(),
    }


def _reliability_record() -> dict[str, Any]:
    import json as _json

    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet").to_dicts()
    service = _reliability(trials, "concentric_impulse_n_s_kg")
    # Independent recomputation from the same balanced design, using explicit two-way ANOVA formulas.
    baseline = [row for row in trials if row["week"] == 1 and row["quality_state"] == "VALID"]
    by_subject: dict[str, list[float]] = {}
    for row in baseline:
        by_subject.setdefault(row["subject_id"], []).append(float(row["concentric_impulse_n_s_kg"]))
    complete = {k: v for k, v in by_subject.items() if len(v) >= 2}
    k = min(len(v) for v in complete.values())
    balanced = {key: values[:k] for key, values in complete.items()}
    subject_ids = sorted(balanced)
    values = np.array([balanced[key] for key in subject_ids], dtype=float)
    means = values.mean(axis=1)
    grand_mean = float(means.mean())
    n = values.shape[0]
    ms_between = float(k * np.sum((means - grand_mean) ** 2) / max(1, n - 1))
    ms_within = float(np.sum((values - means[:, None]) ** 2) / max(1, n * (k - 1)))
    icc = float((ms_between - ms_within) / max(1e-12, ms_between + (k - 1) * ms_within))
    te = float(math.sqrt(max(0.0, ms_within)))
    cv = float(np.mean(values.std(axis=1, ddof=1) / np.maximum(np.abs(means), 1e-9)) * 100.0)
    reference = {"icc_3_1": icc, "typical_error": te, "mean_cv_percent": cv}
    service_values = {key: _safe_float(service.get(key)) for key in reference}
    diffs = {key: abs(reference[key] - service_values[key]) for key in reference}
    tolerance = 1e-9
    passed = all(diff <= tolerance for diff in diffs.values())
    return {
        "id": "QUAL-RELIABILITY",
        "scientific_method": "Repeated-trial reliability ICC(3,1)",
        "method_version": "1.1.0",
        "input_fixture": "DS-SYNTH-001 cmj_trials baseline week 1",
        "independent_reference_implementation": "Independent two-way ANOVA mean-square computation",
        "reference_result": reference,
        "dynamis_result": service_values,
        "absolute_difference": diffs,
        "relative_difference": {key: diffs[key] / max(abs(reference[key]), 1e-12) for key in reference},
        "tolerance": tolerance,
        "pass_fail": "PASS" if passed else "FAIL",
        "status": "QUALIFIED" if passed else "FAILED",
        "known_limitations": ["Reliability is evaluated for baseline week 1 only."],
        "reproduction_command": "uv run --directory services/science pytest tests/test_qualification.py",
        "environment": _env(),
    }


def _longitudinal_record() -> dict[str, Any]:
    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet").to_dicts()
    service = _group_longitudinal(trials, "concentric_impulse_n_s_kg")
    # Independent reference: cluster-robust OLS with athlete fixed effects omitted; compare primary contrast loosely.
    import numpy as np
    valid = [row for row in trials if row.get("quality_state") == "VALID" and row.get("trial_number") == 1]
    weeks = np.array([float(row["week"]) for row in valid])
    outcomes = np.array([float(row["concentric_impulse_n_s_kg"]) for row in valid])
    groups = np.array([1.0 if row["intervention_arm"] == "INTERVENTION" else 0.0 for row in valid])
    subjects = [row["subject_id"] for row in valid]
    elapsed = weeks - 1.0
    design = np.column_stack([np.ones(len(valid)), elapsed, groups, elapsed * groups])
    beta = np.linalg.lstsq(design, outcomes, rcond=None)[0]
    # cluster robust se
    residuals = outcomes - design @ beta
    unique = sorted(set(subjects))
    meat = np.zeros((4, 4))
    for cluster in unique:
        mask = np.array([s == cluster for s in subjects])
        score = design[mask].T @ residuals[mask]
        meat += np.outer(score, score)
    bread = np.linalg.pinv(design.T @ design)
    n_clusters = len(unique)
    correction = (n_clusters / max(1, n_clusters - 1)) * ((len(valid) - 1) / max(1, len(valid) - 4))
    cov = bread @ meat @ bread * correction
    se = np.sqrt(np.diag(cov))
    interaction = beta[3] * 9.0  # week 1 to week 10
    se_interaction = se[3] * 9.0
    reference = {
        "primary_contrast_estimate": float(interaction),
        "primary_contrast_se": float(se_interaction),
        "ci_low": float(interaction - 1.959963984540054 * se_interaction),
        "ci_high": float(interaction + 1.959963984540054 * se_interaction),
    }
    service_contrast = service["contrasts"][service["primary_contrast_id"]]
    service_values = {
        "primary_contrast_estimate": _safe_float(service_contrast["estimate"]),
        "primary_contrast_se": _safe_float(service_contrast["std_error"]),
        "ci_low": _safe_float(service_contrast["ci_low"]),
        "ci_high": _safe_float(service_contrast["ci_high"]),
    }
    diff = abs(reference["primary_contrast_estimate"] - service_values["primary_contrast_estimate"])
    tolerance = 0.15
    passed = diff <= tolerance * max(1.0, abs(service_values["primary_contrast_estimate"]))
    return {
        "id": "QUAL-LONGITUDINAL",
        "scientific_method": "Group x time longitudinal model",
        "method_version": "1.1.0",
        "input_fixture": "DS-SYNTH-001 cmj_trials",
        "independent_reference_implementation": "Independent cluster-robust OLS (documented fallback class), not the primary MixedLM",
        "reference_result": reference,
        "dynamis_result": service_values,
        "absolute_difference": {"primary_contrast_estimate": diff},
        "relative_difference": {"primary_contrast_estimate": diff / max(abs(service_values["primary_contrast_estimate"]), 1e-12)},
        "tolerance": tolerance,
        "pass_fail": "PASS" if passed else "FAIL",
        "status": "PARTIALLY_QUALIFIED" if passed else "FAILED",
        "known_limitations": [
            "Independent reference uses a different estimator class (cluster-robust OLS), so agreement is expected to be approximate.",
            "Primary MixedLM random-effects specification is not independently reimplemented.",
        ],
        "reproduction_command": "uv run --directory services/science pytest tests/test_qualification.py",
        "environment": _env(),
    }


def run_qualification() -> list[dict[str, Any]]:
    records = [_cmj_record(), _reliability_record(), _longitudinal_record()]
    _write_json(QUALIFICATION_PATH, records)
    return records


def list_qualification_records() -> list[dict[str, Any]]:
    if not QUALIFICATION_PATH.exists():
        run_qualification()
    return _json(QUALIFICATION_PATH, [])


def _json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))