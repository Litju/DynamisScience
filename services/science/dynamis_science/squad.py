"""Researcher-configured squad flags and assumption-driven simulations (RES-647).

Everything here is defined by the person using the software: which metrics matter, what counts as a flag,
what the categories are called and which assumptions a simulation applies. The engine only evaluates those
definitions against observed data in the active data revision and reports exactly which rule fired. Simulations
project the researcher's stated assumptions from each athlete's latest observed values; they are labeled as such
and are never stored as observations.
"""

from __future__ import annotations

import secrets
from typing import Any

import numpy as np
import polars as pl

from . import researchstore

MEASURES = {
    "latest": "Latest value",
    "change_from_baseline_pct": "% change from own baseline",
    "change_from_previous_pct": "% change from previous test",
    "vs_squad_sd": "Latest vs squad (SD units)",
    "rolling_mean": "Rolling mean of last N records",
    "acute_chronic_ratio": "Acute:chronic ratio (last A vs last C records)",
    "missed_tests": "Missed tests",
}
OPERATORS = ("<", "<=", ">", ">=", "between", "outside")
TONES = ("negative", "positive", "neutral")


def _workspace(workspace_id: str) -> dict[str, Any]:
    entity = researchstore.get_entity(workspace_id)
    if not entity or not entity.get("workspace"):
        raise researchstore.ResearchValidation("Open a persistent research workspace first")
    return entity


def _metrics(snapshot_id: str) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in researchstore.dataset_metrics(snapshot_id)}


def _axis(frame: pl.DataFrame) -> str | None:
    return next((axis for axis in ("occasion", "week", "day", "date") if axis in frame.columns), None)


def athlete_series(snapshot_id: str, metric: dict[str, Any]) -> tuple[dict[str, list[tuple[Any, float]]], list[Any]]:
    """Per-athlete (axis point, session mean) in axis order, plus every axis point measured in the revision."""
    frame = researchstore.read_snapshot_table(snapshot_id, metric["table"])
    axis = _axis(frame)
    if axis is None:
        raise researchstore.ResearchValidation(f"{metric['label']} has no measured time axis")
    valid = frame.filter(pl.col(metric["column"]).is_not_null() & pl.col(axis).is_not_null())
    means = valid.group_by(["subject_id", axis]).agg(pl.col(metric["column"]).mean().alias("value")).sort(axis)
    series: dict[str, list[tuple[Any, float]]] = {}
    for row in means.iter_rows(named=True):
        series.setdefault(str(row["subject_id"]), []).append((row[axis], float(row["value"])))
    return series, sorted(frame[axis].drop_nulls().unique().to_list())


def _measure(kind: str, values: list[float], squad_latest: list[float], points_total: int, condition: dict[str, Any]) -> float | None:
    if kind == "missed_tests":
        return float(points_total - len(values))
    if not values:
        return None
    latest = values[-1]
    if kind == "latest":
        return latest
    if kind == "change_from_baseline_pct":
        return (latest - values[0]) / values[0] * 100 if len(values) > 1 and values[0] else None
    if kind == "change_from_previous_pct":
        return (latest - values[-2]) / values[-2] * 100 if len(values) > 1 and values[-2] else None
    if kind == "vs_squad_sd":
        sd = float(np.std(squad_latest, ddof=1)) if len(squad_latest) > 2 else 0.0
        return (latest - float(np.mean(squad_latest))) / sd if sd else None
    if kind == "rolling_mean":
        window = int(condition.get("window") or 3)
        return float(np.mean(values[-window:])) if len(values) >= window else None
    if kind == "acute_chronic_ratio":
        acute, chronic = int(condition.get("acute") or 1), int(condition.get("chronic") or 4)
        if len(values) < chronic or acute >= chronic:
            return None
        base = float(np.mean(values[-chronic:]))
        return float(np.mean(values[-acute:])) / base if base else None
    raise researchstore.ResearchValidation(f"Unknown measure {kind}")


def _compare(value: float, condition: dict[str, Any]) -> bool:
    op, threshold = condition["operator"], float(condition["value"])
    if op in ("between", "outside"):
        low, high = sorted((threshold, float(condition["value2"])))
        inside = low <= value <= high
        return inside if op == "between" else not inside
    return {"<": value < threshold, "<=": value <= threshold, ">": value > threshold, ">=": value >= threshold}[op]


def validate_rule(rule: dict[str, Any], metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    name, category = str(rule.get("name") or "").strip(), str(rule.get("category") or "").strip()
    if not name or not category:
        raise researchstore.ResearchValidation("Each rule needs a name and the category it assigns (for example 'In danger')")
    if rule.get("tone", "neutral") not in TONES:
        raise researchstore.ResearchValidation("Tone must be negative, positive or neutral")
    conditions = rule.get("conditions") or []
    if not conditions:
        raise researchstore.ResearchValidation(f"{name}: add at least one condition")
    for condition in conditions:
        if condition.get("metric_id") not in metrics:
            raise researchstore.ResearchValidation(f"{name}: {condition.get('metric_id')} is not measured in this data revision")
        if condition.get("measure") not in MEASURES or condition.get("operator") not in OPERATORS:
            raise researchstore.ResearchValidation(f"{name}: choose a supported measure and operator")
        try:
            float(condition["value"])
            if condition["operator"] in ("between", "outside"):
                float(condition["value2"])
        except (KeyError, TypeError, ValueError) as error:
            raise researchstore.ResearchValidation(f"{name}: thresholds must be numbers") from error
    return {"id": rule.get("id") or f"RULE-{secrets.token_hex(3).upper()}", "name": name, "category": category,
            "tone": rule.get("tone", "neutral"), "match": "any" if rule.get("match") == "any" else "all",
            "enabled": rule.get("enabled", True), "conditions": conditions}


def save_rules(workspace_id: str, rules: list[dict[str, Any]], base_version: int | None = None) -> dict[str, Any]:
    entity = _workspace(workspace_id)
    if not entity.get("dataset_snapshot_id"):
        raise researchstore.ResearchValidation("Add data before defining flag rules")
    metrics = _metrics(entity["dataset_snapshot_id"])
    validated = [validate_rule(rule, metrics) for rule in rules]
    return researchstore.update_entity(workspace_id, {"flag_rules": validated}, base_version, change_type="FLAG_RULES_SAVED")


def evaluate(snapshot_id: str, rules: list[dict[str, Any]], overrides: dict[str, dict[str, list[float]]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Rule hits per athlete. ``overrides`` replaces a metric's series (used to test simulated values)."""
    metrics = _metrics(snapshot_id)
    cache: dict[str, tuple[dict[str, list[float]], int]] = {}

    def series(metric_id: str) -> tuple[dict[str, list[float]], int]:
        if metric_id not in cache:
            observed, points = athlete_series(snapshot_id, metrics[metric_id])
            values = {subject: [value for _, value in rows] for subject, rows in observed.items()}
            values.update((overrides or {}).get(metric_id, {}))
            cache[metric_id] = (values, len(points))
        return cache[metric_id]

    subjects = [str(item) for item in researchstore.read_snapshot_table(snapshot_id, "subjects")["subject_id"].to_list()]
    hits: dict[str, list[dict[str, Any]]] = {subject: [] for subject in subjects}
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        for subject in subjects:
            evidence, matched = [], []
            for condition in rule["conditions"]:
                values, total = series(condition["metric_id"])
                squad = [rows[-1] for rows in values.values() if rows]
                value = _measure(condition["measure"], values.get(subject, []), squad, total, condition)
                ok = value is not None and _compare(value, condition)
                matched.append(ok)
                metric = metrics[condition["metric_id"]]
                label = MEASURES[condition["measure"]]
                if condition["measure"] == "rolling_mean":
                    label = f"Rolling mean of last {condition.get('window') or 3}"
                elif condition["measure"] == "acute_chronic_ratio":
                    label = f"Acute:chronic ratio ({condition.get('acute') or 1} vs {condition.get('chronic') or 4})"
                evidence.append({"metric": metric["label"], "unit": metric["unit"], "measure": label,
                                 "value": None if value is None else round(value, 3), "operator": condition["operator"],
                                 "threshold": condition["value"], "threshold2": condition.get("value2"), "met": ok})
            if (all(matched) if rule["match"] == "all" else any(matched)):
                hits[subject].append({"rule_id": rule["id"], "rule": rule["name"], "category": rule["category"],
                                      "tone": rule["tone"], "evidence": evidence})
    return hits


def squad_board(workspace_id: str, group_by: str = "category", metric_id: str | None = None) -> dict[str, Any]:
    """Every athlete with key metrics and the rules that fired, grouped by category, a subject attribute or trend."""
    entity = _workspace(workspace_id)
    snapshot_id = entity.get("dataset_snapshot_id")
    if not snapshot_id:
        raise researchstore.ResearchValidation("Add data to the workspace to see the squad")
    metrics = _metrics(snapshot_id)
    primary = metric_id or (entity.get("outcomes", {}).get("primary") or [{}])[0].get("id")
    metric = metrics.get(primary) or next(iter(metrics.values()), None)
    if metric is None:
        raise researchstore.ResearchValidation("This data revision has no measured metric")
    observed, points = athlete_series(snapshot_id, metric)
    frame_columns = researchstore.read_snapshot_table(snapshot_id, metric["table"]).columns
    time_word = "days" if _axis(pl.DataFrame(schema=dict.fromkeys(frame_columns, pl.Utf8))) in ("day", "date") else "tests"
    rules = entity.get("flag_rules") or []
    hits = evaluate(snapshot_id, rules)
    subjects = researchstore.read_snapshot_table(snapshot_id, "subjects").to_dicts()
    athletes = []
    for subject in subjects:
        subject_id = str(subject["subject_id"])
        rows = observed.get(subject_id, [])
        values = [value for _, value in rows]
        change = (values[-1] - values[0]) / values[0] * 100 if len(values) > 1 and values[0] else None
        trend = "insufficient data" if change is None else "up" if change > 0 else "down" if change < 0 else "flat"
        athletes.append({"subject_id": subject_id, "display_id": str(subject.get("display_id") or subject_id),
                         "attributes": {key: value for key, value in subject.items() if key not in ("subject_id", "display_id")},
                         "tests": len(values), "tests_expected": len(points), "latest": values[-1] if values else None,
                         "change_from_baseline_pct": change, "trend": trend, "flags": hits.get(subject_id, []),
                         "series": [{"point": point, "value": value} for point, value in rows]})
    def group_of(athlete: dict[str, Any]) -> str:
        if group_by == "category":
            return athlete["flags"][0]["category"] if athlete["flags"] else "No rule fired"
        if group_by == "trend":
            return athlete["trend"]
        return str(athlete["attributes"].get(group_by) or "Not recorded")
    groups: dict[str, list[dict[str, Any]]] = {}
    for athlete in athletes:
        groups.setdefault(group_of(athlete), []).append(athlete)
    return {"workspace_id": workspace_id, "data_revision_id": entity.get("active_data_revision_id"),
            "metric": metric, "metrics": list(metrics.values()), "rules": rules, "group_by": group_by, "time_word": time_word,
            "group_options": ["category", "trend", *sorted({key for athlete in athletes for key in athlete["attributes"]})],
            "groups": [{"name": name, "athletes": members} for name, members in groups.items()],
            "note": "Flags show which of your rules fired on observed data; they are not diagnoses."}


# --------------------------------------------------------------------------- #
# Researcher-defined simulations
# --------------------------------------------------------------------------- #

VARIANTS = ("best", "expected", "worst")


def simulate(workspace_id: str, scenario: dict[str, Any], subject_ids: list[str] | None = None) -> dict[str, Any]:
    """Project each athlete forward under the researcher's assumptions.

    scenario = {"name", "steps": int, "outcome_metric_id",
                "drivers": [{"metric_id", "change_pct_per_step": {"best","expected","worst"}}],
                "effects": [{"driver_metric_id", "outcome_pct_per_driver_pct": {"best","expected","worst"}}],
                "outcome_trend_pct_per_step": {"best","expected","worst"}}
    Each step: driver_t = driver_{t-1} × (1 + change%); outcome_t = outcome_{t-1} × (1 + trend% + Σ effect × driver change%).
    """
    entity = _workspace(workspace_id)
    snapshot_id = entity.get("dataset_snapshot_id")
    metrics = _metrics(snapshot_id)
    name, steps = str(scenario.get("name") or "").strip(), int(scenario.get("steps") or 0)
    outcome = metrics.get(scenario.get("outcome_metric_id"))
    if not name or steps < 1 or steps > 104 or outcome is None:
        raise researchstore.ResearchValidation("Name the scenario, choose a measured outcome and a horizon of 1–104 steps")
    drivers = scenario.get("drivers") or []
    for driver in drivers:
        if driver.get("metric_id") not in metrics:
            raise researchstore.ResearchValidation(f"Driver {driver.get('metric_id')} is not measured in this data revision")
    effects = {item["driver_metric_id"]: item["outcome_pct_per_driver_pct"] for item in scenario.get("effects") or []}
    if set(effects) - {driver["metric_id"] for driver in drivers}:
        raise researchstore.ResearchValidation("Every effect must refer to one of the scenario drivers")

    def pick(values: Any, variant: str) -> float:
        return float((values or {}).get(variant, 0.0)) if isinstance(values, dict) else float(values or 0.0)

    outcome_series, _ = athlete_series(snapshot_id, outcome)
    driver_series = {driver["metric_id"]: athlete_series(snapshot_id, metrics[driver["metric_id"]])[0] for driver in drivers}
    chosen = subject_ids or sorted(outcome_series)
    athletes, projected_outcomes = [], {variant: {} for variant in VARIANTS}
    for subject in chosen:
        rows = outcome_series.get(subject)
        if not rows:
            athletes.append({"subject_id": subject, "status": "No observed outcome; nothing to project from"})
            continue
        start = rows[-1][1]
        projections = {}
        for variant in VARIANTS:
            value, path = start, []
            for _ in range(steps):
                change = pick(scenario.get("outcome_trend_pct_per_step"), variant)
                for driver in drivers:
                    change += pick(effects.get(driver["metric_id"]), variant) * pick(driver.get("change_pct_per_step"), variant)
                value *= 1 + change / 100
                path.append(round(value, 4))
            projections[variant] = path
            projected_outcomes[variant][subject] = [v for _, v in rows] + path
        driver_paths = {}
        for driver in drivers:
            series = driver_series[driver["metric_id"]].get(subject)
            if series:
                level = series[-1][1]
                driver_paths[driver["metric_id"]] = {variant: [round(level * (1 + pick(driver.get("change_pct_per_step"), variant) / 100) ** (k + 1), 4)
                                                               for k in range(steps)] for variant in VARIANTS}
        athletes.append({"subject_id": subject, "status": "PROJECTED", "observed": [{"point": p, "value": v} for p, v in rows],
                         "start": start, "projection": projections, "drivers": driver_paths})
    rules = entity.get("flag_rules") or []
    crossing = {variant: {subject: [hit["category"] for hit in hits]
                          for subject, hits in evaluate(snapshot_id, rules, {outcome["id"]: projected_outcomes[variant]}).items()
                          if hits and subject in projected_outcomes[variant]} for variant in VARIANTS} if rules else {}
    return {"scenario": {**scenario, "name": name}, "designation": "HYPOTHETICAL",
            "basis": "Projection of the researcher's stated assumptions from each athlete's latest observed value; not a model-based prediction.",
            "outcome": {"id": outcome["id"], "label": outcome["label"], "unit": outcome["unit"]},
            "data_revision_id": entity.get("active_data_revision_id"), "athletes": athletes, "flags_at_horizon": crossing}


def save_simulation(workspace_id: str, scenario: dict[str, Any], base_version: int | None = None) -> dict[str, Any]:
    """Keep the scenario definition and its last result with the workspace (versioned like every workspace change)."""
    entity = _workspace(workspace_id)
    result = simulate(workspace_id, scenario)
    record = {"id": scenario.get("id") or f"SIM-{secrets.token_hex(3).upper()}", "definition": result["scenario"],
              "data_revision_id": result["data_revision_id"], "created_at": researchstore._now(),
              "summary": {variant: sorted(subjects) for variant, subjects in result["flags_at_horizon"].items()}}
    simulations = [item for item in entity.get("simulations") or [] if item["id"] != record["id"]] + [record]
    researchstore.update_entity(workspace_id, {"simulations": simulations}, base_version, change_type="SIMULATION_SAVED")
    return {**result, "record": record}

