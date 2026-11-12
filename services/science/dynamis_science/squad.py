"""Researcher-configured squad flags and assumption-driven simulations (RES-647).

Everything here is defined by the person using the software: which metrics matter, what counts as a flag,
what the categories are called and which assumptions a simulation applies. The engine only evaluates those
definitions against observed data in the active data revision and reports exactly which rule fired. Simulations
project the researcher's stated assumptions from each athlete's latest observed values; they are labeled as such
and are never stored as observations.
"""

from __future__ import annotations

import math
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
    "acute_chronic_ratio": "Record mean ratio (last A / last C records; not calendar ACWR)",
    "missed_tests": "Missing measured occasions in revision",
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
    valid = frame.filter(pl.col(metric["column"]).is_not_null() & pl.col(metric["column"]).is_finite() & pl.col(axis).is_not_null())
    if "quality_state" in valid.columns:
        valid = valid.filter(pl.col("quality_state") == "VALID")
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
        window = int(condition.get("window", 3))
        return float(np.mean(values[-window:])) if len(values) >= window else None
    if kind == "acute_chronic_ratio":
        acute, chronic = int(condition.get("acute", 1)), int(condition.get("chronic", 4))
        if acute < 1 or chronic < 2 or len(values) < chronic or acute >= chronic:
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
        for key, default in (("window", 3), ("acute", 1), ("chronic", 4)):
            raw = condition.get(key, default)
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
                raise researchstore.ResearchValidation(f"{name}: record windows must be positive integers")
        if condition.get("measure") == "acute_chronic_ratio" and condition.get("acute", 1) >= condition.get("chronic", 4):
            raise researchstore.ResearchValidation(f"{name}: short record window must be less than long window")
        if not all(math.isfinite(float(condition[k])) for k in (("value", "value2") if condition["operator"] in ("between", "outside") else ("value",))):
            raise researchstore.ResearchValidation(f"{name}: thresholds must be finite")
    return {"id": rule.get("id") or f"RULE-{secrets.token_hex(3).upper()}", "name": name, "category": category,
            "tone": rule.get("tone", "neutral"), "match": "any" if rule.get("match") == "any" else "all",
            "enabled": rule.get("enabled", True), "conditions": conditions}


def save_rules(workspace_id: str, rules: list[dict[str, Any]], base_version: int | None = None) -> dict[str, Any]:
    entity = _workspace(workspace_id)
    if not entity.get("dataset_snapshot_id"):
        raise researchstore.ResearchValidation("Add data before defining flag rules")
    metrics = _metrics(entity["dataset_snapshot_id"])
    validated = [validate_rule(rule, metrics) for rule in rules]
    previous = {r["id"]: r for r in entity.get("flag_rules", [])}
    for rule in validated:
        rule["version"] = previous.get(rule["id"], {}).get("version", 0) + 1
    evaluations = evaluate_records(entity["dataset_snapshot_id"], validated, entity.get("active_data_revision_id"))
    return researchstore.update_entity(workspace_id, {"flag_rules": validated,
        "recorded_flag_evaluations": [*entity.get("recorded_flag_evaluations", []),
            {"at": researchstore._now(), "data_revision_id": entity.get("active_data_revision_id"),
             "rules": validated, "evaluations": evaluations}]}, base_version, change_type="FLAG_RULES_SAVED")


def evaluate_records(snapshot_id: str, rules: list[dict[str, Any]], data_revision_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """All descriptive evaluations, including unavailable values; never classify missing data as normal."""
    metrics = _metrics(snapshot_id)
    snapshot = researchstore.get_snapshot(snapshot_id) or {}
    subjects = [str(s) for s in researchstore.read_snapshot_table(snapshot_id, "subjects")["subject_id"].to_list()]
    records = {subject: [] for subject in subjects}
    cache = {}
    at = researchstore._now()
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        for subject in subjects:
            evidence, states = [], []
            for condition in rule["conditions"]:
                metric = metrics.get(condition["metric_id"])
                rows, points, observed = [], [], {}
                if metric:
                    if metric["id"] not in cache:
                        cache[metric["id"]] = athlete_series(snapshot_id, metric)
                    observed, points = cache[metric["id"]]
                    rows = observed.get(subject, [])
                values = [v for _, v in rows]
                value = _measure(condition["measure"], values, [v[-1][1] for v in observed.values() if v], len(points), condition) if metric else None
                ok = None if value is None else _compare(value, condition)
                states.append(ok)
                label = MEASURES[condition["measure"]]
                if condition["measure"] == "rolling_mean":
                    label = f"Rolling mean of last {condition.get('window', 3)} records"
                elif condition["measure"] == "acute_chronic_ratio":
                    label = f"Record mean ratio ({condition.get('acute', 1)} vs {condition.get('chronic', 4)} records); not calendar ACWR"
                transformed_unit = "%" if condition["measure"].endswith("_pct") else "ratio" if condition["measure"] == "acute_chronic_ratio" else "SD units" if condition["measure"] == "vs_squad_sd" else "occasions" if condition["measure"] == "missed_tests" else (metric or {}).get("unit")
                evidence.append({"metric_id": condition["metric_id"], "metric": (metric or {}).get("label", condition["metric_id"]),
                    "unit": (metric or {}).get("unit"), "statistic_unit": transformed_unit, "measure": label,
                    "value": value, "operator": condition["operator"], "threshold": condition["value"],
                    "threshold2": condition.get("value2"), "met": ok, "source": snapshot.get("source"),
                    "snapshot_id": snapshot_id, "data_revision_id": data_revision_id,
                    "measurement_sources": snapshot.get("measurement_sources", {}).get((metric or {}).get("table"), []),
                    "observations": [{"point": p, "value": v} for p, v in rows],
                    "missing_occasions": [p for p in points if p not in {r[0] for r in rows}],
                    "qc_eligibility": "Finite admitted values; quality_state VALID where recorded",
                    "eligibility": "ELIGIBLE" if value is not None else "NOT_EVALUABLE",
                    "limitation": "Record windows use valid session means, include the short window in the long window, and do not imply elapsed days. Incomplete windows and zero denominators are unavailable; no risk interpretation."})
            if rule["match"] == "all":
                matched = False if False in states else None if None in states else True
            else:
                matched = True if True in states else None if None in states else False
            records[subject].append({"rule_id": rule["id"], "rule": rule["name"], "rule_version": rule.get("version", 1),
                "category": rule["category"], "tone": rule["tone"], "classification": "RESEARCHER_DEFINED",
                "evaluated_at": at, "data_revision_id": data_revision_id,
                "status": "NOT_EVALUABLE" if matched is None else "MATCH" if matched else "NO_MATCH", "evidence": evidence})
    return records


def evaluate(snapshot_id: str, rules: list[dict[str, Any]], *, data_revision_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    return {subject: [r for r in records if r["status"] == "MATCH"]
            for subject, records in evaluate_records(snapshot_id, rules, data_revision_id).items()}


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
    evaluations = evaluate_records(snapshot_id, rules, entity.get("active_data_revision_id"))
    hits = {subject: [r for r in rows if r["status"] == "MATCH"] for subject, rows in evaluations.items()}
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
                         "rule_evaluations": evaluations.get(subject_id, []),
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
            "title": entity["title"],
            "note": "Researcher-defined descriptive rules; thresholds are not scientifically validated. Missing or QC-ineligible measurements are unavailable, not normal. No diagnoses or athlete-risk classification."}


# --------------------------------------------------------------------------- #
# Researcher-defined simulations
# --------------------------------------------------------------------------- #

VARIANTS = ("best", "expected", "worst")


def simulate(workspace_id: str, scenario: dict[str, Any], subject_ids: list[str] | None = None) -> dict[str, Any]:
    """Validate a hypothetical scenario definition without calculating athlete futures.

    scenario = {"name", "steps": int, "outcome_metric_id",
                "drivers": [{"metric_id", "change_pct_per_step": {"best","expected","worst"}}],
                "effects": [{"driver_metric_id", "outcome_pct_per_driver_pct": {"best","expected","worst"}}],
                "outcome_trend_pct_per_step": {"best","expected","worst"}}
    Legacy best/expected/worst keys are retained as saved assumption identifiers only.
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

    return {"scenario": {**scenario, "name": name}, "designation": "HYPOTHETICAL",
            "qualification": {"status": "NOT_QUALIFIED",
                              "message": "Numerical forecast unavailable until RES-619/RES-590 qualification."},
            "numerical_result": None,
            "basis": "Scenario definition only; not a model-based prediction or observed evidence. No numerical forecast is qualified.",
            "outcome": {"id": outcome["id"], "label": outcome["label"], "unit": outcome["unit"]},
            "data_revision_id": entity.get("active_data_revision_id"), "athletes": [], "flags_at_horizon": {}}


def save_simulation(workspace_id: str, scenario: dict[str, Any], base_version: int | None = None) -> dict[str, Any]:
    """Version a hypothetical definition; never store forecast numbers or projected flag classifications."""
    entity = _workspace(workspace_id)
    result = simulate(workspace_id, scenario)
    record = {"id": scenario.get("id") or f"SIM-{secrets.token_hex(3).upper()}", "definition": result["scenario"],
              "data_revision_id": result["data_revision_id"], "created_at": researchstore._now(),
              "summary": {}, "designation": "HYPOTHETICAL", "qualification": result["qualification"],
              "numerical_result": None}
    simulations = [item for item in entity.get("simulations") or [] if item["id"] != record["id"]] + [record]
    researchstore.update_entity(workspace_id, {"simulations": simulations}, base_version, change_type="SIMULATION_SAVED")
    return {**result, "record": record}



# --------------------------------------------------------------------------- #
# Events feed
# --------------------------------------------------------------------------- #

REVISION_MODES = {"SEPARATE": "New data attached", "APPEND": "New measurements appended", "LINK": "New kind of measurement linked"}


def events(workspace_id: str) -> dict[str, Any]:
    """What happened in the workspace, newest first, plus who needs attention now.

    Flag changes compare the researcher's *current* rules between consecutive data revisions, so a rule edit
    re-reads history consistently instead of mixing old and new standards.
    """
    entity = _workspace(workspace_id)
    rules = entity.get("flag_rules") or []
    revisions = researchstore.data_revisions(workspace_id)
    items: list[dict[str, Any]] = []
    previous: dict[str, set[tuple[str, str]]] = {}
    current_hits: dict[str, list[dict[str, Any]]] = {}
    for revision in revisions:
        tables = ", ".join(sorted(t for t in revision["snapshot"].get("tables", {}) if t != "subjects"))
        items.append({"at": revision["created_at"], "kind": "data", "tone": "neutral", "subject_id": None,
                      "title": f"{REVISION_MODES.get(revision['mode'], 'Data')} · revision {revision['number']}",
                      "detail": f"{tables} · {sum(n for t, n in revision['snapshot'].get('row_counts', {}).items() if t != 'subjects'):,} measurement rows"})
        hits = evaluate(revision["snapshot_id"], rules, data_revision_id=revision["id"]) if rules else {}
        state = {subject: {(hit["category"], hit["tone"]) for hit in subject_hits} for subject, subject_hits in hits.items()}
        for subject, categories in state.items():
            before = previous.get(subject, set())
            for category, tone in sorted(categories - before):
                hit = next(h for h in hits[subject] if h["category"] == category)
                items.append({"at": revision["created_at"], "kind": "flag", "tone": tone, "subject_id": subject,
                              "title": f"Retrospective: {subject} entered {category}", "detail": "Current rules re-evaluated now; not recorded at the revision date. " + _evidence_text(hit), "revision": revision["number"], "evaluation_kind": "RETROSPECTIVE", "evaluated_at": researchstore._now()})
            for category, _ in sorted(before - categories):
                items.append({"at": revision["created_at"], "kind": "flag", "tone": "neutral", "subject_id": subject,
                              "title": f"Retrospective: {subject} no longer recorded as matching {category}", "detail": f"Data revision {revision['number']}; current rules evaluated now. Values may be unavailable; absence of a match is not normal status.",
                              "revision": revision["number"], "evaluation_kind": "RETROSPECTIVE", "evaluated_at": researchstore._now()})
        previous, current_hits = state, hits
    active_revision = researchstore.get_data_revision(entity.get("active_data_revision_id"))
    current_hits = evaluate(active_revision["snapshot_id"], rules, data_revision_id=active_revision["id"]) if active_revision and rules else {}
    for record in entity.get("recorded_flag_evaluations", []):
        items.append({"at": record["at"], "kind": "rule_evaluation", "tone": "neutral", "subject_id": None,
                      "title": "Recorded researcher-defined rule evaluation", "detail": f"Revision {record['data_revision_id']}; original rule versions retained.",
                      "evaluation_kind": "RECORDED", "evaluations": record["evaluations"]})
    for run in researchstore.list_runs(workspace_id):
        scope = run.get("scope") or {"kind": "COHORT"}
        who = f"participant {scope['subject_id']}" if scope["kind"] == "INDIVIDUAL" else "cohort"
        items.append({"at": run["created_at"], "kind": "analysis", "tone": "neutral", "subject_id": scope.get("subject_id"),
                      "title": f"Analysis saved · {who}", "detail": f"{run['id']} · {run['method_id']} · {run['method_status']['state'].lower()}"})
    for simulation in entity.get("simulations") or []:
        items.append({"at": simulation["created_at"], "kind": "simulation", "tone": "neutral", "subject_id": None,
                      "title": f"Hypothetical scenario saved · {simulation['definition']['name']}",
                      "detail": "Assumptions only. Numerical forecast unavailable; not observed or qualified evidence."})
    items.sort(key=lambda item: item["at"], reverse=True)
    branched = {(item.get("scope") or {}).get("subject_id") for item in researchstore.list_investigations(workspace_id)}
    attention = [{"kind": "attention", "tone": "negative", "subject_id": subject,
                  "title": f"{subject} · {', '.join(sorted({h['category'] for h in subject_hits if h['tone'] == 'negative'}))}",
                  "detail": "No follow-up branch yet. " + "; ".join(_evidence_text(h) for h in subject_hits if h["tone"] == "negative")}
                 for subject, subject_hits in sorted(current_hits.items())
                 if any(h["tone"] == "negative" for h in subject_hits) and subject not in branched]
    return {"workspace_id": workspace_id, "data_revision_id": entity.get("active_data_revision_id"),
            "attention": attention, "events": items, "rules": len(rules)}


def _evidence_text(hit: dict[str, Any]) -> str:
    return f"Rule “{hit['rule']}”: " + "; ".join(f"{e['metric']} {e['measure'].lower()} = {e['value']}" for e in hit["evidence"])
