"""Performance OS domain service.

This module composes the daily, weekly and seasonal sports-science workspaces
from the immutable synthetic snapshot ``DS-SYNTH-001``.  It never invents an
injury, availability, measurement or prediction: the snapshot has no injury or
exposure table, so those surfaces are explicit empty states.

Operational state that the coach creates (plan targets, session logs, review
notes, test assessments and performance reports) is persisted separately from
the snapshot, carries its own source label and never mutates the admitted
measurement tables.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
from pydantic import BaseModel, Field

from .analysis import _reliability
from .data_root import paths
from .generate import ARTIFACT_DIR, PARQUET_DIR, SNAPSHOT_ID

CURRENT_WEEK = 16
BASELINE_WEEKS = (1, 2, 3, 4)
ROLLING_WEEKS = 4
PLAN_SCHEMA = "dynamis-performance.plan@1.0.0"
REPORT_SCHEMA = "dynamis-performance.report@1.0.0"
ASSESSMENT_SCHEMA = "dynamis-performance.test-assessment@1.0.0"


class PerformanceInputError(ValueError):
    """Raised when an operational command is missing a required input."""

CLUB = {
    "id": "NORTHSIDE-FC",
    "name": "Northside FC",
    "squad": "U21",
    "level": "U21 performance squad",
    "season": "2026/27",
    "timezone": "local",
    "athletes": 28,
}

THRESHOLDS = [
    {
        "id": "readiness_low",
        "label": "Readiness low",
        "metric": "readiness",
        "operator": "below",
        "value": 5.5,
        "unit": "0–10",
        "severity": "action",
        "owner": "Head of Performance",
        "set_at": "2026-11-05",
        "source": "Performance OS threshold registry v1",
        "note": "Single-day wellness report; review, do not diagnose.",
    },
    {
        "id": "load_ratio_high",
        "label": "Load ratio high",
        "metric": "load_ratio",
        "operator": "above",
        "value": 1.30,
        "unit": "AU",
        "severity": "attention",
        "owner": "Head of Performance",
        "set_at": "2026-11-05",
        "source": "Performance OS threshold registry v1",
        "note": "Descriptive 4-week load ratio; not an injury predictor.",
    },
    {
        "id": "cmj_drop",
        "label": "CMJ below baseline",
        "metric": "cmj_delta_pct",
        "operator": "below",
        "value": -2.5,
        "unit": "%",
        "severity": "attention",
        "owner": "Sports Scientist",
        "set_at": "2026-11-05",
        "source": "Performance OS threshold registry v1",
        "note": "Change from the athlete's own weeks 1–4 baseline; check typical error.",
    },
    {
        "id": "soreness_high",
        "label": "Soreness high",
        "metric": "soreness",
        "operator": "above",
        "value": 7.0,
        "unit": "0–10",
        "severity": "attention",
        "owner": "Head of Performance",
        "set_at": "2026-11-05",
        "source": "Performance OS threshold registry v1",
        "note": "Wellness item only; no clinical interpretation.",
    },
]

UNITS = [
    {"quantity": "Jump height", "canonical_unit": "cm", "symbol": "cm", "dimension": "length", "precision": 2, "example": 42.34},
    {"quantity": "Distance", "canonical_unit": "m", "symbol": "m", "dimension": "length", "precision": 0, "example": 216},
    {"quantity": "Sprint time", "canonical_unit": "s", "symbol": "s", "dimension": "time", "precision": 2, "example": 3.42},
    {"quantity": "Phase duration", "canonical_unit": "s", "symbol": "s", "dimension": "time", "precision": 3, "example": 0.222},
    {"quantity": "Force", "canonical_unit": "N", "symbol": "N", "dimension": "force", "precision": 0, "example": 1568},
    {"quantity": "Relative force", "canonical_unit": "N·kg⁻¹", "symbol": "N·kg⁻¹", "dimension": "force/mass", "precision": 1, "example": 32.4},
    {"quantity": "Impulse", "canonical_unit": "N·s·kg⁻¹", "symbol": "N·s·kg⁻¹", "dimension": "impulse/mass", "precision": 3, "example": 1.63},
    {"quantity": "Power", "canonical_unit": "W·kg⁻¹", "symbol": "W·kg⁻¹", "dimension": "power/mass", "precision": 1, "example": 52.1},
    {"quantity": "Velocity", "canonical_unit": "m·s⁻¹", "symbol": "m·s⁻¹", "dimension": "velocity", "precision": 2, "example": 6.3},
    {"quantity": "Acceleration", "canonical_unit": "m·s⁻²", "symbol": "m·s⁻²", "dimension": "acceleration", "precision": 2, "example": 3.2},
    {"quantity": "External load", "canonical_unit": "AU", "symbol": "AU", "dimension": "arbitrary", "precision": 1, "example": 378.2},
    {"quantity": "Session RPE", "canonical_unit": "RPE", "symbol": "RPE", "dimension": "scale 0–10", "precision": 1, "example": 7.0},
    {"quantity": "sRPE load", "canonical_unit": "AU", "symbol": "AU", "dimension": "arbitrary", "precision": 0, "example": 420},
    {"quantity": "Wellness / readiness", "canonical_unit": "0–10", "symbol": "0–10", "dimension": "scale 0–10", "precision": 1, "example": 7.1},
    {"quantity": "Sleep", "canonical_unit": "h", "symbol": "h", "dimension": "time", "precision": 1, "example": 7.14},
    {"quantity": "Body mass", "canonical_unit": "kg", "symbol": "kg", "dimension": "mass", "precision": 2, "example": 79.15},
    {"quantity": "Body weight", "canonical_unit": "N", "symbol": "N", "dimension": "force", "precision": 0, "example": 776},
    {"quantity": "Asymmetry / LSI", "canonical_unit": "%", "symbol": "%", "dimension": "ratio", "precision": 1, "example": 94.2},
    {"quantity": "ICC", "canonical_unit": "ICC", "symbol": "ICC", "dimension": "unitless", "precision": 2, "example": 0.95},
    {"quantity": "CV", "canonical_unit": "%", "symbol": "%", "dimension": "ratio", "precision": 2, "example": 4.21},
    {"quantity": "Typical error", "canonical_unit": "metric unit", "symbol": "TE", "dimension": "metric", "precision": 2, "example": 49.7},
    {"quantity": "Effect size", "canonical_unit": "SD", "symbol": "SD", "dimension": "standardised", "precision": 2, "example": 0.36},
    {"quantity": "Injury incidence", "canonical_unit": "per 1000 h", "symbol": "per 1000 h", "dimension": "rate", "precision": 1, "example": None},
    {"quantity": "Availability", "canonical_unit": "%", "symbol": "%", "dimension": "ratio", "precision": 1, "example": None},
]


# ---------------------------------------------------------------------------
# Snapshot access
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _tables() -> dict[str, pl.DataFrame]:
    return {
        "subjects": pl.read_parquet(PARQUET_DIR / "subjects.parquet"),
        "wellness": pl.read_parquet(PARQUET_DIR / "wellness.parquet"),
        "load": pl.read_parquet(PARQUET_DIR / "training_load.parquet"),
        "cmj": pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet"),
        "match_tracking": pl.read_parquet(PARQUET_DIR / "match_tracking.parquet"),
        "match_events": pl.read_parquet(PARQUET_DIR / "match_events.parquet"),
    }


@lru_cache(maxsize=1)
def _snapshot() -> dict[str, Any]:
    return json.loads((ARTIFACT_DIR / "dataset_snapshot.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _study_document() -> dict[str, Any]:
    return json.loads((ARTIFACT_DIR / "study.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _evidence_document() -> list[dict[str, Any]]:
    return json.loads((ARTIFACT_DIR / "evidence.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _report_document() -> dict[str, Any]:
    return json.loads((ARTIFACT_DIR / "report.json").read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _mean(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return sum(clean) / len(clean) if clean else None


def _sd(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if len(clean) < 2:
        return None
    return float(np.std(clean, ddof=1))


def _safe(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, float) and not math.isfinite(value):
        return fallback
    return value


def _normalise_unit(unit: str | None) -> str:
    """Repair legacy mojibake units in stored evidence artefacts for display."""
    if not unit:
        return ""
    if "N" in unit and "s" in unit and "kg" in unit:
        return "N·s·kg⁻¹"
    return unit.replace("\ufffd", "·")


# ---------------------------------------------------------------------------
# Operational store (plan, logs, notes, assessments, reports)
# ---------------------------------------------------------------------------


def _store_dir() -> Path:
    return paths()["performance"]


def _read_store(name: str, default: Any) -> Any:
    path = _store_dir() / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write_store(name: str, payload: Any) -> None:
    path = _store_dir() / name
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def _hash_payload(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Derived snapshot facts
# ---------------------------------------------------------------------------


def _weekly_rows() -> list[dict[str, Any]]:
    load = _tables()["load"]
    wellness = _tables()["wellness"]
    cmj = _tables()["cmj"].filter(pl.col("quality_state") == "VALID")

    load_week = load.group_by("week").agg(
        pl.col("training_impulse_au").mean().alias("training_impulse_au"),
        pl.col("external_load_au").mean().alias("external_load_au"),
        pl.col("hsr_distance_m").mean().alias("hsr_distance_m"),
        pl.col("session_rpe").mean().alias("session_rpe"),
        pl.col("match_minutes").mean().alias("match_minutes"),
        pl.col("duration_min").mean().alias("duration_min"),
        pl.col("session_count").mean().alias("session_count"),
        pl.col("phase").mode().first().alias("phase"),
    )
    well_week = wellness.group_by("week").agg(
        pl.col("readiness_0_10").mean().alias("readiness"),
        pl.col("sleep_hours").mean().alias("sleep_hours"),
        pl.col("soreness_0_10").mean().alias("soreness"),
        pl.col("fatigue_0_10").mean().alias("fatigue"),
    )
    cmj_week = cmj.group_by("week").agg(
        pl.col("jump_height_cm").mean().alias("cmj_height_cm"),
        pl.col("peak_force_n").mean().alias("peak_force_n"),
        pl.col("concentric_impulse_n_s_kg").mean().alias("concentric_impulse_n_s_kg"),
        pl.col("rsi_mod").mean().alias("rsi_mod"),
        pl.len().alias("valid_trials"),
    )
    frame = (
        load_week.join(well_week, on="week", how="left")
        .join(cmj_week, on="week", how="left")
        .sort("week")
    )
    return [
        {
            "week": int(row["week"]),
            "phase": row["phase"] or "BUILD",
            "match_week": (row["phase"] or "").upper() == "MATCH",
            "training_impulse_au": _round(row["training_impulse_au"], 3),
            "external_load_au": _round(row["external_load_au"], 3),
            "hsr_distance_m": _round(row["hsr_distance_m"], 2),
            "session_rpe": _round(row["session_rpe"], 3),
            "match_minutes": _round(row["match_minutes"], 2),
            "duration_min": _round(row["duration_min"], 1),
            "session_count": _round(row["session_count"], 2),
            "readiness": _round(row["readiness"], 3),
            "sleep_hours": _round(row["sleep_hours"], 3),
            "soreness": _round(row["soreness"], 3),
            "fatigue": _round(row["fatigue"], 3),
            "cmj_height_cm": _round(row["cmj_height_cm"], 3),
            "peak_force_n": _round(row["peak_force_n"], 2),
            "concentric_impulse_n_s_kg": _round(row["concentric_impulse_n_s_kg"], 4),
            "rsi_mod": _round(row["rsi_mod"], 2),
            "valid_trials": int(row["valid_trials"] or 0),
        }
        for row in frame.to_dicts()
    ]


def _athlete_week_frame() -> pl.DataFrame:
    load = _tables()["load"].select(
        "subject_id",
        "week",
        "training_impulse_au",
        "external_load_au",
        "hsr_distance_m",
        "session_rpe",
        "match_minutes",
        "duration_min",
        "session_count",
        "phase",
    )
    wellness = _tables()["wellness"].select(
        "subject_id",
        "week",
        "readiness_0_10",
        "sleep_hours",
        "soreness_0_10",
        "fatigue_0_10",
    )
    cmj = _tables()["cmj"].filter(pl.col("quality_state") == "VALID")
    cmj_week = cmj.group_by(["subject_id", "week"]).agg(
        pl.col("jump_height_cm").mean().alias("cmj_height_cm"),
        pl.col("peak_force_n").mean().alias("peak_force_n"),
        pl.col("concentric_impulse_n_s_kg").mean().alias("concentric_impulse_n_s_kg"),
        pl.col("rsi_mod").mean().alias("rsi_mod"),
        pl.len().alias("cmj_valid_trials"),
    )
    trials = _tables()["cmj"].group_by(["subject_id", "week"]).agg(
        pl.len().alias("cmj_trials"),
        (pl.col("quality_state") == "EXCLUDED").sum().alias("cmj_excluded"),
    )
    return (
        load.join(wellness, on=["subject_id", "week"], how="full", coalesce=True)
        .join(cmj_week, on=["subject_id", "week"], how="left")
        .join(trials, on=["subject_id", "week"], how="left")
        .sort(["subject_id", "week"])
    )


def _athlete_rows(subject_id: str) -> list[dict[str, Any]]:
    frame = _athlete_week_frame().filter(pl.col("subject_id") == subject_id).sort("week")
    rows = frame.to_dicts()
    baseline = [
        row.get("cmj_height_cm")
        for row in rows
        if row["week"] in BASELINE_WEEKS and row.get("cmj_height_cm") is not None
    ]
    baseline_mean = _mean(baseline)
    load_values = [row.get("training_impulse_au") for row in rows]
    output: list[dict[str, Any]] = []
    for row in rows:
        week = int(row["week"])
        current = row.get("cmj_height_cm")
        prior = [
            value
            for index in range(max(0, week - ROLLING_WEEKS - 1), max(0, week - 1))
            if load_values[index] is not None
            for value in [load_values[index]]
        ]
        rolling_load = _mean(prior)
        load_ratio = (
            float(row["training_impulse_au"]) / rolling_load
            if rolling_load and row.get("training_impulse_au") is not None
            else None
        )
        output.append(
            {
                "week": week,
                "phase": row.get("phase") or "BUILD",
                "readiness": _round(row.get("readiness_0_10"), 3),
                "sleep_hours": _round(row.get("sleep_hours"), 3),
                "soreness": _round(row.get("soreness_0_10"), 3),
                "fatigue": _round(row.get("fatigue_0_10"), 3),
                "training_impulse_au": _round(row.get("training_impulse_au"), 3),
                "external_load_au": _round(row.get("external_load_au"), 3),
                "hsr_distance_m": _round(row.get("hsr_distance_m"), 3),
                "session_rpe": _round(row.get("session_rpe"), 3),
                "match_minutes": _round(row.get("match_minutes"), 2),
                "duration_min": _round(row.get("duration_min"), 1),
                "session_count": _round(row.get("session_count"), 2),
                "load_ratio": _round(load_ratio, 4),
                "cmj_height_cm": _round(current, 3),
                "baseline_cmj_height_cm": _round(baseline_mean, 3),
                "cmj_delta_pct": _round(
                    ((float(current) / baseline_mean) - 1) * 100
                    if current is not None and baseline_mean
                    else None,
                    3,
                ),
                "peak_force_n": _round(row.get("peak_force_n"), 2),
                "concentric_impulse_n_s_kg": _round(row.get("concentric_impulse_n_s_kg"), 4),
                "rsi_mod": _round(row.get("rsi_mod"), 2),
                "cmj_trials": int(row.get("cmj_trials") or 0),
                "cmj_excluded": int(row.get("cmj_excluded") or 0),
                "cmj_missing": int(row.get("cmj_valid_trials") or 0) == 0,
            }
        )
    return output


def _data_quality() -> dict[str, Any]:
    cmj = _tables()["cmj"]
    total = int(cmj.height)
    valid = int(cmj.filter(pl.col("quality_state") == "VALID").height)
    excluded = int(cmj.filter(pl.col("quality_state") == "EXCLUDED").height)
    expected = 28 * 16 * 2
    missing = max(0, expected - total)
    return {
        "valid_trials": valid,
        "excluded_trials": excluded,
        "present_trials": total,
        "expected_slots": expected,
        "missing_slots": missing,
        "completeness_pct": _round(valid / expected * 100, 2),
        "quality_state": "WARNING" if excluded or missing else "VALID",
        "source": "DS-SYNTH-001 / cmj_trials.parquet",
        "note": (
            "883 valid and 1 excluded trial; 12 expected trial slots are missing. "
            "Missing and excluded slots are not zero-filled."
        ),
    }


def _athlete_base_rows() -> dict[str, dict[str, Any]]:
    subjects = _tables()["subjects"].to_dicts()
    weekly = _weekly_rows()
    latest = weekly[-1]
    wellness = _tables()["wellness"].filter(pl.col("week") == CURRENT_WEEK).to_dicts()
    load = _tables()["load"].filter(pl.col("week") == CURRENT_WEEK).to_dicts()
    cmj = _tables()["cmj"].filter(
        (pl.col("week") == CURRENT_WEEK) & (pl.col("quality_state") == "VALID")
    )
    cmj_week = cmj.group_by("subject_id").agg(pl.col("jump_height_cm").mean().alias("current"))
    baseline = _tables()["cmj"].filter(
        (pl.col("week").is_in(list(BASELINE_WEEKS))) & (pl.col("quality_state") == "VALID")
    )
    baseline_week = baseline.group_by("subject_id").agg(
        pl.col("jump_height_cm").mean().alias("baseline")
    )
    current = {row["subject_id"]: row["current"] for row in cmj_week.to_dicts()}
    baseline_map = {row["subject_id"]: row["baseline"] for row in baseline_week.to_dicts()}
    wellness_map = {row["subject_id"]: row for row in wellness}
    load_map = {row["subject_id"]: row for row in load}

    previous_load = (
        _tables()["load"]
        .filter(pl.col("week").is_between(CURRENT_WEEK - ROLLING_WEEKS, CURRENT_WEEK - 1))
        .group_by("subject_id")
        .agg(pl.col("training_impulse_au").mean().alias("previous_load"))
    )
    previous_map = {row["subject_id"]: row["previous_load"] for row in previous_load.to_dicts()}

    rows: dict[str, dict[str, Any]] = {}
    for subject in subjects:
        subject_id = subject["subject_id"]
        well = wellness_map.get(subject_id, {})
        lo = load_map.get(subject_id, {})
        athlete_current = current.get(subject_id)
        athlete_baseline = baseline_map.get(subject_id)
        load_ratio = (
            float(lo["training_impulse_au"]) / previous_map[subject_id]
            if lo.get("training_impulse_au") is not None and previous_map.get(subject_id)
            else None
        )
        cmj_delta = (
            ((float(athlete_current) / athlete_baseline) - 1) * 100
            if athlete_current is not None and athlete_baseline
            else None
        )
        rows[subject_id] = {
            **subject,
            "readiness": _round(well.get("readiness_0_10"), 3),
            "sleep_hours": _round(well.get("sleep_hours"), 3),
            "soreness": _round(well.get("soreness_0_10"), 3),
            "fatigue": _round(well.get("fatigue_0_10"), 3),
            "training_impulse_au": _round(lo.get("training_impulse_au"), 3),
            "external_load_au": _round(lo.get("external_load_au"), 3),
            "hsr_distance_m": _round(lo.get("hsr_distance_m"), 3),
            "session_rpe": _round(lo.get("session_rpe"), 3),
            "match_minutes": _round(lo.get("match_minutes"), 2),
            "load_ratio": _round(load_ratio, 4),
            "cmj_height_cm": _round(athlete_current, 3),
            "baseline_cmj_height_cm": _round(athlete_baseline, 3),
            "cmj_delta_pct": _round(cmj_delta, 3),
            "availability": {
                "status": "ROSTER_ONLY",
                "label": "Available — roster only",
                "reason": "No injury or exposure table admitted.",
            },
        }
    return rows


def _flags(athlete: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if athlete["readiness"] is not None and athlete["readiness"] < 5.5:
        flags.append(
            {
                "rule": "readiness_low",
                "label": "Readiness",
                "severity": "action" if athlete["readiness"] < 5.0 else "attention",
                "value": athlete["readiness"],
                "unit": "0–10",
                "threshold": 5.5,
                "detail": f"readiness {athlete['readiness']:.1f}/10 · sleep {athlete['sleep_hours']:.1f} h",
                "priority": 0 if athlete["readiness"] < 5.0 else 2,
            }
        )
    if athlete["load_ratio"] is not None and athlete["load_ratio"] > 1.30:
        flags.append(
            {
                "rule": "load_ratio_high",
                "label": "Load spike",
                "severity": "action" if athlete["load_ratio"] > 1.45 else "attention",
                "value": athlete["load_ratio"],
                "unit": "AU",
                "threshold": 1.30,
                "detail": f"4-week ratio {athlete['load_ratio']:.2f} · RPE {athlete['session_rpe']:.2f}",
                "priority": 0 if athlete["load_ratio"] > 1.45 else 2,
            }
        )
    if athlete["cmj_delta_pct"] is not None and athlete["cmj_delta_pct"] < -2.5:
        flags.append(
            {
                "rule": "cmj_drop",
                "label": "CMJ drop",
                "severity": "action" if athlete["cmj_delta_pct"] < -5.0 else "attention",
                "value": athlete["cmj_delta_pct"],
                "unit": "%",
                "threshold": -2.5,
                "detail": f"{athlete['cmj_delta_pct']:+.1f}% vs weeks 1–4 baseline",
                "priority": 1 if athlete["cmj_delta_pct"] < -4.0 else 2,
            }
        )
    if athlete["soreness"] is not None and athlete["soreness"] > 7.0:
        flags.append(
            {
                "rule": "soreness_high",
                "label": "Soreness",
                "severity": "attention",
                "value": athlete["soreness"],
                "unit": "0–10",
                "threshold": 7.0,
                "detail": f"soreness {athlete['soreness']:.1f}/10 · readiness {athlete['readiness']:.1f}",
                "priority": 3,
            }
        )
    return flags


def _attention() -> tuple[list[dict[str, Any]], int]:
    base = _athlete_base_rows()
    ranked: list[dict[str, Any]] = []
    for athlete in base.values():
        flags = sorted(_flags(athlete), key=lambda flag: (flag["priority"], flag["rule"]))
        if not flags:
            continue
        top = flags[0]
        ranked.append(
            {
                "athlete_id": athlete["display_id"],
                "subject_id": athlete["subject_id"],
                "position": athlete["position"],
                "age": athlete["age"],
                "readiness": athlete["readiness"],
                "sleep_hours": athlete["sleep_hours"],
                "load_ratio": athlete["load_ratio"],
                "cmj_delta_pct": athlete["cmj_delta_pct"],
                "cmj_height_cm": athlete["cmj_height_cm"],
                "baseline_cmj_height_cm": athlete["baseline_cmj_height_cm"],
                "soreness": athlete["soreness"],
                "fatigue": athlete["fatigue"],
                "flag": top,
                "flags": flags,
                "rank": min(flag["priority"] for flag in flags),
            }
        )
    ranked.sort(
        key=lambda item: (
            item["rank"],
            -abs(item["flag"]["value"] or 0),
            item["athlete_id"],
        )
    )
    return ranked[:5], len(ranked)


# ---------------------------------------------------------------------------
# Plan store
# ---------------------------------------------------------------------------


def _week_mean(values: list[float], week: int) -> float | None:
    return _mean(
        [
            value
            for index, value in enumerate(values)
            if week - ROLLING_WEEKS <= index + 1 <= week - 1
        ]
    )


def _seed_plan() -> dict[str, Any]:
    weekly = _weekly_rows()
    actual = [row["training_impulse_au"] for row in weekly]
    reference = _week_mean(actual, CURRENT_WEEK) or actual[-1]
    next_reference = _week_mean(actual, CURRENT_WEEK + 1) or actual[-1]
    sessions = [
        {
            "id": "SES-W17-01",
            "day": "Monday",
            "type": "Recovery",
            "focus": "Low-intensity movement, mobility",
            "planned_load_au": round(next_reference * 0.18),
            "duration_min": 45,
            "group": "Squad",
        },
        {
            "id": "SES-W17-02",
            "day": "Tuesday",
            "type": "Strength",
            "focus": "Lower-body strength, jump potentiation",
            "planned_load_au": round(next_reference * 0.30),
            "duration_min": 75,
            "group": "Squad",
        },
        {
            "id": "SES-W17-03",
            "day": "Thursday",
            "type": "Field",
            "focus": "High-speed exposure, small-sided games",
            "planned_load_au": round(next_reference * 0.34),
            "duration_min": 80,
            "group": "Squad",
        },
        {
            "id": "SES-W17-04",
            "day": "Saturday",
            "type": "Match",
            "focus": "Match exposure",
            "planned_load_au": round(next_reference * 0.18),
            "duration_min": 90,
            "group": "Match squad",
        },
    ]
    return {
        "schema_version": PLAN_SCHEMA,
        "club": CLUB,
        "season": CLUB["season"],
        "current_week": CURRENT_WEEK,
        "status": "DRAFT",
        "version": 1,
        "source": "BASELINE_DERIVED_TEMPLATE",
        "source_label": "Baseline-derived planning template",
        "source_note": (
            "Session targets are a deterministic planning template derived from the "
            "athletes' rolling 4-week mean load. They are not measurements. Edit and "
            "publish to make them the coach's plan."
        ),
        "created_at": _now(),
        "updated_at": _now(),
        "published_at": None,
        "microcycles": [
            {
                "id": "MC-W16",
                "week": CURRENT_WEEK,
                "phase": "BUILD",
                "focus": "Build 4 · match exposure",
                "status": "REFERENCE",
                "reference_load_au": _round(reference, 1),
                "actual_load_au": _round(actual[-1], 1),
                "testing_window": "Weekly CMJ · W16 benchmark complete",
                "sessions": [],
            },
            {
                "id": "MC-W17",
                "week": CURRENT_WEEK + 1,
                "phase": "BUILD",
                "focus": "Build 4 · next microcycle",
                "status": "DRAFT",
                "reference_load_au": _round(next_reference, 1),
                "actual_load_au": None,
                "testing_window": "Weekly CMJ · Monday 08:00",
                "sessions": sessions,
            },
        ],
        "audit": [
            {
                "at": _now(),
                "action": "SEEDED",
                "actor": "system",
                "detail": "Deterministic baseline-derived template.",
            }
        ],
    }


def _plan() -> dict[str, Any]:
    stored = _read_store("plan.json", None)
    if stored is None:
        stored = _seed_plan()
        _write_store("plan.json", stored)
    return stored


def _periodization() -> list[dict[str, Any]]:
    weekly = _weekly_rows()
    blocks: list[dict[str, Any]] = []
    for start in (1, 5, 9, 13):
        rows = [row for row in weekly if start <= row["week"] <= start + 3]
        if not rows:
            continue
        blocks.append(
            {
                "id": f"BLOCK-{start // 4 + 1}",
                "label": f"Block {start // 4 + 1}",
                "phase": "BUILD" if any(row["phase"] == "BUILD" for row in rows) else "MATCH",
                "start_week": start,
                "end_week": start + 3,
                "weeks": [row["week"] for row in rows],
                "mean_load_au": _round(_mean([row["training_impulse_au"] for row in rows]), 1),
                "match_weeks": [row["week"] for row in rows if row["match_week"]],
                "testing_window": f"W{start + 3} benchmark",
                "status": "COMPLETED" if start + 3 <= CURRENT_WEEK else "PLANNED",
            }
        )
    return blocks


# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------


def _movement() -> dict[str, Any]:
    tracking = _tables()["match_tracking"]
    players = [player for player in sorted(tracking["player_id"].unique().to_list()) if player != "BALL"]
    rows: list[dict[str, Any]] = []
    for player in players:
        frame = tracking.filter(pl.col("player_id") == player).sort("time_s").to_dicts()
        steps: list[tuple[float, float]] = []
        resets = 0
        for previous, current in zip(frame, frame[1:]):
            step = math.hypot(current["x_m"] - previous["x_m"], current["y_m"] - previous["y_m"])
            speed = math.hypot(current["vx_m_s"], current["vy_m_s"])
            if step > 1.0:
                resets += 1
            steps.append((step, speed))
        distance = sum(step for step, _ in steps)
        hsr = sum(step for step, speed in steps if speed > 5.0)
        max_speed = max((math.hypot(row["vx_m_s"], row["vy_m_s"]) for row in frame), default=0)
        rows.append(
            {
                "player_id": player,
                "team": frame[0]["team"] if frame else None,
                "duration_s": _round(frame[-1]["time_s"] - frame[0]["time_s"], 1) if frame else None,
                "distance_m": _round(distance, 1),
                "hsr_m": _round(hsr, 1),
                "max_speed_m_s": _round(max_speed, 2),
                "position_resets": resets,
                "speed_zone_high_m": _round(sum(step for step, speed in steps if speed > 4.5), 1),
                "sample_rate_hz": _snapshot()["sample_rates"].get("match_tracking_hz"),
            }
        )
    rows.sort(key=lambda item: item["distance_m"] or 0, reverse=True)
    return {
        "match_id": "MATCH-SYNTH-001",
        "duration_s": 179.9,
        "sample_rate_hz": _snapshot()["sample_rates"].get("match_tracking_hz"),
        "window_label": "3-minute bounded tracking window",
        "scope": "SEGMENT_ONLY",
        "players": rows,
        "quality": {
            "status": "WARNING",
            "note": (
                "The synthetic segment contains position resets >1 m between 0.1 s samples. "
                "Distance is positional path length; HSR uses steps while speed >5.0 m·s⁻¹. "
                "This is not full-match distance and is not a GPS device validation."
            ),
            "position_resets_total": sum(row["position_resets"] for row in rows),
        },
        "source": "DS-SYNTH-001 / match_tracking.parquet",
    }


# ---------------------------------------------------------------------------
# Study/evidence linkage
# ---------------------------------------------------------------------------


def _study_summary() -> dict[str, Any]:
    document = _study_document()
    study = document["study"]
    evidence = [item for item in _evidence_document() if item["dataset_snapshot_id"] == SNAPSHOT_ID]
    return {
        "id": study["id"],
        "title": study["title"],
        "short_title": study["short_title"],
        "state": study["state"],
        "design": study["design"],
        "participants": study["participant_count"],
        "weeks": [study["start_week"], study["end_week"]],
        "snapshot_id": study["dataset_snapshot_id"],
        "evidence_count": len(evidence),
        "primary_evidence": [
            {
                "id": item["id"],
                "title": item["title"],
                "estimate": item["estimate"],
                "unit": _normalise_unit(item.get("unit")),
                "interval": item.get("interval"),
                "evidence_class": item.get("evidence_class"),
                "quality": item.get("quality"),
                "interpretation": item.get("interpretation"),
            }
            for item in evidence[:4]
        ],
        "limitations": next(
            (item.get("diagnostics", {}).get("limitations", []) for item in evidence if item["id"] == "EVID-0001"),
            [],
        ),
    }


def _checklist() -> list[dict[str, Any]]:
    load = _tables()["load"].filter(pl.col("week") == CURRENT_WEEK)
    wellness = _tables()["wellness"].filter(pl.col("week") == CURRENT_WEEK)
    cmj = _tables()["cmj"].filter(
        (pl.col("week") == CURRENT_WEEK) & (pl.col("quality_state") == "VALID")
    )
    report = _report_document()
    performance_reports = _read_store("reports.json", {"reports": []})["reports"]
    frozen = [item for item in performance_reports if item.get("status") == "FROZEN"]
    return [
        {
            "id": "wellness",
            "label": "Wellness received",
            "done": wellness.height == 28,
            "status": f"{wellness.height} / 28",
            "source": "wellness.parquet · week 16",
        },
        {
            "id": "loads",
            "label": "Session loads present",
            "done": load.height == 28,
            "status": f"{load.height} / 28",
            "source": "training_load.parquet · week 16",
        },
        {
            "id": "cmj",
            "label": "CMJ testing complete",
            "done": cmj["subject_id"].n_unique() == 28,
            "status": f"{cmj['subject_id'].n_unique()} / 28",
            "source": "cmj_trials.parquet · week 16",
        },
        {
            "id": "report",
            "label": "Weekly report shared",
            "done": bool(frozen),
            "status": f"{len(frozen)} FROZEN" if frozen else report.get("status", "NOT COMPOSED"),
            "source": "performance reports · scientific report stays separate" if frozen else "report.json · scientific report",
        },
    ]


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------


class SessionLog(BaseModel):
    date: str = Field(min_length=4, max_length=32)
    session_type: str = Field(min_length=1, max_length=64)
    duration_min: float = Field(gt=0, le=600)
    session_rpe: float = Field(ge=0, le=10)
    attendance: int = Field(ge=0, le=200)
    notes: str = Field(default="", max_length=1000)
    author_role: str = Field(default="Head of Performance", max_length=64)


class AthleteNote(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    author_role: str = Field(default="Head of Performance", max_length=64)


class PlanSession(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    day: str = Field(min_length=1, max_length=32)
    type: str = Field(min_length=1, max_length=64)
    focus: str = Field(default="", max_length=240)
    planned_load_au: float = Field(ge=0, le=5000)
    duration_min: float = Field(ge=0, le=600)
    group: str = Field(default="Squad", max_length=64)


class PlanUpdate(BaseModel):
    week: int = Field(ge=1, le=52)
    focus: str = Field(min_length=1, max_length=240)
    testing_window: str = Field(default="", max_length=240)
    sessions: list[PlanSession] = Field(min_length=0, max_length=20)
    publish: bool = False
    actor: str = Field(default="Head of Performance", max_length=64)


class ReportRequest(BaseModel):
    audience: Literal["athlete", "coach", "medical", "board"]
    athlete_id: str | None = None
    role: str = Field(default="Head of Performance", max_length=64)
    freeze: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def context() -> dict[str, Any]:
    snapshot = _snapshot()
    return {
        "club": CLUB,
        "season": {"label": CLUB["season"], "current_week": CURRENT_WEEK, "phase": "BUILD"},
        "snapshot": {
            "id": snapshot["id"],
            "label": snapshot["label"],
            "generated_at": snapshot["generated_at"],
            "seed": snapshot["seed"],
            "synthetic": True,
            "row_counts": snapshot["row_counts"],
            "sample_rates": snapshot["sample_rates"],
            "checksums": snapshot["checksums"],
            "provenance": snapshot["provenance"],
        },
        "availability": {
            "status": "ROSTER_ONLY",
            "available": 28,
            "total": 28,
            "injury_table": False,
            "message": "No injury or exposure table admitted. Availability is roster status only.",
        },
        "thresholds": THRESHOLDS,
        "units": UNITS,
        "as_of": snapshot["generated_at"],
    }


def today() -> dict[str, Any]:
    weekly = _weekly_rows()
    current = weekly[-1]
    base = _athlete_base_rows()
    attention, triage_count = _attention()
    readiness_bands = {"l1": 0, "l2": 0, "l3": 0, "l4": 0}
    for athlete in base.values():
        value = athlete["readiness"]
        if value is None:
            continue
        if value < 5.5:
            readiness_bands["l1"] += 1
        elif value < 6.5:
            readiness_bands["l2"] += 1
        elif value < 7.5:
            readiness_bands["l3"] += 1
        else:
            readiness_bands["l4"] += 1
    quality = _data_quality()
    cmj_baseline = _mean(
        [
            value
            for athlete in base.values()
            for value in [athlete["baseline_cmj_height_cm"]]
            if value is not None
        ]
    )
    mean_readiness = _mean([athlete["readiness"] for athlete in base.values()])
    mean_ratio = _mean([athlete["load_ratio"] for athlete in base.values()])
    below_readiness = sum(
        1 for athlete in base.values() if athlete["readiness"] is not None and athlete["readiness"] < 5.5
    )
    above_ratio = sum(
        1 for athlete in base.values() if athlete["load_ratio"] is not None and athlete["load_ratio"] > 1.30
    )
    movement = _movement()
    player = next((row for row in movement["players"] if row["player_id"] == "PLAYER-14"), None)
    plan = _plan()
    next_microcycle = next(
        (item for item in plan["microcycles"] if item["week"] == CURRENT_WEEK + 1), None
    )
    force_trial = (
        _tables()["cmj"]
        .filter(
            (pl.col("week") == CURRENT_WEEK)
            & (pl.col("quality_state") == "VALID")
            & (pl.col("trial_number") == 1)
        )
        .sort("subject_id")
        .head(1)
        .to_dicts()
    )
    force = force_trial[0] if force_trial else None
    return {
        "force_trial_id": force["trial_id"] if force else None,
        "force_trial": {
            "trial_id": force["trial_id"],
            "display_id": force["display_id"],
            "jump_height_cm": _round(force["jump_height_cm"], 3),
            "peak_force_n": _round(force["peak_force_n"], 2),
            "concentric_impulse_n_s_kg": _round(force["concentric_impulse_n_s_kg"], 4),
            "rsi_mod": _round(force["rsi_mod"], 2),
            "body_mass_kg": _round(force["body_mass_kg"], 2),
            "body_weight_n": _round(force["body_weight_n"], 2),
        }
        if force
        else None,
        "as_of": _snapshot()["generated_at"],
        "week": CURRENT_WEEK,
        "phase": "BUILD",
        "pulse": {
            "roster_active": len(base),
            "roster_total": 28,
            "unavailable": 0,
            "availability_scope": "ROSTER_ONLY",
            "readiness": _round(mean_readiness, 3),
            "readiness_below": below_readiness,
            "readiness_n": len([a for a in base.values() if a["readiness"] is not None]),
            "load_ratio": _round(mean_ratio, 3),
            "load_ratio_above": above_ratio,
            "load_ratio_reference": "4-week baseline",
            "cmj_height_cm": current["cmj_height_cm"],
            "cmj_baseline_cm": _round(cmj_baseline, 3),
            "cmj_delta_pct": _round(
                ((current["cmj_height_cm"] / cmj_baseline) - 1) * 100
                if current["cmj_height_cm"] and cmj_baseline
                else None,
                2,
            ),
            "cmj_n": len([a for a in base.values() if a["cmj_height_cm"] is not None]),
            "quality": quality,
        },
        "readiness_bands": readiness_bands,
        "attention": attention,
        "triage_count": triage_count,
        "weekly": weekly,
        "checklist": _checklist(),
        "data_quality": quality,
        "movement": {
            "scope": movement["scope"],
            "window_label": movement["window_label"],
            "player": player,
            "quality": movement["quality"],
        },
        "study": _study_summary(),
        "plan": {
            "status": plan["status"],
            "version": plan["version"],
            "source_label": plan["source_label"],
            "next_microcycle": next_microcycle,
        },
        "session_logs": _read_store("sessions.json", {"sessions": []})["sessions"][-5:],
        "thresholds": THRESHOLDS,
    }


def athletes() -> list[dict[str, Any]]:
    base = _athlete_base_rows()
    output = []
    for athlete in base.values():
        flags = sorted(_flags(athlete), key=lambda flag: (flag["priority"], flag["rule"]))
        output.append(
            {
                **athlete,
                "flags": flags,
                "primary_flag": flags[0] if flags else None,
            }
        )
    output.sort(key=lambda item: item["display_id"])
    return output


def squad_weeks() -> dict[str, Any]:
    subjects = _tables()["subjects"].to_dicts()
    summaries = _athlete_base_rows()
    frame = _athlete_week_frame()
    output = []
    for subject in subjects:
        rows = frame.filter(pl.col("subject_id") == subject["subject_id"]).sort("week").to_dicts()
        # Use the same derived ratio calculation as Athlete 360.
        detail = _athlete_rows(subject["subject_id"])
        summary = summaries[subject["subject_id"]]
        output.append(
            {
                "subject_id": subject["subject_id"],
                "display_id": subject["display_id"],
                "position": subject["position"],
                "availability": summary["availability"],
                "weeks": [
                    {
                        "week": row["week"],
                        "readiness": row["readiness"],
                        "sleep_hours": row["sleep_hours"],
                        "soreness": row["soreness"],
                        "fatigue": row["fatigue"],
                        "load_ratio": row["load_ratio"],
                        "training_impulse_au": row["training_impulse_au"],
                        "cmj_height_cm": row["cmj_height_cm"],
                        "cmj_delta_pct": row["cmj_delta_pct"],
                        "phase": row["phase"],
                    }
                    for row in detail
                ],
            }
        )
    return {
        "weeks": [row["week"] for row in _weekly_rows()],
        "athletes": output,
        "as_of": _snapshot()["generated_at"],
    }


def athlete_detail(athlete_id: str) -> dict[str, Any]:
    subjects = _tables()["subjects"].to_dicts()
    subject = next(
        (item for item in subjects if item["display_id"] == athlete_id or item["subject_id"] == athlete_id),
        None,
    )
    if subject is None:
        raise researchstore.ResearchNotFound(f"Athlete {athlete_id} is not in the admitted roster")
    rows = _athlete_rows(subject["subject_id"])
    base = _athlete_base_rows()[subject["subject_id"]]
    current = rows[-1]
    flags = sorted(_flags(base), key=lambda flag: (flag["priority"], flag["rule"]))
    trial = (
        _tables()["cmj"]
        .filter(
            (pl.col("subject_id") == subject["subject_id"])
            & (pl.col("week") == CURRENT_WEEK)
            & (pl.col("quality_state") == "VALID")
        )
        .sort("trial_number")
        .head(1)
        .to_dicts()
    )
    force_trial = trial[0] if trial else None
    notes = [
        note
        for note in _read_store("notes.json", {"notes": []})["notes"]
        if note["athlete_id"] == subject["display_id"]
    ][-8:]
    individual_change = {
        "method": "Week 16 mean versus weeks 1–4 baseline",
        "baseline_mean": _round(current["baseline_cmj_height_cm"], 3),
        "current_mean": _round(current["cmj_height_cm"], 3),
        "change_cm": _round(
            current["cmj_height_cm"] - current["baseline_cmj_height_cm"]
            if current["cmj_height_cm"] is not None and current["baseline_cmj_height_cm"]
            else None,
            3,
        ),
        "percent_change": _round(current["cmj_delta_pct"], 3),
        "n_weeks": len(rows),
        "limitations": (
            "Descriptive individual change; a single week can be affected by measurement "
            "error and training state. No causal attribution."
        ),
    }
    return {
        "subject": subject,
        "athlete": {**base, "flags": flags, "primary_flag": flags[0] if flags else None},
        "weeks": rows,
        "current": current,
        "baseline_weeks": list(BASELINE_WEEKS),
        "individual_change": individual_change,
        "force_trial_id": force_trial["trial_id"] if force_trial else None,
        "force_trial": {
            "trial_id": force_trial["trial_id"],
            "jump_height_cm": _round(force_trial["jump_height_cm"], 3),
            "peak_force_n": _round(force_trial["peak_force_n"], 2),
            "concentric_impulse_n_s_kg": _round(force_trial["concentric_impulse_n_s_kg"], 4),
            "rsi_mod": _round(force_trial["rsi_mod"], 2),
            "quality_state": force_trial["quality_state"],
            "sample_rate_hz": 1000,
        }
        if force_trial
        else None,
        "availability": base["availability"],
        "notes": notes,
        "movement": next(
            (player for player in _movement()["players"] if player["player_id"] == "PLAYER-14"),
            None,
        ),
        "study": _study_summary(),
        "thresholds": THRESHOLDS,
        "as_of": _snapshot()["generated_at"],
    }


def load_overview() -> dict[str, Any]:
    weekly = _weekly_rows()
    plan = _plan()
    current = weekly[-1]
    microcycle = next(
        (item for item in plan["microcycles"] if item["week"] == CURRENT_WEEK), None
    )
    return {
        "weekly": weekly,
        "current": current,
        "reference": {
            "id": "rolling_4_week_reference",
            "label": "4-week reference",
            "value": _round(_week_mean([row["training_impulse_au"] for row in weekly], CURRENT_WEEK), 2),
            "method": "Mean of weeks 12–15 team mean training impulse",
            "note": "A reference derived from observed load, not a recorded coach plan.",
        },
        "plan": {
            "status": plan["status"],
            "version": plan["version"],
            "source_label": plan["source_label"],
            "source_note": plan["source_note"],
            "reference_week": microcycle,
            "next_microcycle": next(
                (item for item in plan["microcycles"] if item["week"] == CURRENT_WEEK + 1), None
            ),
        },
        "athletes": athletes(),
        "session_logs": _read_store("sessions.json", {"sessions": []})["sessions"][-20:],
        "thresholds": THRESHOLDS,
        "as_of": _snapshot()["generated_at"],
    }


def log_session(payload: SessionLog) -> dict[str, Any]:
    store = _read_store("sessions.json", {"sessions": []})
    record = {
        "id": f"SESLOG-{len(store['sessions']) + 1:04d}",
        "date": payload.date,
        "session_type": payload.session_type,
        "duration_min": payload.duration_min,
        "session_rpe": payload.session_rpe,
        "srpe_load_au": round(payload.duration_min * payload.session_rpe, 1),
        "attendance": payload.attendance,
        "notes": payload.notes,
        "author_role": payload.author_role,
        "source": "COACH_ENTERED",
        "source_label": "Coach-entered operational log",
        "entered_at": _now(),
    }
    store["sessions"].append(record)
    _write_store("sessions.json", store)
    return record


def add_athlete_note(athlete_id: str, payload: AthleteNote) -> dict[str, Any]:
    athlete = next(
        (
            item
            for item in _tables()["subjects"].to_dicts()
            if item["display_id"] == athlete_id or item["subject_id"] == athlete_id
        ),
        None,
    )
    if athlete is None:
        raise researchstore.ResearchNotFound("Athlete not found")
    store = _read_store("notes.json", {"notes": []})
    note = {
        "id": f"NOTE-{len(store['notes']) + 1:04d}",
        "athlete_id": athlete["display_id"],
        "text": payload.text,
        "author_role": payload.author_role,
        "created_at": _now(),
        "source": "COACH_ENTERED",
        "source_label": "Performance note (user-entered; not clinical)",
    }
    store["notes"].append(note)
    _write_store("notes.json", store)
    return note


def get_plan() -> dict[str, Any]:
    plan = _plan()
    weekly = _weekly_rows()
    return {
        **plan,
        "periodization": _periodization(),
        "actual_weekly": weekly,
        "squad": _athlete_base_rows(),
        "testing_calendar": [
            {
                "id": "TEST-CMJ-W16",
                "date_week": CURRENT_WEEK,
                "window": "Weekly CMJ benchmark",
                "protocol": "PROT-CMJ",
                "status": "COMPLETE",
                "completeness": f"{_tables()['cmj'].filter((pl.col('week') == CURRENT_WEEK) & (pl.col('quality_state') == 'VALID'))['subject_id'].n_unique()} / 28",
            },
            {
                "id": "TEST-CMJ-W17",
                "date_week": CURRENT_WEEK + 1,
                "window": "Weekly CMJ monitoring",
                "protocol": "PROT-CMJ",
                "status": "SCHEDULED",
                "completeness": "not measured",
            },
            {
                "id": "TEST-CMJ-W20",
                "date_week": CURRENT_WEEK + 4,
                "window": "Block 5 benchmark",
                "protocol": "PROT-CMJ",
                "status": "PLANNED",
                "completeness": "not measured",
            },
        ],
        "limitations": [
            "No coach-authored plan existed in the admitted snapshot; the W16 target is a derived reference, not a recorded plan.",
            "Attendance and session-RPE capture are P2 and have no admitted data contract.",
            "Injury and return-to-play planning require an admitted injury/exposure table.",
        ],
        "as_of": _snapshot()["generated_at"],
    }


def update_plan(payload: PlanUpdate) -> dict[str, Any]:
    plan = _plan()
    microcycle = next(
        (item for item in plan["microcycles"] if item["week"] == payload.week), None
    )
    if microcycle is None:
        microcycle = {
            "id": f"MC-W{payload.week}",
            "week": payload.week,
            "phase": "BUILD",
            "status": "DRAFT",
        }
        plan["microcycles"].append(microcycle)
    microcycle.update(
        {
            "focus": payload.focus,
            "testing_window": payload.testing_window,
            "sessions": [session.model_dump() for session in payload.sessions],
            "status": "PUBLISHED" if payload.publish else "DRAFT",
        }
    )
    plan["version"] = int(plan.get("version", 1)) + 1
    plan["updated_at"] = _now()
    if payload.publish:
        plan["status"] = "PUBLISHED"
        plan["published_at"] = _now()
        microcycle["published_at"] = plan["published_at"]
    plan.setdefault("audit", []).append(
        {
            "at": _now(),
            "action": "PUBLISHED" if payload.publish else "UPDATED",
            "actor": payload.actor,
            "detail": f"Week {payload.week}: {len(payload.sessions)} sessions.",
        }
    )
    _write_store("plan.json", plan)
    return get_plan()


def publish_plan() -> dict[str, Any]:
    plan = _plan()
    plan["status"] = "PUBLISHED"
    plan["published_at"] = _now()
    plan["version"] = int(plan.get("version", 1)) + 1
    plan["updated_at"] = plan["published_at"]
    for microcycle in plan["microcycles"]:
        if microcycle["week"] == CURRENT_WEEK + 1:
            microcycle["status"] = "PUBLISHED"
            microcycle["published_at"] = plan["published_at"]
    plan.setdefault("audit", []).append(
        {
            "at": plan["published_at"],
            "action": "PUBLISHED",
            "actor": "Head of Performance",
            "detail": f"Published week {CURRENT_WEEK + 1} microcycle.",
        }
    )
    _write_store("plan.json", plan)
    return get_plan()


def _trial_rows_for_week(week: int) -> list[dict[str, Any]]:
    return _tables()["cmj"].filter(pl.col("week") == week).to_dicts()


def tests() -> dict[str, Any]:
    week = CURRENT_WEEK
    trials = _trial_rows_for_week(week)
    valid = [trial for trial in trials if trial["quality_state"] == "VALID"]
    metrics = [
        ("jump_height_cm", "jump_height_cm", "Jump height", "cm"),
        ("concentric_impulse_n_s_kg", "concentric_impulse_n_s_kg", "Concentric impulse", "N·s·kg⁻¹"),
        ("peak_force_n", "peak_force_n", "Peak force", "N"),
        ("rsi_mod", "rsi_mod", "RSI modified", "cm·s⁻¹"),
    ]
    reliability = []
    for metric_id, column, label, unit in metrics:
        computed = _reliability(valid, column, baseline_weeks=(week,))
        reliability.append(
            {
                "metric_id": metric_id,
                "label": label,
                "unit": unit,
                "status": computed.get("status"),
                "icc": _round(computed.get("icc_3_1"), 4),
                "icc_ci_low": _round(computed.get("icc_3_1_ci_low"), 4),
                "icc_ci_high": _round(computed.get("icc_3_1_ci_high"), 4),
                "typical_error": _round(computed.get("typical_error"), 4),
                "typical_error_percent": _round(computed.get("typical_error_percent"), 3),
                "mean_cv_percent": _round(computed.get("mean_cv_percent"), 3),
                "smallest_worthwhile_change": _round(computed.get("smallest_worthwhile_change"), 4),
                "n_subjects": computed.get("n_subjects"),
                "trials_per_subject": computed.get("trials_per_subject"),
                "method": computed.get("method"),
                "interpretation": computed.get("interpretation"),
            }
        )
    trial_rows = [
        {
            "trial_id": trial["trial_id"],
            "subject_id": trial["subject_id"],
            "display_id": trial["display_id"],
            "week": trial["week"],
            "trial_number": trial["trial_number"],
            "quality_state": trial["quality_state"],
            "exclusion_reason": trial["exclusion_reason"],
            "jump_height_cm": _round(trial["jump_height_cm"], 3),
            "peak_force_n": _round(trial["peak_force_n"], 2),
            "concentric_impulse_n_s_kg": _round(trial["concentric_impulse_n_s_kg"], 4),
            "rsi_mod": _round(trial["rsi_mod"], 2),
            "body_mass_kg": _round(trial["body_mass_kg"], 2),
            "trace_available": bool(trial.get("trace_path")),
        }
        for trial in sorted(trials, key=lambda item: (item["display_id"], item["trial_number"]))
    ]
    assessments = _read_store("test_assessments.json", {"assessments": []})["assessments"]
    return {
        "window": {
            "week": week,
            "label": "Week 16 benchmark",
            "protocol": {
                "id": "PROT-CMJ",
                "name": "Bilateral countermovement jump",
                "frequency": "2 trials/week",
                "device": "Force plate (fixture metadata)",
                "device_record_admitted": False,
                "calibration_record_admitted": False,
                "sample_rate_hz": 1000,
                "source": "DS-SYNTH-001 manifest and metric registry",
            },
            "status": "COMPLETE",
            "athletes_complete": len({trial["subject_id"] for trial in valid}),
            "athletes_expected": 28,
            "trials": len(trials),
            "valid": len(valid),
            "excluded": len(trials) - len(valid),
        },
        "battery": [
            {
                "id": "CMJ-FP",
                "name": "Countermovement jump — force plate",
                "protocol": "PROT-CMJ",
                "unit": "cm · N · N·s·kg⁻¹",
                "status": "ADMITTED",
                "window": "Weekly",
                "quality": "VALID",
                "note": "Force–time traces at 1000 Hz.",
            },
            {
                "id": "SPRINT",
                "name": "Sprint timing",
                "protocol": None,
                "unit": "s",
                "status": "UNAVAILABLE",
                "window": "—",
                "quality": "NO_DATA",
                "note": "No sprint protocol or trial data admitted for this squad.",
            },
            {
                "id": "STRENGTH",
                "name": "Isometric / dynamic strength",
                "protocol": None,
                "unit": "N · N·kg⁻¹",
                "status": "UNAVAILABLE",
                "window": "—",
                "quality": "NO_DATA",
                "note": "No strength testing table admitted for this squad.",
            },
        ],
        "reliability": reliability,
        "trials": trial_rows,
        "assessments": assessments[-5:],
        "data_quality": _data_quality(),
        "limitations": [
            "Device serial, calibration date and plate coverage are not admitted; treat the device as a fixture.",
            "Week-16 reliability is within-session trial agreement, not device agreement.",
            "Peak-force trial variance is near zero in this synthetic fixture; an ICC of 1.00 is a fixture property, not evidence of device perfection.",
            "Missing trials are not zero-filled and excluded trials remain visible.",
        ],
        "as_of": _snapshot()["generated_at"],
    }


def run_reliability() -> dict[str, Any]:
    current = tests()
    payload = {
        "schema_version": ASSESSMENT_SCHEMA,
        "id": f"TEST-ASSESS-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "created_at": _now(),
        "window_week": CURRENT_WEEK,
        "snapshot_id": SNAPSHOT_ID,
        "input_checksum": _snapshot()["checksums"].get("cmj_trials.parquet"),
        "method": "ICC(3,1) within-session reliability on week-16 valid trials",
        "reliability": current["reliability"],
        "n_subjects": 28,
        "trials_per_subject": 2,
        "status": "COMPUTED",
        "provenance": {
            "source": "cmj_trials.parquet",
            "snapshot_id": SNAPSHOT_ID,
            "seed": _snapshot()["seed"],
            "algorithm": "dynamis_science.analysis._reliability",
        },
        "limitations": current["limitations"],
    }
    store = _read_store("test_assessments.json", {"assessments": []})
    store["assessments"].append(payload)
    _write_store("test_assessments.json", store)
    return payload


def movement() -> dict[str, Any]:
    return _movement()


def units() -> dict[str, Any]:
    return {
        "units": UNITS,
        "thresholds": THRESHOLDS,
        "status_atoms": {
            "availability": ["Available", "Modified", "Rehab", "Unavailable", "No data"],
            "data_quality": ["Valid", "Excluded", "Missing", "Estimated", "Modelled"],
            "evidence": ["Direct", "Derived", "Modelled", "Inferred"],
            "plan": ["Planned", "Actual", "Adjusted", "Not recorded"],
        },
        "design_rules": [
            "One question per module.",
            "No value without a unit.",
            "A chart always states its reference window.",
            "A sample always states n and missing count.",
            "Missing is a visible state; never zero.",
            "Planned and actual are separate.",
            "A threshold states its owner and date.",
            "Load ratio is descriptive, not an injury prediction.",
            "Observational data never gets causal language.",
            "Every exception has a next action and owner.",
        ],
    }


def research_link() -> dict[str, Any]:
    return {
        "study": _study_summary(),
        "evidence": [
            {
                **item,
                "unit": _normalise_unit(item.get("unit")),
            }
            for item in _evidence_document()
            if item["dataset_snapshot_id"] == SNAPSHOT_ID
        ],
        "report": {
            "id": _report_document().get("id"),
            "title": _report_document().get("title"),
            "status": _report_document().get("status"),
            "study_id": _report_document().get("study_id"),
        },
        "synthetic": True,
        "as_of": _snapshot()["generated_at"],
    }


# ---------------------------------------------------------------------------
# Performance reports
# ---------------------------------------------------------------------------


def _metric(label: str, value: Any, unit: str, detail: str) -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit, "detail": detail}


def _report_content(audience: str, athlete_id: str | None, role: str) -> dict[str, Any]:
    dashboard = today()
    base = _athlete_base_rows()
    study = _study_summary()
    evidence = [
        {
            **item,
            "unit": _normalise_unit(item.get("unit")),
        }
        for item in _evidence_document()
        if item["dataset_snapshot_id"] == SNAPSHOT_ID
    ]
    coach_sections = [
        {
            "id": "status",
            "title": "Squad status",
            "body": [
                f"{dashboard['pulse']['roster_active']} athletes on the roster. Availability is roster status only because no injury or exposure table is admitted.",
                f"Mean readiness is {dashboard['pulse']['readiness']:.1f}/10 (n={dashboard['pulse']['readiness_n']}); {dashboard['pulse']['readiness_below']} athlete(s) below 5.5.",
                f"Mean 4-week load ratio is {dashboard['pulse']['load_ratio']:.2f} AU; {dashboard['pulse']['load_ratio_above']} athlete(s) above 1.30.",
            ],
            "metrics": [
                _metric("Roster active", dashboard["pulse"]["roster_active"], "athletes", "Roster only"),
                _metric("Readiness", round(dashboard["pulse"]["readiness"], 1), "0–10", f"n={dashboard['pulse']['readiness_n']}"),
                _metric("Load ratio", round(dashboard["pulse"]["load_ratio"], 2), "AU", "4-week baseline"),
                _metric("CMJ", round(dashboard["pulse"]["cmj_height_cm"], 2), "cm", f"{dashboard['pulse']['cmj_delta_pct']:+.1f}% vs baseline"),
            ],
        },
        {
            "id": "attention",
            "title": "Athletes to review",
            "body": [
                f"{dashboard['triage_count']} athletes meet at least one review threshold; the five highest-priority cases are listed below.",
                "A flag is a prompt for human review, not a diagnosis or an injury prediction.",
            ],
            "table": [
                {
                    "athlete": item["athlete_id"],
                    "position": item["position"],
                    "flag": item["flag"]["label"],
                    "detail": item["flag"]["detail"],
                    "action": "Review",
                }
                for item in dashboard["attention"]
            ],
        },
        {
            "id": "load",
            "title": "Training load",
            "body": [
                f"Week {dashboard['week']} team mean training impulse was {dashboard['weekly'][-1]['training_impulse_au']:.1f} AU.",
                "The 4-week reference is derived from observed load and is not a recorded coach plan. Load ratio is descriptive context, not an injury predictor.",
            ],
            "metrics": [
                _metric("Week 16 load", round(dashboard["weekly"][-1]["training_impulse_au"], 1), "AU", "team mean"),
                _metric("External load", round(dashboard["weekly"][-1]["external_load_au"], 1), "AU", "team mean"),
                _metric("HSR distance", round(dashboard["weekly"][-1]["hsr_distance_m"], 1), "m", "team mean"),
                _metric("Match minutes", round(dashboard["weekly"][-1]["match_minutes"], 1), "min", "team mean"),
            ],
        },
        {
            "id": "testing",
            "title": "Testing quality",
            "body": [
                f"{dashboard['data_quality']['valid_trials']} valid CMJ trials, {dashboard['data_quality']['excluded_trials']} excluded and {dashboard['data_quality']['missing_slots']} missing slots.",
                "Force–time data are retained at 1000 Hz. Device and calibration records are not admitted.",
            ],
        },
        {
            "id": "evidence",
            "title": "Research evidence",
            "body": [
                f"Linked study: {study['title']} ({study['participants']} athletes, weeks {study['weeks'][0]}–{study['weeks'][1]}).",
                *[
                    f"{item['title']}: {item['estimate']:.3f} {item['unit']}"
                    + (f" (95% CI {item['interval']['low']:.3f} to {item['interval']['high']:.3f})" if item.get("interval") else "")
                    for item in evidence[:2]
                ],
                "Synthetic-data demonstration. No causal or clinical claim.",
            ],
            "evidence_ids": [item["id"] for item in evidence[:2]],
        },
    ]
    if audience == "coach":
        sections = coach_sections
        title = "Squad performance report"
    elif audience == "athlete":
        subject = next(
            (item for item in base.values() if athlete_id in {item["display_id"], item["subject_id"]}),
            None,
        )
        if subject is None:
            raise PerformanceInputError("An athlete_id is required for an athlete report")
        detail = athlete_detail(subject["display_id"])
        sections = [
            {
                "id": "status",
                "title": "Your status",
                "body": [
                    f"Roster status: {detail['availability']['label']}. No injury or clinical data are held in this report.",
                    f"Readiness {detail['current']['readiness']:.1f}/10, sleep {detail['current']['sleep_hours']:.1f} h, soreness {detail['current']['soreness']:.1f}/10.",
                ],
                "metrics": [
                    _metric("Readiness", round(detail["current"]["readiness"], 1), "0–10", "single-day wellness"),
                    _metric("Sleep", round(detail["current"]["sleep_hours"], 1), "h", "single-day wellness"),
                    _metric("Load ratio", round(detail["current"]["load_ratio"], 2), "AU", "4-week baseline"),
                ],
            },
            {
                "id": "cmj",
                "title": "Jump testing",
                "body": [
                    f"Your week-16 CMJ mean is {detail['current']['cmj_height_cm']:.2f} cm against a weeks 1–4 baseline of {detail['current']['baseline_cmj_height_cm']:.2f} cm ({detail['current']['cmj_delta_pct']:+.1f}%).",
                    detail["individual_change"]["limitations"],
                ],
                "metrics": [
                    _metric("CMJ", round(detail["current"]["cmj_height_cm"], 2), "cm", "week 16 mean"),
                    _metric("Change", round(detail["current"]["cmj_delta_pct"], 1), "%", "vs own baseline"),
                    _metric("Valid trials", detail["current"]["cmj_trials"], "trials", "week 16"),
                ],
            },
            {
                "id": "load",
                "title": "Training load",
                "body": [
                    f"Week 16 training impulse was {detail['current']['training_impulse_au']:.1f} AU over {detail['current']['session_count']:.0f} sessions.",
                    "Planned load and match attendance are separate records; no attendance contract is admitted.",
                ],
            },
            {
                "id": "plan",
                "title": "Next week",
                "body": [
                    "Your next testing window is the weekly CMJ on Monday. Review any flag with the performance team before changing training.",
                ],
            },
        ]
        title = f"Athlete report · {subject['display_id']}"
    elif audience == "medical":
        sections = [
            {
                "id": "availability",
                "title": "Availability",
                "body": [
                    "No injury, diagnosis, exposure or return-to-play table is admitted for this squad.",
                    "Availability below is roster status only. This report does not clear or restrict any athlete.",
                ],
                "metrics": [
                    _metric("Roster active", 28, "athletes", "roster only"),
                    _metric("Injury table", "Not admitted", "", "unavailable"),
                ],
            },
            {
                "id": "wellness",
                "title": "Wellness and readiness",
                "body": [
                    f"Mean readiness {dashboard['pulse']['readiness']:.1f}/10; {dashboard['pulse']['readiness_below']} athlete(s) below 5.5.",
                    "Wellness items are self-report and must not be interpreted as clinical findings.",
                ],
            },
            {
                "id": "testing",
                "title": "Testing quality",
                "body": [
                    f"{dashboard['data_quality']['valid_trials']} valid trials, {dashboard['data_quality']['excluded_trials']} excluded, {dashboard['data_quality']['missing_slots']} missing.",
                    "CMJ is a performance test. It is not a return-to-play criterion.",
                ],
            },
            {
                "id": "limitations",
                "title": "Limitations",
                "body": [
                    "No clinical notes, injury surveillance, exposure denominator or RTP pathway is available.",
                    "This report is an operational summary, not a medical record.",
                ],
            },
        ]
        title = "Medical availability summary"
    else:
        sections = [
            {
                "id": "board",
                "title": "Performance overview",
                "body": [
                    f"Roster active {dashboard['pulse']['roster_active']}/28. Mean readiness {dashboard['pulse']['readiness']:.1f}/10. Mean 4-week load ratio {dashboard['pulse']['load_ratio']:.2f} AU.",
                    f"CMJ team mean {dashboard['pulse']['cmj_height_cm']:.2f} cm ({dashboard['pulse']['cmj_delta_pct']:+.1f}% vs baseline). Data quality {dashboard['data_quality']['valid_trials']}/{dashboard['data_quality']['present_trials']} valid trials.",
                ],
                "metrics": [
                    _metric("Roster active", 28, "athletes", "roster only"),
                    _metric("Readiness", round(dashboard["pulse"]["readiness"], 1), "0–10", "squad mean"),
                    _metric("Load ratio", round(dashboard["pulse"]["load_ratio"], 2), "AU", "4-week baseline"),
                    _metric("CMJ", round(dashboard["pulse"]["cmj_height_cm"], 2), "cm", "team mean"),
                ],
            },
            {
                "id": "decisions",
                "title": "Decisions and risks",
                "body": [
                    f"{dashboard['triage_count']} athletes meet a review threshold; the five highest-priority cases are being reviewed.",
                    "The injury module is unavailable; availability and injury burden cannot be reported.",
                    "Load ratio is not used to predict injury.",
                ],
            },
            {
                "id": "evidence",
                "title": "Evidence",
                "body": [
                    f"{study['title']} provides {study['evidence_count']} promoted evidence item(s) on the synthetic snapshot.",
                    "Research remains separate from operational decision-making; no causal claim is made for individual athletes.",
                ],
                "evidence_ids": [item["id"] for item in evidence[:3]],
            },
            {
                "id": "limitations",
                "title": "Limitations",
                "body": [
                    "All performance data are synthetic and have no external validity.",
                    "No injury, exposure, attendance or clinical data are admitted.",
                ],
            },
        ]
        title = "Board performance brief"
    return {
        "audience": audience,
        "title": title,
        "role": role,
        "sections": sections,
        "study": study,
        "evidence_ids": [item["id"] for item in evidence[:3]],
        "evidence": evidence[:3],
        "limitations": [
            "Synthetic fixture DS-SYNTH-001: no real athletes, clubs or measurements.",
            "No injury, exposure, attendance or clinical data admitted.",
            "Availability is roster status only.",
            "Load ratio is descriptive and not an injury predictor.",
        ],
        "provenance": {
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_checksums": _snapshot()["checksums"],
            "source_tables": sorted(_snapshot()["row_counts"].keys()),
            "as_of": _snapshot()["generated_at"],
            "report_engine": "dynamis-performance.report@1.0.0",
        },
    }


def list_reports(audience: str | None = None) -> list[dict[str, Any]]:
    reports = _read_store("reports.json", {"reports": []})["reports"]
    if audience:
        reports = [report for report in reports if report["audience"] == audience]
    return sorted(reports, key=lambda item: item["version"], reverse=True)


def create_report(payload: ReportRequest) -> dict[str, Any]:
    content = _report_content(payload.audience, payload.athlete_id, payload.role)
    store = _read_store("reports.json", {"reports": []})
    existing = [report for report in store["reports"] if report["audience"] == payload.audience]
    version = max((report["version"] for report in existing), default=0) + 1
    report = {
        "id": f"RPT-PERF-{payload.audience.upper()}-{version:03d}",
        "schema_version": REPORT_SCHEMA,
        "version": version,
        "status": "FROZEN" if payload.freeze else "DRAFT",
        "created_at": _now(),
        "frozen_at": _now() if payload.freeze else None,
        "created_by": payload.role,
        "athlete_id": payload.athlete_id,
        **content,
    }
    report["content_hash"] = _hash_payload(
        {
            "audience": report["audience"],
            "title": report["title"],
            "sections": report["sections"],
            "provenance": report["provenance"],
        }
    )
    store["reports"].append(report)
    _write_store("reports.json", store)
    return report


def freeze_report(report_id: str) -> dict[str, Any]:
    store = _read_store("reports.json", {"reports": []})
    report = next((item for item in store["reports"] if item["id"] == report_id), None)
    if report is None:
        raise researchstore.ResearchNotFound("Report not found")
    if report["status"] == "FROZEN":
        return report
    report["status"] = "FROZEN"
    report["frozen_at"] = _now()
    report["content_hash"] = _hash_payload(
        {
            "audience": report["audience"],
            "title": report["title"],
            "sections": report["sections"],
            "provenance": report["provenance"],
        }
    )
    _write_store("reports.json", store)
    return report


def get_report(report_id: str) -> dict[str, Any]:
    store = _read_store("reports.json", {"reports": []})
    report = next((item for item in store["reports"] if item["id"] == report_id), None)
    if report is None:
        raise researchstore.ResearchNotFound("Report not found")
    return report


def export_report(report_id: str) -> str:
    return render_report(get_report(report_id))


def render_report(report: dict[str, Any]) -> str:
    escape = html.escape
    section_html = []
    for section in report["sections"]:
        body = "".join(f"<p>{escape(str(paragraph))}</p>" for paragraph in section.get("body", []))
        metrics = ""
        if section.get("metrics"):
            metrics = "<table class='metrics'>" + "".join(
                f"<tr><th>{escape(str(item['label']))}</th><td>{escape(str(item['value']))} "
                f"{escape(str(item['unit']))}</td><td>{escape(str(item['detail']))}</td></tr>"
                for item in section["metrics"]
            ) + "</table>"
        table = ""
        if section.get("table"):
            headers = list(section["table"][0].keys()) if section["table"] else []
            table = "<table><thead><tr>" + "".join(f"<th>{escape(h)}</th>" for h in headers) + "</tr></thead><tbody>"
            table += "".join(
                "<tr>" + "".join(f"<td>{escape(str(row.get(h, '')))}</td>" for h in headers) + "</tr>"
                for row in section["table"]
            )
            table += "</tbody></table>"
        section_html.append(
            f"<section><h2>{escape(section['title'])}</h2>{body}{metrics}{table}</section>"
        )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{escape(report['title'])}</title>
<style>
body{{font-family:'IBM Plex Sans',Segoe UI,sans-serif;max-width:860px;margin:40px auto;padding:0 32px;color:#17212b;font-size:13px;line-height:1.55}}
h1{{font-size:24px;margin:0 0 4px}} .meta{{font-family:monospace;font-size:10px;color:#5b6c78;border-bottom:1px solid #d5dde2;padding-bottom:12px;margin-bottom:22px}}
h2{{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:#5b6c78;margin:24px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:11px;margin:8px 0}} th,td{{text-align:left;border-bottom:1px solid #d5dde2;padding:4px 6px}} th{{color:#5b6c78}}
footer{{margin-top:30px;border-top:1px solid #d5dde2;padding-top:10px;font-family:monospace;font-size:9px;color:#6b7a85}}
@media print{{body{{margin:0;padding:24px}}}}
</style></head><body>
<h1>{escape(report['title'])}</h1>
<div class="meta">{escape(report['id'])} · version {report['version']} · {escape(report['status'])} · {escape(report['audience'])} · as of {escape(report['provenance']['as_of'])}</div>
{''.join(section_html)}
<section><h2>Limitations</h2>{''.join(f'<p>— {escape(item)}</p>' for item in report['limitations'])}</section>
<footer>{escape(str(report['provenance']))}<br>{escape(' · '.join(report['limitations']))}</footer>
</body></html>"""
    return document
