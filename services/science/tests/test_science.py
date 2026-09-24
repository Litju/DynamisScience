from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from dynamis_science.analysis import _group_longitudinal, _reliability, simulate_training_response
from dynamis_science.generate import ARTIFACT_DIR, PARQUET_DIR, generate_data


def test_generation_is_deterministic() -> None:
    first = generate_data()
    first_checksums = first["snapshot"]["checksums"]
    second = generate_data()
    assert second["snapshot"]["checksums"] == first_checksums
    assert second["counts"]["subjects"] == 28
    assert second["counts"]["trials"] == 884
    assert second["counts"]["missing_slots"] == 12


def test_generated_schemas_are_explicit() -> None:
    generate_data()
    subjects = pl.read_parquet(PARQUET_DIR / "subjects.parquet")
    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet")
    tracking = pl.read_parquet(PARQUET_DIR / "match_tracking.parquet")
    pose = pl.read_parquet(PARQUET_DIR / "match_pose.parquet")
    assert {"subject_id", "position", "intervention_arm", "body_mass_kg"}.issubset(subjects.columns)
    assert {"trial_id", "phase_boundaries", "concentric_impulse_n_s_kg", "quality_state"}.issubset(trials.columns)
    assert {"match_id", "frame", "player_id", "x_m", "y_m"}.issubset(tracking.columns)
    assert {"match_id", "frame", "athlete_id", "joint", "x_m", "y_m", "z_m", "confidence"}.issubset(pose.columns)
    assert subjects.height == 28
    assert trials.height == 884
    missing = json.loads((ARTIFACT_DIR / "missing_observations.json").read_text(encoding="utf-8"))
    assert len(missing) == 12


def test_force_trial_contains_phases_and_finite_metrics() -> None:
    generate_data()
    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet")
    traces = pl.read_parquet(PARQUET_DIR / "force_traces.parquet")
    trial = trials.filter(pl.col("trial_id") == "CMJ-001-10-1").to_dicts()[0]
    trace = traces.filter(pl.col("trial_id") == trial["trial_id"])
    assert trace.height > 2000
    assert set(trace["phase"].unique()) == {"QUIET_STANDING", "UNWEIGHTING", "BRAKING", "PROPULSION", "FLIGHT", "LANDING"}
    for field in ["jump_height_cm", "concentric_impulse_n_s_kg", "eccentric_braking_impulse_n_s_kg", "eccentric_braking_duration_s", "peak_force_n", "peak_power_w_kg"]:
        assert np.isfinite(float(trial[field]))
        assert float(trial[field]) > 0


def test_reliability_and_longitudinal_analysis_are_computed() -> None:
    generate_data()
    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet").to_dicts()
    reliability = _reliability(trials, "concentric_impulse_n_s_kg")
    longitudinal = _group_longitudinal(trials, "concentric_impulse_n_s_kg")
    assert reliability["n_subjects"] == 28
    assert 0 <= reliability["icc_3_1"] <= 1
    assert reliability["typical_error"] > 0
    contrast = longitudinal["contrasts"]["intervention_vs_comparison_week_10"]
    assert np.isfinite(contrast["estimate"])
    assert contrast["ci_low"] < contrast["estimate"] < contrast["ci_high"]
    assert longitudinal["n_observations"] > 0


def test_training_response_simulation_is_deterministic_and_explicit() -> None:
    first = simulate_training_response([300, 420, 500, 450, 350], {"tau_fitness_weeks": 4, "fatigue_tau_weeks": 1.8})
    second = simulate_training_response([300, 420, 500, 450, 350], {"tau_fitness_weeks": 4, "fatigue_tau_weeks": 1.8})
    assert first == second
    assert len(first["states"]) == 5
    assert all({"fitness", "fatigue", "performance_state"}.issubset(state) for state in first["states"])


def test_evidence_and_snapshot_metadata_are_serializable() -> None:
    result = generate_data()
    evidence = json.loads((ARTIFACT_DIR / "evidence.json").read_text(encoding="utf-8"))
    snapshot = result["snapshot"]
    assert snapshot["id"] == "DS-SYNTH-001"
    assert snapshot["seed"] == 20260924
    assert snapshot["checksums"]
    assert evidence[0]["analysis_run_id"] == "RUN-0001"
    assert evidence[0]["dataset_snapshot_id"] == snapshot["id"]
    assert "algorithm_version" in evidence[0]["provenance"]
