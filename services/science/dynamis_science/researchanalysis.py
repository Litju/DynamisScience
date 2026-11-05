"""Generic scientific execution for scientist-authored studies.

The numerical routines are the same ones qualified during RES-587.  This module
adapts them to arbitrary admitted snapshots and scientist-authored cohorts; it
does not introduce a second statistical implementation.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import polars as pl

from . import realanalysis, researchstore
from .realanalysis import Z_CRITICAL

SOFTWARE = {
    "service": "dynamis-science@0.3.0",
    "python": platform.python_version(),
    "numpy": np.__version__,
    "statsmodels": "0.14",
    "polars": pl.__version__,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _metric(snapshot_id: str, metric_id: str) -> dict[str, Any]:
    metrics = researchstore.dataset_metrics(snapshot_id)
    metric = next((item for item in metrics if item["id"] == metric_id), None)
    if metric is None:
        raise researchstore.ResearchValidation(f"Metric {metric_id} is not present in {snapshot_id}")
    return metric


def axis_for(snapshot_id: str, metric: dict[str, Any], definition: dict[str, Any] | None = None) -> tuple[str, str]:
    table = metric["table"]
    if table == "cmj_occasions":
        return "occasion", "Testing occasion"
    if table == "cmj_trials":
        return "week", "Week"
    if table == "signal_trials":
        activity = (definition or {}).get("activity")
        return ("trial_number", "Repeated trial") if activity else ("activity", "Activity")
    return "row", "Observation"


def _frame(snapshot_id: str, metric: dict[str, Any], cohort_ids: list[str], definition: dict[str, Any] | None = None) -> pl.DataFrame:
    frame = researchstore.read_snapshot_table(snapshot_id, metric["table"])
    if "subject_id" in frame.columns:
        frame = frame.filter(pl.col("subject_id").is_in(cohort_ids))
    activity = (definition or {}).get("activity")
    if activity and "activity" in frame.columns:
        frame = frame.filter(pl.col("activity") == activity)
    return frame


def _descriptive(snapshot_id: str, metric: dict[str, Any], cohort_ids: list[str], definition: dict[str, Any] | None = None) -> dict[str, Any]:
    frame = _frame(snapshot_id, metric, cohort_ids, definition)
    axis, axis_label = axis_for(snapshot_id, metric, definition)
    if axis not in frame.columns:
        raise researchstore.ResearchValidation(f"{metric['table']} has no {axis} axis")
    rows = [row for row in frame.iter_rows(named=True) if row.get(metric["column"]) is not None]
    points = sorted({int(row[axis]) for row in rows if row.get(axis) is not None})
    subjects = sorted({str(row["subject_id"]) for row in rows})
    summary = []
    for point in points:
        values = [float(row[metric["column"]]) for row in rows if int(row[axis]) == point and row.get(metric["column"]) is not None]
        mean = float(np.mean(values)) if values else None
        sd = float(np.std(values, ddof=1)) if len(values) > 1 else None
        half = float(1.96 * sd / math.sqrt(len(values))) if sd and values else None
        summary.append(
            {
                axis: point,
                "week": point,
                "arm": "INTERVENTION",
                "n": len(values),
                "n_athletes": len({str(row["subject_id"]) for row in rows if int(row[axis]) == point}),
                "mean": mean,
                "sd": sd,
                "ci_low": mean - half if mean is not None and half is not None else None,
                "ci_high": mean + half if mean is not None and half is not None else None,
                "missing_athletes": len(subjects) - len({str(row["subject_id"]) for row in rows if int(row[axis]) == point}),
                "excluded_trials": 0,
                "missing_trials": max(0, len(subjects) - len({str(row["subject_id"]) for row in rows if int(row[axis]) == point})),
            }
        )
    first = summary[0] if summary else None
    last = summary[-1] if summary else None
    change = last["mean"] - first["mean"] if first and last and first["mean"] is not None and last["mean"] is not None else None
    return {
        "method": f"Descriptive {axis_label.lower()} summaries with normal 95% intervals",
        "status": "COMPUTED",
        "outcome": metric["id"],
        "unit": metric["unit"],
        "axis": axis,
        "axis_label": axis_label,
        "points": summary,
        "occasions": summary,
        "change_first_to_last": change,
        "percent_change_first_to_last": (change / first["mean"] * 100) if change is not None and first and first["mean"] else None,
        "n_subjects": len(subjects),
        "n_observations": len(rows),
        "limitations": [
            "Descriptive only; no model-based inference.",
            "Missing observations are reported, not imputed.",
        ],
    }


def _individual_change(snapshot_id: str, metric: dict[str, Any], cohort_ids: list[str], definition: dict[str, Any], reference: int, contrast: int) -> dict[str, Any]:
    frame = _frame(snapshot_id, metric, cohort_ids, definition)
    axis, axis_label = axis_for(snapshot_id, metric, definition)
    if axis not in frame.columns:
        raise researchstore.ResearchValidation(f"{metric['table']} has no {axis} axis")
    rows = [row for row in frame.iter_rows(named=True) if row.get(metric["column"]) is not None]
    by_subject: dict[str, dict[int, list[float]]] = {}
    for row in rows:
        by_subject.setdefault(str(row["subject_id"]), {}).setdefault(int(row[axis]), []).append(float(row[metric["column"]]))
    values = []
    missing = []
    for subject_id in sorted(by_subject):
        reference_values = by_subject[subject_id].get(reference, [])
        contrast_values = by_subject[subject_id].get(contrast, [])
        if not reference_values or not contrast_values:
            missing.append({"subject_id": subject_id, "reason": f"Missing {reference} or {contrast} observation"})
            continue
        baseline = float(np.mean(reference_values))
        post = float(np.mean(contrast_values))
        values.append({"subject_id": subject_id, "baseline": baseline, "post": post, "change": post - baseline, "percent_change": (post - baseline) / baseline * 100 if baseline else None})
    if len(values) < 3:
        raise researchstore.ResearchValidation("Fewer than three complete pairs; individual change is not estimable")
    changes = np.array([item["change"] for item in values], dtype=float)
    change_sd = float(np.std(changes, ddof=1)) if len(changes) > 1 else None
    typical_error = change_sd / math.sqrt(2) if change_sd else None
    for item in values:
        item["standardized_change"] = item["change"] / change_sd if change_sd else None
        item["exceeds_typical_error"] = abs(item["change"]) > typical_error if typical_error else None
    median = float(np.median(changes))
    return {
        "method": "Individual change between two repeated observations",
        "status": "COMPUTED",
        "axis": axis,
        "axis_label": axis_label,
        "reference": reference,
        "contrast": contrast,
        "athletes": values,
        "n_subjects": len(values),
        "median_change": median,
        "mean_change": float(np.mean(changes)),
        "change_sd": change_sd,
        "standardized_change": median / change_sd if change_sd else None,
        "typical_error": typical_error,
        "typical_error_note": "Cohort change SD / √2 is context for individual change, not a same-session measurement-error estimate.",
        "missing": missing,
        "limitations": [
            "Descriptive; no causal individual response is inferred.",
            "Typical error is not estimated from repeated same-session trials unless the dataset provides them.",
        ],
    }


def eligible_spec(entity: dict[str, Any], plan: dict[str, Any] | None, method_id: str, outcome_id: str, parameters: dict[str, Any], cohort_id: str, excluded: list[str]) -> tuple[dict[str, Any] | None, str]:
    if plan and plan.get("status") == "FROZEN":
        if (
            plan["method_id"] == method_id
            and plan["outcome_metric_id"] == outcome_id
            and plan["cohort_id"] == cohort_id
            and canonical_parameters(plan.get("parameters", {})) == canonical_parameters(parameters)
            and not excluded
        ):
            return researchstore.plan_as_spec(plan, entity), "PLANNED"
        if plan["method_id"] == method_id or plan["outcome_metric_id"] == outcome_id:
            return None, "EXPLORATORY"
    return None, "EXPLORATORY"


def canonical_parameters(parameters: dict[str, Any]) -> str:
    return canonical_json({key: parameters[key] for key in sorted(parameters)})


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def execute(
    entity: dict[str, Any],
    cohort: dict[str, Any],
    plan: dict[str, Any] | None,
    method_id: str,
    outcome_metric_id: str,
    parameters: dict[str, Any] | None,
    excluded_subject_ids: list[str] | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    snapshot_id = entity["dataset_snapshot_id"]
    metric = _metric(snapshot_id, outcome_metric_id)
    metrics = researchstore.dataset_metrics(snapshot_id)
    methods = {item["id"]: item for item in researchstore.methods_for_snapshot(snapshot_id)}
    if method_id not in methods:
        raise researchstore.ResearchValidation(f"Method {method_id} is not registered for snapshot {snapshot_id}")
    if metric["table"] not in methods[method_id]["required_tables"]:
        raise researchstore.ResearchValidation(f"{methods[method_id]['name']} is not applicable to {metric['table']}")
    parameters = {**(plan.get("parameters", {}) if plan else {}), **(parameters or {})}
    definition = {
        "snapshot_id": snapshot_id,
        "require_metric_id": outcome_metric_id,
        "activity": parameters.get("activity") or cohort.get("activity"),
        "exclude_subject_ids": excluded_subject_ids or [],
    }
    resolved = researchstore.resolve_cohort(cohort, snapshot_id, excluded_subject_ids=excluded_subject_ids)
    cohort_ids = resolved["cohort"]["subject_ids"]
    if not cohort_ids:
        raise researchstore.ResearchValidation("The resolved cohort is empty")
    diagnostics: dict[str, Any] = {}
    figure_data: dict[str, Any] | None = None
    if method_id == "METH-REAL-TREND":
        frame = researchstore.read_snapshot_table(snapshot_id, "cmj_occasions")
        result = realanalysis._fit_trend(
            frame,
            metric["column"],
            cohort_ids,
            int(parameters.get("reference_occasion", 1)),
            int(parameters.get("contrast_occasion", 4)),
            metric["unit"],
        )
        diagnostics = result["diagnostics"]
        summary = _descriptive(snapshot_id, metric, cohort_ids, definition)
        figure_data = {
            "kind": "LINE",
            "unit": metric["unit"],
            "metric": {"label": metric["label"], "unit": metric["unit"], "id": metric["definition_id"], "metric_id": metric["id"]},
            "series": [{"arm": "INTERVENTION", "week": row["occasion"], "n": row["n"], "mean": row["mean"], "sd": row["sd"], "ci_low": row["ci_low"], "ci_high": row["ci_high"]} for row in summary["points"]],
        }
    elif method_id == "METH-REAL-DESC":
        result = _descriptive(snapshot_id, metric, cohort_ids, definition)
        diagnostics = {
            "status": "COMPUTED",
            "axis": result["axis"],
            "points": len(result["points"]),
            "n_subjects": result["n_subjects"],
            "n_observations": result["n_observations"],
            "assumptions": ["Descriptive summaries only."],
            "limitations": result["limitations"],
        }
        figure_data = {
            "kind": "LINE",
            "unit": metric["unit"],
            "metric": {"label": metric["label"], "unit": metric["unit"], "id": metric["definition_id"], "metric_id": metric["id"]},
            "series": [{"arm": "INTERVENTION", "week": row[result["axis"]], "n": row["n"], "mean": row["mean"], "sd": row["sd"], "ci_low": row["ci_low"], "ci_high": row["ci_high"]} for row in result["points"]],
        }
    elif method_id == "METH-U-CHANGE":
        result = _individual_change(
            snapshot_id,
            metric,
            cohort_ids,
            definition,
            int(parameters.get("reference_week", parameters.get("reference_occasion", 1))),
            int(parameters.get("contrast_week", parameters.get("contrast_occasion", 2))),
        )
        diagnostics = {
            "status": "COMPUTED",
            "n_subjects": result["n_subjects"],
            "typical_error": result["typical_error"],
            "change_sd": result["change_sd"],
            "missing": result["missing"],
            "assumptions": ["Paired observations are comparable."],
            "limitations": result["limitations"],
        }
        figure_data = {
            "kind": "SCATTER",
            "unit": metric["unit"],
            "points": [{"subject_id": item["subject_id"], "baseline": item["baseline"], "change": item["change"]} for item in result["athletes"]],
            "typical_error": result["typical_error"],
        }
    elif method_id == "METH-REAL-RELIABILITY":
        activity = str(parameters.get("activity", "Walking"))
        result = realanalysis.reliability(snapshot_id, cohort_ids, activity, int(parameters.get("max_trials", 8)))
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
        if result.get("status") == "COMPUTED":
            figure_data = {
                "kind": "DISTRIBUTION",
                "unit": "%",
                "values": [row["cv_percent"] for row in result.get("cv_percent_by_subject", [])],
            }
    elif method_id == "METH-REAL-SIGNAL-QA":
        result = realanalysis.signal_qa(snapshot_id, cohort_ids)
        diagnostics = {
            "status": "COMPUTED",
            "activities": len(result["activities"]),
            "imu_trials": result["imu"]["n_trials"],
            "body_weight_comparisons": result["body_weight"]["n"],
            "assumptions": ["Force_Z is vertical in the local plate frame.", "The sum of available plates represents total vertical GRF."],
            "limitations": result["limitations"],
        }
        figure_data = {
            "kind": "LINE",
            "unit": "N",
            "series": [
                {"arm": "INTERVENTION", "week": index, "n": row["n_trials"], "mean": row["peak_fz_mean_n"], "sd": row["peak_fz_sd_n"], "ci_low": None, "ci_high": None, "label": row["activity"]}
                for index, row in enumerate(result["activities"], start=1)
            ],
        }
    elif method_id == "METH-U-DESC":
        result = _descriptive(snapshot_id, metric, cohort_ids, definition)
        diagnostics = {
            "status": "COMPUTED",
            "axis": result["axis"],
            "points": len(result["points"]),
            "n_subjects": result["n_subjects"],
            "n_observations": result["n_observations"],
            "assumptions": ["Descriptive summaries only."],
            "limitations": result["limitations"],
        }
        figure_data = {
            "kind": "LINE",
            "unit": metric["unit"],
            "metric": {"label": metric["label"], "unit": metric["unit"], "id": metric["definition_id"], "metric_id": metric["id"]},
            "series": [{"arm": "INTERVENTION", "week": row[result["axis"]], "n": row["n"], "mean": row["mean"], "sd": row["sd"], "ci_low": row["ci_low"], "ci_high": row["ci_high"]} for row in result["points"]],
        }
    else:  # pragma: no cover - rejected methods never reach execution
        raise researchstore.ResearchValidation(f"Method {method_id} is not executable")
    duration_ms = (time.perf_counter() - started) * 1000
    spec, alignment = eligible_spec(entity, plan, method_id, outcome_metric_id, parameters, cohort["id"], excluded_subject_ids or [])
    if spec is None:
        digest = _digest([entity["id"], method_id, outcome_metric_id, parameters, cohort["id"], excluded_subject_ids or []])[:8].upper()
        spec = {
            "id": f"SPEC-U-X-{digest}",
            "study_id": entity["id"],
            "name": f"Exploratory {methods[method_id]['name']}",
            "method_id": method_id,
            "method_version": methods[method_id]["version"],
            "cohort_id": cohort["id"],
            "snapshot_id": snapshot_id,
            "outcome_metric_id": outcome_metric_id,
            "model_formula": methods[method_id]["name"],
            "parameters": parameters,
            "planned_contrasts": [],
            "status": "EXPLORATORY",
            "primary_estimand": methods[method_id].get("name", ""),
            "deviates_from": [plan.get("spec_id")] if plan and plan.get("spec_id") else [],
            "prospective": False,
        }
        alignment = "EXPLORATORY"
    result_digest = _digest(result)[:16]
    reproducibility_key = _digest(
        {
            "snapshot_checksums": researchstore.get_snapshot(snapshot_id).get("checksums", {}),
            "spec_id": spec["id"],
            "cohort_id": cohort["id"],
            "parameters": parameters,
            "excluded": sorted(excluded_subject_ids or []),
        }
    )[:24]
    run = {
        "analysis_spec_id": spec["id"],
        "project_id": entity["project_id"],
        "study_id": entity["id"],
        "snapshot_id": snapshot_id,
        "cohort_id": cohort["id"],
        "plan_id": plan["id"] if plan else None,
        "method_id": method_id,
        "outcome_metric_id": outcome_metric_id,
        "status": "COMPLETED",
        "plan_alignment": alignment,
        "created_at": _now(),
        "duration_ms": round(duration_ms, 3),
        "software_versions": {**SOFTWARE, "r": "4.6.2 (qualification only)"},
        "seed": None,
        "parameters": parameters,
        "result": result,
        "diagnostics": diagnostics,
        "output_artifact_ids": [],
        "reproducibility_key": reproducibility_key,
        "result_digest": result_digest,
        "execution": {"analysis_spec": spec, "cohort": resolved["cohort"]},
        "figure_data": figure_data,
    }
    return researchstore.append_run(run)


def promote(run_id: str) -> dict[str, Any]:
    run = researchstore.get_run(run_id)
    if run is None:
        raise researchstore.ResearchNotFound(f"Run {run_id} not found")
    existing = researchstore.list_evidence(run["study_id"])
    prior = next((item for item in existing if item["analysis_run_id"] == run_id), None)
    if prior is not None:
        figure = next((item for item in researchstore.list_figures(run["study_id"]) if prior["id"] in item.get("evidence_ids", [])), None)
        return {"evidence_artifact": prior, "figure_artifact": figure, "already_promoted": True}
    entity = researchstore.get_entity(run["study_id"])
    if entity is None:
        raise researchstore.ResearchNotFound("Study not found")
    if run.get("status") != "COMPLETED":
        raise researchstore.ResearchValidation("Only completed runs can be promoted")
    if not run.get("diagnostics"):
        raise researchstore.ResearchValidation("A result without diagnostics cannot become evidence")
    profile = _evidence_profile(run, entity)
    evidence = researchstore.append_evidence(entity["project_id"], entity["id"], run_id, profile["evidence"])
    figure = None
    if profile.get("figure") is not None:
        figure = researchstore.append_figure(entity["project_id"], entity["id"], run_id, evidence["id"], profile["figure"])
    return {"evidence_artifact": evidence, "figure_artifact": figure, "already_promoted": False}


def _metric_label(snapshot_id: str, metric_id: str) -> dict[str, Any]:
    return _metric(snapshot_id, metric_id)


def _evidence_profile(run: dict[str, Any], entity: dict[str, Any]) -> dict[str, Any]:
    result = run["result"]
    snapshot = researchstore.get_snapshot(run["snapshot_id"]) or {}
    metric = _metric_label(run["snapshot_id"], run["outcome_metric_id"])
    protocol_id = (entity.get("protocols") or [{"id": "PROT-U"}])[0]["id"]
    plan_alignment = run.get("plan_alignment", "EXPLORATORY")
    evidence_class = "PLANNED" if plan_alignment == "PLANNED" else "EXPLORATORY"
    kind = "EFFECT" if run["method_id"] == "METH-REAL-TREND" else "RELIABILITY" if run["method_id"] == "METH-REAL-RELIABILITY" else "CHANGE" if run["method_id"] == "METH-U-CHANGE" else "DESCRIPTIVE"
    uncertainty = None
    uncertainty_label = None
    interval = None
    value = None
    effect_size = None
    contrast_id = None
    if run["method_id"] == "METH-REAL-TREND":
        contrast = result["contrasts"][result["primary_contrast_id"]]
        change = result["contrasts"][f"occasion_{result['reference_occasion']}_to_{result['contrast_occasion']}"]
        value = change["estimate"]
        uncertainty = (change["ci_high"] - change["ci_low"]) / 2
        uncertainty_label = "95% CI half-width for the model-implied change"
        interval = {"low": change["ci_low"], "high": change["ci_high"], "level": 0.95, "kind": "Wald 95% CI"}
        effect_size = result.get("effect_size")
        contrast_id = result["primary_contrast_id"]
        title = f"{metric['label']} change across testing occasions"
        interpretation = (
            f"Within-subject {metric['label'].lower()} changed by {contrast['estimate']:+.3f} {metric['unit']} per occasion "
            f"(95% CI {contrast['ci_low']:.3f} to {contrast['ci_high']:.3f}); the model-implied change from occasion "
            f"{result['reference_occasion']} to {result['contrast_occasion']} was {change['estimate']:+.3f} {metric['unit']} "
            f"(95% CI {change['ci_low']:.3f} to {change['ci_high']:.3f}). The design is observational; this is a within-subject "
            "change, not a causal intervention effect."
        )
        quality = "VALID" if result.get("converged") else "WARNING"
    elif run["method_id"] == "METH-REAL-RELIABILITY":
        computed = result.get("status") == "COMPUTED"
        value = result.get("icc_3_1")
        if computed:
            uncertainty = (result["icc_3_1_ci_high"] - result["icc_3_1_ci_low"]) / 2
            uncertainty_label = "95% CI half-width"
            interval = {"low": result["icc_3_1_ci_low"], "high": result["icc_3_1_ci_high"], "level": 0.95, "kind": "Shrout–Fleiss F-based 95% CI"}
        effect_size = result.get("mean_cv_percent")
        title = f"Trial-to-trial reliability of {metric['label'].lower()} · {result.get('activity', '')}"
        interpretation = (
            f"ICC(3,1) was {result.get('icc_3_1', float('nan')):.3f} (95% CI {result.get('icc_3_1_ci_low', float('nan')):.3f} to "
            f"{result.get('icc_3_1_ci_high', float('nan')):.3f}); within-subject CV was {result.get('mean_cv_percent', float('nan')):.1f}% and "
            f"typical error was {result.get('typical_error', float('nan')):.1f} {metric['unit']}. This is within-activity reliability, not device agreement."
        ) if computed else str(result.get("message", "Insufficient data for reliability."))
        quality = "VALID" if computed else "WARNING"
    elif run["method_id"] == "METH-REAL-SIGNAL-QA":
        body = result["body_weight"]
        value = body.get("bias_n")
        uncertainty = body.get("sd_n")
        uncertainty_label = "SD of paired differences"
        title = "Force-plate and IMU signal qualification"
        interval = {"low": body.get("loa_low_n"), "high": body.get("loa_high_n"), "level": 0.95, "kind": "95% limits of agreement"} if body.get("loa_low_n") is not None else None
        interpretation = (
            f"Signal qualification covered {len(result['activities'])} activities and {result['imu']['n_trials']} IMU trials. "
            f"Support-window mean force differed from anthropometric body weight by {body.get('bias_n', float('nan')):.0f} N "
            f"({body.get('mean_percent_error', float('nan')):.1f}%), with 95% limits of agreement "
            f"{body.get('loa_low_n', float('nan')):.0f} to {body.get('loa_high_n', float('nan')):.0f} N. "
            "This estimator is reported as a tested comparison, not a validated body-weight measurement."
        )
        quality = "VALID"
    elif run["method_id"] == "METH-U-CHANGE":
        value = result["median_change"]
        uncertainty = result.get("typical_error")
        uncertainty_label = "typical error of a change (cohort SD / √2)"
        title = f"Individual change in {metric['label'].lower()}"
        interpretation = (
            f"Median individual change was {result['median_change']:+.3f} {metric['unit']} "
            f"({result['standardized_change']:.2f} SD of the cohort change) against a typical error of "
            f"{result.get('typical_error') if result.get('typical_error') is not None else 'not estimable'} {metric['unit']}. "
            "This is descriptive context, not a causal individual response."
        )
        quality = "EXPLORATORY"
    else:
        value = result.get("change_first_to_last")
        title = f"Descriptive trajectory of {metric['label'].lower()}"
        last = (result.get("points") or [{}])[-1]
        if last.get("ci_low") is not None and last.get("ci_high") is not None:
            uncertainty = (last["ci_high"] - last["ci_low"]) / 2
            uncertainty_label = "95% CI half-width at the final point"
            interval = {"low": last["ci_low"], "high": last["ci_high"], "level": 0.95, "kind": "normal 95% CI"}
        interpretation = (
            f"Observed mean {metric['label'].lower()} changed by {value if value is not None else '—'} {metric['unit']} "
            f"from the first to the last available {result.get('axis_label', 'observation').lower()}. "
            "Descriptive only; no model or causal effect is inferred."
        )
        quality = "EXPLORATORY"
    evidence = {
        "title": title,
        "kind": kind,
        "metric_id": metric["id"],
        "value": value,
        "unit": metric["unit"],
        "estimate": value,
        "uncertainty": uncertainty,
        "uncertainty_label": uncertainty_label,
        "interval": interval,
        "effect_size": effect_size,
        "contrast_id": contrast_id,
        "population": f"{entity.get('population', 'Participants')} · {entity['id']}",
        "sample_size": int(result.get("n_subjects") or result.get("n_observations") or 0),
        "protocol_id": protocol_id,
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
            "source": f"computed from {run['snapshot_id']} {metric['table']}",
            "algorithm": result.get("method", "qualified local estimator"),
            "algorithm_version": "1.0.0",
            "snapshot_checksum": (snapshot.get("checksums") or {}).get(f"{metric['table']}.parquet"),
            "source_doi": (snapshot.get("source") or {}).get("doi"),
            "source_license": ((snapshot.get("source") or {}).get("license") or {}).get("id") if isinstance((snapshot.get("source") or {}).get("license"), dict) else (snapshot.get("source") or {}).get("license"),
            "estimator": result.get("estimator"),
            "executed_at": run.get("created_at"),
            "promoted_from_run": run["id"],
        },
        "interpretation": interpretation,
    }
    figure = None
    if run.get("figure_data"):
        figure = {
            "title": title,
            "kind": run["figure_data"].get("kind", "LINE"),
            "dataset_snapshot_id": run["snapshot_id"],
            "analysis_run_id": run["id"],
            "spec": {
                "x": result.get("axis_label", "observation"),
                "y": metric["label"],
                "unit": metric["unit"],
                "metric_id": metric["id"],
                "cohort_id": run["cohort_id"],
                "source_artifact": f"{metric['table']}.parquet",
                "summary": "computed from the immutable run",
            },
            "data": run["figure_data"],
        }
    return {"evidence": evidence, "figure": figure}


def explore(entity: dict[str, Any], cohort: dict[str, Any], metric_id: str, excluded: list[str] | None, reference: str = "RAW") -> dict[str, Any]:
    snapshot_id = entity["dataset_snapshot_id"]
    metric = _metric(snapshot_id, metric_id)
    resolved = researchstore.resolve_cohort(cohort, snapshot_id, excluded_subject_ids=excluded)
    cohort_ids = resolved["cohort"]["subject_ids"]
    frame = _frame(snapshot_id, metric, cohort_ids, cohort)
    axis, axis_label = axis_for(snapshot_id, metric, cohort)
    if axis not in frame.columns:
        raise researchstore.ResearchValidation(f"{metric['table']} has no {axis} axis")
    rows = [row for row in frame.iter_rows(named=True) if row.get(metric["column"]) is not None]
    points = sorted({int(row[axis]) for row in rows if row.get(axis) is not None})
    subjects = sorted({str(row["subject_id"]) for row in rows})
    display = {str(row["subject_id"]): row.get("display_id", str(row["subject_id"])) for row in researchstore.read_snapshot_table(snapshot_id, "subjects").iter_rows(named=True)}
    athletes = []
    for subject_id in cohort_ids:
        subject_rows = [row for row in rows if str(row["subject_id"]) == subject_id]
        raw = []
        n_valid = []
        for point in points:
            values = [float(row[metric["column"]]) for row in subject_rows if int(row[axis]) == point]
            raw.append(float(np.mean(values)) if values else None)
            n_valid.append(len(values))
        baseline = raw[0] if raw else None
        if reference == "CHANGE":
            values = [None if value is None or baseline is None else value - baseline for value in raw]
        elif reference == "PERCENT":
            values = [None if value is None or not baseline else (value - baseline) / baseline * 100 for value in raw]
        else:
            values = raw
        athletes.append(
            {
                "subject_id": subject_id,
                "display_id": display.get(subject_id, subject_id),
                "intervention_arm": "INTERVENTION",
                "raw": raw,
                "values": values,
                "n_valid": n_valid,
                "n_excluded": [0] * len(points),
                "n_missing": [0 if value is not None else 1 for value in raw],
                "baseline": baseline,
            }
        )
    summary = []
    for point in points:
        values = []
        for athlete in athletes:
            index = points.index(point)
            if athlete["values"][index] is not None:
                values.append(athlete["values"][index])
        mean = float(np.mean(values)) if values else None
        sd = float(np.std(values, ddof=1)) if len(values) > 1 else None
        half = float(1.96 * sd / math.sqrt(len(values))) if sd and values else None
        summary.append(
            {
                "arm": "INTERVENTION",
                "week": point,
                axis: point,
                "n": len(values),
                "n_athletes": len(values),
                "mean": mean,
                "sd": sd,
                "ci_low": mean - half if mean is not None and half is not None else None,
                "ci_high": mean + half if mean is not None and half is not None else None,
                "missing_athletes": len(athletes) - len(values),
                "excluded_trials": 0,
                "missing_trials": len(athletes) - len(values),
            }
        )
    return {
        "metric": {"column": metric["column"], "label": metric["label"], "unit": metric["unit"], "id": metric["definition_id"], "metric_id": metric_id},
        "unit": metric["unit"] if reference != "PERCENT" else "%",
        "reference": reference,
        "reference_label": {"RAW": "observed values", "CHANGE": f"change from first {axis_label.lower()}", "PERCENT": f"percent change from first {axis_label.lower()}"}[reference],
        "cohort": {"id": cohort["id"], "status": cohort["status"], "n": resolved["n"], "excluded_subject_ids": sorted(excluded or [])},
        "summary": summary,
        "athletes": athletes,
        "context": [],
        "annotations": {
            "intervention_block": {"start_week": points[0] if points else 1, "end_week": points[-1] if points else 1, "source": axis_label},
            "load_peaks": [],
            "load_peak_rule": "No training-load context is present in this snapshot; no load peaks are inferred.",
        },
        "method": {
            "unit_of_analysis": f"{axis_label.lower()} within participant",
            "interval": "mean ± 1.96 × between-participant SEM",
            "engine": "polars + numpy",
            "note": f"{axis_label} values are taken from the admitted snapshot. Missing values are shown as missing and never imputed.",
        },
        "provenance": {
            "snapshot_id": snapshot_id,
            "source_doi": (researchstore.get_snapshot(snapshot_id) or {}).get("source", {}).get("doi"),
            "checksum": (researchstore.get_snapshot(snapshot_id) or {}).get("checksums", {}).get(f"{metric['table']}.parquet"),
        },
    }


def athlete_longitudinal(entity: dict[str, Any], cohort: dict[str, Any], subject_id: str, metric_id: str) -> dict[str, Any]:
    snapshot_id = entity["dataset_snapshot_id"]
    metric = _metric(snapshot_id, metric_id)
    subjects = researchstore.read_snapshot_table(snapshot_id, "subjects").to_dicts()
    subject = next((row for row in subjects if str(row["subject_id"]) == subject_id), None)
    if subject is None:
        raise researchstore.ResearchNotFound("Subject not found")
    frame = researchstore.read_snapshot_table(snapshot_id, metric["table"])
    frame = frame.filter(pl.col("subject_id") == subject_id)
    axis, axis_label = axis_for(snapshot_id, metric, cohort)
    rows = [row for row in frame.iter_rows(named=True) if row.get(metric["column"]) is not None]
    points = sorted({int(row[axis]) for row in rows if row.get(axis) is not None})
    observations = []
    for point in points:
        point_rows = [row for row in rows if int(row[axis]) == point]
        values = [float(row[metric["column"]]) for row in point_rows]
        observations.append(
            {
                "week": point,
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
                "phase": axis_label,
                "load": None,
                "wellness": None,
                "trials": [
                    {
                        "trial_id": str(row.get("trial_id") or f"{subject_id}-{axis}-{point}-{index}"),
                        "trial_number": index + 1,
                        "quality_state": str(row.get("quality_state") or "VALID"),
                        "exclusion_reason": row.get("exclusion_reason") or "",
                        "value": float(row[metric["column"]]),
                        "trace_available": False,
                    }
                    for index, row in enumerate(point_rows)
                ],
            }
        )
    raw = [item["value"] for item in observations]
    baseline = raw[0] if raw else None
    post = raw[-1] if raw else None
    change = post - baseline if baseline is not None and post is not None else None
    return {
        "subject": subject,
        "metric": {"column": metric["column"], "label": metric["label"], "unit": metric["unit"], "id": metric["definition_id"], "metric_id": metric_id},
        "observations": observations,
        "typical_error": None,
        "individual": {
            "method": f"First versus last available {axis_label.lower()}",
            "baseline_weeks": [points[0]] if points else [],
            "post_weeks": [points[-1]] if points else [],
            "baseline_mean": baseline,
            "post_mean": post,
            "change": change,
            "percent_change": (change / baseline * 100) if change is not None and baseline else None,
            "standardized_change": None,
            "exceeds_typical_error": None,
            "typical_error": None,
            "cohort_change_sd": None,
            "n_subjects": 1,
            "limitations": "Descriptive individual change; measurement error is not estimable from this snapshot unless repeated same-session trials are present.",
        },
        "provenance": {"snapshot_id": snapshot_id, "source": f"{metric['table']}.parquet", "quality_rule": "Missing values remain visible and are never imputed."},
    }
