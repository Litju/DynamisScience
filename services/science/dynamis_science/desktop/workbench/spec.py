"""Plain-Python analysis specification for the RES-620 workbench (no Qt).

Roles, type rules, validation, a stable hash for stale detection, and the Python
syntax / run payload that correspond to the configured method.  Nothing here
computes statistics; it only describes calls into existing code.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

NUMERICAL, CATEGORICAL, ORDINAL, IDENTIFIER = "numerical", "categorical", "ordinal", "identifier"
VAR_TYPES = (NUMERICAL, CATEGORICAL, ORDINAL, IDENTIFIER)

QUALIFIED, DESCRIPTIVE, NOT_QUALIFIED = "qualified", "descriptive", "not qualified"


@dataclass(frozen=True)
class RoleRule:
    label: str
    types: frozenset[str]
    min: int = 0
    max: int | None = 1  # None = unbounded; 0 = role unavailable


def _r(label: str, types: tuple[str, ...], min: int = 0, max: int | None = 1) -> RoleRule:
    return RoleRule(label, frozenset(types), min, max)


_ANY = (NUMERICAL, CATEGORICAL, ORDINAL)
_WITHIN = (ORDINAL, CATEGORICAL)

# kind -> role -> rule.  Identifier is accepted only by the "subject" role.
ROLE_RULES: dict[str, dict[str, RoleRule]] = {
    "descriptives": {"outcome": _r("Variables", (NUMERICAL,), 1, None), "factors": _r("Split by", (CATEGORICAL, ORDINAL))},
    "frequencies": {"factors": _r("Variables", (CATEGORICAL, ORDINAL), 1, None)},
    "athlete_change": {
        "outcome": _r("Outcome", (NUMERICAL,), 1),
        "subject": _r("Athlete", (IDENTIFIER,), 1),
        "occasion": _r("Occasion", (ORDINAL,), 1),
    },
    "mixed_model": {
        "outcome": _r("Outcome", (NUMERICAL,), 1),
        "subject": _r("Subject (random intercept)", (IDENTIFIER,), 1),
        "occasion": _r("Occasion (random slope)", (ORDINAL,), 1),
        "covariates": _r("Covariates", (), 0, 0),  # the qualified engine has none
        "factors": _r("Factors", (), 0, 0),
    },
    "reliability": {
        "outcome": _r("Outcome", (NUMERICAL,), 1),
        "subject": _r("Subject", (IDENTIFIER,), 1),
        "covariates": _r("Covariates", (), 0, 0),
        "factors": _r("Factors", (), 0, 0),
    },
    "ttest": {
        "outcome": _r("Outcome", (NUMERICAL,), 1),
        "occasion": _r("Paired by", _WITHIN, 1),
        "subject": _r("Subject", (IDENTIFIER,), 1),
    },
    "anova": {
        "outcome": _r("Outcome", (NUMERICAL,), 1),
        "occasion": _r("Repeated factor", _WITHIN, 1),
        "subject": _r("Subject", (IDENTIFIER,), 1),
    },
    "regression": {
        "outcome": _r("Outcome", (NUMERICAL,), 1),
        "covariates": _r("Predictors", _ANY, 1, None),
    },
}
ROLES = ("outcome", "covariates", "factors", "subject", "occasion")

# kind -> (method id in researchstore.METHODS or None, claim class)
_METHOD = {
    "descriptives": ("METH-REAL-DESC", DESCRIPTIVE),
    "frequencies": (None, DESCRIPTIVE),
    "athlete_change": ("METH-U-CHANGE", DESCRIPTIVE),
    "mixed_model": ("METH-REAL-TREND", QUALIFIED),
    "reliability": ("METH-REAL-RELIABILITY", QUALIFIED),
    "ttest": (None, NOT_QUALIFIED),
    "anova": (None, NOT_QUALIFIED),
    "regression": (None, NOT_QUALIFIED),
}
STUDY_FOR_TABLE = {"cmj_occasions": "STUDY-REAL-001", "signal_trials": "STUDY-REAL-002"}

# Defaults mirror realstore's registered specs (SPEC-REAL-TREND-001 / SPEC-REAL-REL-001).
DEFAULTS: dict[str, dict[str, Any]] = {
    "descriptives": {},
    "frequencies": {},
    "athlete_change": {"reference_occasion": None, "contrast_occasion": None},
    "mixed_model": {"reference_occasion": 1, "contrast_occasion": 4, "alpha": 0.05, "excluded_subject_ids": []},
    "reliability": {"activity": "Walking", "max_trials": 8, "excluded_subject_ids": []},
    "ttest": {"level_1": None, "level_2": None},
    "anova": {},
    "regression": {},
}


def method_status(kind: str) -> dict[str, Any]:
    """Qualification status read from researchstore.METHODS (not hard-coded)."""
    from ... import researchstore

    method_id, claim = _METHOD[kind]
    meta = researchstore.METHODS.get(method_id) if method_id else None
    if claim == QUALIFIED and not (meta and meta["qualification"]["status"] == "QUALIFIED"):
        claim = NOT_QUALIFIED  # never advertise qualification the codebase does not record
    return {
        "status": claim,
        "method_id": method_id,
        "version": meta["version"] if meta else None,
        "record": meta["qualification"].get("record") if meta else None,
        "promotable": claim == QUALIFIED,
    }


@dataclass
class AnalysisSpec:
    kind: str
    roles: dict[str, list[str]] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    snapshot_id: str = ""
    table: str = ""
    variable_types: dict[str, str] = field(default_factory=dict)  # name -> variable type

    # -- helpers ---------------------------------------------------------
    def role(self, name: str) -> list[str]:
        return list(self.roles.get(name, []))

    def effective_options(self) -> dict[str, Any]:
        return {**DEFAULTS.get(self.kind, {}), **self.options}

    @property
    def study_id(self) -> str | None:
        return self.options.get("study_id") or STUDY_FOR_TABLE.get(self.table)

    def can_accept(self, role: str, variable: str) -> str | None:
        """None if `variable` may be dropped on `role`, else the rejection message."""
        rule = ROLE_RULES.get(self.kind, {}).get(role)
        vtype = self.variable_types.get(variable)
        if rule is None:
            return f"{role} is not used by this analysis"
        if rule.max == 0:
            return f"{rule.label} is not available in the qualified engine"
        if vtype is None:
            return f"{variable} has no known type"
        if vtype not in rule.types:
            if vtype == IDENTIFIER:
                return f"{variable} is an identifier; it can only be used as the subject"
            return f"{variable} is {vtype}; {rule.label} accepts {', '.join(sorted(rule.types))}"
        if rule.max is not None and variable not in self.role(role) and len(self.role(role)) >= rule.max:
            return f"{rule.label} takes at most {rule.max}"
        return None

    # -- validation ------------------------------------------------------
    def validate(self) -> list[dict[str, str]]:
        """Issues as {"role", "severity", "message"}; no "error" means runnable."""
        if self.kind not in ROLE_RULES:
            return [{"role": "", "severity": "error", "message": f"Unknown analysis {self.kind!r}"}]
        issues: list[dict[str, str]] = []

        def add(role: str, message: str) -> None:
            issues.append({"role": role, "severity": "error", "message": message})

        rules = ROLE_RULES[self.kind]
        for role, names in self.roles.items():
            if names and role not in rules:
                add(role, f"{role} is not used by this analysis")
        seen: dict[str, str] = {}
        for role, rule in rules.items():
            names = self.role(role)
            if rule.max == 0:
                if names:
                    add(role, f"The qualified {self.kind.replace('_', ' ')} engine has no {role}; remove {', '.join(names)}")
                continue
            if len(names) < rule.min:
                add(role, f"{rule.label}: assign at least {rule.min}")
            if rule.max is not None and len(names) > rule.max:
                add(role, f"{rule.label}: at most {rule.max}")
            for name in names:
                vtype = self.variable_types.get(name)
                if vtype is None or vtype not in rule.types:
                    add(role, self.can_accept(role, name) or f"{name} not allowed")
                if name in seen:
                    add(role, f"{name} is already used as {seen[name]}")
                seen[name] = role
        issues.extend(self._validate_options())
        return issues

    def _validate_options(self) -> list[dict[str, str]]:
        o = self.effective_options()
        out: list[dict[str, str]] = []

        def err(msg: str) -> None:
            out.append({"role": "options", "severity": "error", "message": msg})

        if self.kind == "mixed_model":
            ref, con, alpha = o["reference_occasion"], o["contrast_occasion"], o["alpha"]
            if not isinstance(ref, int) or ref < 1:
                err("reference_occasion must be an integer >= 1")
            if not isinstance(con, int) or con < 2:
                err("contrast_occasion must be an integer >= 2")
            if isinstance(ref, int) and isinstance(con, int) and con <= ref:
                err("contrast_occasion must be after reference_occasion")
            if not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
                err("alpha must be between 0 and 1")
        if self.kind == "reliability":
            mt = o["max_trials"]
            if not isinstance(mt, int) or not 2 <= mt <= 8:
                err("max_trials must be an integer between 2 and 8")
            if not str(o["activity"]).strip():
                err("activity is required")
        if self.kind in ("mixed_model", "reliability"):
            if self.study_id is None:
                err("study unknown: set table (cmj_occasions or signal_trials) or options['study_id']")
            elif self.role("outcome") and self.outcome_metric_id() is None:
                err(f"{self.role('outcome')[0]} is not a registered metric of the real-data engine")
        if self.kind == "ttest" and o["level_1"] is not None and o["level_1"] == o["level_2"]:
            err("Choose two different levels to compare")
        return out

    # -- identity --------------------------------------------------------
    def canonical(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "snapshot_id": self.snapshot_id,
            "table": self.table,
            "roles": {r: self.role(r) for r in ROLES if self.role(r)},
            "options": self.effective_options(),
        }

    def spec_hash(self) -> str:
        blob = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # -- engine bridge ---------------------------------------------------
    def outcome_metric_id(self) -> str | None:
        from ... import realanalysis

        column = (self.role("outcome") or [""])[0]
        table = {"mixed_model": "cmj_occasions", "reliability": "signal_trials"}.get(self.kind)
        for mid, meta in realanalysis.METRICS.items():
            if meta["column"] == column and (table is None or meta["table"] == table):
                return mid
        return None

    def to_run_payload(self) -> dict[str, Any]:
        """Payload for DynamisAppService.execute_analysis_isolated(study_id, payload)."""
        if self.kind not in ("mixed_model", "reliability"):
            raise ValueError(f"{self.kind} has no engine payload (only the qualified analyses do)")
        errors = [i["message"] for i in self.validate() if i["severity"] == "error"]
        if errors:
            raise ValueError("; ".join(errors))
        o = self.effective_options()
        if self.kind == "mixed_model":
            method = "METH-REAL-TREND"
            params = {k: o[k] for k in ("reference_occasion", "contrast_occasion", "alpha")}
        else:
            method = "METH-REAL-RELIABILITY"
            params = {"activity": o["activity"], "max_trials": o["max_trials"]}
        return {
            "method_id": method,
            "outcome_metric_id": self.outcome_metric_id(),
            "excluded_subject_ids": list(o["excluded_subject_ids"]),
            "parameters": params,
        }

    # -- syntax ----------------------------------------------------------
    def to_python_syntax(self) -> str:
        st = method_status(self.kind)
        q = json.dumps
        o = self.effective_options()
        out, cov, fac = self.role("outcome"), self.role("covariates"), self.role("factors")
        subj = (self.role("subject") or ["<subject>"])[0]
        occ = (self.role("occasion") or ["<occasion>"])[0]
        y = (out or ["<outcome>"])[0]
        head = ""
        if st["status"] == NOT_QUALIFIED:
            head = "# NOT QUALIFIED: exploratory only; cannot be promoted to evidence.\n"
        elif st["status"] == DESCRIPTIVE:
            head = "# DESCRIPTIVE: no inference; not promoted as a modeled claim.\n"
        k = self.kind
        if k == "descriptives":
            by = f"data.groupby({q(fac[0])})" if fac else "data"
            return head + f"{by}[[{', '.join(q(v) for v in out)}]].describe()"
        if k == "frequencies":
            return head + "\n".join(f"data[{q(v)}].value_counts(dropna=False)" for v in fac)
        if k == "athlete_change":
            first = "wide.columns[0]" if o["reference_occasion"] is None else repr(o["reference_occasion"])
            last = "wide.columns[-1]" if o["contrast_occasion"] is None else repr(o["contrast_occasion"])
            return (
                head
                + f"wide = data.pivot(index={q(subj)}, columns={q(occ)}, values={q(y)})\n"
                + f"change = wide[{last}] - wide[{first}]  # missing stays NaN"
            )
        if k in ("mixed_model", "reliability"):
            if any(i["severity"] == "error" for i in self.validate()):
                return "# complete the role assignment to generate the call"
            payload = json.dumps(self.to_run_payload(), indent=4)
            if k == "mixed_model":
                note = (
                    f"# {st['method_id']} v{st['version']} ({st['record']}): ML, random intercept + occasion slope\n"
                    f"# {y} ~ occasion_c + (1 + occasion_c | {subj})\n"
                )
            else:
                note = (
                    f"# {st['method_id']} v{st['version']} ({st['record']}): ICC(3,1), "
                    "first k trials per subject in acquisition order\n"
                )
            return (
                note
                + "from dynamis_science.desktop.services import DynamisAppService\n"
                + f"DynamisAppService().execute_analysis_isolated({q(self.study_id)}, {payload})"
            )
        if k == "ttest":
            return (
                head
                + f"wide = data.pivot(index={q(subj)}, columns={q(occ)}, values={q(y)})\n"
                + f"stats.ttest_rel(wide[{o['level_2']!r}], wide[{o['level_1']!r}], nan_policy=\"omit\")"
            )
        if k == "anova":
            return head + f"AnovaRM(data, depvar={q(y)}, subject={q(subj)}, within=[{q(occ)}]).fit()"
        if k == "regression":
            terms = " + ".join(
                f"C({v})" if self.variable_types.get(v) in (CATEGORICAL, ORDINAL) else v for v in cov
            )
            return head + f"smf.ols({q(f'{y} ~ {terms}')}, data=data).fit()"
        raise ValueError(k)
