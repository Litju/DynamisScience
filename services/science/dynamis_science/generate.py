from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .analysis import (
    build_analysis_artifacts,
    build_reliability_evidence,
    build_training_response_model,
)

SEED = 20260924
GENERATOR_VERSION = "dynamis-synthetic@1.0.0"
SCHEMA_VERSION = "dynamis-science.schema@1.0.0"
SNAPSHOT_ID = "DS-SYNTH-001"
GENERATED_AT = "2026-09-24T00:00:00Z"
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
PARQUET_DIR = DATA_DIR / "parquet"
ARTIFACT_DIR = DATA_DIR / "artifacts"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
POSITIONS = ["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
SUBJECT_COUNT = 28
WEEK_COUNT = 16


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _write_parquet(name: str, rows: list[dict[str, Any]]) -> None:
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(PARQUET_DIR / f"{name}.parquet", compression="zstd")


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_arm(arm: str) -> str:
    return "INTERVENTION" if arm == "INTERVENTION" else "COMPARISON"


def _phase_for_time(t: float, boundaries: dict[str, float]) -> str:
    if t < boundaries["movement_onset"]:
        return "QUIET_STANDING"
    if t < boundaries["unweighting_end"]:
        return "UNWEIGHTING"
    if t < boundaries["braking_end"]:
        return "BRAKING"
    if t < boundaries["takeoff"]:
        return "PROPULSION"
    if t < boundaries["landing"]:
        return "FLIGHT"
    return "LANDING"


def _force_trace(
    rng: np.random.Generator,
    subject: dict[str, Any],
    week: int,
    trial_number: int,
    intervention_factor: float,
    load_factor: float,
    emit_trace: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, float]]:
    sample_rate = 1000.0
    duration = 2.35
    times = np.arange(0, duration, 1 / sample_rate)
    mass = float(subject["body_mass_kg"])
    body_weight = mass * 9.80665
    athlete_factor = float(subject["response_factor"])
    impulse_factor = float(subject["impulse_factor"])
    jump_factor = float(subject["jump_factor"])
    arm = subject["intervention_arm"]
    progress = 0.0
    if arm == "INTERVENTION" and 3 <= week <= 10:
        progress = (week - 2) / 8
    elif arm == "INTERVENTION" and week > 10:
        progress = 1.0
    strength_gain = 1 + 0.075 * progress * athlete_factor
    capacity = impulse_factor * strength_gain
    recovery_penalty = 0.045 if week == 12 else 0.0
    movement_onset = 0.42 + rng.normal(0, 0.012)
    unweighting_end = movement_onset + 0.13 + rng.normal(0, 0.006)
    braking_duration = (0.235 - 0.014 * progress * athlete_factor) + rng.normal(0, 0.007)
    braking_end = unweighting_end + max(0.15, braking_duration)
    takeoff = braking_end + 0.245 + rng.normal(0, 0.008)
    flight_time = 0.585 * jump_factor + 0.085 * (capacity - 1) + rng.normal(0, 0.008)
    flight_time = float(np.clip(flight_time, 0.48, 0.72))
    landing = takeoff + flight_time
    boundaries = {
        "movement_onset": movement_onset,
        "unweighting_end": unweighting_end,
        "braking_end": braking_end,
        "takeoff": takeoff,
        "landing": landing,
    }
    quiet = times < movement_onset
    unweighting = (times >= movement_onset) & (times < unweighting_end)
    braking = (times >= unweighting_end) & (times < braking_end)
    propulsion = (times >= braking_end) & (times < takeoff)
    flight = (times >= takeoff) & (times < landing)
    landing_phase = times >= landing
    net_norm = np.zeros_like(times, dtype=float)
    net_norm[quiet] = rng.normal(0, 0.0025, int(quiet.sum()))
    unweight_progress = (times[unweighting] - movement_onset) / max(0.01, unweighting_end - movement_onset)
    net_norm[unweighting] = -0.22 * impulse_factor * np.sin(np.pi * unweight_progress)
    braking_progress = (times[braking] - unweighting_end) / max(0.01, braking_end - unweighting_end)
    net_norm[braking] = capacity * (-0.66 * np.sin(np.pi * braking_progress) - 0.08 * braking_progress)
    propulsion_progress = (times[propulsion] - braking_end) / max(0.01, takeoff - braking_end)
    net_norm[propulsion] = capacity * (0.95 * np.sin(np.pi * propulsion_progress * 0.82) + 0.18 * propulsion_progress) - 0.05
    net_norm[flight] = rng.normal(0, 0.003, int(flight.sum()))
    landing_progress = (times[landing_phase] - landing) / max(0.01, duration - landing)
    net_norm[landing_phase] = 1.18 * np.exp(-((landing_progress / 0.22) ** 2)) - 0.16 * np.exp(-((landing_progress / 0.55) ** 2))
    phase = np.full(times.shape, "QUIET_STANDING", dtype=object)
    phase[unweighting] = "UNWEIGHTING"
    phase[braking] = "BRAKING"
    phase[propulsion] = "PROPULSION"
    phase[flight] = "FLIGHT"
    phase[landing_phase] = "LANDING"
    force = np.maximum(body_weight * (1 + net_norm), 0.05 * body_weight)
    if week == 12:
        force *= 1 - recovery_penalty
    velocity = np.cumsum((force - body_weight) / mass) / sample_rate
    displacement = np.cumsum(velocity) / sample_rate
    net_force = force - body_weight
    concentric_slice = propulsion
    braking_slice = (times >= movement_onset) & (times < braking_end)
    concentric_impulse = float(np.trapezoid(net_force[concentric_slice], times[concentric_slice]) / mass)
    braking_impulse = float(abs(np.trapezoid(net_force[braking_slice], times[braking_slice]) / mass))
    braking_duration = float(braking_end - unweighting_end)
    countermovement_depth = float(abs(min(displacement)) * 100)
    flight_duration = float(landing - takeoff)
    jump_height = float(9.80665 * flight_duration * flight_duration / 8 * 100)
    peak_force = float(np.max(force))
    propulsion_power = force[concentric_slice] * np.maximum(velocity[concentric_slice], 0)
    peak_power = float(np.max(propulsion_power) / mass) if propulsion_power.size else 0.0
    rsi_mod = float(jump_height / max(0.01, takeoff - braking_end))
    quality_state = "EXCLUDED" if (week == 6 and subject["display_id"] == "ATH-004" and trial_number == 2) else "VALID"
    if quality_state == "EXCLUDED":
        force = force * (1 + 0.12 * np.sin(np.linspace(0, 18, len(force))))
    trial_id = f"TMP-{subject['display_id']}-{week}-{trial_number}"
    rows = [] if not emit_trace else [
        {
            "trial_id": trial_id,
            "time_s": round(float(time), 4),
            "force_n": round(float(value), 5),
            "body_weight_n": round(body_weight, 5),
            "phase": str(phase[index]),
        }
        for index, (time, value) in enumerate(zip(times, force))
    ]
    metrics = {
        "jump_height_cm": jump_height,
        "concentric_impulse_n_s_kg": concentric_impulse,
        "eccentric_braking_impulse_n_s_kg": braking_impulse,
        "eccentric_braking_duration_s": braking_duration,
        "countermovement_depth_cm": countermovement_depth,
        "peak_force_n": peak_force,
        "peak_power_w_kg": peak_power,
        "rsi_mod": rsi_mod,
        "movement_onset_s": movement_onset,
        "takeoff_s": takeoff,
        "landing_s": landing,
        "body_weight_n": body_weight,
    }
    return rows, metrics, boundaries


def _subjects(rng: np.random.Generator) -> list[dict[str, Any]]:
    """Build the synthetic roster.

    Each athlete carries persistent traits so repeated trials are correlated
    within an athlete: ``impulse_factor`` (baseline force-production capacity),
    ``jump_factor`` (flight-time tendency) and ``response_factor``
    (heterogeneous response to the strength block).
    """
    rows = []
    for index in range(1, SUBJECT_COUNT + 1):
        arm = "INTERVENTION" if index % 2 == 1 else "COMPARISON"
        rows.append(
            {
                "subject_id": f"SUB-{index:03d}",
                "display_id": f"ATH-{index:03d}",
                "position": POSITIONS[(index - 1) % len(POSITIONS)],
                "age": int(np.clip(20 + rng.normal(0, 3.1), 18, 34)),
                "body_mass_kg": round(float(np.clip(77 + rng.normal(0, 6.5), 64, 98)), 2),
                "height_cm": round(float(np.clip(181 + rng.normal(0, 6.8), 168, 201)), 1),
                "training_age_years": int(np.clip(8 + rng.normal(0, 4.0), 2, 22)),
                "intervention_arm": _normalise_arm(arm),
                "impulse_factor": round(float(np.clip(rng.normal(1.0, 0.062), 0.80, 1.22)), 4),
                "jump_factor": round(float(np.clip(rng.normal(1.0, 0.045), 0.86, 1.16)), 4),
                "response_factor": round(float(np.clip(rng.normal(1.0, 0.16), 0.55, 1.45)), 4),
                "status": "ACTIVE",
            }
        )
    return rows


def _load_and_wellness(
    rng: np.random.Generator, subjects: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    load_rows: list[dict[str, Any]] = []
    wellness_rows: list[dict[str, Any]] = []
    for subject in subjects:
        base_load = 380 + rng.normal(0, 34)
        for week in range(1, WEEK_COUNT + 1):
            is_match_week = week in {4, 8, 12, 15}
            strength_week = subject["intervention_arm"] == "INTERVENTION" and 3 <= week <= 10
            spike = 1.34 if week == 11 else 1.0
            taper = 0.74 if week in {4, 8, 12, 15} else 1.0
            session_count = 2 if week in {4, 8, 12, 15} else 4
            external = max(180, base_load * spike * taper * rng.normal(1.0, 0.08))
            duration = int(np.clip(54 + external / 18 + rng.normal(0, 5), 35, 105))
            hsr = max(0, external / 16 + rng.normal(0, 18))
            accel = max(0, external / 24 + rng.normal(0, 12))
            rpe = float(np.clip(5.2 + external / 220 + rng.normal(0, 0.45), 1, 10))
            impulse = external * rpe / 10
            match_minutes = 90 if is_match_week and week != 4 else (68 if is_match_week else 0)
            load_rows.append(
                {
                    "load_id": f"LOAD-{subject['display_id']}-{week:02d}",
                    "subject_id": subject["subject_id"],
                    "display_id": subject["display_id"],
                    "week": week,
                    "session_count": session_count,
                    "duration_min": duration,
                    "external_load_au": round(external, 2),
                    "hsr_distance_m": round(hsr, 2),
                    "acceleration_load_au": round(accel, 2),
                    "session_rpe": round(rpe, 2),
                    "training_impulse_au": round(impulse, 2),
                    "match_minutes": match_minutes,
                    "phase": "MATCH" if is_match_week else ("STRENGTH_BLOCK" if strength_week else "BUILD"),
                    "load_factor": round(float(external / (base_load * taper)), 4),
                }
            )
            wellness_rows.append(
                {
                    "wellness_id": f"WELL-{subject['display_id']}-{week:02d}",
                    "subject_id": subject["subject_id"],
                    "display_id": subject["display_id"],
                    "week": week,
                    "sleep_hours": round(float(np.clip(7.4 + rng.normal(0, 0.8) - (0.5 if week == 12 else 0), 4.5, 9.5)), 2),
                    "soreness_0_10": round(float(np.clip(3.0 + (1.2 if week == 12 else 0) + rng.normal(0, 0.8), 1, 8)), 2),
                    "fatigue_0_10": round(float(np.clip(3.2 + (1.0 if week == 11 else 0) + rng.normal(0, 0.8), 1, 9)), 2),
                    "readiness_0_10": round(float(np.clip(7.1 - (1.4 if week == 12 else 0) - (0.4 if week == 11 else 0) + rng.normal(0, 0.7), 2, 10)), 2),
                }
            )
    return load_rows, wellness_rows


def _tracking_and_pose(rng: np.random.Generator) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    frames = 1800
    frame_rate = 10
    tracking: list[dict[str, Any]] = []
    pose: list[dict[str, Any]] = []
    events = [
        {"event_id": "EV-01", "event_type": "POSSESSION_CHANGE", "label": "Possession change", "start_s": 24, "end_s": 37, "athlete_id": "PLAYER-07"},
        {"event_id": "EV-02", "event_type": "PROGRESSIVE_RUN", "label": "Progressive run", "start_s": 51, "end_s": 66, "athlete_id": "PLAYER-11"},
        {"event_id": "EV-03", "event_type": "HIGH_SPEED_SPRINT", "label": "High-speed sprint", "start_s": 88, "end_s": 103, "athlete_id": "PLAYER-14"},
        {"event_id": "EV-04", "event_type": "SHOT_SEQUENCE", "label": "Shot sequence", "start_s": 132, "end_s": 149, "athlete_id": "PLAYER-09"},
    ]
    for player in range(1, 23):
        team = "HOME" if player <= 11 else "AWAY"
        base_x = 4 + (player - 1) * 4.2 if team == "HOME" else 96 - ((player - 12) * 4.2)
        base_z = 3 + (player % 5) * 8
        phase = rng.uniform(0, 2 * math.pi)
        for frame in range(frames):
            t = frame / frame_rate
            x = float(np.clip(base_x + 4.2 * math.sin(t / 13 + phase) + 1.2 * math.sin(t / 3.1 + phase), 1.0, 105.0))
            z = float(np.clip(base_z + 5.0 * math.cos(t / 11 + phase * 0.7) + 1.4 * math.sin(t / 2.6 + phase), 1.0, 68.0))
            if 88 <= t <= 103 and player == 14:
                x = float(np.clip(22 + (t - 88) * 1.1, 1, 105))
                z = float(np.clip(38 + 0.7 * math.sin(t), 1, 68))
            if 132 <= t <= 149 and player == 9:
                x = float(np.clip(90 - (t - 132) * 0.35, 1, 105))
                z = float(np.clip(42 + 0.5 * math.sin(t / 2), 1, 68))
            velocity = 4.8 + (1.5 if 88 <= t <= 103 and player == 14 else 0)
            tracking.append(
                {
                    "match_id": "MATCH-SYNTH-001",
                    "frame": frame,
                    "time_s": round(t, 2),
                    "player_id": f"PLAYER-{player:02d}",
                    "team": team,
                    "x_m": round(x, 4),
                    "y_m": round(z, 4),
                    "vx_m_s": round(float(velocity * math.cos(t / 10 + phase)), 4),
                    "vy_m_s": round(float(velocity * math.sin(t / 10 + phase)), 4),
                }
            )
            if player in {7, 9, 11, 14}:
                stride = math.sin(t * 7.5 + phase)
                joints = {
                    "hip": (x, z, 0.95 + 0.04 * stride),
                    "knee": (x + 0.12, z + 0.12 * stride, 0.55),
                    "ankle": (x + 0.22, z + 0.18 * stride, 0.12),
                    "left_hip": (x - 0.16, z - 0.08, 0.92),
                    "left_knee": (x - 0.12, z - 0.24 * stride, 0.54),
                    "left_ankle": (x - 0.18, z - 0.32 * stride, 0.11),
                    "right_hip": (x + 0.16, z + 0.08, 0.92),
                    "right_knee": (x + 0.12, z + 0.24 * stride, 0.54),
                    "right_ankle": (x + 0.18, z + 0.32 * stride, 0.11),
                    "shoulder": (x, z, 1.38),
                    "left_shoulder": (x - 0.22, z, 1.36),
                    "right_shoulder": (x + 0.22, z, 1.36),
                    "left_elbow": (x - 0.3, z - 0.18 * stride, 1.12),
                    "right_elbow": (x + 0.3, z + 0.18 * stride, 1.12),
                    "left_wrist": (x - 0.34, z - 0.32 * stride, 0.96),
                    "right_wrist": (x + 0.34, z + 0.32 * stride, 0.96),
                }
                for joint, (jx, jy, jz) in joints.items():
                    pose.append(
                        {
                            "match_id": "MATCH-SYNTH-001",
                            "frame": frame,
                            "time_s": round(t, 2),
                            "athlete_id": f"PLAYER-{player:02d}",
                            "joint": joint,
                            "x_m": round(float(jx), 4),
                            "y_m": round(float(jy), 4),
                            "z_m": round(float(jz), 4),
                            "confidence": round(float(np.clip(0.91 + rng.normal(0, 0.025), 0.75, 0.99)), 4),
                        }
                    )
    ball = []
    for frame in range(frames):
        t = frame / frame_rate
        x = 52 + 20 * math.sin(t / 14) + 3 * math.sin(t / 3)
        z = 34 + 14 * math.cos(t / 17) + 2 * math.sin(t / 2.8)
        ball.append(
            {
                "match_id": "MATCH-SYNTH-001",
                "frame": frame,
                "time_s": round(t, 2),
                "player_id": "BALL",
                "team": "BALL",
                "x_m": round(float(np.clip(x, 1, 105)), 4),
                "y_m": round(float(np.clip(z, 1, 68)), 4),
                "vx_m_s": round(float(1.4 * math.cos(t / 14)), 4),
                "vy_m_s": round(float(-1.1 * math.sin(t / 14)), 4),
            }
        )
    return tracking + ball, pose, events


def _build_trials(
    rng: np.random.Generator,
    subjects: list[dict[str, Any]],
    load_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    load_lookup = {(row["display_id"], row["week"]): row for row in load_rows}
    trial_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    missing_slots: list[dict[str, Any]] = []
    for subject in subjects:
        for week in range(1, WEEK_COUNT + 1):
            load = load_lookup[(subject["display_id"], week)]
            for trial_number in range(1, 3):
                if trial_number == 2 and week in {4, 8, 12, 15} and int(subject["display_id"].split("-")[-1]) % 9 == 0:
                    missing_slots.append({"subject_id": subject["subject_id"], "display_id": subject["display_id"], "week": week, "trial_number": trial_number, "reason": "Second CMJ trial not captured during match-congestion window"})
                    continue
                trace_selected = (trial_number == 1 and week in {1, 6, 10, 12, 16}) or (week == 1 and trial_number == 2) or (week == 6 and subject["display_id"] == "ATH-004" and trial_number == 2)
                trace, metrics, boundaries = _force_trace(
                    rng,
                    subject,
                    week,
                    trial_number,
                    1.0,
                    float(load["load_factor"]),
                    emit_trace=trace_selected,
                )
                trial_id = f"CMJ-{subject['display_id'].replace('ATH-', '')}-{week:02d}-{trial_number}"
                for row in trace:
                    row["trial_id"] = trial_id
                if trace_selected:
                    trace_rows.extend(trace)
                quality_state = "EXCLUDED" if (week == 6 and subject["display_id"] == "ATH-004" and trial_number == 2) else "VALID"
                exclusion_reason = "Force plate discontinuity flagged by deterministic QC rule" if quality_state == "EXCLUDED" else ""
                trial_rows.append(
                    {
                        "trial_id": trial_id,
                        "subject_id": subject["subject_id"],
                        "display_id": subject["display_id"],
                        "session_id": f"SESSION-{subject['display_id']}-{week:02d}",
                        "week": week,
                        "trial_number": trial_number,
                        "quality_state": quality_state,
                        "exclusion_reason": exclusion_reason,
                        "intervention_arm": subject["intervention_arm"],
                        "body_mass_kg": subject["body_mass_kg"],
                        **{key: round(value, 6) for key, value in metrics.items()},
                        "phase_boundaries": json.dumps(boundaries, sort_keys=True),
                        "trace_path": f"data/parquet/force_traces.parquet#trial_id={trial_id}",
                    }
                )
    return trial_rows, trace_rows, missing_slots


PRIMARY_ESTIMAND = "Intervention × Time: difference in change from week 1 to week 10, intervention minus comparison"
LONG_FORMULA = "{outcome} ~ week + group + week:group; athlete random intercept + random week slope (estimator ladder recorded on the run)"
LONG_PARAMETERS = {"reference_week": 1, "contrast_week": 10, "alpha": 0.05}


def _analysis_specs() -> list[dict[str, Any]]:
    return [
        {"id": "SPEC-LONG-001", "study_id": "STUDY-001", "name": "Group longitudinal effect on concentric impulse", "method_id": "METH-LONG", "method_version": "1.1.0", "cohort_id": "COHORT-001", "snapshot_id": SNAPSHOT_ID, "outcome_metric_id": "MET-CMJ-IMPULSE", "model_formula": LONG_FORMULA.format(outcome="concentric_impulse"), "parameters": LONG_PARAMETERS, "planned_contrasts": [PRIMARY_ESTIMAND], "primary_estimand": PRIMARY_ESTIMAND, "status": "FROZEN"},
        {"id": "SPEC-LONG-002", "study_id": "STUDY-001", "name": "Group longitudinal effect on eccentric braking duration", "method_id": "METH-LONG", "method_version": "1.1.0", "cohort_id": "COHORT-001", "snapshot_id": SNAPSHOT_ID, "outcome_metric_id": "MET-CMJ-BRAKING-DURATION", "model_formula": LONG_FORMULA.format(outcome="eccentric_braking_duration"), "parameters": LONG_PARAMETERS, "planned_contrasts": [PRIMARY_ESTIMAND], "primary_estimand": PRIMARY_ESTIMAND, "status": "FROZEN"},
        {"id": "SPEC-REL-001", "study_id": "STUDY-001", "name": "Baseline repeated-trial reliability", "method_id": "METH-REL", "method_version": "1.1.0", "cohort_id": "COHORT-001", "snapshot_id": SNAPSHOT_ID, "outcome_metric_id": "MET-CMJ-IMPULSE", "model_formula": "ICC(3,1) with balanced repeated baseline trials", "parameters": {"baseline_weeks": [1], "alpha": 0.05}, "planned_contrasts": ["Within-subject CV, typical error, ICC(3,1)"], "status": "FROZEN"},
        {"id": "SPEC-IND-001", "study_id": "STUDY-001", "name": "Individual longitudinal change", "method_id": "METH-IND", "method_version": "1.1.0", "cohort_id": "COHORT-001", "snapshot_id": SNAPSHOT_ID, "outcome_metric_id": "MET-CMJ-IMPULSE", "model_formula": "baseline mean, observed post-block change, standardized change, typical-error context", "parameters": {"baseline_weeks": [1, 2], "post_weeks": [9, 10]}, "planned_contrasts": ["Individual descriptive change"], "status": "FROZEN"},
    ]


def _metric_definitions(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usage: dict[str, int] = {}
    for spec in specs:
        metric_id = spec.get("outcome_metric_id")
        if metric_id:
            usage[metric_id] = usage.get(metric_id, 0) + 1
    return [
        {
            "id": "MET-CMJ-IMPULSE",
            "canonical_id": "cmj.concentric_impulse",
            "name": "CMJ / Concentric Impulse",
            "quantity": "impulse normalised to body mass",
            "unit": "N·s·kg⁻¹",
            "method": "trapezoidal integration of net vertical GRF over the propulsion phase, divided by body mass",
            "protocol_id": "PROT-CMJ",
            "algorithm": "cmj-metrics",
            "version": "1.0.0",
            "status": "ACTIVE",
            "dependencies": ["body_mass_kg", "force_trace", "phase_boundaries"],
            "known_limitations": ["Phase boundary estimates depend on force-plate signal quality.", "Integration window changes the absolute value."],
            "usage_count": usage.get("MET-CMJ-IMPULSE", 0),
        },
        {
            "id": "MET-CMJ-HEIGHT",
            "canonical_id": "cmj.jump_height.flight_time",
            "name": "CMJ / Jump Height from Flight Time",
            "quantity": "jump height",
            "unit": "cm",
            "method": "g·t²/8 from takeoff-to-landing flight time",
            "protocol_id": "PROT-CMJ",
            "algorithm": "cmj-metrics",
            "version": "1.0.0",
            "status": "ACTIVE",
            "dependencies": ["takeoff_s", "landing_s"],
            "known_limitations": ["Flight-time estimates assume symmetric takeoff and landing.", "Not interchangeable with impulse-momentum jump height."],
            "usage_count": usage.get("MET-CMJ-HEIGHT", 0),
        },
        {
            "id": "MET-CMJ-HEIGHT-IMPULSE",
            "canonical_id": "cmj.jump_height.impulse_momentum",
            "name": "CMJ / Jump Height from Impulse-Momentum",
            "quantity": "jump height",
            "unit": "cm",
            "method": "takeoff velocity squared over 2g, where takeoff velocity is the integrated net impulse divided by body mass",
            "protocol_id": "PROT-CMJ",
            "algorithm": "cmj-metrics",
            "version": "1.0.0",
            "status": "ACTIVE",
            "dependencies": ["concentric_impulse_n_s_kg", "body_mass_kg"],
            "known_limitations": ["Sensitive to the integration window.", "A distinct definition of jump height, not a re-expression of the flight-time metric."],
            "usage_count": usage.get("MET-CMJ-HEIGHT-IMPULSE", 0),
        },
        {
            "id": "MET-CMJ-BRAKING-DURATION",
            "canonical_id": "cmj.eccentric_braking_duration",
            "name": "CMJ / Eccentric Braking Duration",
            "quantity": "phase duration",
            "unit": "s",
            "method": "end of unweighting to end of eccentric braking phase",
            "protocol_id": "PROT-CMJ",
            "algorithm": "cmj-metrics",
            "version": "1.0.0",
            "status": "ACTIVE",
            "dependencies": ["unweighting_end_s", "braking_end_s"],
            "known_limitations": ["Event detection is sensitive to filtering and sampling choices."],
            "usage_count": usage.get("MET-CMJ-BRAKING-DURATION", 0),
        },
        {
            "id": "MET-CMJ-BRAKING-IMPULSE",
            "canonical_id": "cmj.eccentric_braking_impulse",
            "name": "CMJ / Eccentric Braking Impulse",
            "quantity": "impulse normalised to body mass",
            "unit": "N·s·kg⁻¹",
            "method": "absolute trapezoidal integration of net vertical GRF from movement onset to end of braking",
            "protocol_id": "PROT-CMJ",
            "algorithm": "cmj-metrics",
            "version": "1.0.0",
            "status": "ACTIVE",
            "dependencies": ["body_mass_kg", "force_trace", "phase_boundaries"],
            "known_limitations": ["Braking impulse and braking duration are distinct quantities and must not be substituted."],
            "usage_count": usage.get("MET-CMJ-BRAKING-IMPULSE", 0),
        },
        {
            "id": "MET-CMJ-POWER",
            "canonical_id": "cmj.peak_power",
            "name": "CMJ / Peak Power",
            "quantity": "peak mechanical power normalised to body mass",
            "unit": "W·kg⁻¹",
            "method": "maximum of force × centre-of-mass velocity during propulsion, divided by body mass",
            "protocol_id": "PROT-CMJ",
            "algorithm": "cmj-metrics",
            "version": "1.0.0",
            "status": "ACTIVE",
            "dependencies": ["body_mass_kg", "force_trace", "velocity_trace"],
            "known_limitations": ["Velocity is integrated from the force trace, so it accumulates any force offset error."],
            "usage_count": usage.get("MET-CMJ-POWER", 0),
        },
        {
            "id": "MET-CMJ-DEPTH",
            "canonical_id": "cmj.countermovement_depth",
            "name": "CMJ / Countermovement Depth",
            "quantity": "displacement",
            "unit": "cm",
            "method": "magnitude of the most negative integrated displacement before takeoff",
            "protocol_id": "PROT-CMJ",
            "algorithm": "cmj-metrics",
            "version": "1.0.0",
            "status": "ACTIVE",
            "dependencies": ["force_trace", "body_mass_kg"],
            "known_limitations": ["Double integration of force amplifies low-frequency drift."],
            "usage_count": usage.get("MET-CMJ-DEPTH", 0),
        },
        {
            "id": "MET-CMJ-RSI-MOD",
            "canonical_id": "cmj.rsi_mod",
            "name": "CMJ / Reactive Strength Index (modified)",
            "quantity": "jump height per unit propulsion time",
            "unit": "cm·s⁻¹",
            "method": "jump height divided by propulsion duration",
            "protocol_id": "PROT-CMJ",
            "algorithm": "cmj-metrics",
            "version": "1.0.0",
            "status": "ACTIVE",
            "dependencies": ["jump_height_cm", "braking_end_s", "takeoff_s"],
            "known_limitations": ["Inherits the assumptions of the flight-time jump height metric."],
            "usage_count": usage.get("MET-CMJ-RSI-MOD", 0),
        },
    ]


def _registry(specs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "metrics": _metric_definitions(specs),
        "protocols": [
            {"id": "PROT-CMJ", "name": "Bilateral countermovement jump", "status": "ACTIVE", "frequency": "2 trials per week", "method": "Repeated maximal trials with 1000 Hz force-plate capture on audit trials; first valid trial drives group inference."},
            {"id": "PROT-LOAD", "name": "Weekly external load exposure", "status": "ACTIVE", "frequency": "Weekly aggregation", "method": "Session duration, external load proxy, high-speed running, acceleration load and session RPE aggregated to a weekly training impulse."},
            {"id": "PROT-MATCH", "name": "Match segment tracking", "status": "ACTIVE", "frequency": "Match exposure", "method": "10 Hz bounded synthetic segment with synchronized tracking, ball and pose streams."},
        ],
        "algorithms": [
            {"id": "ALG-CMJ", "name": "CMJ phase-aware metric extraction", "version": "1.0.0", "status": "ACTIVE", "implementation": "services/science/dynamis_science/generate.py::_force_trace", "description": "Deterministic phase template with trapezoidal net-force integration."},
            {"id": "ALG-MIXEDLM", "name": "Group × time repeated-measures model", "version": "1.1.0", "status": "ACTIVE", "implementation": "services/science/dynamis_science/analysis.py::_group_longitudinal", "description": "statsmodels MixedLM with athlete random intercept and random week slope; documented estimator ladder down to athlete-clustered OLS."},
            {"id": "ALG-IND", "name": "Baseline/post descriptive change", "version": "1.1.0", "status": "ACTIVE", "implementation": "services/science/dynamis_science/analysis.py::_individual_change", "description": "Per-athlete baseline (weeks 1-2) and post-block (weeks 9-10) means with standardised change."},
            {"id": "ALG-ICC", "name": "Balanced two-way ICC(3,1)", "version": "1.1.0", "status": "ACTIVE", "implementation": "services/science/dynamis_science/analysis.py::_reliability", "description": "Within-subject CV, typical error (√MSE) and Shrout–Fleiss confidence limits."},
            {"id": "ALG-FITNESS-FATIGUE", "name": "Training response impulse model", "version": "0.2.0", "status": "PROTOTYPE", "implementation": "services/science/dynamis_science/analysis.py::_training_response", "description": "Grid-searched fitness–fatigue time constants with exposed residuals."},
        ],
        "methods": [
            {"id": "METH-LONG", "name": "Group × time longitudinal model", "version": "1.1.0", "status": "FROZEN", "algorithm": "ALG-MIXEDLM", "estimator": "statsmodels MixedLM, athlete random intercept + random week slope", "fallback": "MixedLM random intercept, then GEE exchangeable, then athlete-clustered OLS (recorded on the run)", "estimand": PRIMARY_ESTIMAND, "requirements": ["At least 2 arms with repeated weekly observations", "First valid CMJ trial per athlete-week", "Week centred on the reference week"], "outputs": ["difference-in-change contrast with SE and Wald 95% CI", "baseline balance", "model-implied cross-sectional difference", "residual diagnostics"], "known_limitations": ["Linear week term; non-linear responses appear as structured residuals.", "Wald intervals rely on a normal approximation."]},
            {"id": "METH-REL", "name": "Repeated-trial reliability", "version": "1.1.0", "status": "FROZEN", "algorithm": "ALG-ICC", "estimator": "ICC(3,1) / within-subject CV / typical error", "requirements": ["At least 3 athletes with 2 or more valid trials in the baseline week", "Balanced trials per athlete (trimmed to the minimum k)"], "outputs": ["ICC(3,1) with Shrout-Fleiss 95% CI", "typical error (square root of MSE)", "within-subject CV per athlete", "smallest worthwhile change"], "known_limitations": ["Two trials per athlete bound the precision of the ICC.", "Reliability is estimated for baseline conditions only."]},
            {"id": "METH-IND", "name": "Individual change context", "version": "1.1.0", "status": "FROZEN", "algorithm": "ALG-IND", "estimator": "baseline versus post-block descriptive change", "requirements": ["Valid trials in baseline weeks 1-2 and post-block weeks 9-10"], "outputs": ["baseline mean", "post mean", "raw and standardised change", "comparison with the typical error of a change"], "known_limitations": ["Descriptive only; not a causal individual response.", "Typical error of a change is derived from the cohort change SD."]},
        ],
        "models": [
            {"id": "MODEL-FITNESS-FATIGUE", "name": "Training response impulse model", "version": "0.2.0", "status": "PROTOTYPE", "kind": "Mechanistic", "description": "A bounded mechanistic demonstration fitted to weekly training-load and CMJ observations.", "inputs": ["weekly training impulse (AU)", "weekly mean first-trial concentric impulse (N·s·kg⁻¹)"], "known_limitations": ["Aggregate group-mean prototype; not an individual predictor.", "Grid-searched parameters without uncertainty."]},
            {"id": "MODEL-BAYES", "name": "Bayesian hierarchical models", "status": "UNAVAILABLE", "kind": "Bayesian", "description": "Roadmap category. No Bayesian executor is implemented in this MVP."},
            {"id": "MODEL-ML", "name": "Machine learning", "status": "UNAVAILABLE", "kind": "Machine Learning", "description": "Roadmap category. No machine-learning model is trained or served in this MVP."},
            {"id": "MODEL-PIML", "name": "Physics-informed ML", "status": "UNAVAILABLE", "kind": "Physics-Informed ML", "description": "Roadmap category. No physics-informed learning is implemented in this MVP."},
            {"id": "MODEL-DIFFBIO", "name": "Differentiable biomechanics", "status": "UNAVAILABLE", "kind": "Differentiable Biomechanics", "description": "Roadmap category. No differentiable biomechanical simulator is implemented in this MVP."},
        ],
    }


def _study_artifacts(specs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "study": {
            "id": "STUDY-001",
            "title": "CMJ Response to 8-Week Strength Intervention",
            "short_title": "CMJ Strength Intervention",
            "state": "ACTIVE",
            "research_question": "Does the strength intervention alter CMJ propulsion and braking strategy relative to comparison athletes?",
            "design": "Controlled longitudinal cohort with repeated pre/post CMJ measures.",
            "intervention": "Progressive strength block in weeks 3–10; comparison athletes continue usual care.",
            "primary_outcomes": ["cmj.concentric_impulse", "cmj.eccentric_braking_duration"],
            "secondary_outcomes": ["cmj.jump_height.flight_time", "cmj.peak_power", "cmj.countermovement_depth"],
            "dataset_snapshot_id": SNAPSHOT_ID,
            "participant_count": SUBJECT_COUNT,
            "start_week": 1,
            "end_week": 16,
            "protocol_ids": ["PROT-CMJ", "PROT-LOAD", "PROT-MATCH"],
            "analysis_spec_ids": [spec["id"] for spec in specs],
        },
        "question": {"id": "RQ-001", "study_id": "STUDY-001", "statement": "Does the strength intervention alter CMJ propulsion and braking strategy relative to comparison athletes?", "estimand": PRIMARY_ESTIMAND + ", estimated with a repeated-measures model of first valid weekly trials.", "population": "28 synthetic elite football athletes", "exposure": "Weeks 3–10 progressive strength block", "outcomes": ["cmj.concentric_impulse", "cmj.eccentric_braking_duration"], "time_horizon": "Baseline through follow-up week 16"},
        "hypotheses": [
            {"id": "HYP-001", "study_id": "STUDY-001", "question_id": "RQ-001", "statement": "Intervention athletes will show a greater increase in concentric impulse than comparison athletes.", "direction": "increase", "status": "PRIMARY", "rationale": "The intervention emphasises rate of force development and force expression."},
            {"id": "HYP-002", "study_id": "STUDY-001", "question_id": "RQ-001", "statement": "Intervention athletes will show a modest reduction in eccentric braking duration.", "direction": "decrease", "status": "PRIMARY", "rationale": "Improved braking strategy may accompany increased braking impulse."},
            {"id": "HYP-003", "study_id": "STUDY-001", "question_id": "RQ-001", "statement": "Jump height, peak power and countermovement depth will move in the same direction as concentric impulse, but with smaller standardised effects.", "direction": "increase", "status": "SECONDARY", "rationale": "Secondary outcomes are recorded to check that the primary result is not an isolated artefact of one extraction method."},
        ],
        "groups": {
            "intervention": {"label": "Intervention", "arm": "INTERVENTION", "block_weeks": [3, 10], "description": "Progressive strength block alongside usual football training."},
            "comparison": {"label": "Comparison", "arm": "COMPARISON", "block_weeks": [3, 10], "description": "Usual care; no additional strength block."},
        },
        "cohort": {"id": "COHORT-001", "study_id": "STUDY-001", "name": "Elite football longitudinal cohort", "description": "All synthetic athletes with a valid baseline CMJ session and at least one post-block observation.", "subject_ids": [f"SUB-{i:03d}" for i in range(1, 29)], "exclusion_criteria": ["No baseline CMJ session", "Force trace fails deterministic QC rule"], "snapshot_id": SNAPSHOT_ID, "status": "FROZEN"},
        "protocols": [
            {"id": "PROT-CMJ", "study_id": "STUDY-001", "name": "Bilateral countermovement jump", "description": "Two maximal CMJ trials per week with force-plate traces retained on audit weeks.", "frequency": "2 trials/week", "status": "ACTIVE", "duration_weeks": 16, "visit_labels": ["Baseline", "Intervention", "Post", "Follow-up"]},
            {"id": "PROT-LOAD", "study_id": "STUDY-001", "name": "Weekly external load exposure", "description": "Session duration, external load, high-speed running, acceleration load, RPE and match exposure.", "frequency": "Weekly aggregation", "status": "ACTIVE", "duration_weeks": 16, "visit_labels": ["Build", "Match", "Taper"]},
            {"id": "PROT-MATCH", "study_id": "STUDY-001", "name": "Match segment tracking", "description": "Bounded 10 Hz tracking and pose segment for synchronized field and joint-space inspection.", "frequency": "Match exposure", "status": "ACTIVE", "duration_weeks": 16, "visit_labels": ["Segment"]},
        ],
        "analysis_specs": specs,
        "plan": {"id": "PLAN-001", "status": "FROZEN", "frozen_before_inspection": True, "primary_outcomes": ["concentric impulse", "eccentric braking duration"], "secondary_outcomes": ["jump height (flight time)", "peak power", "countermovement depth"], "exclusion_criteria": ["No baseline CMJ session", "Force trace fails deterministic QC rule"], "planned_models": ["Group × time mixed model (SPEC-LONG-001, SPEC-LONG-002)", "ICC(3,1) reliability (SPEC-REL-001)", "Individual change context (SPEC-IND-001)"], "planned_contrasts": [PRIMARY_ESTIMAND], "primary_estimand": PRIMARY_ESTIMAND, "planned_reliability": "Baseline week-1 repeated trials: ICC(3,1), within-subject CV and typical error", "post_plan_rule": "Any analysis whose method, outcome, cohort, parameters or exclusions differ from a frozen spec is recorded as EXPLORATORY.", "immutability_rule": "Changing cohort, method, parameters, dataset or exclusions creates a new AnalysisSpec and a new AnalysisRun."},
    }


def _report() -> dict[str, Any]:
    return {
        "id": "REPORT-001",
        "title": "Strength Intervention — Interim Scientific Report",
        "study_id": "STUDY-001",
        "status": "DRAFT",
        "evidence_ids": ["EVID-0001", "EVID-0002", "EVID-0003"],
        "figure_ids": ["FIG-0001", "FIG-0002"],
        "sections": ["Study question and design", "Dataset and cohort", "Methods", "Intervention result", "Reliability context", "Interpretation", "Limitations", "Reproducibility and provenance"],
        "citations": [
            {"artifact_id": "EVID-0001", "section": "Intervention result", "added_at": GENERATED_AT},
            {"artifact_id": "FIG-0001", "section": "Intervention result", "added_at": GENERATED_AT},
            {"artifact_id": "EVID-0002", "section": "Reliability context", "added_at": GENERATED_AT},
            {"artifact_id": "FIG-0002", "section": "Reliability context", "added_at": GENERATED_AT},
            {"artifact_id": "EVID-0003", "section": "Reliability context", "added_at": GENERATED_AT},
        ],
        "provenance_note": "All displayed estimates and figures are computed from DS-SYNTH-001 using frozen analysis specifications.",
        "created_at": GENERATED_AT,
    }


def _investigation() -> dict[str, Any]:
    """The seeded primary investigation.

    Blocks reference typed domain objects by ID; the GUI renders them but is
    not the authority for any scientific value.
    """
    blocks = [
        {"id": "B-QUESTION", "type": "question", "title": "Research question", "state": {"question_id": "RQ-001", "plan_id": "PLAN-001"}},
        {"id": "B-DATASET", "type": "dataset", "title": "DS-SYNTH-001", "state": {"snapshot_id": SNAPSHOT_ID}},
        {"id": "B-COHORT", "type": "cohort", "title": "Study cohort", "state": {"cohort_id": "COHORT-001", "excluded_subject_ids": []}},
        {"id": "B-EXPLORE", "type": "explore", "title": "Concentric impulse longitudinal trajectory", "state": {"metric_id": "MET-CMJ-IMPULSE", "population": "ALL", "view": "LONGITUDINAL", "reference": "RAW", "context": ["LOAD", "MATCH"], "cohort_block_id": "B-COHORT"}},
        {"id": "B-ANALYSIS", "type": "analysis", "title": "Longitudinal intervention model", "state": {"spec_id": "SPEC-LONG-001", "method_id": "METH-LONG", "outcome_metric_id": "MET-CMJ-IMPULSE", "parameters": dict(LONG_PARAMETERS), "cohort_block_id": "B-COHORT", "run_id": "RUN-0001"}},
        {"id": "B-DIAGNOSTICS", "type": "diagnostics", "title": "Model diagnostics", "state": {"analysis_block_id": "B-ANALYSIS"}},
        {"id": "B-EVIDENCE", "type": "evidence", "title": "Intervention × Time effect", "state": {"analysis_block_id": "B-ANALYSIS", "evidence_id": "EVID-0001"}},
        {"id": "B-FIGURE", "type": "figure", "title": "Group longitudinal response", "state": {"evidence_block_id": "B-EVIDENCE", "figure_id": "FIG-0001"}},
        {"id": "B-INTERPRETATION", "type": "interpretation", "title": "Interpretation", "state": {"evidence_block_id": "B-EVIDENCE", "note": "The difference-in-change estimate is read against the baseline reliability (EVID-0002): an effect smaller than the smallest worthwhile change would not support a practically meaningful adaptation. The week-12 dip coincides with the week-11 load spike and is not part of the planned contrast."}},
        {"id": "B-REPORT", "type": "report_section", "title": "Report · Intervention result", "state": {"report_id": "REPORT-001", "section": "Intervention result"}},
    ]
    return {
        "id": "INV-001",
        "study_id": "STUDY-001",
        "title": "Primary Intervention Analysis",
        "status": "ACTIVE",
        "version": 1,
        "created_at": GENERATED_AT,
        "updated_at": GENERATED_AT,
        "blocks": [{**block, "collapsed": False} for block in blocks],
    }


def _write_snapshot_manifest() -> dict[str, Any]:
    files = sorted(PARQUET_DIR.glob("*.parquet"))
    checksums = {path.name: _checksum(path) for path in files}
    row_counts = {}
    for path in files:
        row_counts[path.stem] = pl.read_parquet(path).height
    pose_athletes = sorted(pl.read_parquet(PARQUET_DIR / "match_pose.parquet")["athlete_id"].unique().to_list())
    manifest = {
        "id": SNAPSHOT_ID,
        "label": "Synthetic football longitudinal snapshot",
        "seed": SEED,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "row_counts": row_counts,
        "checksums": checksums,
        "sample_rates": {"force_traces_hz": 1000, "match_tracking_hz": 10, "match_pose_hz": 10},
        "subjects": {"total": SUBJECT_COUNT, "weeks": WEEK_COUNT, "positions": POSITIONS},
        "pose_athletes": pose_athletes,
        "missing_observations": len(json.loads((ARTIFACT_DIR / "missing_observations.json").read_text(encoding="utf-8"))) if (ARTIFACT_DIR / "missing_observations.json").exists() else None,
        "provenance": {
            "source": "deterministic local generator",
            "code_application_version": GENERATOR_VERSION,
            "generator": "services/science/dynamis_science/generate.py",
            "simulated_entities": "No real athletes, clubs, matches, or measurements",
        },
    }
    _write_json(ARTIFACT_DIR / "dataset_snapshot.json", manifest)
    return manifest


def generate_data() -> dict[str, Any]:
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    subjects = _subjects(rng)
    load_rows, wellness_rows = _load_and_wellness(rng, subjects)
    trial_rows, trace_rows, missing_slots = _build_trials(rng, subjects, load_rows)
    tracking_rows, pose_rows, events = _tracking_and_pose(rng)
    _write_parquet("subjects", subjects)
    _write_parquet("training_load", load_rows)
    _write_parquet("wellness", wellness_rows)
    _write_parquet("cmj_trials", trial_rows)
    _write_parquet("force_traces", trace_rows)
    _write_parquet("match_tracking", tracking_rows)
    _write_parquet("match_pose", pose_rows)
    _write_parquet("match_events", events)
    specs = _analysis_specs()
    registry = _registry(specs)
    study = _study_artifacts(specs)
    _write_json(SYNTHETIC_DIR / "generator_manifest.json", {"seed": SEED, "generator_version": GENERATOR_VERSION, "schema_version": SCHEMA_VERSION, "files": ["subjects", "training_load", "wellness", "cmj_trials", "force_traces", "match_tracking", "match_pose", "match_events"]})
    _write_json(ARTIFACT_DIR / "registry.json", registry)
    _write_json(ARTIFACT_DIR / "study.json", study)
    _write_json(ARTIFACT_DIR / "report.json", _report())
    _write_json(ARTIFACT_DIR / "investigations.json", [_investigation()])
    _write_json(ARTIFACT_DIR / "missing_observations.json", missing_slots)
    snapshot = _write_snapshot_manifest()
    analysis = build_analysis_artifacts(trial_rows, load_rows, snapshot, study, registry)
    _write_json(ARTIFACT_DIR / "analysis_runs.json", analysis["runs"])
    _write_json(ARTIFACT_DIR / "evidence.json", analysis["evidence"])
    _write_json(ARTIFACT_DIR / "figures.json", analysis["figures"])
    _write_json(ARTIFACT_DIR / "model_spec.json", analysis["model_spec"])
    _write_json(ARTIFACT_DIR / "model_run.json", analysis["model_run"])
    _write_json(ARTIFACT_DIR / "overview_signal.json", analysis["overview_signal"])
    counts = {"subjects": len(subjects), "trials": len(trial_rows), "trace_rows": len(trace_rows), "tracking": len(tracking_rows), "pose": len(pose_rows), "events": len(events), "load": len(load_rows), "wellness": len(wellness_rows), "missing_slots": len(missing_slots)}
    return {"snapshot": snapshot, "counts": counts, "artifacts": analysis}


if __name__ == "__main__":
    result = generate_data()
    print(json.dumps({"snapshot": result["snapshot"]["id"], "counts": result["counts"]}, indent=2))
