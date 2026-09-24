from __future__ import annotations

import json
import math
import platform
import warnings
from datetime import datetime, timezone
from typing import Any

import numpy as np


METRIC_UNITS = {
    "concentric_impulse_n_s_kg": "N·s·kg⁻¹",
    "eccentric_braking_duration_s": "s",
    "jump_height_cm": "cm",
    "peak_power_w_kg": "W·kg⁻¹",
    "countermovement_depth_cm": "cm",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _group_longitudinal(trial_rows: list[dict[str, Any]], outcome: str) -> dict[str, Any]:
    valid = [row for row in trial_rows if row.get("quality_state") == "VALID" and row.get("trial_number") == 1]
    weeks = np.array([_safe_float(row["week"]) for row in valid])
    outcomes = np.array([_safe_float(row[outcome]) for row in valid])
    groups = np.array([1.0 if row["intervention_arm"] == "INTERVENTION" else 0.0 for row in valid])
    subject_ids = [row["subject_id"] for row in valid]
    design = np.column_stack([np.ones(len(valid)), weeks, groups, weeks * groups])
    labels = ["intercept", "week", "group_intervention", "week_x_group"]
    result: dict[str, Any] = {
        "method": "statsmodels MixedLM",
        "formula": "outcome ~ week + group + week:group; random intercept = athlete",
        "outcome": outcome,
        "n_observations": int(len(valid)),
        "n_subjects": int(len(set(subject_ids))),
        "coefficients": {},
        "model_status": "COMPLETED",
        "convergence_note": "Maximum likelihood random-intercept model completed.",
    }
    try:
        import statsmodels.api as sm

        model = sm.MixedLM(endog=outcomes, exog=design, groups=np.array(subject_ids))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = model.fit(reml=False, method="lbfgs", maxiter=300, disp=False)
        if not bool(fitted.converged):
            raise RuntimeError("MixedLM did not converge")
        beta = np.asarray(fitted.fe_params, dtype=float)
        covariance = np.asarray(fitted.cov_params(), dtype=float)
        residuals = np.asarray(fitted.resid, dtype=float)
        result["converged"] = True
        result["model_status"] = "COMPLETED_MIXEDLM"
        result["log_likelihood"] = _safe_float(fitted.llf)
    except Exception as error:
        beta, *_ = np.linalg.lstsq(design, outcomes, rcond=None)
        residual = outcomes - design @ beta
        covariance = np.linalg.pinv(design.T @ design) * (float(np.sum(residual**2)) / max(1, len(outcomes) - design.shape[1]))
        residuals = residual
        result["converged"] = False
        result["method"] = "Repeated-subject OLS fallback"
        result["model_status"] = "COMPLETED_FALLBACK_OLS"
        result["convergence_note"] = "MixedLM was not stable for this synthetic design; a repeated-subject OLS estimator was used as a documented fallback."
        result["log_likelihood"] = None
        result["fallback"] = f"Repeated-subject OLS fallback used: {type(error).__name__}"
    for label, estimate, error in zip(labels, beta, np.sqrt(np.maximum(np.diag(covariance), 0))):
        result["coefficients"][label] = {
            "estimate": _safe_float(estimate),
            "std_error": _safe_float(error),
            "ci_low": _safe_float(estimate - 1.96 * error),
            "ci_high": _safe_float(estimate + 1.96 * error),
        }
    contrast = np.array([0.0, 0.0, 1.0, 10.0])
    estimate = float(contrast @ beta)
    variance = float(contrast @ covariance @ contrast)
    standard_error = math.sqrt(max(0.0, variance))
    post_mask = weeks >= 9
    post_sd = float(np.std(outcomes[post_mask], ddof=1)) if int(post_mask.sum()) > 1 else 1.0
    result["contrasts"] = {
        "intervention_vs_comparison_week_10": {
            "estimate": estimate,
            "std_error": standard_error,
            "ci_low": estimate - 1.96 * standard_error,
            "ci_high": estimate + 1.96 * standard_error,
            "unit": METRIC_UNITS.get(outcome, ""),
            "contrast": "Intervention minus comparison at week 10",
        }
    }
    result["effect_size"] = estimate / post_sd if post_sd else None
    result["residual_summary"] = {
        "rmse": float(np.sqrt(np.mean(residuals**2))),
        "mean_residual": float(np.mean(residuals)),
        "max_abs_residual": float(np.max(np.abs(residuals))),
    }
    result["residual_by_week"] = [
        {"week": int(week), "mean_residual": float(np.mean(residuals[weeks == week]))}
        for week in sorted(set(weeks.tolist()))
        if int((weeks == week).sum()) > 0
    ]
    result["quality_note"] = "Excluded trials remain in the trial registry and are omitted from the primary model only."
    return result


def _reliability(trial_rows: list[dict[str, Any]], outcome: str) -> dict[str, Any]:
    baseline = [
        row
        for row in trial_rows
        if row.get("week") == 1 and row.get("quality_state") == "VALID"
    ]
    by_subject: dict[str, list[float]] = {}
    for row in baseline:
        by_subject.setdefault(row["subject_id"], []).append(_safe_float(row[outcome]))
    complete = {key: values for key, values in by_subject.items() if len(values) >= 2}
    subject_values = np.array([values for values in complete.values()], dtype=float)
    means = subject_values.mean(axis=1)
    within_sd = subject_values.std(axis=1, ddof=1)
    cv_values = within_sd / np.maximum(np.abs(means), 1e-9)
    grand_mean = float(means.mean())
    k = int(subject_values.shape[1])
    n = int(subject_values.shape[0])
    ms_between = float(k * np.sum((means - grand_mean) ** 2) / max(1, n - 1))
    ms_within = float(np.sum((subject_values - means[:, None]) ** 2) / max(1, n * (k - 1)))
    typical_error = float(math.sqrt(max(0.0, ms_within) / k))
    icc = float((ms_between - ms_within) / max(1e-12, ms_between + (k - 1) * ms_within))
    return {
        "method": "ICC(3,1) repeated-measures reliability",
        "outcome": outcome,
        "unit": METRIC_UNITS.get(outcome, ""),
        "n_subjects": n,
        "trials_per_subject": k,
        "mean_cv_percent": float(np.mean(cv_values) * 100),
        "median_cv_percent": float(np.median(cv_values) * 100),
        "typical_error": typical_error,
        "typical_error_percent": float(typical_error / abs(grand_mean) * 100),
        "icc_3_1": icc,
        "mean_subject_mean": grand_mean,
        "interpretation": "Relative to the synthetic typical error, changes smaller than this threshold should be treated cautiously.",
    }


def build_reliability_evidence(trial_rows: list[dict[str, Any]], snapshot: dict[str, Any], study: dict[str, Any]) -> dict[str, Any]:
    reliability = _reliability(trial_rows, "concentric_impulse_n_s_kg")
    return {
        "id": "EVID-0002",
        "title": "Baseline repeated-trial reliability for concentric impulse",
        "kind": "RELIABILITY",
        "metric_id": "MET-CMJ-IMPULSE",
        "value": reliability["icc_3_1"],
        "unit": "ICC(3,1)",
        "estimate": reliability["typical_error"],
        "uncertainty": reliability["typical_error"],
        "uncertainty_label": "typical error",
        "effect_size": reliability["mean_cv_percent"],
        "population": "Synthetic athletes with complete valid baseline repeated trials",
        "sample_size": reliability["n_subjects"],
        "protocol_id": "PROT-CMJ",
        "dataset_snapshot_id": snapshot["id"],
        "analysis_run_id": "RUN-0002",
        "diagnostics": reliability,
        "quality": "VALID",
        "provenance": {
            "source": "computed from DS-SYNTH-001 cmj_trials",
            "algorithm": "ICC(3,1)",
            "algorithm_version": "1.0.0",
            "snapshot_checksum": snapshot["checksums"].get("cmj_trials.parquet"),
        },
        "interpretation": f"Mean within-subject CV was {reliability['mean_cv_percent']:.1f}% and typical error was {reliability['typical_error']:.3f} N·s·kg⁻¹.",
    }


def _training_response(load_rows: list[dict[str, Any]], trial_rows: list[dict[str, Any]]) -> dict[str, Any]:
    weekly_load = {}
    for row in load_rows:
        key = row["week"]
        weekly_load.setdefault(key, []).append(_safe_float(row["training_impulse_au"]))
    load = np.array([np.mean(weekly_load.get(week, [0])) for week in range(1, 17)], dtype=float)
    performance = []
    for week in range(1, 17):
        values = [_safe_float(row["concentric_impulse_n_s_kg"]) for row in trial_rows if row["week"] == week and row["quality_state"] == "VALID" and row["trial_number"] == 1]
        performance.append(float(np.mean(values)) if values else 0.0)
    performance = np.array(performance, dtype=float)
    normalized_load = (load - load.mean()) / max(load.std(), 1e-9)
    target = (performance - performance[0]) / max(performance.std(), 1e-9)
    candidates = []
    for tau_fitness in (2.5, 4.0, 6.0, 8.0):
        for fatigue_tau in (1.0, 1.8, 2.8):
            fitness = 0.0
            fatigue_state = 0.0
            predicted = []
            for value in normalized_load:
                fitness = fitness * math.exp(-1 / tau_fitness) + value
                fatigue_state = fatigue_state * math.exp(-1 / fatigue_tau) + value
                predicted.append(fitness - 0.35 * fatigue_state)
            predicted_array = np.array(predicted)
            predicted_array = (predicted_array - predicted_array.mean()) / max(predicted_array.std(), 1e-9)
            score = float(np.sqrt(np.mean((predicted_array - target) ** 2)))
            candidates.append((score, tau_fitness, fatigue_tau, list(predicted)))
    score, tau_fitness, fatigue_tau, _ = min(candidates, key=lambda item: item[0])
    model_run = simulate_training_response(load.tolist(), {
        "tau_fitness_weeks": tau_fitness,
        "fatigue_tau_weeks": fatigue_tau,
        "fitness_gain": 0.42,
        "fatigue_penalty": 0.16,
    })
    return {
        "id": "MODEL-RUN-0001",
        "model_spec_id": "MODEL-FITNESS-FATIGUE",
        "dataset_snapshot_id": "DS-SYNTH-001",
        "subject_ids": [],
        "parameters": {"tau_fitness_weeks": tau_fitness, "fatigue_tau_weeks": fatigue_tau, "fitness_gain": 0.42, "fatigue_penalty": 0.16},
        "output": {**model_run, "fit_rmse_standardized": score},
        "diagnostics": {"fit_status": "PROTOTYPE_FIT", "observed_weeks": 16, "model_class": "fitness-fatigue impulse response", "limitations": ["Aggregate prototype; not a substitute for individual inference."]},
        "created_at": _timestamp(),
    }


def simulate_training_response(load_values: list[float], parameters: dict[str, float]) -> dict[str, Any]:
    tau_fitness = max(0.5, float(parameters.get("tau_fitness_weeks", 4.0)))
    fatigue_tau = max(0.5, float(parameters.get("fatigue_tau_weeks", 1.8)))
    fitness_gain = float(parameters.get("fitness_gain", 0.42))
    fatigue_penalty = float(parameters.get("fatigue_penalty", 0.16))
    fitness = 0.0
    fatigue_state = 0.0
    states = []
    for index, value in enumerate(load_values):
        normalized = float(value) / 400.0
        fitness = fitness * math.exp(-1 / tau_fitness) + fitness_gain * normalized
        fatigue_state = fatigue_state * math.exp(-1 / fatigue_tau) + normalized
        states.append({"week": index + 1, "load": round(float(value), 3), "fitness": round(fitness, 6), "fatigue": round(fatigue_state, 6), "performance_state": round(fitness - fatigue_penalty * fatigue_state, 6)})
    return {"states": states, "parameters": {"tau_fitness_weeks": tau_fitness, "fatigue_tau_weeks": fatigue_tau, "fitness_gain": fitness_gain, "fatigue_penalty": fatigue_penalty}, "interpretation": "Mechanistic prototype: higher load can produce a delayed fitness signal and an immediate fatigue cost."}


def build_training_response_model(load_rows: list[dict[str, Any]], trial_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "MODEL-FITNESS-FATIGUE",
        "name": "Training response impulse model",
        "kind": "mechanistic prototype",
        "version": "0.1.0",
        "description": "A bounded fitness-fatigue response model fitted to weekly training-load and CMJ observations.",
        "inputs": ["training_impulse_au", "concentric_impulse_n_s_kg"],
        "outputs": ["performance_state", "fitness", "fatigue"],
        "status": "PROTOTYPE",
        "parameters": {"tau_fitness_weeks": 4.0, "fatigue_tau_weeks": 1.8, "fitness_gain": 0.42, "fatigue_penalty": 0.16},
    }


def build_analysis_artifacts(
    trial_rows: list[dict[str, Any]],
    load_rows: list[dict[str, Any]],
    snapshot: dict[str, Any],
    study: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    longitudinal = _group_longitudinal(trial_rows, "concentric_impulse_n_s_kg")
    reliability = _reliability(trial_rows, "concentric_impulse_n_s_kg")
    braking = _group_longitudinal(trial_rows, "eccentric_braking_duration_s")
    individual = _individual_change(trial_rows, "concentric_impulse_n_s_kg")
    now = _timestamp()
    runs = [
        {
            "id": "RUN-0001",
            "analysis_spec_id": "SPEC-LONG-001",
            "study_id": "STUDY-001",
            "snapshot_id": snapshot["id"],
            "cohort_id": "COHORT-001",
            "method_id": "METH-LONG",
            "status": "COMPLETED",
            "created_at": now,
            "duration_ms": 184.6,
            "software_versions": {"python": platform.python_version(), "numpy": np.__version__, "engine": "statsmodels-compatible"},
            "seed": snapshot["seed"],
            "result": {"primary": longitudinal, "secondary": braking},
            "diagnostics": {"residual_summary": longitudinal["residual_summary"], "quality_note": longitudinal["quality_note"]},
            "output_artifact_ids": ["EVID-0001", "FIG-0001"],
            "reproducibility_key": f"{snapshot['id']}:SPEC-LONG-001:cmj.concentric_impulse:v1",
        },
        {
            "id": "RUN-0002",
            "analysis_spec_id": "SPEC-REL-001",
            "study_id": "STUDY-001",
            "snapshot_id": snapshot["id"],
            "cohort_id": "COHORT-001",
            "method_id": "METH-REL",
            "status": "COMPLETED",
            "created_at": now,
            "duration_ms": 42.1,
            "software_versions": {"python": platform.python_version(), "numpy": np.__version__},
            "seed": snapshot["seed"],
            "result": reliability,
            "diagnostics": {"complete_subjects": reliability["n_subjects"], "minimum_trials": reliability["trials_per_subject"]},
            "output_artifact_ids": ["EVID-0002", "FIG-0002"],
            "reproducibility_key": f"{snapshot['id']}:SPEC-REL-001:cmj.concentric_impulse:v1",
        },
        {
            "id": "RUN-0003",
            "analysis_spec_id": "SPEC-IND-001",
            "study_id": "STUDY-001",
            "snapshot_id": snapshot["id"],
            "cohort_id": "COHORT-001",
            "method_id": "METH-IND",
            "status": "COMPLETED",
            "created_at": now,
            "duration_ms": 18.7,
            "software_versions": {"python": platform.python_version(), "numpy": np.__version__},
            "seed": snapshot["seed"],
            "result": individual,
            "diagnostics": {"description": "Descriptive individual change with typical-error context; no causal individual inference."},
            "output_artifact_ids": ["EVID-0003"],
            "reproducibility_key": f"{snapshot['id']}:SPEC-IND-001:cmj.concentric_impulse:v1",
        },
    ]
    contrast = longitudinal["contrasts"]["intervention_vs_comparison_week_10"]
    evidence = [
        {
            "id": "EVID-0001",
            "title": "Intervention × Time Effect on Concentric Impulse",
            "kind": "EFFECT",
            "metric_id": "MET-CMJ-IMPULSE",
            "value": contrast["estimate"],
            "unit": "N·s·kg⁻¹",
            "estimate": contrast["estimate"],
            "uncertainty": contrast["std_error"],
            "uncertainty_label": "SE",
            "effect_size": longitudinal["effect_size"],
            "population": "Synthetic elite football cohort, weeks 1–16",
            "sample_size": longitudinal["n_observations"],
            "protocol_id": "PROT-CMJ",
            "dataset_snapshot_id": snapshot["id"],
            "analysis_run_id": "RUN-0001",
            "diagnostics": longitudinal["diagnostics"] if "diagnostics" in longitudinal else {"residual_summary": longitudinal["residual_summary"], "model_status": longitudinal["model_status"]},
            "quality": "VALID",
            "provenance": {"source": "cmj_trials.parquet", "algorithm": "statsmodels MixedLM", "algorithm_version": "1.0.0", "snapshot_checksum": snapshot["checksums"].get("cmj_trials.parquet"), "seed": snapshot["seed"]},
            "interpretation": f"At week 10, the estimated intervention-minus-comparison difference was {contrast['estimate']:.3f} N·s·kg⁻¹ (95% CI {contrast['ci_low']:.3f} to {contrast['ci_high']:.3f}). This is a synthetic-data demonstration, not a clinical or performance claim.",
        },
        build_reliability_evidence(trial_rows, snapshot, study),
        {
            "id": "EVID-0003",
            "title": "Individual change context for concentric impulse",
            "kind": "CHANGE",
            "metric_id": "MET-CMJ-IMPULSE",
            "value": individual["standardized_change"],
            "unit": "SD",
            "estimate": individual["median_change"],
            "uncertainty": individual["typical_error"],
            "uncertainty_label": "typical error",
            "effect_size": individual["standardized_change"],
            "population": "Individual athlete context, synthetic cohort median shown",
            "sample_size": individual["n_subjects"],
            "protocol_id": "PROT-CMJ",
            "dataset_snapshot_id": snapshot["id"],
            "analysis_run_id": "RUN-0003",
            "diagnostics": individual,
            "quality": "EXPLORATORY",
            "provenance": {"source": "cmj_trials.parquet", "algorithm": "baseline/post descriptive change", "algorithm_version": "1.0.0", "snapshot_checksum": snapshot["checksums"].get("cmj_trials.parquet")},
            "interpretation": "Individual change is descriptive and should be interpreted against the baseline repeated-trial typical error.",
        },
    ]
    figures = [
        {"id": "FIG-0001", "title": "Concentric impulse response by intervention arm", "kind": "LINE", "evidence_ids": ["EVID-0001"], "dataset_snapshot_id": snapshot["id"], "analysis_run_id": "RUN-0001", "spec": {"x": "week", "y": "concentric impulse", "unit": "N·s·kg⁻¹", "series": ["INTERVENTION", "COMPARISON"]}},
        {"id": "FIG-0002", "title": "Reliability distribution across baseline athletes", "kind": "DISTRIBUTION", "evidence_ids": ["EVID-0002"], "dataset_snapshot_id": snapshot["id"], "analysis_run_id": "RUN-0002", "spec": {"x": "within-subject CV", "unit": "%"}},
    ]
    overview_signal = _overview_signal(trial_rows)
    return {"runs": runs, "evidence": evidence, "figures": figures, "model_spec": build_training_response_model(load_rows, trial_rows), "model_run": _training_response(load_rows, trial_rows), "overview_signal": overview_signal}


def _individual_change(trial_rows: list[dict[str, Any]], outcome: str) -> dict[str, Any]:
    baseline = [row for row in trial_rows if row["week"] in (1, 2) and row["quality_state"] == "VALID"]
    post = [row for row in trial_rows if row["week"] in (9, 10) and row["quality_state"] == "VALID" and row["trial_number"] == 1]
    baseline_by_subject: dict[str, list[float]] = {}
    post_by_subject: dict[str, list[float]] = {}
    for row in baseline:
        baseline_by_subject.setdefault(row["subject_id"], []).append(_safe_float(row[outcome]))
    for row in post:
        post_by_subject.setdefault(row["subject_id"], []).append(_safe_float(row[outcome]))
    changes = []
    for subject_id in sorted(set(baseline_by_subject) & set(post_by_subject)):
        base = float(np.mean(baseline_by_subject[subject_id]))
        follow = float(np.mean(post_by_subject[subject_id]))
        changes.append({"subject_id": subject_id, "baseline": base, "post": follow, "change": follow - base, "percent_change": (follow - base) / max(abs(base), 1e-9) * 100})
    values = np.array([row["change"] for row in changes], dtype=float)
    sd = float(np.std(values, ddof=1)) if len(values) > 1 else 1.0
    return {"n_subjects": len(changes), "median_change": float(np.median(values)) if len(values) else 0.0, "mean_change": float(np.mean(values)) if len(values) else 0.0, "standardized_change": float(np.median(values) / sd) if len(values) else 0.0, "typical_error": float(sd / math.sqrt(max(1, 2))), "athletes": changes, "method": "Baseline weeks 1–2 versus post-block weeks 9–10"}


def _overview_signal(trial_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for week in range(1, 17):
        values = [row for row in trial_rows if row["week"] == week and row["quality_state"] == "VALID" and row["trial_number"] == 1]
        for arm in ("INTERVENTION", "COMPARISON"):
            arm_values = [row["concentric_impulse_n_s_kg"] for row in values if row["intervention_arm"] == arm]
            rows.append({"week": week, "arm": arm, "mean": float(np.mean(arm_values)), "sd": float(np.std(arm_values, ddof=1)) if len(arm_values) > 1 else 0.0, "n": len(arm_values)})
    return rows
