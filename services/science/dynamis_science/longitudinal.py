"""RES-647 cohort and individual longitudinal research inside one persistent workspace.

Individual investigations are versioned rows of the existing ``investigations`` table with an INDIVIDUAL scope.
They reference observations of the workspace's admitted revisions; no source data is copied per participant.
Experimental protocols and hypothetical scenarios are versioned fields of the investigation. Scenarios never
carry a number unless a qualified forecasting model exists, and none does yet.
"""

from __future__ import annotations

import math
import secrets
from typing import Any

import numpy as np
import polars as pl

from . import researchstore

PERIOD_KINDS = ("BASELINE", "INTERVENTION", "EXPOSURE", "COMPARISON", "WASHOUT", "FOLLOW_UP")
PROTOCOL_DESIGNS = {
    "OBSERVATIONAL_TRACKING": "Retrospective observational tracking — not an experiment",
    "N_OF_1_EXPERIMENT": "Documented N-of-1 experimental design",
}
SCENARIO_KINDS = {
    "REFERENCE": "Reference scenario",
    "ALTERNATIVE": "Alternative assumption scenario",
    "WORST_CASE": "Worst-case stress-test scenario",
}
HORIZON_UNITS = ("occasions", "weeks", "days")
NOT_QUALIFIED = "NOT QUALIFIED — Numerical forecast unavailable."
FORECAST_REASON = ("No individualized forecasting model (hierarchical, Bayesian, state-space or mechanistic) has passed "
                   "RES-590/RES-619 qualification, so no numerical scenario result is computed.")


def _workspace(workspace_id: str) -> dict[str, Any]:
    entity = researchstore.get_entity(workspace_id)
    if not entity or not entity.get("workspace"):
        raise researchstore.ResearchValidation("Open a persistent research workspace first")
    return entity


def _context(workspace_id: str, metric_id: str | None = None, revision_id: str | None = None) -> tuple[dict[str, Any], str, dict[str, Any]]:
    entity = _workspace(workspace_id)
    if revision_id:
        revision = researchstore.get_data_revision(revision_id)
        if not revision or revision["workspace_id"] != workspace_id:
            raise researchstore.ResearchValidation("This data revision does not belong to the workspace")
        snapshot_id = revision["snapshot_id"]
    else:
        snapshot_id = entity.get("dataset_snapshot_id")
    if not snapshot_id:
        raise researchstore.ResearchValidation("Add data to the workspace before selecting participants")
    metrics = [item for item in researchstore.dataset_metrics(snapshot_id) if item["table"] in {"cmj_occasions", "cmj_trials"}]
    primary = metric_id or (entity.get("outcomes", {}).get("primary") or [{}])[0].get("id")
    metric = next((item for item in metrics if item["id"] == primary), metrics[0] if metrics else None)
    if metric is None:
        raise researchstore.ResearchValidation("This data revision has no longitudinal outcome (CMJ occasions or weekly trials)")
    return entity, snapshot_id, metric


def _axis(metric: dict[str, Any]) -> str:
    return "occasion" if metric["table"] == "cmj_occasions" else "week"


def _observations(snapshot_id: str, metric: dict[str, Any]) -> tuple[pl.DataFrame, str, list[int]]:
    frame = researchstore.read_snapshot_table(snapshot_id, metric["table"])
    axis = _axis(metric)
    if axis not in frame.columns:
        raise researchstore.ResearchValidation(f"Missing {axis} metadata; map the measured time axis during import.")
    points = sorted(int(value) for value in frame[axis].drop_nulls().unique().to_list())
    return frame, axis, points


# --------------------------------------------------------------------------- #
# Individuals explorer
# --------------------------------------------------------------------------- #


def participant_catalogue(workspace_id: str, query: str = "") -> dict[str, Any]:
    entity, snapshot_id, metric = _context(workspace_id)
    frame, axis, points = _observations(snapshot_id, metric)
    subjects = researchstore.read_snapshot_table(snapshot_id, "subjects").to_dicts()
    investigations = individual_investigations(workspace_id)
    needle = query.strip().lower()
    rows = []
    for subject in subjects:
        subject_id = str(subject["subject_id"])
        display = str(subject.get("display_id") or subject_id)
        if needle and needle not in subject_id.lower() and needle not in display.lower():
            continue
        own = frame.filter(pl.col("subject_id") == subject_id)
        valid = own.filter(pl.col(metric["column"]).is_not_null() & pl.col(axis).is_not_null())
        sessions = sorted(int(value) for value in valid[axis].unique().to_list())
        flagged = own.filter(pl.col("quality_state") != "VALID").height if "quality_state" in own.columns else 0
        rows.append({
            "subject_id": subject_id, "display_id": display,
            "sessions": len(sessions), "observations": valid.height,
            "latest": sessions[-1] if sessions else None,
            "completeness": len(sessions) / len(points) if points else 0.0,
            "missing_occasions": [point for point in points if point not in sessions],
            "empty_values": own.height - valid.height, "quality_flags": flagged,
            "investigations": [{"id": item["id"], "title": item["title"]} for item in investigations
                               if item["scope"]["subject_id"] == subject_id],
        })
    return {"workspace_id": workspace_id, "data_revision_id": entity.get("active_data_revision_id"),
            "snapshot_id": snapshot_id, "metric": metric, "axis": axis, "occasions": points, "participants": rows}


# --------------------------------------------------------------------------- #
# Individual investigations
# --------------------------------------------------------------------------- #


def individual_investigations(workspace_id: str, subject_id: str | None = None) -> list[dict[str, Any]]:
    return [item for item in researchstore.list_investigations(workspace_id)
            if (item.get("scope") or {}).get("kind") == "INDIVIDUAL"
            and (subject_id is None or item["scope"]["subject_id"] == subject_id)]


def get_individual_investigation(investigation_id: str) -> dict[str, Any]:
    investigation = researchstore.get_investigation(investigation_id)
    if not investigation or (investigation.get("scope") or {}).get("kind") != "INDIVIDUAL":
        raise researchstore.ResearchValidation("Select an individual investigation")
    return investigation


def create_individual_investigation(workspace_id: str, subject_id: str, title: str, question: str = "") -> dict[str, Any]:
    entity, snapshot_id, _ = _context(workspace_id)
    if entity["state"] == "ARCHIVED":
        raise researchstore.ResearchConflict("Restore this workspace before creating investigations")
    if not title.strip():
        raise researchstore.ResearchValidation("An investigation title is required")
    known = set(researchstore.read_snapshot_table(snapshot_id, "subjects")["subject_id"].cast(pl.Utf8).to_list())
    if subject_id not in known:
        raise researchstore.ResearchValidation("This participant is not present in the active data revision")
    return researchstore.create_investigation(workspace_id, title, blocks=[], fields={
        "scope": {"kind": "INDIVIDUAL", "subject_id": subject_id},
        "question": question.strip(),
        "created_on_data_revision_id": entity.get("active_data_revision_id"),
        "protocol": {"design": "OBSERVATIONAL_TRACKING", "design_label": PROTOCOL_DESIGNS["OBSERVATIONAL_TRACKING"],
                     "periods": [], "testing_occasions": [], "changes": [], "adherence": []},
        "scenarios": [],
    })


def investigation_runs(investigation_id: str) -> list[dict[str, Any]]:
    investigation = get_individual_investigation(investigation_id)
    return [run for run in researchstore.list_runs(investigation["study_id"]) if run.get("investigation_id") == investigation_id]


def individual_eligibility(investigation_id: str) -> list[dict[str, Any]]:
    """Method availability for this participant on the active revision, with the reason for every unavailable method."""
    investigation = get_individual_investigation(investigation_id)
    entity, snapshot_id, metric = _context(investigation["study_id"])
    scope = {"kind": "INDIVIDUAL", "subject_id": investigation["scope"]["subject_id"], "investigation_id": investigation_id}
    preview = {**researchstore._default_cohort_definition(metric, snapshot_id), "include_subject_ids": [scope["subject_id"]],
               "scope": scope, "id": "PREVIEW", "status": "DRAFT"}
    resolved = researchstore.resolve_cohort(preview, snapshot_id)
    return researchstore.method_eligibility({**entity, "outcomes": {"primary": [metric]}}, preview, resolved, None)


def select_research_scope(workspace_id: str, kind: str, investigation_id: str | None = None) -> dict[str, Any]:
    """Persist the visible research context so reopening restores the same scope."""
    entity = _workspace(workspace_id)
    if kind == "COHORT":
        context = {"scope": "COHORT", "subject_id": None, "investigation_id": None}
    elif kind == "INDIVIDUAL":
        investigation = get_individual_investigation(investigation_id or "")
        if investigation["study_id"] != workspace_id:
            raise researchstore.ResearchValidation("The investigation belongs to another workspace")
        context = {"scope": "INDIVIDUAL", "subject_id": investigation["scope"]["subject_id"], "investigation_id": investigation["id"]}
    else:
        raise researchstore.ResearchValidation(f"Unknown research scope {kind}")
    if entity.get("research_context") == context:
        return entity
    return researchstore.update_entity(workspace_id, {"research_context": context}, change_type="SCOPE_SELECTED")


# --------------------------------------------------------------------------- #
# Individual trajectory method (METH-U-INDIVIDUAL)
# --------------------------------------------------------------------------- #


def individual_points(snapshot_id: str, metric: dict[str, Any], subject_id: str) -> tuple[str, list[dict[str, Any]]]:
    frame, axis, points = _observations(snapshot_id, metric)
    own = frame.filter(pl.col("subject_id") == subject_id)
    result = []
    for point in points:
        rows = own.filter(pl.col(axis) == point).to_dicts()
        values = [float(row[metric["column"]]) for row in rows if row.get(metric["column"]) is not None
                  and math.isfinite(float(row[metric["column"]])) and row.get("quality_state", "VALID") == "VALID"]
        result.append({
            axis: point, "week": point, "n_trials": len(values), "values": values,
            "mean": float(np.mean(values)) if values else None,
            "within_session_sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
            "empty_values": len(rows) - len(values),
            "quality_flags": sorted({str(row["quality_state"]) for row in rows if row.get("quality_state") not in (None, "VALID")}),
            "status": "OBSERVED" if values else "MISSING",
        })
    return axis, result


def individual_trajectory(snapshot_id: str, metric: dict[str, Any], subject_id: str) -> dict[str, Any]:
    axis, points = individual_points(snapshot_id, metric, subject_id)
    observed = [point for point in points if point["n_trials"]]
    if len(observed) < 2:
        raise researchstore.ResearchValidation("At least two measured occasions are required for a within-person trajectory")
    repeated = [point for point in observed if point["n_trials"] > 1]
    df = sum(point["n_trials"] - 1 for point in repeated)
    # Pooled within-session SD: trial-to-trial noise only, assuming exchangeable same-session trials.
    trial_sd = math.sqrt(sum((point["n_trials"] - 1) * point["within_session_sd"] ** 2 for point in repeated) / df) if df else None
    first, last = observed[0], observed[-1]
    change = last["mean"] - first["mean"]
    change_se = trial_sd * math.sqrt(1 / first["n_trials"] + 1 / last["n_trials"]) if trial_sd is not None else None
    return {
        "method": "Individual observed trajectory with repeated-trial error context",
        "status": "COMPUTED", "subject_id": subject_id, "outcome": metric["id"], "unit": metric["unit"],
        "axis": axis, "axis_label": "Testing occasion" if axis == "occasion" else "Week",
        "points": points, "n_subjects": 1, "n_observations": sum(point["n_trials"] for point in observed),
        "observed_occasions": [point[axis] for point in observed],
        "missing_occasions": [point[axis] for point in points if not point["n_trials"]],
        "first": first[axis], "last": last[axis],
        "change_first_to_last": change,
        "percent_change_first_to_last": change / first["mean"] * 100 if first["mean"] else None,
        "within_session_sd": trial_sd, "within_session_df": df,
        "change_trial_noise_se": change_se,
        "error_note": ("Trial-noise SE of the change = pooled within-session SD × √(1/n_first + 1/n_last); it excludes "
                       "day-to-day biological variation. Assumes independent trials and common within-session variance across sessions; "
                       "heteroscedastic sessions can invalidate this noise summary. It is not total longitudinal uncertainty." if change_se is not None else
                       "Not estimable: no occasion has repeated same-session trials."),
        "limitations": [
            "Observational within-person description; not a personalized causal estimate or forecast.",
            "Missing occasions are listed, not imputed.",
            "Trial error excludes day-to-day biological variation and is not an individual response threshold.",
            "Pooled variance assumes common session variance and independent trial errors; unequal variance is not modeled. Single-trial endpoints borrow this pooled noise estimate.",
        ],
    }


# --------------------------------------------------------------------------- #
# Experimental protocol
# --------------------------------------------------------------------------- #


def _text(value: Any) -> str:
    return str(value or "").strip()


def save_protocol(investigation_id: str, protocol: dict[str, Any], base_version: int | None) -> dict[str, Any]:
    get_individual_investigation(investigation_id)  # validates the scope
    design = protocol.get("design", "OBSERVATIONAL_TRACKING")
    if design not in PROTOCOL_DESIGNS:
        raise researchstore.ResearchValidation(f"Unknown protocol design {design}")
    periods = []
    for index, period in enumerate(protocol.get("periods", []), start=1):
        kind = period.get("kind")
        if kind not in PERIOD_KINDS:
            raise researchstore.ResearchValidation(f"Period {index}: unknown kind {kind}")
        try:
            start, end = int(period["start"]), int(period["end"])
        except (KeyError, TypeError, ValueError) as error:
            raise researchstore.ResearchValidation(f"Period {index}: start and end must be measured occasions/weeks") from error
        if start > end:
            raise researchstore.ResearchValidation(f"Period {index}: start is after end")
        periods.append({"id": f"P{index}", "kind": kind, "label": _text(period.get("label")) or kind.title(),
                        "start": start, "end": end, "notes": _text(period.get("notes"))})
    ordered = sorted(periods, key=lambda item: item["start"])
    for before, after in zip(ordered, ordered[1:]):
        if after["start"] <= before["end"]:
            raise researchstore.ResearchValidation(f"Periods {before['label']} and {after['label']} overlap")
    labels = {item["label"] for item in periods}
    adherence = []
    for item in protocol.get("adherence", []):
        if item.get("period") not in labels:
            raise researchstore.ResearchValidation("Adherence must reference a documented period")
        percent = item.get("adherence_percent")
        if percent is not None and not 0 <= float(percent) <= 100:
            raise researchstore.ResearchValidation("Adherence must be between 0 and 100%")
        adherence.append({"period": item["period"], "adherence_percent": None if percent is None else float(percent),
                          "deviations": _text(item.get("deviations"))})
    changes = [{"at": int(item["at"]), "description": _text(item.get("description"))} for item in protocol.get("changes", [])]
    if any(not item["description"] for item in changes):
        raise researchstore.ResearchValidation("Describe every protocol change")
    record = {
        "design": design, "design_label": PROTOCOL_DESIGNS[design], "periods": periods,
        "testing_occasions": sorted({int(value) for value in protocol.get("testing_occasions", [])}),
        "changes": changes, "adherence": adherence,
        "assignment": _text(protocol.get("assignment")), "prespecified": bool(protocol.get("prespecified")),
        "blinding": _text(protocol.get("blinding")),
    }
    if design == "N_OF_1_EXPERIMENT":
        issues = []
        active = sum(item["kind"] in {"INTERVENTION", "EXPOSURE"} for item in periods)
        control = sum(item["kind"] in {"BASELINE", "COMPARISON"} for item in periods)
        if active < 2 or control < 2:
            issues.append("an N-of-1 experiment needs at least two intervention and two comparison/baseline periods (replicated crossover)")
        if not record["assignment"]:
            issues.append("document how period order was assigned (e.g. randomized sequence)")
        if not record["prespecified"]:
            issues.append("periods must be prespecified before the outcome measurements")
        if issues:
            raise researchstore.ResearchValidation("Not an experimental design: " + "; ".join(issues) + ". A repeated-measurement history alone is observational tracking.")
    return researchstore.update_investigation_fields(investigation_id, {"protocol": record}, base_version, "investigation.protocol_saved")


def protocol_observations(investigation_id: str) -> list[dict[str, Any]]:
    """Observed measurements of the active revision that fall within each documented period."""
    investigation = get_individual_investigation(investigation_id)
    _, snapshot_id, metric = _context(investigation["study_id"])
    axis, points = individual_points(snapshot_id, metric, investigation["scope"]["subject_id"])
    return [{**period, "occasions": [point[axis] for point in points if period["start"] <= point[axis] <= period["end"] and point["n_trials"]],
             "trials": sum(point["n_trials"] for point in points if period["start"] <= point[axis] <= period["end"])}
            for period in investigation["protocol"]["periods"]]


# --------------------------------------------------------------------------- #
# Scenario laboratory (HYPOTHETICAL)
# --------------------------------------------------------------------------- #


def save_scenario(investigation_id: str, scenario: dict[str, Any], base_version: int | None) -> dict[str, Any]:
    investigation = get_individual_investigation(investigation_id)
    workspace_id = investigation["study_id"]
    revision_id = scenario.get("data_revision_id") or _workspace(workspace_id).get("active_data_revision_id")
    _, snapshot_id, metric = _context(workspace_id, scenario.get("outcome_metric_id"), revision_id)
    if scenario.get("outcome_metric_id") and scenario["outcome_metric_id"] != metric["id"]:
        raise researchstore.ResearchValidation("The outcome is not measured in the referenced data revision")
    kind = scenario.get("kind")
    if kind not in SCENARIO_KINDS:
        raise researchstore.ResearchValidation(f"Unknown scenario type {kind}")
    title = _text(scenario.get("title"))
    assumptions = [_text(item) for item in scenario.get("assumptions", []) if _text(item)]
    if not title or not assumptions:
        raise researchstore.ResearchValidation("A scenario needs a title and at least one explicit assumption")
    unit = _text(scenario.get("unit")) or metric["unit"]
    if unit != metric["unit"]:
        raise researchstore.ResearchValidation(f"The outcome is recorded in {metric['unit']}, not {unit}")
    bounds = []
    for item in scenario.get("parameter_bounds", []):
        name, lower, upper = _text(item.get("name")), float(item["lower"]), float(item["upper"])
        if not name or lower > upper:
            raise researchstore.ResearchValidation("Each parameter bound needs a name and lower ≤ upper")
        bounds.append({"name": name, "lower": lower, "upper": upper, "unit": _text(item.get("unit"))})
    if not bounds:
        raise researchstore.ResearchValidation("Define the parameter bounds of the scenario")
    horizon = scenario.get("horizon") or {}
    if float(horizon.get("value") or 0) <= 0 or horizon.get("unit") not in HORIZON_UNITS:
        raise researchstore.ResearchValidation("Define a positive time horizon in occasions, weeks or days")
    adverse = _text(scenario.get("adverse_outcome"))
    if kind == "WORST_CASE" and not adverse:
        raise researchstore.ResearchValidation("A worst-case stress test must define the adverse outcome")
    model_run = None
    if scenario.get("model_run_id"):
        run = researchstore.get_run(scenario["model_run_id"])
        if not run or run.get("study_id") != workspace_id:
            raise researchstore.ResearchValidation("The referenced model run belongs to another workspace")
        model_run = {"id": run["id"], "method_id": run["method_id"], "method_version": run["method_version"],
                     "data_revision_id": run.get("data_revision_id")}
    previous = [item for item in investigation["scenarios"] if item["id"] == scenario.get("id")]
    if scenario.get("id") and not previous:
        raise researchstore.ResearchValidation("Unknown scenario")
    record = {
        "id": scenario.get("id") or f"SCN-U-{secrets.token_hex(4).upper()}",
        "version": max((item["version"] for item in previous), default=0) + 1, "designation": "HYPOTHETICAL",
        "kind": kind, "kind_label": SCENARIO_KINDS[kind], "title": title,
        "data_revision_id": revision_id, "snapshot_id": snapshot_id, "model_run": model_run,
        "subject_id": investigation["scope"]["subject_id"],
        "outcome_metric_id": metric["id"], "outcome_label": metric["label"], "unit": unit,
        "parameter_bounds": bounds, "horizon": {"value": float(horizon["value"]), "unit": horizon["unit"]},
        "adverse_outcome": adverse, "assumptions": assumptions,
        # shortcut: no forecasting model is qualified (RES-590/RES-619); add a numerical path only once one is.
        "qualification": {"status": "NOT_QUALIFIED", "message": NOT_QUALIFIED, "reason": FORECAST_REASON},
        "numerical_result": None,
        "created_at": researchstore._now(),
    }
    return researchstore.update_investigation_fields(investigation_id, {"scenarios": [*investigation["scenarios"], record]},
                                                     base_version, "investigation.scenario_saved")


def current_scenarios(investigation: dict[str, Any]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in investigation.get("scenarios", []):
        latest[item["id"]] = item
    return list(latest.values())


# --------------------------------------------------------------------------- #
# Compare with cohort
# --------------------------------------------------------------------------- #


def compare_with_cohort(workspace_id: str, subject_id: str, metric_id: str | None = None) -> dict[str, Any]:
    from .researchanalysis import _descriptive

    entity, snapshot_id, metric = _context(workspace_id, metric_id)
    axis, own = individual_points(snapshot_id, metric, subject_id)
    others = [str(item) for item in researchstore.read_snapshot_table(snapshot_id, "subjects")["subject_id"].to_list() if str(item) != subject_id]
    cohort = _descriptive(snapshot_id, metric, others, None) if others else {"points": []}
    by_point = {row[axis]: row for row in cohort["points"]}
    rows = []
    for point in own:
        reference = by_point.get(point[axis], {})
        rows.append({
            axis: point[axis], "individual_mean": point["mean"], "individual_trials": point["n_trials"],
            "individual_within_session_sd": point["within_session_sd"], "individual_status": point["status"],
            "cohort_n": reference.get("n", 0), "cohort_mean": reference.get("mean"), "cohort_sd": reference.get("sd"),
            "cohort_ci_low": reference.get("ci_low"), "cohort_ci_high": reference.get("ci_high"),
            "comparable": bool(point["n_trials"] and reference.get("n")),
        })
    revision = entity.get("active_data_revision_id")
    modeled = [{"run_id": run["id"], "method_id": run["method_id"], "status": run["method_status"]["state"],
                "label": "Cohort-level model estimate; not an individual forecast"}
               for run in researchstore.list_runs(workspace_id)
               if run.get("data_revision_id") == revision and run["method_id"] == "METH-REAL-TREND"
               and (run.get("scope") or {}).get("kind", "COHORT") == "COHORT" and run["method_status"]["state"] == "CURRENT"]
    scenarios = [{"id": item["id"], "title": item["title"], "kind_label": item["kind_label"], "designation": item["designation"],
                  "qualification": item["qualification"]["message"]}
                 for investigation in individual_investigations(workspace_id, subject_id) for item in current_scenarios(investigation)]
    return {
        "workspace_id": workspace_id, "data_revision_id": revision, "snapshot_id": snapshot_id, "subject_id": subject_id,
        "metric": {"id": metric["id"], "label": metric["label"], "unit": metric["unit"]}, "axis": axis,
        "compatibility": "Same admitted revision, metric, canonical unit and measurement axis.",
        "cohort_definition": f"Other participants in the revision (n = {len(others)}), descriptive Student-t 95% intervals",
        "rows": rows, "modeled_estimates": modeled, "hypothetical_scenarios": scenarios,
        "limitations": [
            "Cohort summaries are population descriptions, not forecasts for this participant.",
            "Individual values are observed session means; within-session SD reflects trial noise only.",
            "Hypothetical scenarios are definitions only and are not evidence.",
        ],
    }
