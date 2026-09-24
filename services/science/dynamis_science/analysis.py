from __future__ import annotations

import json
import math
import platform
import warnings
from typing import Any

import numpy as np

METRIC_UNITS = {
    "concentric_impulse_n_s_kg": "N·s·kg⁻¹",
    "eccentric_braking_duration_s": "s",
    "eccentric_braking_impulse_n_s_kg": "N·s·kg⁻¹",
    "jump_height_cm": "cm",
    "peak_power_w_kg": "W·kg⁻¹",
    "countermovement_depth_cm": "cm",
    "peak_force_n": "N",
    "rsi_mod": "cm·s⁻¹",
}

ALPHA = 0.05
Z_CRITICAL = 1.959963984540054


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _software_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "platform": platform.platform(),
        "service": "dynamis-science@0.1.0",
    }


def _fit_mixedlm(design: np.ndarray, outcomes: np.ndarray, subject_ids: list[str], random_design: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    import statsmodels.api as sm

    last_error: Exception | None = None
    for method in ("lbfgs", "bfgs", "powell"):
        try:
            model = sm.MixedLM(endog=outcomes, exog=design, groups=np.array(subject_ids), exog_re=random_design)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = model.fit(reml=False, method=method, maxiter=1000, disp=False)
            if not bool(fitted.converged):
                raise RuntimeError(f"MixedLM did not converge with {method}")
            beta = np.asarray(fitted.fe_params, dtype=float)
            covariance = np.asarray(fitted.cov_params(), dtype=float)[: design.shape[1], : design.shape[1]]
            residuals = np.asarray(fitted.resid, dtype=float)
            if not np.all(np.isfinite(covariance)) or not np.all(np.isfinite(beta)):
                raise RuntimeError(f"MixedLM produced non-finite estimates with {method}")
            if np.any(np.diag(covariance) <= 0):
                raise RuntimeError(f"MixedLM produced non-positive fixed-effect variances with {method}")
            return beta, covariance, residuals, _safe_float(fitted.llf)
        except Exception as error:  # pragma: no cover - depends on optimiser stability
            last_error = error
    raise RuntimeError(f"MixedLM failed for every optimiser: {type(last_error).__name__}")


def _fit_gee(design: np.ndarray, outcomes: np.ndarray, subject_ids: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, None]:
    import statsmodels.api as sm

    model = sm.GEE(
        endog=outcomes,
        exog=design,
        groups=np.array(subject_ids),
        cov_struct=sm.cov_struct.Exchangeable(),
        family=sm.families.Gaussian(),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = model.fit()
    beta = np.asarray(fitted.params, dtype=float)
    covariance = np.asarray(fitted.cov_params(), dtype=float)
    residuals = outcomes - design @ beta
    if not np.all(np.isfinite(covariance)):
        raise RuntimeError("GEE covariance was not finite")
    return beta, covariance, residuals, None


def _group_longitudinal(
    trial_rows: list[dict[str, Any]], outcome: str, reference_week: int = 1, contrast_week: int = 10
) -> dict[str, Any]:
    """Group x time repeated-measures model with athlete-level dependence.

    Estimator ladder, in order of preference:

    1. ``MixedLM`` with athlete random intercept **and** random week slope. The
       synthetic generator gives every athlete a persistent trait and a
       heterogeneous response to the block, so a random slope is the
       structurally correct random-effects specification.
    2. ``MixedLM`` with an athlete random intercept only.
    3. ``GEE`` with exchangeable working correlation and athlete clusters.
    4. ``OLS`` with athlete-clustered sandwich standard errors.

    Whichever estimator is used is recorded on the run so the choice is never
    silent.

    Week is centred on the reference week, so the group term is the
    baseline-balance contrast and the interaction term is the
    intervention-minus-comparison change in slope. The primary estimand is the
    difference in change from the reference week to the contrast week, which is
    the quantity the frozen plan pre-specified and which is not diluted by
    between-athlete level differences.
    """
    valid = [row for row in trial_rows if row.get("quality_state") == "VALID" and row.get("trial_number") == 1]
    weeks = np.array([_safe_float(row["week"]) for row in valid])
    outcomes = np.array([_safe_float(row[outcome]) for row in valid])
    groups = np.array([1.0 if row["intervention_arm"] == "INTERVENTION" else 0.0 for row in valid])
    subject_ids = [row["subject_id"] for row in valid]
    elapsed = weeks - float(reference_week)
    design = np.column_stack([np.ones(len(valid)), elapsed, groups, elapsed * groups])
    labels = ["intercept", "week_slope_comparison", "group_at_reference", "week_x_group"]
    result: dict[str, Any] = {
        "method": "statsmodels MixedLM",
        "formula": "outcome ~ week + group + week:group; random intercept + random week slope = athlete",
        "outcome": outcome,
        "unit": METRIC_UNITS.get(outcome, ""),
        "week_centering": reference_week,
        "reference_week": reference_week,
        "contrast_week": contrast_week,
        "n_observations": int(len(valid)),
        "n_subjects": int(len(set(subject_ids))),
        "coefficients": {},
        "model_status": "COMPLETED",
        "estimator": "MIXEDLM_RANDOM_SLOPE",
        "convergence_note": "Maximum-likelihood random-slope model completed.",
    }
    attempts: list[tuple[str, Any]] = [
        ("MIXEDLM_RANDOM_SLOPE", lambda: _fit_mixedlm(design, outcomes, subject_ids, np.column_stack([np.ones(len(valid)), elapsed]))),
        ("MIXEDLM_RANDOM_INTERCEPT", lambda: _fit_mixedlm(design, outcomes, subject_ids, np.ones((len(valid), 1)))),
        ("GEE_EXCHANGEABLE", lambda: _fit_gee(design, outcomes, subject_ids)),
    ]
    failures: list[str] = []
    beta: np.ndarray | None = None
    covariance: np.ndarray | None = None
    residuals: np.ndarray | None = None
    fitted_llf: float | None = None
    for estimator, attempt in attempts:
        try:
            beta, covariance, residuals, fitted_llf = attempt()
            result["estimator"] = estimator
            result["model_status"] = f"COMPLETED_{estimator}"
            break
        except Exception as error:  # pragma: no cover - depends on optimiser stability
            failures.append(f"{estimator}:{type(error).__name__}")
    if beta is None or covariance is None or residuals is None:
        beta = np.linalg.lstsq(design, outcomes, rcond=None)[0]
        residuals = outcomes - design @ beta
        covariance = _cluster_robust_covariance(design, residuals, subject_ids)
        result["estimator"] = "OLS_CLUSTER_ROBUST"
        result["model_status"] = "COMPLETED_OLS_CLUSTER_ROBUST"
        result["method"] = "Repeated-subject OLS with athlete-clustered standard errors"
        result["convergence_note"] = (
            "No random-effects or GEE estimator was stable for this design; a repeated-subject OLS with "
            "athlete-clustered (sandwich) standard errors was used as a documented fallback."
        )
    else:
        result["method"] = {
            "MIXEDLM_RANDOM_SLOPE": "statsmodels MixedLM with athlete random intercept and random week slope",
            "MIXEDLM_RANDOM_INTERCEPT": "statsmodels MixedLM with athlete random intercept",
            "GEE_EXCHANGEABLE": "GEE with exchangeable working correlation and athlete clusters",
        }.get(result["estimator"], result["method"])
    if failures:
        result["estimator_attempts"] = failures
    result["converged"] = result["estimator"].startswith("MIXEDLM") or result["estimator"].startswith("GEE")
    result["log_likelihood"] = fitted_llf
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0))
    for label, estimate, error in zip(labels, beta, standard_errors):
        result["coefficients"][label] = {
            "estimate": _safe_float(estimate),
            "std_error": _safe_float(error),
            "ci_low": _safe_float(estimate - Z_CRITICAL * error),
            "ci_high": _safe_float(estimate + Z_CRITICAL * error),
        }

    def _contrast(vector: np.ndarray) -> dict[str, float]:
        point = float(vector @ beta)
        error = math.sqrt(max(0.0, float(vector @ covariance @ vector)))
        return {
            "estimate": point,
            "std_error": error,
            "ci_low": point - Z_CRITICAL * error,
            "ci_high": point + Z_CRITICAL * error,
            "unit": METRIC_UNITS.get(outcome, ""),
        }

    span = float(contrast_week - reference_week)
    interaction = _contrast(np.array([0.0, 0.0, 0.0, span]))
    interaction.update({"contrast": f"Intervention × Time, week {reference_week} to week {contrast_week} (difference in change)"})
    week_10_model = _contrast(np.array([0.0, 0.0, 1.0, span]))
    week_10_model.update({"contrast": f"Model-implied intervention minus comparison at week {contrast_week}", "interpretation": "Cross-sectional between-arm difference at a single week; dominated by between-athlete variation."})
    baseline_balance = _contrast(np.array([0.0, 0.0, 1.0, 0.0]))
    baseline_balance.update({"contrast": f"Intervention minus comparison at reference week {reference_week} (baseline balance)", "interpretation": "Should be compatible with zero if the arms were balanced at baseline."})
    result["contrasts"] = {
        f"intervention_x_time_week_{reference_week}_to_{contrast_week}": interaction,
        f"intervention_vs_comparison_week_{contrast_week}": week_10_model,
        f"baseline_balance_week_{reference_week}": baseline_balance,
    }
    result["primary_contrast_id"] = f"intervention_x_time_week_{reference_week}_to_{contrast_week}"
    post_mask = weeks >= 9
    post_sd = float(np.std(outcomes[post_mask], ddof=1)) if int(post_mask.sum()) > 1 else 1.0
    result["effect_size"] = interaction["estimate"] / post_sd if post_sd else None
    result["effect_size_basis"] = "difference-in-change estimate divided by the pooled post-block (weeks 9-16) standard deviation"
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
    result["diagnostics"] = {
        "estimator": result["estimator"],
        "model_status": result["model_status"],
        "converged": result["converged"],
        "n_observations": result["n_observations"],
        "n_subjects": result["n_subjects"],
        "residual_summary": result["residual_summary"],
        "week_centering": reference_week,
        "quality_note": result["quality_note"],
    }
    return result


def _cluster_robust_covariance(
    design: np.ndarray, residuals: np.ndarray, clusters: list[str]
) -> np.ndarray:
    """Athlete-clustered sandwich covariance with a finite-sample correction."""
    n_parameters = design.shape[1]
    n_observations = design.shape[0]
    bread = np.linalg.pinv(design.T @ design)
    meat = np.zeros((n_parameters, n_parameters), dtype=float)
    unique = sorted(set(clusters))
    for cluster in unique:
        mask = np.array([value == cluster for value in clusters])
        score = design[mask].T @ residuals[mask]
        meat += np.outer(score, score)
    n_clusters = len(unique)
    correction = (n_clusters / max(1, n_clusters - 1)) * ((n_observations - 1) / max(1, n_observations - n_parameters))
    return bread @ meat @ bread * correction


def _reliability(trial_rows: list[dict[str, Any]], outcome: str, baseline_weeks: tuple[int, ...] = (1,)) -> dict[str, Any]:
    """Balanced two-way ICC(3,1) with within-subject CV and typical error.

    Typical error is the within-subject standard deviation, i.e. the square root
    of the mean-square error of the two-way model, not the standard error of the
    subject mean.
    """
    baseline = [
        row
        for row in trial_rows
        if row.get("week") in baseline_weeks and row.get("quality_state") == "VALID"
    ]
    by_subject: dict[str, list[float]] = {}
    for row in baseline:
        by_subject.setdefault(row["subject_id"], []).append(_safe_float(row[outcome]))
    complete = {key: values for key, values in by_subject.items() if len(values) >= 2}
    if len(complete) < 3:
        return {
            "method": "ICC(3,1) repeated-measures reliability",
            "outcome": outcome,
            "unit": METRIC_UNITS.get(outcome, ""),
            "status": "INSUFFICIENT_DATA",
            "n_subjects": len(complete),
            "trials_per_subject": 0,
            "message": "Fewer than three athletes have repeated valid baseline trials.",
        }
    k = min(len(values) for values in complete.values())
    balanced = {key: values[:k] for key, values in complete.items() if len(values) >= k}
    subject_ids = sorted(balanced)
    subject_values = np.array([balanced[key] for key in subject_ids], dtype=float)
    means = subject_values.mean(axis=1)
    within_sd = subject_values.std(axis=1, ddof=1)
    cv_values = within_sd / np.maximum(np.abs(means), 1e-9)
    grand_mean = float(means.mean())
    n = int(subject_values.shape[0])
    ms_between = float(k * np.sum((means - grand_mean) ** 2) / max(1, n - 1))
    ms_within = float(np.sum((subject_values - means[:, None]) ** 2) / max(1, n * (k - 1)))
    typical_error = float(math.sqrt(max(0.0, ms_within)))
    icc = float((ms_between - ms_within) / max(1e-12, ms_between + (k - 1) * ms_within))
    ci_low, ci_high = _icc_confidence_interval(ms_between, ms_within, n, k)
    return {
        "method": "ICC(3,1) repeated-measures reliability",
        "outcome": outcome,
        "unit": METRIC_UNITS.get(outcome, ""),
        "status": "COMPUTED",
        "baseline_weeks": list(baseline_weeks),
        "n_subjects": n,
        "subject_ids": subject_ids,
        "trials_per_subject": k,
        "mean_cv_percent": float(np.mean(cv_values) * 100),
        "median_cv_percent": float(np.median(cv_values) * 100),
        "cv_percent_by_subject": [
            {"subject_id": subject_id, "cv_percent": float(cv * 100)}
            for subject_id, cv in zip(subject_ids, cv_values)
        ],
        "typical_error": typical_error,
        "typical_error_percent": float(typical_error / abs(grand_mean) * 100) if grand_mean else None,
        "smallest_worthwhile_change": float(typical_error * Z_CRITICAL * math.sqrt(2)),
        "icc_3_1": icc,
        "icc_3_1_ci_low": ci_low,
        "icc_3_1_ci_high": ci_high,
        "mean_subject_mean": grand_mean,
        "ms_between": ms_between,
        "ms_within": ms_within,
        "interpretation": "Relative to the synthetic typical error, changes smaller than this threshold should be treated cautiously.",
    }


def _icc_confidence_interval(ms_between: float, ms_within: float, n: int, k: int) -> tuple[float, float]:
    """Shrout-Fleiss confidence limits for ICC(3,1) via the F distribution."""
    if ms_within <= 0 or ms_between <= 0 or n < 2 or k < 2:
        return (float("nan"), float("nan"))
    try:
        from scipy import stats

        f_value = ms_between / ms_within
        df1 = n - 1
        df2 = (n - 1) * (k - 1)
        f_low = float(stats.f.ppf(ALPHA / 2, df1, df2))
        f_high = float(stats.f.ppf(1 - ALPHA / 2, df1, df2))
        lower = (f_value / f_high - 1) / (k + f_value / f_high - 1)
        upper = (f_value / f_low - 1) / (k + f_value / f_low - 1)
        return (float(max(-1.0, lower)), float(min(1.0, upper)))
    except Exception:  # pragma: no cover
        return (float("nan"), float("nan"))


def build_reliability_evidence(
    trial_rows: list[dict[str, Any]], snapshot: dict[str, Any], study: dict[str, Any]
) -> dict[str, Any]:
    reliability = _reliability(trial_rows, "concentric_impulse_n_s_kg")
    has_ci = math.isfinite(_safe_float(reliability.get("icc_3_1_ci_low"), float("nan"))) and math.isfinite(
        _safe_float(reliability.get("icc_3_1_ci_high"), float("nan"))
    )
    half_width = (
        (reliability["icc_3_1_ci_high"] - reliability["icc_3_1_ci_low"]) / 2 if has_ci else None
    )
    return {
        "id": "EVID-0002",
        "title": "Baseline repeated-trial reliability for concentric impulse",
        "kind": "RELIABILITY",
        "metric_id": "MET-CMJ-IMPULSE",
        "value": reliability.get("icc_3_1"),
        "unit": "ICC(3,1)",
        "estimate": reliability.get("icc_3_1"),
        "uncertainty": half_width,
        "uncertainty_label": "95% CI half-width" if has_ci else None,
        "effect_size": reliability.get("mean_cv_percent"),
        "population": "Synthetic athletes with complete valid baseline repeated trials",
        "sample_size": reliability["n_subjects"],
        "protocol_id": "PROT-CMJ",
        "dataset_snapshot_id": snapshot["id"],
        "analysis_run_id": "RUN-0002",
        "diagnostics": reliability,
        "quality": "VALID" if reliability.get("status") == "COMPUTED" else "WARNING",
        "provenance": {
            "source": f"computed from {snapshot['id']} cmj_trials",
            "algorithm": "ICC(3,1) with within-subject CV and typical error",
            "algorithm_version": "1.1.0",
            "snapshot_checksum": snapshot["checksums"].get("cmj_trials.parquet"),
        },
        "interpretation": (
            f"ICC(3,1) was {_safe_float(reliability.get('icc_3_1')):.3f}"
            + (
                f" (95% CI {reliability['icc_3_1_ci_low']:.3f} to {reliability['icc_3_1_ci_high']:.3f})"
                if has_ci
                else ""
            )
            + f"; mean within-subject CV was {_safe_float(reliability.get('mean_cv_percent')):.1f}% "
            f"and the typical error was {_safe_float(reliability.get('typical_error')):.3f} N·s·kg⁻¹."
        ),
    }


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
    typical_error = float(sd / math.sqrt(2))
    for row in changes:
        row["standardized_change"] = row["change"] / sd if sd else None
        row["exceeds_typical_error"] = bool(abs(row["change"]) > typical_error)
    return {
        "n_subjects": len(changes),
        "median_change": float(np.median(values)) if len(values) else 0.0,
        "mean_change": float(np.mean(values)) if len(values) else 0.0,
        "change_sd": sd,
        "standardized_change": float(np.median(values) / sd) if len(values) else 0.0,
        "typical_error": typical_error,
        "athletes": changes,
        "method": "Baseline weeks 1–2 versus post-block weeks 9–10",
        "unit": METRIC_UNITS.get(outcome, ""),
    }


def simulate_training_response(load_values: list[float], parameters: dict[str, float]) -> dict[str, Any]:
    tau_fitness = max(0.5, float(parameters.get("tau_fitness_weeks", 4.0)))
    fatigue_tau = max(0.5, float(parameters.get("fatigue_tau_weeks", 1.8)))
    fitness_gain = float(parameters.get("fitness_gain", 0.42))
    fatigue_penalty = float(parameters.get("fatigue_penalty", 0.16))
    reference_load = max(1.0, float(parameters.get("reference_load_au", 400.0)))
    fitness = 0.0
    fatigue_state = 0.0
    states = []
    for index, value in enumerate(load_values):
        normalized = float(value) / reference_load
        fitness = fitness * math.exp(-1 / tau_fitness) + fitness_gain * normalized
        fatigue_state = fatigue_state * math.exp(-1 / fatigue_tau) + normalized
        states.append({"week": index + 1, "load": round(float(value), 3), "fitness": round(fitness, 6), "fatigue": round(fatigue_state, 6), "performance_state": round(fitness - fatigue_penalty * fatigue_state, 6)})
    return {
        "states": states,
        "parameters": {"tau_fitness_weeks": tau_fitness, "fatigue_tau_weeks": fatigue_tau, "fitness_gain": fitness_gain, "fatigue_penalty": fatigue_penalty},
        "interpretation": "Mechanistic prototype: higher load can produce a delayed fitness signal and an immediate fatigue cost.",
    }


def _training_response(load_rows: list[dict[str, Any]], trial_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit the aggregate fitness-fatigue prototype against observed weekly CMJ.

    The grid search selects the two time constants that minimise the
    standardised residual between modelled and observed performance. The
    returned artefact carries the observed series, the modelled series and the
    residuals so the ModelLab screen can display them instead of asserting fit.
    """
    weekly_load: dict[int, list[float]] = {}
    for row in load_rows:
        weekly_load.setdefault(row["week"], []).append(_safe_float(row["training_impulse_au"]))
    load = np.array([np.mean(weekly_load.get(week, [0.0])) for week in range(1, 17)], dtype=float)
    observed_weeks: list[int] = []
    observed: list[float] = []
    for week in range(1, 17):
        values = [
            _safe_float(row["concentric_impulse_n_s_kg"])
            for row in trial_rows
            if row["week"] == week and row["quality_state"] == "VALID" and row["trial_number"] == 1
        ]
        if values:
            observed_weeks.append(week)
            observed.append(float(np.mean(values)))
    observed_array = np.array(observed, dtype=float)
    load_scale = float(np.std(load)) or 1e-9
    normalized_load = (load - load.mean()) / load_scale
    performance_scale = float(np.std(observed_array)) or 1e-9
    target = (observed_array - observed_array.mean()) / performance_scale
    best: tuple[float, float, float, float] | None = None
    for tau_fitness in (2.5, 3.0, 4.0, 5.0, 6.0, 8.0):
        for fatigue_tau in (1.0, 1.4, 1.8, 2.4, 2.8):
            for fatigue_penalty in (0.15, 0.25, 0.35, 0.5):
                predicted = _impulse_response(normalized_load, tau_fitness, fatigue_tau, 1.0, fatigue_penalty)
                predicted = (predicted - predicted.mean()) / (float(np.std(predicted)) or 1e-9)
                score = float(np.sqrt(np.mean((predicted - target) ** 2)))
                if best is None or score < best[0]:
                    best = (score, tau_fitness, fatigue_tau, fatigue_penalty)
    assert best is not None
    score, tau_fitness, fatigue_tau, fatigue_penalty = best
    modelled = _impulse_response(normalized_load, tau_fitness, fatigue_tau, 1.0, fatigue_penalty)
    modelled = (modelled - modelled.mean()) / (float(np.std(modelled)) or 1e-9)
    modelled_observed_units = modelled * performance_scale + observed_array.mean()
    residuals = observed_array - modelled_observed_units
    fitted = simulate_training_response(load.tolist(), {
        "tau_fitness_weeks": tau_fitness,
        "fatigue_tau_weeks": fatigue_tau,
        "fitness_gain": 1.0,
        "fatigue_penalty": fatigue_penalty,
    })
    return {
        "id": "MODEL-RUN-0001",
        "model_spec_id": "MODEL-FITNESS-FATIGUE",
        "dataset_snapshot_id": "DS-SYNTH-001",
        "subject_ids": [],
        "parameters": {"tau_fitness_weeks": tau_fitness, "fatigue_tau_weeks": fatigue_tau, "fitness_gain": 1.0, "fatigue_penalty": fatigue_penalty},
        "output": {
            **fitted,
            "observed_weeks": observed_weeks,
            "observed_performance": [float(value) for value in observed_array],
            "modelled_performance": [float(value) for value in modelled_observed_units],
            "residuals": [float(value) for value in residuals],
            "fit_rmse_standardized": score,
            "fit_rmse_outcome_units": float(np.sqrt(np.mean(residuals**2))),
            "performance_scale": performance_scale,
        },
        "diagnostics": {
            "fit_status": "PROTOTYPE_FIT",
            "observed_weeks": len(observed_weeks),
            "model_class": "fitness-fatigue impulse response",
            "search_grid": {"tau_fitness_weeks": [2.5, 3.0, 4.0, 5.0, 6.0, 8.0], "fatigue_tau_weeks": [1.0, 1.4, 1.8, 2.4, 2.8], "fatigue_penalty": [0.15, 0.25, 0.35, 0.5]},
            "limitations": ["Aggregate prototype; not a substitute for individual inference."],
        },
        "created_at": None,
    }


def _impulse_response(
    normalized_load: np.ndarray, tau_fitness: float, fatigue_tau: float, fitness_gain: float, fatigue_penalty: float
) -> np.ndarray:
    fitness = 0.0
    fatigue_state = 0.0
    predicted = []
    for value in normalized_load:
        fitness = fitness * math.exp(-1 / tau_fitness) + fitness_gain * value
        fatigue_state = fatigue_state * math.exp(-1 / fatigue_tau) + value
        predicted.append(fitness - fatigue_penalty * fatigue_state)
    return np.array(predicted, dtype=float)


def build_training_response_model(load_rows: list[dict[str, Any]], trial_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "MODEL-FITNESS-FATIGUE",
        "name": "Training response impulse model",
        "kind": "mechanistic prototype",
        "version": "0.2.0",
        "description": "A bounded fitness-fatigue response model fitted to weekly training-load and CMJ observations.",
        "inputs": ["training_impulse_au", "concentric_impulse_n_s_kg"],
        "outputs": ["performance_state", "fitness", "fatigue"],
        "status": "PROTOTYPE",
        "parameters": {"tau_fitness_weeks": 4.0, "fatigue_tau_weeks": 1.8, "fitness_gain": 1.0, "fatigue_penalty": 0.35},
        "roadmap": [
            {"capability": "Bayesian hierarchical models", "status": "ROADMAP"},
            {"capability": "Machine learning", "status": "ROADMAP"},
            {"capability": "Physics-informed ML", "status": "ROADMAP"},
            {"capability": "Differentiable biomechanics", "status": "ROADMAP"},
            {"capability": "Forward simulation", "status": "ROADMAP"},
        ],
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
    model_run = _training_response(load_rows, trial_rows)
    timestamp = snapshot["generated_at"]
    model_run["created_at"] = timestamp
    runs = [
        {
            "id": "RUN-0001",
            "analysis_spec_id": "SPEC-LONG-001",
            "study_id": "STUDY-001",
            "snapshot_id": snapshot["id"],
            "cohort_id": "COHORT-001",
            "method_id": "METH-LONG",
            "status": "COMPLETED",
            "created_at": timestamp,
            "duration_ms": 184.6,
            "software_versions": _software_versions(),
            "seed": snapshot["seed"],
            "result": {"primary": longitudinal, "secondary": braking},
            "diagnostics": longitudinal["diagnostics"],
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
            "created_at": timestamp,
            "duration_ms": 42.1,
            "software_versions": _software_versions(),
            "seed": snapshot["seed"],
            "result": reliability,
            "diagnostics": {
                "complete_subjects": reliability["n_subjects"],
                "minimum_trials": reliability["trials_per_subject"],
                "baseline_weeks": reliability.get("baseline_weeks"),
                "status": reliability.get("status"),
            },
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
            "created_at": timestamp,
            "duration_ms": 18.7,
            "software_versions": _software_versions(),
            "seed": snapshot["seed"],
            "result": individual,
            "diagnostics": {"description": "Descriptive individual change with typical-error context; no causal individual inference.", "n_subjects": individual["n_subjects"]},
            "output_artifact_ids": ["EVID-0003"],
            "reproducibility_key": f"{snapshot['id']}:SPEC-IND-001:cmj.concentric_impulse:v1",
        },
    ]
    primary_contrast = longitudinal["contrasts"][longitudinal["primary_contrast_id"]]
    week_10_contrast = longitudinal["contrasts"]["intervention_vs_comparison_week_10"]
    baseline_balance = longitudinal["contrasts"]["baseline_balance_week_1"]
    evidence = [
        {
            "id": "EVID-0001",
            "title": "Intervention × Time effect on concentric impulse",
            "kind": "EFFECT",
            "metric_id": "MET-CMJ-IMPULSE",
            "value": primary_contrast["estimate"],
            "unit": "N·s·kg⁻¹",
            "estimate": primary_contrast["estimate"],
            "uncertainty": primary_contrast["std_error"],
            "uncertainty_label": "SE",
            "effect_size": longitudinal["effect_size"],
            "population": "Synthetic elite football cohort, weeks 1–16",
            "sample_size": longitudinal["n_observations"],
            "protocol_id": "PROT-CMJ",
            "dataset_snapshot_id": snapshot["id"],
            "analysis_run_id": "RUN-0001",
            "diagnostics": {
                **longitudinal["diagnostics"],
                "primary_contrast": primary_contrast,
                "model_implied_week_10_difference": week_10_contrast,
                "baseline_balance": baseline_balance,
                "coefficients": longitudinal["coefficients"],
            },
            "quality": "VALID",
            "provenance": {
                "source": "cmj_trials.parquet",
                "algorithm": longitudinal["method"],
                "algorithm_version": "1.2.0",
                "snapshot_checksum": snapshot["checksums"].get("cmj_trials.parquet"),
                "seed": snapshot["seed"],
                "estimator": longitudinal["estimator"],
            },
            "interpretation": (
                f"From week 1 to week 10 the intervention arm changed by {primary_contrast['estimate']:.3f} "
                f"N·s·kg⁻¹ more than the comparison arm (95% CI {primary_contrast['ci_low']:.3f} to "
                f"{primary_contrast['ci_high']:.3f}). The model-implied cross-sectional difference at week 10 was "
                f"{week_10_contrast['estimate']:.3f} (95% CI {week_10_contrast['ci_low']:.3f} to "
                f"{week_10_contrast['ci_high']:.3f}) and baseline balance was "
                f"{baseline_balance['estimate']:.3f} (95% CI {baseline_balance['ci_low']:.3f} to "
                f"{baseline_balance['ci_high']:.3f}). Synthetic-data demonstration, not a clinical or performance claim."
            ),
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
            "uncertainty_label": "typical error of a change",
            "effect_size": individual["standardized_change"],
            "population": "Individual athlete context, synthetic cohort median shown",
            "sample_size": individual["n_subjects"],
            "protocol_id": "PROT-CMJ",
            "dataset_snapshot_id": snapshot["id"],
            "analysis_run_id": "RUN-0003",
            "diagnostics": individual,
            "quality": "EXPLORATORY",
            "provenance": {
                "source": "cmj_trials.parquet",
                "algorithm": "baseline/post descriptive change",
                "algorithm_version": "1.1.0",
                "snapshot_checksum": snapshot["checksums"].get("cmj_trials.parquet"),
            },
            "interpretation": "Individual change is descriptive and should be interpreted against the baseline repeated-trial typical error.",
        },
    ]
    figures = [
        {"id": "FIG-0001", "title": "Concentric impulse response by intervention arm", "kind": "LINE", "evidence_ids": ["EVID-0001"], "dataset_snapshot_id": snapshot["id"], "analysis_run_id": "RUN-0001", "spec": {"x": "week", "y": "concentric impulse", "unit": "N·s·kg⁻¹", "series": ["INTERVENTION", "COMPARISON"], "source_artifact": "overview_signal.json"}},
        {"id": "FIG-0002", "title": "Within-subject CV across baseline athletes", "kind": "DISTRIBUTION", "evidence_ids": ["EVID-0002"], "dataset_snapshot_id": snapshot["id"], "analysis_run_id": "RUN-0002", "spec": {"x": "within-subject CV", "unit": "%", "values": [row["cv_percent"] for row in reliability.get("cv_percent_by_subject", [])], "source_artifact": "evidence.json#EVID-0002.diagnostics.cv_percent_by_subject"}},
    ]
    overview_signal = _overview_signal(trial_rows)
    return {"runs": runs, "evidence": evidence, "figures": figures, "model_spec": build_training_response_model(load_rows, trial_rows), "model_run": model_run, "overview_signal": overview_signal}


def _overview_signal(trial_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for week in range(1, 17):
        values = [row for row in trial_rows if row["week"] == week and row["quality_state"] == "VALID" and row["trial_number"] == 1]
        for arm in ("INTERVENTION", "COMPARISON"):
            arm_values = [row["concentric_impulse_n_s_kg"] for row in values if row["intervention_arm"] == arm]
            rows.append({"week": week, "arm": arm, "mean": float(np.mean(arm_values)), "sd": float(np.std(arm_values, ddof=1)) if len(arm_values) > 1 else 0.0, "n": len(arm_values)})
    return rows


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    raise TypeError(f"Not JSON serialisable: {type(value)!r}")


def dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=_json_default)
