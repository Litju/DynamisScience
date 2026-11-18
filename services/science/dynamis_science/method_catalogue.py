"""Versioned scientific contracts for the existing engines; no estimators live here."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

CATALOGUE_VERSION = "1.3.0"
MIN_TREND_REPEATED_ATHLETES = 3

# Estimands and limits follow the RES-619 matrix, not menu labels.
DETAILS = {
    "METH-ONSET-EXACT": ("Finite-schedule sharp-null test of no outcome response to any permissible onset; descriptive post-minus-pre mean separate",
                        "Statistic and descriptive difference in outcome units; p dimensionless", "Exact finite-support p; resolution 1/M; no causal CI",
                        "randomized_onset.py:evaluate", "docs/science/RES-716_RANDOMIZED_ONSET.md; tests/test_randomized_onset.py"),
    "METH-EXPERIMENT-DESC": ("Session-weighted descriptions by actual protocol phase; observed change and date-based slope",
                             "Outcome units; SD in outcome units; slope in outcome units/day", "No confidence interval, p-value or causal effect",
                             "experiments.py:describe", "tests/test_experiment_analysis.py"),
    "METH-REAL-TREND": ("Population mean within-athlete change per ordinal occasion and selected contrast",
                        "Outcome unit per occasion; contrast in outcome units", "ML Wald 95% z interval; no small-sample correction",
                        "realanalysis.py:_fit_trend", "R lme4 ML comparison: docs/science/res619-evidence/r-mixedlm-summary.csv"),
    "METH-REAL-RELIABILITY": ("Within-session single-trial consistency ICC(3,1); TE = sqrt(two-way MSE); MDC95 = 1.96 sqrt(2) TE",
                              "ICC dimensionless; TE/MDC95 in N; CV in %", "Shrout–Fleiss F-based ICC 95% CI",
                              "realanalysis.py:reliability / analysis.py:two_way_icc", "docs/science/res619-evidence/r-reliability-icc.csv"),
    "METH-REAL-DESC": ("Mean of athlete values per occasion (trials averaged within athlete)", "Outcome units", "Student-t 95% CI across athletes, df = n - 1",
                       "researchanalysis.py:_descriptive", "docs/science/RES-619_METHODOLOGY.md"),
    "METH-U-DESC": ("Mean of athlete values per axis point (trials averaged within athlete)", "Outcome units", "Student-t 95% CI across athletes; undefined with one athlete",
                    "researchanalysis.py:_descriptive", "docs/science/RES-619_METHODOLOGY.md"),
    "METH-U-CHANGE": ("Observed per-athlete paired change; cohort change SD", "Outcome units", "Descriptive; no causal interval. TE only from same-session repeats",
                      "researchanalysis.py:_individual_change", "docs/science/RES-619_METHODOLOGY.md"),
    "METH-U-INDIVIDUAL": ("One participant's observed session means and first-to-last change", "Outcome units", "Trial-noise SE excludes between-day biological variation; no causal CI",
                          "longitudinal.py:individual_trajectory", "tests/test_longitudinal_research.py:test_individual_trajectory_independent_recomputation"),
    "METH-REAL-SIGNAL-QA": ("Restricted summed vertical force and IMU signal quality summaries", "N, N s, Hz and clock offsets as labelled", "Descriptive QA; no cross-modality validity or body-weight recovery claim",
                           "realanalysis.py:signal_qa", "qualification_real.py:qualify_signal"),
}


def catalogue() -> list[dict[str, Any]]:
    """Detached, serializable method specs. Qualification remains bounded to recorded evidence."""
    from .researchstore import METHODS, REJECTED_METHODS

    result = []
    for identity, meta in METHODS.items():
        estimand, units, uncertainty, implementation, evidence = DETAILS[identity]
        item = copy.deepcopy(meta)
        item.update(catalogue_version=CATALOGUE_VERSION, estimand=estimand, units=units,
                    uncertainty=uncertainty, implementation=implementation,
                    evidence_references=["docs/science/RES-619_METHODOLOGY.md", evidence],
                    scopes=["INDIVIDUAL" if identity in {"METH-U-INDIVIDUAL", "METH-EXPERIMENT-DESC", "METH-ONSET-EXACT"} else "COHORT"],
                    method_class="DESCRIPTIVE" if identity in {"METH-U-DESC", "METH-REAL-DESC", "METH-U-CHANGE", "METH-U-INDIVIDUAL", "METH-EXPERIMENT-DESC"} else "QUALIFIED",
                    execution_route="researchanalysis.execute", report_outputs=meta["output_schema"],
                    timebase="Ordinal occasion/week; no equal calendar spacing assumed" if "signal_trials" not in meta["required_tables"] else "Activity / acquisition-ordered trials; native signals 1000 Hz")
        item["limitations"] = [*item["constraints"], "Qualification is numerical and scope-specific; no independent human statistical approval is implied."]
        if identity in {'METH-EXPERIMENT-DESC', 'METH-ONSET-EXACT'}:
            item['timebase'] = 'Actual timezone-aware visit timestamps; elapsed 24-hour days, not ordinal occasions'
        if identity == 'METH-ONSET-EXACT':
            item['timebase'] = 'Fixed increasing timezone-aware timestamps, exact schedule required; ordinal keys define the permissible onset support'
        if identity == "METH-REAL-TREND":
            item["assumptions"] += ["Independent, homoscedastic within-athlete errors; outcome missingness is ignorable (MAR assumed)."]
            item["limitations"] += ["Wald intervals have no Satterthwaite/Kenward–Roger correction; fallback to random intercept changes the SE basis."]
        if identity == "METH-REAL-RELIABILITY":
            item["assumptions"] += ["Normal errors for F-based intervals; no subject × trial interaction."]
        result.append(item)
    for identity, name, status, reason, implementation in (
        ("METH-LONG", "Synthetic arm × time reference", "QUALIFIED", "Synthetic reference study only; fallback estimator class is recorded. Not a generic cohort method.", "analysis.py:_group_longitudinal"),
        ("METH-REL", "Synthetic baseline ICC / TE / MDC95 reference", "QUALIFIED", "Synthetic baseline reference only; not device or between-day reliability.", "analysis.py:two_way_icc"),
        ("METH-EXPERIMENT", "Individual experimental effect", "UNAVAILABLE", "No qualified within-person causal estimator is available (RES-717).", "longitudinal.py:period_summaries"),
        ("METH-FORECAST", "Individual scenario forecast", "UNAVAILABLE", "No qualified forecasting model is available (RES-590).", "longitudinal.py:FORECAST_REASON"),
        ("METH-FITNESS-FATIGUE", "Fitness–fatigue prototype", "EXPLORATORY", "Research prototype; no qualified research execution contract.", "analysis.py:_training_response"),
        *[(key, value["name"], "UNAVAILABLE", value["reason"], "realanalysis.py:signal_qa") for key, value in REJECTED_METHODS.items()],
    ):
        result.append(dict(id=identity, name=name, version="1.1.0" if identity in {"METH-LONG", "METH-REL"} else "1.0.0",
                           catalogue_version=CATALOGUE_VERSION, method_class=status, estimand=name,
                           scopes=["COHORT"] if identity in {"METH-LONG", "METH-REL"} else ["INDIVIDUAL"],
                           supported_designs=[], required_tables=[], required_shape=reason, units="As specified in reference implementation",
                           assumptions=[], uncertainty="No additional uncertainty claim", diagnostics=[], output_schema=[], report_outputs=[],
                           missingness="See reference implementation", constraints=[reason], limitations=[reason], reason=reason,
                           parameter_schema={}, qualification=copy.deepcopy(REJECTED_METHODS.get(identity, {}).get("qualification", {"status": status, "basis": reason})),
                           evidence_references=["docs/science/RES-619_METHODOLOGY.md"], implementation=implementation,
                           execution_route="synthetic reference only" if identity in {"METH-LONG", "METH-REL"} else None,
                           timebase="See reference implementation"))
        if identity in {"METH-LONG", "METH-REL"}:
            result[-1].update(
                estimand="Between-arm difference in change" if identity == "METH-LONG" else "Baseline single-trial consistency ICC(3,1), TE and MDC95",
                units="Outcome units; ICC dimensionless; CV in %",
                supported_designs=["SYNTHETIC_REFERENCE"], required_tables=["cmj_trials"],
                required_shape="First valid trial per athlete-week in two arms" if identity == "METH-LONG" else "At least three athletes with two valid baseline trials; balanced first k",
                assumptions=["Linear arm-specific slopes and random athlete effects" if identity == "METH-LONG" else "Two-way ANOVA, fixed trial factor; no subject × trial interaction"],
                uncertainty="Wald 95% interval" if identity == "METH-LONG" else "Shrout–Fleiss F-based ICC 95% CI; TE = sqrt(MSE), MDC95 = 1.96 sqrt(2) TE",
                diagnostics=["Estimator/fallback identity", "residual summaries"] if identity == "METH-LONG" else ["Balanced trials", "excluded trials", "within-athlete CV"],
                output_schema=["Difference-in-change contrast and SE"] if identity == "METH-LONG" else ["ICC and CI", "TE", "MDC95"],
                missingness="Observed valid trials only; no imputation", timebase="Ordinal training week / baseline repeated trials")
            result[-1]["report_outputs"] = result[-1]["output_schema"]
    return result


def method_spec(identity: str) -> dict[str, Any]:
    return next(item for item in catalogue() if item["id"] == identity)


def trend_repetition(rows: list[dict], outcome: str) -> int:
    """Count athletes with finite outcomes at two or more distinct ordinal occasions."""
    occasions_by_athlete: dict[str, set[int]] = {}
    for row in rows:
        occasion, value = row.get("occasion"), row.get(outcome)
        if (type(occasion) in (int, float) and math.isfinite(occasion) and occasion == int(occasion)
                and type(value) in (int, float) and math.isfinite(value)):
            occasions_by_athlete.setdefault(row["subject_id"], set()).add(int(occasion))
    return sum(len(occasions) >= 2 for occasions in occasions_by_athlete.values())


def eligibility(method: dict, metric: dict, rows: list[dict], subject_ids: list[str],
                scope: dict, design: str, parameters: dict | None = None, experiment: dict | None = None) -> dict:
    """Check actual selected rows, before any fit or persistence. Missing outcomes stay missing."""
    p = parameters or {}
    if method['id'] == 'METH-ONSET-EXACT':
        from .randomized_onset import eligibility as onset_eligibility
        return onset_eligibility(method, metric, subject_ids, scope, p, experiment)
    if method['id'] == 'METH-EXPERIMENT-DESC':
        from .experiments import analysis_eligibility
        return analysis_eligibility(method, metric, subject_ids, scope, p, experiment)
    identity, table, column = method["id"], metric["table"], metric["column"]
    issues = []
    if method.get("reason"):
        issues.append(method["reason"])
    if scope.get("kind", "COHORT") not in method["scopes"]:
        issues.append("Individual-scope method; select a participant investigation to use it." if "INDIVIDUAL" in method["scopes"]
                      else "Cohort-level method; an individual investigation requires the individual trajectory method.")
    if table not in method["required_tables"]:
        issues.append(f"Requires {', '.join(method['required_tables']) or 'a dedicated qualified implementation'}; selected outcome is in {table}.")
    if design and design not in method["supported_designs"]:
        issues.append(f"Design {design} is unsupported; no treatment or causal effect is inferred.")
    if not metric.get("unit"):
        issues.append("Outcome units must be recorded in the metric registry.")
    for key, schema in method.get("parameter_schema", {}).items():
        if key not in p:
            continue
        value = p[key]
        valid = ((type(value) is int and schema["type"] == "integer")
                 or (type(value) in (int, float) and schema["type"] == "number" and math.isfinite(value))
                 or (isinstance(value, str) and schema["type"] == "string" and bool(value.strip())))
        if not valid or ("minimum" in schema and value < schema["minimum"]) or ("maximum" in schema and value > schema["maximum"]):
            issues.append(f"Invalid parameter {key}: expected {schema['type']} within the method's declared bounds.")
    # Invalid types must not reach comparisons, row selection or the numerical engine.
    if any(issue.startswith("Invalid parameter") for issue in issues):
        return {**copy.deepcopy(method), "method_id": identity, "status": "INELIGIBLE", "issues": issues}
    selected = [r for r in rows if r.get("subject_id") in subject_ids]
    if identity == "METH-REAL-RELIABILITY":
        if column != "fz_peak_n" or metric.get("unit") != "N":
            issues.append("Reliability engine requires peak vertical force fz_peak_n in N; it cannot run another metric.")
        selected = [r for r in selected if r.get("activity") == p.get("activity", "Walking")]
    values = [r for r in selected if r.get(column) is not None]
    population = {"subjects": len(subject_ids), "observed_rows": len(values),
                  "missing_rows": len(selected) - len(values)}
    if any(not isinstance(r[column], (int, float)) or not math.isfinite(r[column]) for r in values):
        issues.append("Outcome contains non-finite or non-numeric values; correct the input before analysis.")
    if not values:
        issues.append("No observed outcome values remain in the selected population.")
    axis = "occasion" if table == "cmj_occasions" else "week" if table == "cmj_trials" else "activity"
    if identity in {"METH-REAL-TREND", "METH-U-DESC", "METH-REAL-DESC", "METH-U-CHANGE", "METH-U-INDIVIDUAL"}:
        if any(r.get(axis) is None for r in values) or not values:
            issues.append(f"Missing {axis} metadata; map the measured time axis during import.")
        if axis in {"occasion", "week"} and any(
                r.get(axis) is not None and (not isinstance(r[axis], (int, float))
                or not math.isfinite(r[axis]) or int(r[axis]) != r[axis]) for r in values):
            issues.append(f"The {axis} axis requires finite integer ordinal values.")
            return {**copy.deepcopy(method), "method_id": identity, "status": "INELIGIBLE", "issues": issues}
    if identity == "METH-REAL-TREND":
        repeated = trend_repetition(values, column)
        population["athletes_with_repeated_occasions"] = repeated
        if repeated < MIN_TREND_REPEATED_ATHLETES:
            issues.append(f"Only {repeated} athletes have outcomes on two or more distinct occasions; "
                          f"at least {MIN_TREND_REPEATED_ATHLETES} are required for a longitudinal trend.")
        if len(values) < 8:
            issues.append(f"Only {len(values)} complete observations; at least 8 are required.")
        keys = [(r.get("subject_id"), r.get(axis)) for r in selected]
        if len(keys) != len(set(keys)):
            issues.append("MixedLM requires one row per athlete and occasion; duplicate rows would overweight athletes.")
        levels = {r.get(axis) for r in values if r.get(axis) is not None}
        ref, con = p.get("reference_occasion", min(levels) if levels else 1), p.get("contrast_occasion", max(levels) if levels else 2)
        if ref not in levels or con not in levels or con <= ref:
            issues.append("Select two observed occasions in increasing order for the contrast.")
        if p.get("alpha", 0.05) != 0.05:
            issues.append("The existing engine supplies fixed 95% intervals; alpha must be 0.05.")
    if identity in {"METH-U-INDIVIDUAL", "METH-U-CHANGE"}:
        levels = {r.get(axis) for r in values if r.get(axis) is not None}
        if len(levels) < 2:
            issues.append(f"Only {len(levels)} measured {axis}(s); at least two are required.")
        if identity == "METH-U-CHANGE":
            ref = p.get("reference_week", p.get("reference_occasion", 1))
            con = p.get("contrast_week", p.get("contrast_occasion", 2))
            paired = [s for s in subject_ids if {ref, con} <= {r.get(axis) for r in values if r["subject_id"] == s}]
            if con <= ref or not paired:
                issues.append("No complete pairs for the selected increasing reference/contrast occasions.")
    if identity == "METH-REAL-RELIABILITY":
        counts = {s: sum(r["subject_id"] == s for r in values) for s in subject_ids}
        if sum(n >= 2 for n in counts.values()) < 3:
            issues.append("At least three participants must have at least two repeated trials in the selected activity.")
        k = p.get("max_trials", 8)
        if type(k) is not int or not 2 <= k <= 8:
            issues.append("max_trials must be an integer between 2 and 8.")
        keys = [(r["subject_id"], r.get("trial_number")) for r in selected]
        if any(key[1] is None for key in keys) or len(keys) != len(set(keys)):
            issues.append("Unique acquisition-ordered trial_number metadata is required per athlete.")
        if any(type(key[1]) is not int or key[1] < 1 for key in keys):
            issues.append("Acquisition trial numbers must be positive integers.")
        if len(values) != len(selected):
            issues.append("Reliability requires complete trial outcomes; remove or correct empty trials explicitly.")
    return {**copy.deepcopy(method), "method_id": identity, "status": "INELIGIBLE" if issues else "ELIGIBLE", "issues": issues,
            "population": population}


def execution_binding(identity: str, metric: dict, parameters: dict, snapshot: dict,
                      revision: str | None, subjects: list[str], excluded: list[str]) -> dict:
    """Capture contract and implementation bytes, including uncommitted source changes."""
    root = Path(__file__).resolve().parent
    sources = [root / name for name in ("method_catalogue.py", "analysis.py", "realanalysis.py", "researchanalysis.py", "longitudinal.py", "researchstore.py", "experiments.py", "randomized_onset.py")]
    digest = hashlib.sha256()
    for path in sources:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=3, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        head = None
    return copy.deepcopy(dict(catalogue_version=CATALOGUE_VERSION, method_spec=method_spec(identity),
                              method_id=identity, method_version=method_spec(identity)["version"], parameters=parameters,
                              outcome=metric, snapshot_id=snapshot["id"], snapshot_checksums=snapshot.get("checksums", {}),
                              data_revision_id=revision, included_subject_ids=subjects, excluded_subject_ids=excluded,
                              source_revision={"git_head": head, "implementation_sha256": digest.hexdigest()}))


def binding_digest(binding: dict) -> str:
    return hashlib.sha256(json.dumps(binding, sort_keys=True, default=str).encode()).hexdigest()
