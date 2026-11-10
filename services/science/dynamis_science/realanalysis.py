"""Scientific analyses and evidence promotion for admitted real datasets."""

from __future__ import annotations

import hashlib
import json
import math
import time
import warnings
from datetime import datetime, timezone
from typing import Any

import numpy as np
import polars as pl

from . import realstore
from .realstore import (
    STUDY_MENDELEY,
    STUDY_MOVESMART,
    artifact_dir,
    get_snapshot,
    get_study,
    read_table,
)

Z_CRITICAL = 1.959963984540054
ALPHA = 0.05
SOFTWARE = {
    "service": "dynamis-science@0.2.0",
    "python": "3.12",
    "numpy": np.__version__,
    "statsmodels": "0.14",
    "polars": "1.0",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path, default):
    import os

    if not os.path.exists(path):
        return default
    return json.loads(open(path, encoding="utf-8").read())


def _write(path, value):
    import os
    import uuid

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, path)


def list_runs() -> list[dict[str, Any]]:
    runs = _read(artifact_dir() / "real_runs.json", [])
    evidence = list_evidence()
    result = []
    for run in runs:
        reproduces = [
            other["id"]
            for other in runs
            if other["id"] != run["id"]
            and other.get("reproducibility_key") == run.get("reproducibility_key")
            and other.get("result_digest") == run.get("result_digest")
            and other["id"] < run["id"]
        ]
        result.append(
            {
                **run,
                "reproduces": reproduces,
                "evidence_ids": [item["id"] for item in evidence if item.get("analysis_run_id") == run["id"]],
            }
        )
    return result


def get_run(run_id: str) -> dict[str, Any] | None:
    return next((run for run in list_runs() if run["id"] == run_id), None)


def list_evidence() -> list[dict[str, Any]]:
    return _read(artifact_dir() / "real_evidence.json", [])


def list_figures() -> list[dict[str, Any]]:
    return _read(artifact_dir() / "real_figures.json", [])


def get_evidence(evidence_id: str) -> dict[str, Any] | None:
    return next((item for item in list_evidence() if item["id"] == evidence_id), None)


def get_figure(figure_id: str) -> dict[str, Any] | None:
    return next((item for item in list_figures() if item["id"] == figure_id), None)


def _next_id(prefix: str, records: list[dict[str, Any]]) -> str:
    numbers = [
        int(item["id"].split("-")[-1])
        for item in records
        if str(item.get("id", "")).startswith(prefix)
        and str(item["id"].split("-")[-1]).isdigit()
    ]
    return f"{prefix}{max(numbers, default=0) + 1:04d}"


# --------------------------------------------------------------------------- #
# Metric registry and cohort resolution
# --------------------------------------------------------------------------- #


METRICS: dict[str, dict[str, Any]] = {
    "MET-REAL-CMJ-HEIGHT": {
        "column": "cmj_height_cm",
        "label": "Countermovement jump height",
        "unit": "cm",
        "id": "cmj.jump_height.deposited",
        "table": "cmj_occasions",
        "source_column": "CMJht",
        "source_unit": "m",
    },
    "MET-REAL-ISO-REL-PEAK": {
        "column": "isometric_relative_peak_force_n_kg",
        "label": "Isometric relative peak force",
        "unit": "N/kg",
        "id": "isometric.relative_peak_force.deposited",
        "table": "cmj_occasions",
        "source_column": "isorelativepeakforce",
        "source_unit": "N/kg",
    },
    "MET-REAL-BS-REL": {
        "column": "back_squat_relative_kg_kg",
        "label": "Relative 1RM back squat",
        "unit": "kg/kg",
        "id": "strength.back_squat.relative_1rm",
        "table": "cmj_occasions",
        "source_column": "BSrel",
        "source_unit": "kg/kg",
    },
    "MET-REAL-SPRINT-20M": {
        "column": "sprint_20m_s",
        "label": "20 m sprint time",
        "unit": "s",
        "id": "sprint.20m_time",
        "table": "sprint_trials",
        "source_column": "sprinttimea",
        "source_unit": "s",
    },
    "MET-REAL-FZ-PEAK": {
        "column": "fz_peak_n",
        "label": "Peak vertical ground reaction force",
        "unit": "N",
        "id": "grf.peak_vertical",
        "table": "signal_trials",
        "source_column": "Force_Z",
        "source_unit": "N",
    },
    "MET-REAL-FZ-IMPULSE": {
        "column": "support_window_mean_n",
        "label": "Support-window mean vertical force",
        "unit": "N",
        "id": "grf.vertical_impulse",
        "table": "signal_trials",
        "source_column": "Force_Z",
        "source_unit": "N",
    },
    "MET-REAL-IMU-ACCEL": {
        "column": "accel_peak_g",
        "label": "Apple Watch peak user acceleration",
        "unit": "g",
        "id": "imu.user_acceleration",
        "table": "imu_trials",
        "source_column": "userAcceleration",
        "source_unit": "g",
    },
}


def metric(metric_id: str) -> dict[str, Any]:
    if metric_id not in METRICS:
        raise ValueError(f"Unknown real-data outcome metric: {metric_id}")
    return {**METRICS[metric_id], "metric_id": metric_id}


def _subjects(study_id: str) -> list[dict[str, Any]]:
    study = get_study(study_id)
    if study is None:
        return []
    frame = read_table(study["snapshot"]["id"], "subjects")
    return frame.to_dicts()


def _cohort(study_id: str, excluded: list[str] | None = None) -> dict[str, Any]:
    study = get_study(study_id)
    if study is None:
        raise ValueError("Unknown real-data study")
    excluded = sorted(set(excluded or []))
    base = study["cohort"]
    subjects = _subjects(study_id)
    included = [row for row in subjects if row["subject_id"] not in excluded]
    if study_id == STUDY_MENDELEY:
        quality = study["data_health"]
        missing = quality["missing_observations"]
        valid = 250 - missing
        expected = 252
        missing_slots = quality["missing_slots"]
        excluded_trials: list[dict[str, Any]] = []
        n_trials = 168
    else:
        expected = int(study["snapshot"]["row_counts"].get("signal_trials", 0))
        valid = expected
        missing = 0
        missing_slots = []
        excluded_trials = []
        n_trials = expected
    athletes = []
    for row in subjects:
        if row["subject_id"] in excluded:
            continue
        athletes.append(
            {
                "subject_id": row["subject_id"],
                "display_id": row["display_id"],
                "position": row["position"],
                "intervention_arm": "INTERVENTION",
                "included": True,
                "valid_trials": 4 if study_id == STUDY_MENDELEY else int(row.get("matched_trial_count", 0)),
                "excluded_trials": 0,
                "missing_trials": 1 if study_id == STUDY_MENDELEY and row["subject_id"] in {"MEN-04", "MEN-14"} else 0,
            }
        )
    return {
        "cohort": {
            **base,
            "subject_ids": [row["subject_id"] for row in included],
            "excluded_subject_ids": excluded,
            "derived_from": "COHORT-REAL-001" if excluded else None,
            "status": "DRAFT" if excluded else "FROZEN",
        },
        "n": len(included),
        "arm_counts": {"INTERVENTION": len(included), "COMPARISON": 0},
        "inclusion_criteria": ["All athletes with an admitted observation in the snapshot."],
        "exclusion_criteria": base.get("exclusion_criteria", []),
        "filters": {"excluded_subject_ids": excluded},
        "trial_quality": {
            "valid": valid - (len(excluded) * 4 if study_id == STUDY_MENDELEY else 0),
            "excluded": len(excluded),
            "missing": missing,
            "expected": expected,
            "missing_by_arm": {"INTERVENTION": missing},
            "excluded_trials": excluded_trials,
            "missing_slots": missing_slots,
        },
        "n_trials": n_trials,
        "athletes": athletes,
        "snapshot_id": study["snapshot"]["id"],
    }


# --------------------------------------------------------------------------- #
# Exploration
# --------------------------------------------------------------------------- #


def explore(study_id: str, metric_id: str, excluded: list[str] | None, reference: str = "RAW") -> dict[str, Any]:
    study = get_study(study_id)
    if study is None:
        raise ValueError("Unknown real-data study")
    definition = metric(metric_id)
    cohort = _cohort(study_id, excluded)
    included = {row["subject_id"] for row in cohort["athletes"]}
    frame = read_table(study["snapshot"]["id"], definition["table"]).filter(
        pl.col("subject_id").is_in(list(included))
    )
    subjects = {row["subject_id"]: row for row in _subjects(study_id)}
    if study_id == STUDY_MENDELEY:
        occasions = sorted(frame["occasion"].unique().to_list())
        value_column = definition["column"]
        summary = []
        athletes = []
        for subject_id in sorted(included):
            subject_rows = frame.filter(pl.col("subject_id") == subject_id)
            raw_values: list[float | None] = []
            n_valid: list[int] = []
            for occasion in occasions:
                rows = subject_rows.filter(pl.col("occasion") == occasion)
                values = [float(v) for v in rows[value_column].to_list() if v is not None]
                raw_values.append(float(np.mean(values)) if values else None)
                n_valid.append(len(values))
            baseline = raw_values[0]
            if reference == "CHANGE":
                values = [None if value is None or baseline is None else value - baseline for value in raw_values]
            elif reference == "PERCENT":
                values = [None if value is None or not baseline else (value - baseline) / baseline * 100 for value in raw_values]
            else:
                values = raw_values
            athletes.append(
                {
                    "subject_id": subject_id,
                    "display_id": subjects[subject_id]["display_id"],
                    "intervention_arm": "INTERVENTION",
                    "raw": raw_values,
                    "values": values,
                    "n_valid": n_valid,
                    "n_excluded": [0] * len(occasions),
                    "n_missing": [0 if value is not None else 1 for value in raw_values],
                    "baseline": baseline,
                }
            )
        for occasion in occasions:
            rows = frame.filter(pl.col("occasion") == occasion)
            values = np.array([float(v) for v in rows[value_column].to_list() if v is not None], dtype=float)
            if reference != "RAW":
                baseline_rows = frame.filter(pl.col("occasion") == 1)
                baseline_by_subject = {
                    row["subject_id"]: float(row[value_column])
                    for row in baseline_rows.iter_rows(named=True)
                    if row[value_column] is not None
                }
                centered = []
                for row in rows.iter_rows(named=True):
                    if row[value_column] is None or row["subject_id"] not in baseline_by_subject:
                        continue
                    base = baseline_by_subject[row["subject_id"]]
                    if reference == "CHANGE":
                        centered.append(float(row[value_column]) - base)
                    elif base:
                        centered.append((float(row[value_column]) - base) / base * 100)
                values = np.array(centered, dtype=float)
            mean = float(values.mean()) if len(values) else None
            sd = float(values.std(ddof=1)) if len(values) > 1 else None
            half = float(1.96 * sd / math.sqrt(len(values))) if sd and len(values) else None
            summary.append(
                {
                    "arm": "INTERVENTION",
                    "week": occasion,
                    "occasion": occasion,
                    "n": len(values),
                    "n_athletes": len(values),
                    "mean": mean,
                    "sd": sd,
                    "ci_low": mean - half if mean is not None and half is not None else None,
                    "ci_high": mean + half if mean is not None and half is not None else None,
                    "missing_athletes": int((frame.filter(pl.col("occasion") == occasion).select(pl.col("subject_id")).n_unique()) - len(values)),
                    "excluded_trials": 0,
                    "missing_trials": 1 if occasion == 4 else 0,
                }
            )
        labels = [f"Occasion {occasion}" for occasion in occasions]
        unit = definition["unit"]
        return {
            "metric": {
                "column": definition["column"],
                "label": definition["label"],
                "unit": unit,
                "id": definition["id"],
                "metric_id": metric_id,
            },
            "unit": unit,
            "reference": reference,
            "reference_label": {"RAW": "observed values", "CHANGE": "change from occasion 1", "PERCENT": "percent change from occasion 1"}[reference],
            "cohort": {"id": cohort["cohort"]["id"], "status": cohort["cohort"]["status"], "n": cohort["n"], "excluded_subject_ids": cohort["cohort"]["excluded_subject_ids"]},
            "summary": summary,
            "athletes": athletes,
            "context": [],
            "annotations": {
                "intervention_block": {"start_week": 1, "end_week": 4, "source": "four repeated testing occasions; not calendar weeks"},
                "load_peaks": [],
                "load_peak_rule": "Training-load context is not deposited; no load peaks are inferred.",
            },
            "method": {
                "unit_of_analysis": "athlete-occasion (post-priming row)",
                "interval": "mean ± 1.96 × between-athlete SEM",
                "engine": "polars + numpy",
                "note": f"Occasions are the four deposited testing blocks ({', '.join(labels)}), not calendar weeks. Missing rows are shown as missing and never imputed.",
            },
            "provenance": {
                "snapshot_id": study["snapshot"]["id"],
                "source_doi": study["source"]["doi"],
                "source_license": study["source"]["license"]["id"],
                "checksum": study["snapshot"]["checksums"].get(f"{definition['table']}.parquet"),
            },
        }
    # MoveSmart explore: one point per activity, repeated trials aggregated within subject.
    activities = sorted(frame["activity"].unique().to_list())
    summary = []
    athletes = []
    for subject_id in sorted(included):
        subject_rows = frame.filter(pl.col("subject_id") == subject_id)
        values = []
        n_valid = []
        for activity in activities:
            rows = subject_rows.filter(pl.col("activity") == activity)
            vals = [float(v) for v in rows[definition["column"]].to_list() if v is not None]
            values.append(float(np.mean(vals)) if vals else None)
            n_valid.append(len(vals))
        athletes.append(
            {
                "subject_id": subject_id,
                "display_id": subjects[subject_id]["display_id"],
                "intervention_arm": "INTERVENTION",
                "raw": values,
                "values": values,
                "n_valid": n_valid,
                "n_excluded": [0] * len(activities),
                "n_missing": [0 if value is not None else 1 for value in values],
                "baseline": values[0] if values else None,
            }
        )
    for index, activity in enumerate(activities, start=1):
        rows = frame.filter(pl.col("activity") == activity)
        values = np.array([float(v) for v in rows[definition["column"]].to_list() if v is not None], dtype=float)
        mean = float(values.mean()) if len(values) else None
        sd = float(values.std(ddof=1)) if len(values) > 1 else None
        half = float(1.96 * sd / math.sqrt(len(values))) if sd and len(values) else None
        summary.append(
            {
                "arm": "INTERVENTION",
                "week": index,
                "activity": activity,
                "n": len(values),
                "n_athletes": int(rows["subject_id"].n_unique()),
                "mean": mean,
                "sd": sd,
                "ci_low": mean - half if mean is not None and half is not None else None,
                "ci_high": mean + half if mean is not None and half is not None else None,
                "missing_athletes": 0,
                "excluded_trials": 0,
                "missing_trials": 0,
            }
        )
    return {
        "metric": {
            "column": definition["column"],
            "label": definition["label"],
            "unit": definition["unit"],
            "id": definition["id"],
            "metric_id": metric_id,
        },
        "unit": definition["unit"],
        "reference": "RAW",
        "reference_label": "observed values",
        "cohort": {"id": cohort["cohort"]["id"], "status": cohort["cohort"]["status"], "n": cohort["n"], "excluded_subject_ids": cohort["cohort"]["excluded_subject_ids"]},
        "summary": summary,
        "athletes": athletes,
        "context": [],
        "annotations": {
            "intervention_block": {"start_week": 1, "end_week": len(activities), "source": "activities are ordered alphabetically; there is no intervention"},
            "load_peaks": [],
            "load_peak_rule": "No training-load data.",
        },
        "method": {
            "unit_of_analysis": "trial for summaries; athlete-activity mean for individual traces",
            "interval": "mean ± 1.96 × SEM across trials",
            "engine": "polars + numpy",
            "note": "Activities are not a longitudinal sequence; the x-axis is an activity index, not time.",
        },
        "provenance": {
            "snapshot_id": study["snapshot"]["id"],
            "source_doi": study["source"]["doi"],
            "source_license": study["source"]["license"]["id"],
            "checksum": study["snapshot"]["checksums"].get(f"{definition['table']}.parquet"),
        },
    }


def athlete_longitudinal(study_id: str, subject_id: str, metric_id: str) -> dict[str, Any]:
    study = get_study(study_id)
    if study is None:
        raise ValueError("Unknown real-data study")
    definition = metric(metric_id)
    subjects = {row["subject_id"]: row for row in _subjects(study_id)}
    if subject_id not in subjects:
        raise ValueError("Subject not found")
    frame = read_table(study["snapshot"]["id"], definition["table"]).filter(
        pl.col("subject_id") == subject_id
    )
    observations = []
    if study_id == STUDY_MENDELEY:
        baseline_values = [
            float(row[definition["column"]])
            for row in frame.iter_rows(named=True)
            if row["occasion"] == 1 and row[definition["column"]] is not None
        ]
        baseline_mean = float(np.mean(baseline_values)) if baseline_values else None
        for occasion in sorted(frame["occasion"].unique().to_list()):
            rows = frame.filter(pl.col("occasion") == occasion)
            values = [float(row[definition["column"]]) for row in rows.iter_rows(named=True) if row[definition["column"]] is not None]
            value = float(np.mean(values)) if values else None
            observations.append(
                {
                    "week": occasion,
                    "value": value,
                    "n_trials": len(values),
                    "expected_trials": 1,
                    "missing_trials": 0 if values else 1,
                    "excluded_trials": 0,
                    "quality_state": "VALID" if values else "MISSING",
                    "rolling_mean": None,
                    "rolling_sd": None,
                    "z_score": None,
                    "percent_change_from_baseline": (value - baseline_mean) / baseline_mean * 100 if value is not None and baseline_mean else None,
                    "coefficient_of_variation": None,
                    "typical_error": None,
                    "phase": "Testing occasion",
                    "load": None,
                    "wellness": None,
                    "trials": [
                        {
                            "trial_id": row["trial_id"],
                            "week": occasion,
                            "trial_number": 1,
                            "value": float(row[definition["column"]]),
                            "quality_state": row.get("quality_state", "VALID"),
                            "exclusion_reason": None,
                            "trace_available": False,
                        }
                        for row in rows.iter_rows(named=True)
                        if row[definition["column"]] is not None
                    ],
                }
            )
        values = [item["value"] for item in observations if item["value"] is not None]
        change = (values[-1] - values[0]) if len(values) >= 2 else None
        cohort_values = []
        for row in read_table(study["snapshot"]["id"], "cmj_occasions").iter_rows(named=True):
            if row[definition["column"]] is not None:
                cohort_values.append(float(row[definition["column"]]))
        sd = float(np.std(cohort_values, ddof=1)) if len(cohort_values) > 1 else 1.0
        individual = {
            "method": "first and last observed testing occasion",
            "baseline_weeks": [1],
            "post_weeks": [observations[-1]["week"]] if observations else [],
            "baseline_mean": values[0] if values else None,
            "post_mean": values[-1] if values else None,
            "change": change,
            "percent_change": (change / values[0] * 100) if change is not None and values and values[0] else None,
            "standardized_change": change / sd if change is not None and sd else None,
            "exceeds_typical_error": None,
            "typical_error": 0.0,
            "cohort_change_sd": sd,
            "n_subjects": len(_subjects(study_id)),
            "limitations": "No repeated within-session trial exists, so typical error and standardised change cannot be estimated from this deposit.",
        }
    else:
        for index, activity in enumerate(sorted(frame["activity"].unique().to_list()), start=1):
            rows = frame.filter(pl.col("activity") == activity)
            values = [float(row[definition["column"]]) for row in rows.iter_rows(named=True) if row[definition["column"]] is not None]
            observations.append(
                {
                    "week": index,
                    "value": float(np.mean(values)) if values else None,
                    "n_trials": len(values),
                    "expected_trials": len(values),
                    "missing_trials": 0,
                    "excluded_trials": 0,
                    "quality_state": "VALID" if values else "MISSING",
                    "rolling_mean": None,
                    "rolling_sd": None,
                    "z_score": None,
                    "percent_change_from_baseline": None,
                    "coefficient_of_variation": None,
                    "typical_error": None,
                    "phase": activity,
                    "load": None,
                    "wellness": None,
                    "trials": [
                        {
                            "trial_id": row["trial_id"],
                            "week": index,
                            "trial_number": int(row["trial_number"]),
                            "value": float(row[definition["column"]]),
                            "quality_state": "VALID",
                            "exclusion_reason": None,
                            "trace_available": True,
                        }
                        for row in rows.iter_rows(named=True)
                        if row[definition["column"]] is not None
                    ],
                }
            )
        first = observations[0]["value"] if observations else None
        last = observations[-1]["value"] if observations else None
        individual = {
            "method": "activity mean, not a longitudinal change",
            "baseline_weeks": [1],
            "post_weeks": [len(observations)],
            "baseline_mean": first,
            "post_mean": last,
            "change": (last - first) if first is not None and last is not None else None,
            "percent_change": None,
            "standardized_change": None,
            "exceeds_typical_error": None,
            "typical_error": 0.0,
            "cohort_change_sd": 0.0,
            "n_subjects": len(_subjects(study_id)),
            "limitations": "Activities are not a time sequence; this panel is descriptive only.",
        }
    return {
        "subject": subjects[subject_id],
        "metric": {"column": definition["column"], "label": definition["label"], "unit": definition["unit"], "id": definition["id"], "metric_id": metric_id},
        "observations": observations,
        "typical_error": 0.0,
        "individual": individual,
        "provenance": {"snapshot_id": study["snapshot"]["id"], "source_doi": study["source"]["doi"]},
    }


# --------------------------------------------------------------------------- #
# Statistical methods
# --------------------------------------------------------------------------- #


def _reliability_matrix(values: np.ndarray) -> dict[str, Any]:
    from .analysis import two_way_icc

    n, k = values.shape
    means = values.mean(axis=1)
    within_sd = values.std(axis=1, ddof=1) if k > 1 else np.zeros(n)
    cv_values = within_sd / np.maximum(np.abs(means), 1e-9)
    grand_mean = float(means.mean())
    icc = two_way_icc(values)
    typical_error = icc["typical_error"]
    return {
        "method": "ICC(3,1) repeated-measures reliability",
        "status": "COMPUTED",
        "n_subjects": int(n),
        "trials_per_subject": int(k),
        "mean_cv_percent": float(np.mean(cv_values) * 100),
        "median_cv_percent": float(np.median(cv_values) * 100),
        "cv_percent_by_subject": [
            {"subject_id": str(index), "cv_percent": float(cv * 100)} for index, cv in enumerate(cv_values)
        ],
        "typical_error_percent": float(typical_error / abs(grand_mean) * 100) if grand_mean else None,
        "minimal_detectable_change_95": float(typical_error * Z_CRITICAL * math.sqrt(2)),
        **icc,
        "mean_subject_mean": grand_mean,
    }


def _fit_trend(frame, outcome: str, cohort_ids: list[str], reference: int, contrast: int, unit: str = "cm") -> dict[str, Any]:
    from statsmodels.regression.mixed_linear_model import MixedLM

    rows = [
        row
        for row in frame.iter_rows(named=True)
        if row["subject_id"] in cohort_ids and row.get(outcome) is not None
    ]
    rows.sort(key=lambda row: (row["subject_id"], row["occasion"]))
    if len(rows) < 8:
        raise ValueError("Fewer than 8 complete observations; mixed model is not estimable")
    occasions = np.array([float(row["occasion"]) for row in rows])
    outcomes = np.array([float(row[outcome]) for row in rows])
    subjects = [str(row["subject_id"]) for row in rows]
    elapsed = occasions - float(reference)
    design = np.column_stack([np.ones(len(rows)), elapsed])
    random_design = np.column_stack([np.ones(len(rows)), elapsed])
    labels = ["intercept", "occasion_slope"]
    attempts: list[str] = []
    fitted = None
    estimator = "MIXEDLM_RANDOM_SLOPE"

    def best_fit(random_effects_design: np.ndarray, prefix: str) -> Any | None:
        """Run several optimisers and keep the highest-likelihood converged fit.

        L-BFGS-B can stop in a local optimum for random-slope models (observed
        on the real Mendeley data: logLik -215.8 vs the lme4 optimum -208.3).
        Selecting the best of several deterministic starts makes the Python
        reference reproducible and comparable with lme4.
        """
        candidates: list[tuple[float, str, Any]] = []
        for method in ("lbfgs", "bfgs", "powell", "nm"):
            try:
                model = MixedLM(
                    endog=outcomes,
                    exog=design,
                    groups=np.array(subjects),
                    exog_re=random_effects_design,
                )
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    candidate = model.fit(
                        reml=False, method=method, maxiter=20000, disp=False
                    )
                if not bool(candidate.converged):
                    raise RuntimeError(f"did not converge with {method}")
                beta = np.asarray(candidate.fe_params, dtype=float)
                covariance = np.asarray(candidate.cov_params(), dtype=float)[
                    : design.shape[1], : design.shape[1]
                ]
                likelihood = float(candidate.llf)
                if (
                    not np.all(np.isfinite(beta))
                    or not np.all(np.isfinite(covariance))
                    or not math.isfinite(likelihood)
                ):
                    raise RuntimeError("non-finite estimates")
                candidates.append((likelihood, method, candidate))
            except Exception as error:  # noqa: BLE001 - optimizer-specific
                attempts.append(f"{prefix}-{method}:{type(error).__name__}")
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        likelihood, method, candidate = candidates[0]
        attempts.append(f"{prefix}:selected={method}:logLik={likelihood:.6f}")
        return candidate

    fitted = best_fit(random_design, "slope")
    if fitted is None:
        # Documented fallback: random intercept only.
        estimator = "MIXEDLM_RANDOM_INTERCEPT"
        fitted = best_fit(np.ones((len(rows), 1)), "intercept")
    if fitted is None:
        raise RuntimeError("MixedLM failed for every documented specification")
    beta = np.asarray(fitted.fe_params, dtype=float)
    covariance = np.asarray(fitted.cov_params(), dtype=float)[: design.shape[1], : design.shape[1]]
    residuals = outcomes - design @ beta
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0))
    span = float(contrast - reference)
    slope = float(beta[1])
    slope_se = float(standard_errors[1])
    change = slope * span
    change_se = slope_se * span
    random_effects = {}
    try:
        cov_re = np.asarray(fitted.cov_re, dtype=float)
        random_effects = {
            "subject_intercept_variance": float(cov_re[0, 0]),
            "subject_slope_variance": float(cov_re[1, 1]) if cov_re.shape[0] > 1 else 0.0,
            "subject_intercept_slope_covariance": float(cov_re[0, 1]) if cov_re.shape[0] > 1 else 0.0,
            "residual_variance": float(fitted.scale),
        }
    except Exception:
        random_effects = {}
    baseline_sd = float(np.std([float(row[outcome]) for row in rows if row["occasion"] == reference], ddof=1)) if sum(1 for row in rows if row["occasion"] == reference) > 1 else float(np.std(outcomes, ddof=1))
    # Residual diagnostics. `residuals` are marginal (y - X beta): they keep the
    # between-athlete variance and are used for population mean-structure misfit
    # by occasion. The Q-Q uses conditional Pearson residuals (y - X beta - Z b) / sigma,
    # the scale on which the within-athlete normality assumption is stated.
    conditional = np.asarray(fitted.resid, dtype=float)
    sigma = math.sqrt(max(1e-12, float(fitted.scale)))
    order = np.argsort(conditional)
    ranks = (np.arange(len(conditional)) + 0.625) / (len(conditional) + 0.25)
    from scipy import stats

    theoretical = stats.norm.ppf(ranks)
    standardized = conditional / sigma
    residual_qq = [
        {"theoretical": float(theoretical[index]), "observed": float(standardized[order[index]])}
        for index in range(0, len(residuals), max(1, len(residuals) // 60))
    ]
    residual_by_occasion = []
    for occasion in sorted(set(int(value) for value in occasions)):
        mask = occasions == occasion
        residual_by_occasion.append({"week": occasion, "mean_residual": float(np.mean(residuals[mask]))})
    result = {
        "method": "statsmodels MixedLM with athlete random intercept and random occasion slope",
        "formula": f"{outcome} ~ occasion_c + (1 + occasion_c | subject_id), ML",
        "outcome": outcome,
        "unit": unit,
        "reference_occasion": reference,
        "contrast_occasion": contrast,
        "n_observations": int(len(rows)),
        "n_subjects": int(len(set(subjects))),
        "coefficients": {
            label: {
                "estimate": float(beta[index]),
                "std_error": float(standard_errors[index]),
                "ci_low": float(beta[index] - Z_CRITICAL * standard_errors[index]),
                "ci_high": float(beta[index] + Z_CRITICAL * standard_errors[index]),
            }
            for index, label in enumerate(labels)
        },
        "model_status": "COMPLETED",
        "estimator": estimator,
        "optimizer": next((item.split(":")[1].replace("selected=", "") for item in attempts if "selected=" in item), None),
        "estimator_attempts": attempts,
        "converged": True,
        "log_likelihood": float(fitted.llf),
        "random_effects": random_effects,
        "contrasts": {
            "occasion_slope": {
                "estimate": slope,
                "std_error": slope_se,
                "ci_low": slope - Z_CRITICAL * slope_se,
                "ci_high": slope + Z_CRITICAL * slope_se,
                "unit": f"{unit} per occasion",
                "contrast": f"Within-athlete change in {outcome} per testing occasion",
                "interpretation": "Positive values indicate higher outcome values at later occasions.",
            },
            f"occasion_{reference}_to_{contrast}": {
                "estimate": change,
                "std_error": change_se,
                "ci_low": change - Z_CRITICAL * change_se,
                "ci_high": change + Z_CRITICAL * change_se,
                "unit": unit,
                "contrast": f"Change from occasion {reference} to occasion {contrast}",
                "interpretation": "Model-implied within-athlete change over the observed span.",
            },
        },
        "primary_contrast_id": "occasion_slope",
        "effect_size": change / baseline_sd if baseline_sd else None,
        "effect_size_basis": "change from reference to contrast occasion divided by baseline between-athlete SD",
        "diagnostics": {
            "estimator": estimator,
            "optimizer": next((item.split(":")[1].replace("selected=", "") for item in attempts if "selected=" in item), None),
            "model_status": "COMPLETED",
            "converged": True,
            "n_observations": int(len(rows)),
            "n_subjects": int(len(set(subjects))),
            "residual_summary": {
                "rmse": float(math.sqrt(np.mean(residuals ** 2))),
                "mean_residual": float(np.mean(residuals)),
                "max_abs_residual": float(np.max(np.abs(residuals))),
            },
            "week_centering": reference,
            "quality_note": "Complete-case analysis; missing CMJ rows are not imputed.",
            "estimator_attempts": attempts,
            "log_likelihood": float(fitted.llf),
            "residual_by_week": residual_by_occasion,
            "residual_qq": residual_qq,
            "residual_qq_type": "CONDITIONAL_PEARSON",
            "residual_definitions": {
                "residual_summary": "marginal: y - X beta_hat (includes between-athlete deviations)",
                "residual_by_week": "marginal: y - X beta_hat, mean per occasion",
                "residual_qq": "conditional Pearson: (y - X beta_hat - Z b_hat) / sigma_hat; BLUP shrinkage makes these less dispersed than N(0,1) and correlated, so the Q-Q is exploratory",
            },
            "conditional_residual_summary": {
                "sd_over_sigma": float(np.std(standardized, ddof=1)),
                "max_abs_pearson": float(np.max(np.abs(standardized))),
            },
            "conditional_residuals": [
                {"subject_id": subjects[index], "occasion": int(occasions[index]), "residual": float(conditional[index])}
                for index in range(len(conditional))
            ],
            "residual_by_arm": {"INTERVENTION": {"n": int(len(rows)), "sd": float(np.std(residuals, ddof=1)), "mean": float(np.mean(residuals))}},
            "sample_context": {
                "valid_first_trials_used": int(len(rows)),
                "excluded_trials_in_cohort": 0,
                "excluded_trial_ids": [],
                "valid_repeat_trials_not_modelled": 0,
                "observations_per_subject_min": int(min(sum(1 for subj in subjects if subj == subject) for subject in set(subjects))),
                "observations_per_subject_max": int(max(sum(1 for subj in subjects if subj == subject) for subject in set(subjects))),
                "weeks_observed": sorted(set(int(value) for value in occasions)),
            },
            "baseline_balance": {
                "estimate": 0.0,
                "std_error": 0.0,
                "ci_low": 0.0,
                "ci_high": 0.0,
                "unit": "cm",
                "contrast": "Single-arm study; baseline between-arm balance is not applicable.",
                "interpretation": "There is no comparison arm in the deposited table.",
            },
            "assumptions": [
                "Linearity of the occasion effect on the model scale.",
                "Normally distributed athlete intercepts and occasion slopes.",
                "Missing CMJ rows are missing at random conditional on athlete.",
                "The four COND values are ordered testing occasions, not randomised conditions.",
            ],
            "limitations": [
                "Single-arm design; no causal contrast against a concurrent control.",
                "The deposit does not map COND 1-4 to calendar weeks or training phases.",
                "No raw force traces, so CMJ height cannot be independently recomputed.",
                "Only 19 athletes contribute the fourth occasion; two are missing.",
            ],
        },
    }
    return result


def descriptive_trend(snapshot_id: str, outcome: str, cohort_ids: list[str], unit: str = "cm") -> dict[str, Any]:
    frame = read_table(snapshot_id, "cmj_occasions")
    rows = [row for row in frame.iter_rows(named=True) if row["subject_id"] in cohort_ids and row.get(outcome) is not None]
    occasions = sorted({int(row["occasion"]) for row in rows})
    summary = []
    for occasion in occasions:
        values = np.array([float(row[outcome]) for row in rows if int(row["occasion"]) == occasion], dtype=float)
        mean = float(values.mean())
        sd = float(values.std(ddof=1)) if len(values) > 1 else None
        half = float(1.96 * sd / math.sqrt(len(values))) if sd and len(values) else None
        summary.append({"occasion": occasion, "n": int(len(values)), "mean": mean, "sd": sd, "ci_low": mean - half if half else None, "ci_high": mean + half if half else None})
    first = next((item for item in summary if item["occasion"] == 1), None)
    last = summary[-1] if summary else None
    change = last["mean"] - first["mean"] if first and last else None
    return {
        "method": "Descriptive occasion means with normal 95% intervals",
        "status": "COMPUTED",
        "outcome": outcome,
        "unit": unit,
        "occasions": summary,
        "change_first_to_last": change,
        "percent_change_first_to_last": (change / first["mean"] * 100) if change is not None and first and first["mean"] else None,
        "n_subjects": len({row["subject_id"] for row in rows}),
        "n_observations": len(rows),
        "limitations": ["Descriptive only; no model-based inference.", "Occasions are not mapped to calendar weeks."],
    }


def signal_qa(snapshot_id: str, cohort_ids: list[str]) -> dict[str, Any]:
    trials = read_table(snapshot_id, "signal_trials")
    rows = [row for row in trials.iter_rows(named=True) if row["subject_id"] in cohort_ids]
    activities = sorted({row["activity"] for row in rows})
    summary = []
    for activity in activities:
        subset = [row for row in rows if row["activity"] == activity]
        peaks = np.array([float(row["fz_peak_n"]) for row in subset], dtype=float)
        offsets = np.array([float(row["imu_clock_offset_s"]) for row in subset if row["imu_clock_offset_s"] is not None])
        summary.append(
            {
                "activity": activity,
                "n_trials": len(subset),
                "n_subjects": len({row["subject_id"] for row in subset}),
                "peak_fz_mean_n": float(peaks.mean()),
                "peak_fz_sd_n": float(peaks.std(ddof=1)) if len(peaks) > 1 else None,
                "peak_fz_min_n": float(peaks.min()),
                "peak_fz_max_n": float(peaks.max()),
                "sampling_hz": sorted({float(row["sampling_hz"]) for row in subset}),
                "three_plate_trials": sum(1 for row in subset if row["force_file_count"] == 3),
                "nan_trials": sum(1 for row in subset if (row["nan_count"] or 0) > 0),
                "clock_offset_median_s": float(np.median(offsets)) if offsets.size else None,
                "clock_offset_sd_s": float(offsets.std(ddof=1)) if offsets.size > 1 else None,
            }
        )
    imu = read_table(snapshot_id, "imu_trials")
    imu_rows = [row for row in imu.iter_rows(named=True) if row["subject_id"] in cohort_ids]
    rates = np.array([float(row["sampling_hz_median"]) for row in imu_rows if row["sampling_hz_median"] is not None])
    gravity = np.array([float(row["gravity_mean_g"]) for row in imu_rows if row["gravity_mean_g"] is not None])
    accel = np.array([float(row["accel_peak_g"]) for row in imu_rows if row["accel_peak_g"] is not None])
    body_weight = []
    for row in rows:
        if row["activity"] in {"Walking", "Heel drop"} and row["support_window_mean_n"] is not None and row["metadata_weight_n"]:
            body_weight.append(
                {
                    "subject_id": row["subject_id"],
                    "activity": row["activity"],
                    "trial_id": row["trial_id"],
                    "support_window_mean_n": float(row["support_window_mean_n"]),
                    "metadata_weight_n": float(row["metadata_weight_n"]),
                    "difference_n": float(row["support_window_mean_n"] - row["metadata_weight_n"]),
                    "percent_error": float((row["support_window_mean_n"] - row["metadata_weight_n"]) / row["metadata_weight_n"] * 100),
                }
            )
    diffs = np.array([item["difference_n"] for item in body_weight], dtype=float)
    bias = float(diffs.mean()) if diffs.size else None
    sd = float(diffs.std(ddof=1)) if diffs.size > 1 else None
    return {
        "method": "Force-plate and IMU signal qualification",
        "status": "COMPUTED",
        "activities": summary,
        "imu": {
            "n_trials": len(imu_rows),
            "sampling_hz_min": float(rates.min()) if rates.size else None,
            "sampling_hz_max": float(rates.max()) if rates.size else None,
            "gravity_mean_min_g": float(gravity.min()) if gravity.size else None,
            "gravity_mean_max_g": float(gravity.max()) if gravity.size else None,
            "accel_peak_max_g": float(accel.max()) if accel.size else None,
        },
        "body_weight": {
            "n": len(body_weight),
            "bias_n": bias,
            "sd_n": sd,
            "loa_low_n": bias - 1.96 * sd if bias is not None and sd is not None else None,
            "loa_high_n": bias + 1.96 * sd if bias is not None and sd is not None else None,
            "mean_percent_error": float(np.mean([item["percent_error"] for item in body_weight])) if body_weight else None,
            "rows": body_weight,
        },
        "sampling_hz": 1000.0,
        "limitations": [
            "Body weight is compared with anthropometric metadata embedded in participant folder names, not with an independent scale measurement.",
            "Only walking and heel-drop support windows are expected to approximate body weight; running and drop landings are not.",
            "Device clocks differ by hours; no sample-level synchronisation is claimed.",
            "Only 120 of 398 matched trials have all three force plates.",
        ],
    }


def reliability(snapshot_id: str, cohort_ids: list[str], activity: str, max_trials: int = 8) -> dict[str, Any]:
    trials = read_table(snapshot_id, "signal_trials")
    rows = [row for row in trials.iter_rows(named=True) if row["subject_id"] in cohort_ids and row["activity"] == activity]
    by_subject: dict[str, list[float]] = {}
    # Keep acquisition order: trials are the ICC(3,1) column factor, never sort by value.
    for row in sorted(rows, key=lambda item: (item["subject_id"], int(item["trial_number"]))):
        by_subject.setdefault(row["subject_id"], []).append(float(row["fz_peak_n"]))
    complete = {key: values for key, values in by_subject.items() if len(values) >= 2}
    if len(complete) < 3:
        return {"method": "ICC(3,1)", "status": "INSUFFICIENT_DATA", "message": "Fewer than three participants have at least two trials.", "activity": activity}
    k = min(max_trials, min(len(values) for values in complete.values()))
    subjects = sorted(complete)
    matrix = np.array([complete[subject][:k] for subject in subjects], dtype=float)
    result = _reliability_matrix(matrix)
    result.update(
        {
            "activity": activity,
            "subject_ids": subjects,
            "outcome": "peak vertical GRF",
            "unit": "N",
            "n_trials_available": len(rows),
            "n_trials_used": int(matrix.size),
            "excluded_trials": len(rows) - int(matrix.size),
            "limitations": [
                f"Balanced subset: the first {k} trials per participant are used; later trials are excluded to keep the ICC design balanced.",
                "Peak force is not normalised to body weight, so between-participant differences remain.",
                "Walking speed is not controlled in the deposited trials.",
                "The deposit has no calibration log.",
            ],
        }
    )
    result["cv_percent_by_subject"] = [
        {"subject_id": subject, "cv_percent": float(matrix[index].std(ddof=1) / max(abs(matrix[index].mean()), 1e-9) * 100)}
        for index, subject in enumerate(subjects)
    ]
    return result


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #


def _spec_for(study: dict[str, Any], method_id: str, outcome_id: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            spec
            for spec in study["analysis_specs"]
            if spec["method_id"] == method_id
            and spec["outcome_metric_id"] == outcome_id
            and spec["parameters"] == parameters
        ),
        None,
    )


def execute(
    study_id: str,
    method_id: str,
    outcome_metric_id: str,
    excluded_subject_ids: list[str] | None,
    parameters: dict[str, Any] | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    study = get_study(study_id)
    if study is None:
        raise ValueError("Real-data study not found")
    cohort = _cohort(study_id, excluded_subject_ids)
    cohort_ids = cohort["cohort"]["subject_ids"]
    parameters = parameters or {}
    allowed = {
        STUDY_MENDELEY: {"METH-REAL-TREND", "METH-REAL-DESC"},
        STUDY_MOVESMART: {"METH-REAL-SIGNAL-QA", "METH-REAL-RELIABILITY", "METH-REAL-BODYWEIGHT"},
    }[study_id]
    if method_id not in allowed:
        raise ValueError(f"Method {method_id} is not applicable to {study_id}")
    spec = _spec_for(study, method_id, outcome_metric_id, parameters)
    if method_id == "METH-REAL-TREND":
        result = _fit_trend(
            read_table(study["snapshot"]["id"], "cmj_occasions"),
            metric(outcome_metric_id)["column"],
            cohort_ids,
            int(parameters.get("reference_occasion", 1)),
            int(parameters.get("contrast_occasion", 4)),
            metric(outcome_metric_id)["unit"],
        )
        diagnostics = result["diagnostics"]
    elif method_id == "METH-REAL-DESC":
        result = descriptive_trend(study["snapshot"]["id"], metric(outcome_metric_id)["column"], cohort_ids, metric(outcome_metric_id)["unit"])
        diagnostics = {
            "status": "COMPUTED",
            "occasions": len(result["occasions"]),
            "n_subjects": result["n_subjects"],
            "n_observations": result["n_observations"],
            "assumptions": ["Descriptive summaries only."],
            "limitations": result["limitations"],
        }
    elif method_id == "METH-REAL-SIGNAL-QA":
        result = signal_qa(study["snapshot"]["id"], cohort_ids)
        diagnostics = {
            "status": "COMPUTED",
            "activities": len(result["activities"]),
            "imu_trials": result["imu"]["n_trials"],
            "body_weight_comparisons": result["body_weight"]["n"],
            "assumptions": ["Force_Z is vertical in the local plate frame.", "The sum of available plates represents total vertical GRF."],
            "limitations": result["limitations"],
        }
    elif method_id == "METH-REAL-BODYWEIGHT":
        qa = signal_qa(study["snapshot"]["id"], cohort_ids)
        result = {"method": "Body-weight recovery from support-phase impulse", "status": "COMPUTED", **qa["body_weight"], "activities": qa["activities"], "limitations": qa["limitations"]}
        diagnostics = {
            "status": "COMPUTED",
            "n": qa["body_weight"]["n"],
            "bias_n": qa["body_weight"]["bias_n"],
            "sd_n": qa["body_weight"]["sd_n"],
            "assumptions": ["Support windows include a complete sequence of steps for walking.", "Anthropometric metadata are accurate."],
            "limitations": qa["limitations"],
        }
    elif method_id == "METH-REAL-RELIABILITY":
        activity = str(parameters.get("activity", "Walking"))
        result = reliability(study["snapshot"]["id"], cohort_ids, activity, int(parameters.get("max_trials", 8)))
        diagnostics = {
            "status": result.get("status"),
            "activity": activity,
            "n_subjects": result.get("n_subjects"),
            "trials_per_subject": result.get("trials_per_subject"),
            "n_trials_used": result.get("n_trials_used"),
            "excluded_trials": result.get("excluded_trials"),
            "assumptions": ["Balanced subset of the first k trials per participant.", "Peak force is measured in the same activity."],
            "limitations": result.get("limitations", []),
        }
    else:  # pragma: no cover
        raise ValueError("Unhandled method")
    if spec is None:
        digest = hashlib.sha256(
            json.dumps([study_id, method_id, outcome_metric_id, parameters, cohort["cohort"]["id"]], sort_keys=True).encode()
        ).hexdigest()[:8].upper()
        spec = {
            "id": f"SPEC-REAL-X-{digest}",
            "study_id": study_id,
            "name": f"Exploratory {method_id}",
            "method_id": method_id,
            "method_version": "1.0.0",
            "cohort_id": cohort["cohort"]["id"],
            "snapshot_id": study["snapshot"]["id"],
            "outcome_metric_id": outcome_metric_id,
            "model_formula": result.get("formula", result.get("method", "")),
            "parameters": parameters,
            "planned_contrasts": [],
            "status": "EXPLORATORY",
            "registered_after_source_acquisition": True,
        }
    runs = _read(artifact_dir() / "real_runs.json", [])
    run_id = _next_id("RUN-REAL-", runs)
    duration_ms = (time.perf_counter() - started) * 1000
    result_for_digest = json.loads(json.dumps(result, sort_keys=True, default=str))
    result_digest = hashlib.sha256(json.dumps(result_for_digest, sort_keys=True).encode()).hexdigest()[:16]
    reproducibility_key = hashlib.sha256(
        json.dumps(
            [study["snapshot"]["id"], spec["id"], cohort["cohort"]["id"], parameters, study["snapshot"]["checksums"]],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:24]
    run = {
        "id": run_id,
        "analysis_spec_id": spec["id"],
        "study_id": study_id,
        "snapshot_id": study["snapshot"]["id"],
        "cohort_id": cohort["cohort"]["id"],
        "method_id": method_id,
        "outcome_metric_id": outcome_metric_id,
        "status": "COMPLETED",
        "plan_alignment": "EXPLORATORY",
        "created_at": _now(),
        "duration_ms": duration_ms,
        "software_versions": {**SOFTWARE, "r": "4.6.2 (qualification only)"},
        "seed": 0,
        "parameters": parameters,
        "result": result,
        "diagnostics": diagnostics,
        "output_artifact_ids": [],
        "reproducibility_key": reproducibility_key,
        "result_digest": result_digest,
        "execution": {"analysis_spec": spec, "cohort": cohort["cohort"]},
        "evidence_ids": [],
    }
    runs.append(run)
    _write(artifact_dir() / "real_runs.json", runs)
    return get_run(run_id) or run


# --------------------------------------------------------------------------- #
# Evidence promotion
# --------------------------------------------------------------------------- #


def _evidence_payload(run: dict[str, Any], study: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = run["result"]
    snapshot = study["snapshot"]
    if run["method_id"] == "METH-REAL-TREND":
        contrast = result["contrasts"][result["primary_contrast_id"]]
        change = result["contrasts"][f"occasion_{result['reference_occasion']}_to_{result['contrast_occasion']}"]
        evidence = {
            "title": "CMJ height change across four repeated testing occasions",
            "kind": "EFFECT",
            "metric_id": "MET-REAL-CMJ-HEIGHT",
            "value": change["estimate"],
            "unit": "cm",
            "estimate": change["estimate"],
            "slope_per_occasion": contrast["estimate"],
            "uncertainty": (change["ci_high"] - change["ci_low"]) / 2,
            "uncertainty_label": "95% CI half-width for change from occasion 1 to 4",
            "effect_size": result.get("effect_size"),
            "contrast_id": result["primary_contrast_id"],
            "population": "21 highly trained male collegiate athletes; single arm",
            "sample_size": result["n_subjects"],
            "protocol_id": "PROT-REAL-CMJ-FP",
            "dataset_snapshot_id": snapshot["id"],
            "analysis_run_id": run["id"],
            "diagnostics": result["diagnostics"],
            "quality": "VALID" if result.get("converged") else "WARNING",
            "provenance": {
                "source": f"computed from {snapshot['id']} cmj_occasions",
                "algorithm": result["method"],
                "algorithm_version": "1.0.0",
                "snapshot_checksum": snapshot["checksums"].get("cmj_occasions.parquet"),
                "source_doi": study["source"]["doi"],
                "source_license": study["source"]["license"]["id"],
                "r_reference": "R 4.6.2 lme4 2.1-0, ML; see qualification record QUAL-REAL-MIXEDLM",
            },
            "interpretation": (
                f"Within-athlete CMJ height changed by {contrast['estimate']:+.2f} cm per occasion "
                f"(95% CI {contrast['ci_low']:.2f} to {contrast['ci_high']:.2f}); the model-implied change "
                f"from occasion 1 to 4 was {change['estimate']:+.2f} cm (95% CI {change['ci_low']:.2f} to {change['ci_high']:.2f}). "
                "The design is single-arm; this is not a causal effect of the intervention."
            ),
            "evidence_class": "EXPLORATORY",
            "interval": {"low": change["ci_low"], "high": change["ci_high"], "level": 0.95, "kind": "Wald 95% CI"},
        }
        summary = result["diagnostics"].get("residual_by_week", [])
        figure = {
            "title": "CMJ height by testing occasion",
            "kind": "LINE",
            "analysis_run_id": run["id"],
            "dataset_snapshot_id": snapshot["id"],
            "spec": {
                "x": "occasion",
                "y": "CMJ height",
                "unit": "cm",
                "series": ["INTERVENTION"],
                "metric_id": "MET-REAL-CMJ-HEIGHT",
                "cohort_id": run["cohort_id"],
                "source_artifact": "cmj_occasions.parquet",
            },
            "data": {
                "kind": "LINE",
                "unit": "cm",
                "metric": {"label": "CMJ height", "unit": "cm", "id": "cmj.jump_height.deposited", "metric_id": "MET-REAL-CMJ-HEIGHT"},
                "series": [],
            },
        }
        # Build the figure series from the descriptive run if available, otherwise from the model data.
        frame = read_table(snapshot["id"], "cmj_occasions")
        for occasion in sorted(frame["occasion"].unique().to_list()):
            values = np.array([float(row["cmj_height_cm"]) for row in frame.iter_rows(named=True) if row["occasion"] == occasion and row["cmj_height_cm"] is not None])
            mean = float(values.mean()) if values.size else None
            sd = float(values.std(ddof=1)) if values.size > 1 else None
            half = float(1.96 * sd / math.sqrt(values.size)) if sd and values.size else None
            figure["data"]["series"].append({"arm": "INTERVENTION", "week": occasion, "n": int(values.size), "mean": mean, "sd": sd, "ci_low": mean - half if half else None, "ci_high": mean + half if half else None})
        return evidence, figure
    if run["method_id"] == "METH-REAL-RELIABILITY":
        evidence = {
            "title": f"Trial-to-trial reliability of peak vertical GRF · {result['activity']}",
            "kind": "RELIABILITY",
            "metric_id": "MET-REAL-FZ-PEAK",
            "value": result["icc_3_1"],
            "unit": "ICC(3,1)",
            "estimate": result["icc_3_1"],
            "uncertainty": (result["icc_3_1_ci_high"] - result["icc_3_1_ci_low"]) / 2 if math.isfinite(result["icc_3_1_ci_high"]) else None,
            "uncertainty_label": "95% CI half-width",
            "effect_size": result["mean_cv_percent"],
            "population": f"{result['n_subjects']} participants; {result['trials_per_subject']} repeated {result['activity'].lower()} trials each",
            "sample_size": result["n_subjects"],
            "protocol_id": "PROT-REAL-OVERGROUND",
            "dataset_snapshot_id": snapshot["id"],
            "analysis_run_id": run["id"],
            "diagnostics": result,
            "quality": "VALID" if result["icc_3_1"] >= 0 else "WARNING",
            "provenance": {
                "source": f"computed from {snapshot['id']} signal_trials",
                "algorithm": "ICC(3,1) with within-subject CV and typical error",
                "algorithm_version": "1.0.0",
                "snapshot_checksum": snapshot["checksums"].get("signal_trials.parquet"),
                "source_doi": study["source"]["doi"],
                "source_license": study["source"]["license"]["id"],
            },
            "interpretation": (
                f"ICC(3,1) for peak vertical GRF across repeated {result['activity'].lower()} trials was "
                f"{result['icc_3_1']:.3f} (95% CI {result['icc_3_1_ci_low']:.3f} to {result['icc_3_1_ci_high']:.3f}); "
                f"within-subject CV was {result['mean_cv_percent']:.1f}% and typical error was {result['typical_error']:.0f} N. "
                "This is within-activity reliability, not agreement between devices."
            ),
            "evidence_class": "EXPLORATORY",
            "interval": {"low": result["icc_3_1_ci_low"], "high": result["icc_3_1_ci_high"], "level": 0.95, "kind": "Shrout-Fleiss F-based 95% CI"},
        }
        figure = {
            "title": f"Within-subject CV of peak vertical GRF · {result['activity']}",
            "kind": "DISTRIBUTION",
            "analysis_run_id": run["id"],
            "dataset_snapshot_id": snapshot["id"],
            "spec": {"x": "within-subject CV", "unit": "%", "values": [row["cv_percent"] for row in result["cv_percent_by_subject"]], "source_artifact": "signal_trials.parquet"},
            "data": {"kind": "DISTRIBUTION", "unit": "%", "values": [row["cv_percent"] for row in result["cv_percent_by_subject"]]},
        }
        return evidence, figure
    if run["method_id"] == "METH-REAL-SIGNAL-QA":
        body = result["body_weight"]
        evidence = {
            "title": "Force-plate and IMU measurement qualification",
            "kind": "DESCRIPTIVE",
            "metric_id": "MET-REAL-FZ-IMPULSE",
            "value": body.get("bias_n"),
            "unit": "N",
            "estimate": body.get("bias_n"),
            "uncertainty": body.get("sd_n"),
            "uncertainty_label": "SD of support-window minus metadata body weight",
            "effect_size": body.get("mean_percent_error"),
            "population": "10 healthy adults; five activities; 398 matched trials",
            "sample_size": len({row["subject_id"] for row in read_table(snapshot["id"], "signal_trials").iter_rows(named=True)}),
            "protocol_id": "PROT-REAL-OVERGROUND",
            "dataset_snapshot_id": snapshot["id"],
            "analysis_run_id": run["id"],
            "diagnostics": result,
            "quality": "WARNING",
            "provenance": {
                "source": f"computed from {snapshot['id']} signal_trials and imu_trials",
                "algorithm": "support-phase detection and impulse integration",
                "algorithm_version": "1.0.0",
                "snapshot_checksum": snapshot["checksums"].get("signal_trials.parquet"),
                "source_doi": study["source"]["doi"],
                "source_license": study["source"]["license"]["id"],
            },
            "interpretation": (
                f"Across {body.get('n', 0)} walking/heel-drop trials, support-window mean force differed from "
                f"anthropometric body weight by {body.get('bias_n', float('nan')):+.0f} N "
                f"(SD {body.get('sd_n', float('nan')):.0f} N). Device clocks differed by about four hours; "
                "trial matching is by participant, activity and trial number, not by timestamp."
            ),
            "evidence_class": "EXPLORATORY",
            "interval": None,
        }
        figure = {
            "title": "Peak vertical GRF by activity",
            "kind": "DISTRIBUTION",
            "analysis_run_id": run["id"],
            "dataset_snapshot_id": snapshot["id"],
            "spec": {"x": "activity", "unit": "N", "values": [item["peak_fz_mean_n"] for item in result["activities"]], "source_artifact": "signal_trials.parquet"},
            "data": {"kind": "DISTRIBUTION", "unit": "N", "values": [item["peak_fz_mean_n"] for item in result["activities"]]},
        }
        return evidence, figure
    if run["method_id"] == "METH-REAL-BODYWEIGHT":
        evidence = {
            "title": "Body-weight recovery from support-phase impulse",
            "kind": "DESCRIPTIVE",
            "metric_id": "MET-REAL-FZ-IMPULSE",
            "value": result.get("bias_n"),
            "unit": "N",
            "estimate": result.get("bias_n"),
            "uncertainty": result.get("sd_n"),
            "uncertainty_label": "SD of differences",
            "effect_size": result.get("mean_percent_error"),
            "population": "Walking and heel-drop trials with a complete support window",
            "sample_size": result.get("n", 0),
            "protocol_id": "PROT-REAL-OVERGROUND",
            "dataset_snapshot_id": snapshot["id"],
            "analysis_run_id": run["id"],
            "diagnostics": result,
            "quality": "WARNING",
            "provenance": {"source": f"computed from {snapshot['id']} signal_trials", "algorithm": "support-window mean force vs anthropometric weight", "algorithm_version": "1.0.0", "source_doi": study["source"]["doi"]},
            "interpretation": f"Mean bias {result.get('bias_n', float('nan')):+.0f} N; 95% limits of agreement {result.get('loa_low_n', float('nan')):+.0f} to {result.get('loa_high_n', float('nan')):+.0f} N.",
            "evidence_class": "EXPLORATORY",
            "interval": None,
        }
        figure = {"title": "Support-window mean force", "kind": "DISTRIBUTION", "analysis_run_id": run["id"], "dataset_snapshot_id": snapshot["id"], "spec": {"unit": "N", "values": [row["support_window_mean_n"] for row in result.get("rows", [])]}, "data": {"kind": "DISTRIBUTION", "unit": "N", "values": [row["support_window_mean_n"] for row in result.get("rows", [])]}}
        return evidence, figure
    raise ValueError("No evidence mapping for this method")


def promote(run_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise ValueError("Run not found")
    evidence_items = list_evidence()
    existing = next((item for item in evidence_items if item["analysis_run_id"] == run_id), None)
    if existing:
        figure = next((item for item in list_figures() if existing["id"] in item.get("evidence_ids", [])), None)
        return {"evidence_artifact": existing, "figure_artifact": figure, "already_promoted": True}
    study = get_study(run["study_id"])
    assert study is not None
    evidence, figure = _evidence_payload(run, study)
    evidence_id = _next_id("EVID-REAL-", evidence_items)
    figures = list_figures()
    figure_id = _next_id("FIG-REAL-", figures)
    evidence = {
        "id": evidence_id,
        **evidence,
        "study_id": run["study_id"],
        "analysis_spec_id": run["analysis_spec_id"],
        "cohort_id": run["cohort_id"],
        "reproducibility_key": run["reproducibility_key"],
        "result_digest": run["result_digest"],
        "version": 1,
        "state": "CURRENT",
        "created_at": _now(),
        "figure_ids": [figure_id],
    }
    figure = {
        "id": figure_id,
        **figure,
        "evidence_ids": [evidence_id],
        "study_id": run["study_id"],
        "created_at": _now(),
    }
    evidence_items.append(evidence)
    figures.append(figure)
    _write(artifact_dir() / "real_evidence.json", evidence_items)
    _write(artifact_dir() / "real_figures.json", figures)
    runs = _read(artifact_dir() / "real_runs.json", [])
    for item in runs:
        if item["id"] == run_id:
            item["output_artifact_ids"] = [evidence_id, figure_id]
    _write(artifact_dir() / "real_runs.json", runs)
    return {"evidence_artifact": evidence, "figure_artifact": figure, "already_promoted": False}


# --------------------------------------------------------------------------- #
# Investigations
# --------------------------------------------------------------------------- #


def _default_blocks(study_id: str) -> list[dict[str, Any]]:
    if study_id == STUDY_MENDELEY:
        return [
            {"id": "B-QUESTION-1", "type": "question", "title": "Research question", "state": {}, "collapsed": False},
            {"id": "B-DATASET-1", "type": "dataset", "title": "Immutable real-data snapshot", "state": {}, "collapsed": False},
            {"id": "B-COHORT-1", "type": "cohort", "title": "Cohort", "state": {"excluded_subject_ids": []}, "collapsed": False},
            {"id": "B-EXPLORE-1", "type": "explore", "title": "CMJ height across testing occasions", "state": {"metric_id": "MET-REAL-CMJ-HEIGHT", "population": "ALL", "reference": "RAW", "context": []}, "collapsed": False},
            {"id": "B-ANALYSIS-1", "type": "analysis", "title": "Linear mixed-effects change model", "state": {"method_id": "METH-REAL-TREND", "outcome_metric_id": "MET-REAL-CMJ-HEIGHT", "parameters": {"reference_occasion": 1, "contrast_occasion": 4, "alpha": 0.05}, "cohort_block_id": "B-COHORT-1"}, "collapsed": False},
            {"id": "B-DIAGNOSTICS-1", "type": "diagnostics", "title": "Model diagnostics", "state": {"analysis_block_id": "B-ANALYSIS-1"}, "collapsed": False},
            {"id": "B-EVIDENCE-1", "type": "evidence", "title": "Evidence from the run", "state": {"analysis_block_id": "B-ANALYSIS-1"}, "collapsed": False},
            {"id": "B-REPORT-1", "type": "report_section", "title": "Report", "state": {}, "collapsed": False},
        ]
    return [
        {"id": "B-QUESTION-1", "type": "question", "title": "Research question", "state": {}, "collapsed": False},
        {"id": "B-DATASET-1", "type": "dataset", "title": "Immutable real-data snapshot", "state": {}, "collapsed": False},
        {"id": "B-COHORT-1", "type": "cohort", "title": "Cohort", "state": {"excluded_subject_ids": []}, "collapsed": False},
        {"id": "B-ANALYSIS-1", "type": "analysis", "title": "Signal qualification", "state": {"method_id": "METH-REAL-SIGNAL-QA", "outcome_metric_id": "MET-REAL-FZ-PEAK", "parameters": {}, "cohort_block_id": "B-COHORT-1"}, "collapsed": False},
        {"id": "B-DIAGNOSTICS-1", "type": "diagnostics", "title": "Signal diagnostics", "state": {"analysis_block_id": "B-ANALYSIS-1"}, "collapsed": False},
        {"id": "B-EVIDENCE-1", "type": "evidence", "title": "Qualification evidence", "state": {"analysis_block_id": "B-ANALYSIS-1"}, "collapsed": False},
        {"id": "B-ANALYSIS-2", "type": "analysis", "title": "Peak-force reliability", "state": {"method_id": "METH-REAL-RELIABILITY", "outcome_metric_id": "MET-REAL-FZ-PEAK", "parameters": {"activity": "Walking", "max_trials": 8}, "cohort_block_id": "B-COHORT-1"}, "collapsed": False},
        {"id": "B-DIAGNOSTICS-2", "type": "diagnostics", "title": "Reliability diagnostics", "state": {"analysis_block_id": "B-ANALYSIS-2"}, "collapsed": False},
        {"id": "B-EVIDENCE-2", "type": "evidence", "title": "Reliability evidence", "state": {"analysis_block_id": "B-ANALYSIS-2"}, "collapsed": False},
        {"id": "B-REPORT-1", "type": "report_section", "title": "Report", "state": {}, "collapsed": False},
    ]


def list_investigations() -> list[dict[str, Any]]:
    path = artifact_dir() / "real_investigations.json"
    records = _read(path, [])
    if records:
        return records
    records = [
        {
            "id": "INV-REAL-001",
            "study_id": STUDY_MENDELEY,
            "title": "Primary longitudinal analysis",
            "status": "ACTIVE",
            "version": 1,
            "created_at": _now(),
            "updated_at": _now(),
            "blocks": _default_blocks(STUDY_MENDELEY),
        },
        {
            "id": "INV-REAL-002",
            "study_id": STUDY_MOVESMART,
            "title": "Measurement qualification",
            "status": "ACTIVE",
            "version": 1,
            "created_at": _now(),
            "updated_at": _now(),
            "blocks": _default_blocks(STUDY_MOVESMART),
        },
    ]
    _write(path, records)
    return records


def get_investigation(investigation_id: str) -> dict[str, Any] | None:
    return next((item for item in list_investigations() if item["id"] == investigation_id), None)


def update_investigation(investigation_id: str, blocks: list[dict[str, Any]], base_version: int) -> dict[str, Any]:
    records = list_investigations()
    item = next((record for record in records if record["id"] == investigation_id), None)
    if item is None:
        raise ValueError("Investigation not found")
    if int(base_version) != int(item["version"]):
        raise ValueError(f"Version conflict: expected {item['version']}, received {base_version}")
    item["blocks"] = blocks
    item["version"] = int(item["version"]) + 1
    item["updated_at"] = _now()
    _write(artifact_dir() / "real_investigations.json", records)
    return item
