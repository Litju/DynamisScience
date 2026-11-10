"""Scientific contract tests for the DynamisScience local service.

These tests protect the properties the product depends on: determinism, the
documented structure of the synthetic dataset, the correctness of the force and
statistical computations, and the integrity of the evidence/lineage chain.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from dynamis_science.analysis import (
    _group_longitudinal,
    _individual_change,
    _reliability,
    simulate_scenario,
    simulate_training_response,
    two_way_icc,
)
from dynamis_science.qualification import anova_icc_reference
from dynamis_science.generate import ARTIFACT_DIR, PARQUET_DIR, SNAPSHOT_ID, generate_data

WEEKS = range(1, 17)


@pytest.fixture(scope="module")
def dataset() -> dict:
    return generate_data()




def _trials() -> list[dict]:
    return pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet").to_dicts()


def _first_trial(rows: list[dict], arm: str, weeks: tuple[int, ...], metric: str) -> float:
    values = [
        row[metric]
        for row in rows
        if row["intervention_arm"] == arm
        and row["quality_state"] == "VALID"
        and row["trial_number"] == 1
        and row["week"] in weeks
    ]
    assert values, f"No valid {arm} observations in weeks {weeks}"
    return float(np.mean(values))


# --------------------------------------------------------------------------- #
# Synthetic generation
# --------------------------------------------------------------------------- #


def test_generation_is_byte_deterministic(dataset: dict) -> None:
    first = {name: digest for name, digest in dataset["snapshot"]["checksums"].items()}
    first_artifacts = {
        name: (ARTIFACT_DIR / name).read_text(encoding="utf-8")
        for name in ("analysis_runs.json", "evidence.json", "figures.json", "model_run.json", "study.json")
    }
    second = generate_data()
    assert second["snapshot"]["checksums"] == first
    for name, content in first_artifacts.items():
        assert (ARTIFACT_DIR / name).read_text(encoding="utf-8") == content, f"{name} is not deterministic"


def test_snapshot_manifest_is_complete(dataset: dict) -> None:
    manifest = dataset["snapshot"]
    assert manifest["id"] == SNAPSHOT_ID
    assert manifest["seed"] == 20260924
    assert manifest["generator_version"] and manifest["schema_version"]
    assert manifest["generated_at"]
    assert set(manifest["checksums"]) == {f"{name}.parquet" for name in manifest["row_counts"]}
    assert all(len(digest) == 64 for digest in manifest["checksums"].values())
    assert manifest["sample_rates"] == {"force_traces_hz": 1000, "match_tracking_hz": 10, "match_pose_hz": 10}


def test_dataset_shape_matches_the_study_contract(dataset: dict) -> None:
    subjects = pl.read_parquet(PARQUET_DIR / "subjects.parquet")
    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet")
    load = pl.read_parquet(PARQUET_DIR / "training_load.parquet")
    wellness = pl.read_parquet(PARQUET_DIR / "wellness.parquet")
    assert subjects.height == 28
    assert trials.height == 884
    assert load.height == 448 and wellness.height == 448
    assert set(subjects["position"].unique()) == {"GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"}
    assert set(subjects["intervention_arm"].unique()) == {"INTERVENTION", "COMPARISON"}
    assert sorted(trials["week"].unique()) == list(WEEKS)
    assert sorted(trials["trial_number"].unique()) == [1, 2]
    assert {"impulse_factor", "jump_factor", "response_factor"}.issubset(subjects.columns)


def test_realistic_missingness_and_flagged_trial(dataset: dict) -> None:
    missing = json.loads((ARTIFACT_DIR / "missing_observations.json").read_text(encoding="utf-8"))
    assert len(missing) == 12
    assert all(row["reason"] for row in missing)
    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet")
    flagged = trials.filter(pl.col("quality_state") == "EXCLUDED")
    assert flagged.height == 1
    assert flagged["exclusion_reason"][0]
    assert flagged["trial_id"][0] == "CMJ-004-06-2"


def test_known_intervention_structure_is_present(dataset: dict) -> None:
    """The generator's documented effect must actually be recoverable."""
    rows = _trials()
    baseline = (1, 2)
    post = (9, 10)

    intervention_delta = _first_trial(rows, "INTERVENTION", post, "concentric_impulse_n_s_kg") - _first_trial(
        rows, "INTERVENTION", baseline, "concentric_impulse_n_s_kg"
    )
    comparison_delta = _first_trial(rows, "COMPARISON", post, "concentric_impulse_n_s_kg") - _first_trial(
        rows, "COMPARISON", baseline, "concentric_impulse_n_s_kg"
    )
    assert intervention_delta > 0.05, "concentric impulse must improve gradually in the intervention arm"
    assert intervention_delta - comparison_delta > 0.05

    braking_delta = _first_trial(rows, "INTERVENTION", post, "eccentric_braking_duration_s") - _first_trial(
        rows, "INTERVENTION", baseline, "eccentric_braking_duration_s"
    )
    assert braking_delta < -0.002, "braking duration must show a modest reduction"
    assert braking_delta < _first_trial(rows, "COMPARISON", post, "eccentric_braking_duration_s") - _first_trial(
        rows, "COMPARISON", baseline, "eccentric_braking_duration_s"
    )

    jump_delta = _first_trial(rows, "INTERVENTION", post, "jump_height_cm") - _first_trial(
        rows, "INTERVENTION", baseline, "jump_height_cm"
    )
    assert 0 < jump_delta < 2.0, "jump height improvement must be present but modest"

    load = pl.read_parquet(PARQUET_DIR / "training_load.parquet").to_dicts()
    weekly = {week: float(np.mean([row["training_impulse_au"] for row in load if row["week"] == week])) for week in WEEKS}
    assert weekly[11] > weekly[10] * 1.15, "week 11 must carry the load spike"
    assert weekly[12] < weekly[11] * 0.7, "week 12 must be a taper"
    assert weekly[14] > weekly[12] * 1.3, "load must recover after the transient"

    impulse_by_week = {
        week: float(np.mean([row["concentric_impulse_n_s_kg"] for row in rows if row["week"] == week and row["trial_number"] == 1 and row["quality_state"] == "VALID"]))
        for week in WEEKS
    }
    assert impulse_by_week[12] < impulse_by_week[10] * 0.97, "week 12 must show transient performance suppression"
    assert impulse_by_week[14] > impulse_by_week[12] * 1.05, "performance must recover after the transient"

    wellness = pl.read_parquet(PARQUET_DIR / "wellness.parquet").to_dicts()
    readiness = {week: float(np.mean([row["readiness_0_10"] for row in wellness if row["week"] == week])) for week in WEEKS}
    assert readiness[12] == min(readiness.values()), "week 12 must be the worst readiness week"


def test_persistent_athlete_traits_create_repeated_measure_structure(dataset: dict) -> None:
    rows = _trials()
    week_one = [row for row in rows if row["week"] == 1 and row["quality_state"] == "VALID"]
    by_subject: dict[str, list[float]] = {}
    for row in week_one:
        by_subject.setdefault(row["subject_id"], []).append(row["concentric_impulse_n_s_kg"])
    means = np.array([np.mean(values) for values in by_subject.values()])
    within = np.array([np.std(values, ddof=1) for values in by_subject.values()])
    assert means.std(ddof=1) > within.mean() * 2, "between-athlete variance must exceed trial noise"


# --------------------------------------------------------------------------- #
# ForceLab
# --------------------------------------------------------------------------- #


def test_force_trace_contains_all_phases_and_matches_stored_metrics(dataset: dict) -> None:
    trials = pl.read_parquet(PARQUET_DIR / "cmj_trials.parquet").to_dicts()
    traces = pl.read_parquet(PARQUET_DIR / "force_traces.parquet")
    trial = next(row for row in trials if row["trial_id"] == "CMJ-001-10-1")
    trace = traces.filter(pl.col("trial_id") == trial["trial_id"])
    assert trace.height == 2350
    assert set(trace["phase"].unique()) == {"QUIET_STANDING", "UNWEIGHTING", "BRAKING", "PROPULSION", "FLIGHT", "LANDING"}

    boundaries = json.loads(trial["phase_boundaries"])
    times = trace["time_s"].to_numpy()
    force = trace["force_n"].to_numpy()
    mass = trial["body_mass_kg"]
    body_weight = trace["body_weight_n"][0]
    net = force - body_weight

    propulsion = (times >= boundaries["braking_end"]) & (times < boundaries["takeoff"])
    recomputed = float(np.trapezoid(net[propulsion], times[propulsion]) / mass)
    assert recomputed == pytest.approx(trial["concentric_impulse_n_s_kg"], abs=1e-4)

    braking = (times >= boundaries["movement_onset"]) & (times < boundaries["braking_end"])
    assert abs(float(np.trapezoid(net[braking], times[braking]) / mass)) == pytest.approx(
        trial["eccentric_braking_impulse_n_s_kg"], abs=1e-4
    )

    flight = boundaries["landing"] - boundaries["takeoff"]
    assert 9.80665 * flight**2 / 8 * 100 == pytest.approx(trial["jump_height_cm"], abs=1e-3)
    assert float(force.max()) == pytest.approx(trial["peak_force_n"], abs=1e-2)
    assert all(math.isfinite(float(trial[field])) and float(trial[field]) > 0 for field in (
        "jump_height_cm",
        "concentric_impulse_n_s_kg",
        "eccentric_braking_impulse_n_s_kg",
        "eccentric_braking_duration_s",
        "countermovement_depth_cm",
        "peak_force_n",
        "peak_power_w_kg",
        "rsi_mod",
    ))


def test_flagged_trial_remains_discoverable_with_a_distorted_signal(dataset: dict) -> None:
    traces = pl.read_parquet(PARQUET_DIR / "force_traces.parquet")
    flagged = traces.filter(pl.col("trial_id") == "CMJ-004-06-2")
    assert flagged.height == 2350
    quiet = flagged.filter(pl.col("phase") == "QUIET_STANDING")
    assert float(quiet["force_n"].std()) > 0.05 * float(quiet["body_weight_n"][0]) * 0.01






# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


def test_group_longitudinal_uses_a_random_effects_estimator_and_reports_contrasts(dataset: dict) -> None:
    result = _group_longitudinal(_trials(), "concentric_impulse_n_s_kg")
    assert result["estimator"].startswith("MIXEDLM"), result.get("estimator_attempts")
    assert result["converged"] is True
    assert result["n_subjects"] == 28
    assert result["n_observations"] == 448

    primary = result["contrasts"][result["primary_contrast_id"]]
    assert primary["ci_low"] < primary["estimate"] < primary["ci_high"]
    assert primary["estimate"] > 0, "intervention × time change must be positive in this dataset"
    assert primary["ci_low"] > 0, "the intervention × time effect must exclude zero"
    assert primary["std_error"] < primary["estimate"]

    balance = result["contrasts"]["baseline_balance_week_1"]
    assert balance["ci_low"] < 0 < balance["ci_high"], "arms must be compatible with baseline balance"

    for label in ("intercept", "week_slope_comparison", "group_at_reference", "week_x_group"):
        coefficient = result["coefficients"][label]
        assert coefficient["ci_low"] < coefficient["estimate"] < coefficient["ci_high"]
        assert coefficient["std_error"] > 0

    assert result["residual_summary"]["rmse"] > 0
    assert len(result["residual_by_week"]) == 16


def test_braking_duration_shows_the_documented_reduction(dataset: dict) -> None:
    result = _group_longitudinal(_trials(), "eccentric_braking_duration_s")
    primary = result["contrasts"][result["primary_contrast_id"]]
    assert primary["estimate"] < 0
    assert primary["ci_high"] < 0
    assert primary["unit"] == "s"


def test_reliability_math_is_correct(dataset: dict) -> None:
    rows = _trials()
    result = _reliability(rows, "concentric_impulse_n_s_kg")
    assert result["status"] == "COMPUTED"
    assert result["n_subjects"] == 28
    assert result["trials_per_subject"] == 2
    assert 0 < result["icc_3_1"] < 1
    assert result["icc_3_1_ci_low"] < result["icc_3_1"] < result["icc_3_1_ci_high"]
    assert 0 < result["mean_cv_percent"] < 15

    baseline = [row for row in rows if row["week"] == 1 and row["quality_state"] == "VALID"]
    by_subject: dict[str, list[float]] = {}
    for row in sorted(baseline, key=lambda item: item["trial_number"]):
        by_subject.setdefault(row["subject_id"], []).append(row["concentric_impulse_n_s_kg"])
    values = np.array([by_subject[key] for key in sorted(by_subject)], dtype=float)
    reference = anova_icc_reference(values)
    # Typical error is sqrt of the two-way residual MS (mean trial change removed).
    assert result["typical_error"] == pytest.approx(reference["typical_error"], rel=1e-9)
    assert result["icc_3_1"] == pytest.approx(reference["icc_3_1"], rel=1e-9)
    assert result["minimal_detectable_change_95"] == pytest.approx(1.959963984540054 * math.sqrt(2) * reference["typical_error"], rel=1e-12)
    assert len(result["cv_percent_by_subject"]) == 28


def test_two_way_icc_reproduces_shrout_fleiss_1979_table() -> None:
    # Shrout & Fleiss (1979), Psychol Bull 86:420, Table 2: 6 targets x 4 judges.
    values = np.array([[9, 2, 5, 8], [6, 1, 3, 2], [8, 4, 6, 8], [7, 1, 2, 6], [10, 5, 6, 9], [6, 2, 4, 7]], dtype=float)
    result = two_way_icc(values)
    assert round(result["icc_1_1_sensitivity"], 2) == 0.17
    assert round(result["icc_2_1_sensitivity"], 2) == 0.29
    assert round(result["icc_3_1"], 2) == 0.71
    assert result["icc_3_1"] == pytest.approx(anova_icc_reference(values)["icc_3_1"], rel=1e-12)
    assert result["icc_3_1_ci_low"] < result["icc_3_1"] < result["icc_3_1_ci_high"]
    # A pure systematic trial shift must not change ICC(3,1) consistency or typical error.
    shifted = values + np.array([0.0, 3.0, -2.0, 5.0])
    assert two_way_icc(shifted)["icc_3_1"] == pytest.approx(result["icc_3_1"], rel=1e-12)
    assert two_way_icc(shifted)["typical_error"] == pytest.approx(result["typical_error"], rel=1e-12)


def test_individual_change_reports_baseline_current_and_typical_error(dataset: dict) -> None:
    result = _individual_change(_trials(), "concentric_impulse_n_s_kg")
    assert result["n_subjects"] == 28
    assert result["typical_error"] > 0
    assert len(result["athletes"]) == 28
    for athlete in result["athletes"]:
        assert athlete["baseline"] > 0 and athlete["post"] > 0
        assert athlete["change"] == pytest.approx(athlete["post"] - athlete["baseline"])
        assert isinstance(athlete["exceeds_typical_error"], bool)
    intervention = [row for row in result["athletes"] if int(row["subject_id"].split("-")[-1]) % 2 == 1]
    comparison = [row for row in result["athletes"] if int(row["subject_id"].split("-")[-1]) % 2 == 0]
    assert np.mean([row["change"] for row in intervention]) > np.mean([row["change"] for row in comparison])


# --------------------------------------------------------------------------- #
# Modelling
# --------------------------------------------------------------------------- #


def test_training_response_simulation_is_deterministic_and_scenario_sensitive() -> None:
    first = simulate_training_response([300, 420, 500, 450, 350], {"tau_fitness_weeks": 4, "fatigue_tau_weeks": 1.8})
    second = simulate_training_response([300, 420, 500, 450, 350], {"tau_fitness_weeks": 4, "fatigue_tau_weeks": 1.8})
    assert first == second
    assert len(first["states"]) == 5
    assert all({"fitness", "fatigue", "performance_state"}.issubset(state) for state in first["states"])

    changed_load = simulate_training_response([600, 420, 500, 450, 350], {"tau_fitness_weeks": 4, "fatigue_tau_weeks": 1.8})
    assert [state["performance_state"] for state in changed_load["states"]] != [
        state["performance_state"] for state in first["states"]
    ]
    changed_tau = simulate_training_response([300, 420, 500, 450, 350], {"tau_fitness_weeks": 8, "fatigue_tau_weeks": 1.8})
    assert [state["performance_state"] for state in changed_tau["states"]] != [
        state["performance_state"] for state in first["states"]
    ]


def test_fitted_model_run_exposes_observed_modelled_and_residuals(dataset: dict) -> None:
    run = json.loads((ARTIFACT_DIR / "model_run.json").read_text(encoding="utf-8"))
    output = run["output"]
    assert len(output["observed_weeks"]) == 16
    assert len(output["observed_performance"]) == len(output["modelled_performance"]) == len(output["residuals"]) == 16
    for observed, modelled, residual in zip(output["observed_performance"], output["modelled_performance"], output["residuals"]):
        assert residual == pytest.approx(observed - modelled, abs=1e-9)
    assert output["fit_rmse_standardized"] > 0
    assert run["diagnostics"]["fit_status"] == "PROTOTYPE_FIT"
    assert run["parameters"]["tau_fitness_weeks"] > 0
    assert run["parameters"]["fatigue_tau_weeks"] > 0
    spec = json.loads((ARTIFACT_DIR / "model_spec.json").read_text(encoding="utf-8"))
    assert spec["status"] == "PROTOTYPE"
    assert all(item["status"] == "ROADMAP" for item in spec["roadmap"])


# --------------------------------------------------------------------------- #
# Evidence and lineage
# --------------------------------------------------------------------------- #


def test_evidence_artifacts_reference_real_artifacts(dataset: dict) -> None:
    evidence = json.loads((ARTIFACT_DIR / "evidence.json").read_text(encoding="utf-8"))
    runs = json.loads((ARTIFACT_DIR / "analysis_runs.json").read_text(encoding="utf-8"))
    run_ids = {run["id"] for run in runs}
    snapshot = dataset["snapshot"]
    assert {item["id"] for item in evidence} == {"EVID-0001", "EVID-0002", "EVID-0003"}
    for item in evidence:
        assert item["analysis_run_id"] in run_ids
        assert item["dataset_snapshot_id"] == snapshot["id"]
        assert item["protocol_id"] == "PROT-CMJ"
        assert item["sample_size"] > 0
        assert item["provenance"]["snapshot_checksum"] == snapshot["checksums"]["cmj_trials.parquet"]
        assert item["provenance"]["algorithm_version"]
        assert item["interpretation"]
    for run in runs:
        for artifact_id in run["output_artifact_ids"]:
            assert artifact_id in {item["id"] for item in evidence} | {"FIG-0001", "FIG-0002"}
    figures = json.loads((ARTIFACT_DIR / "figures.json").read_text(encoding="utf-8"))
    reliability_figure = next(figure for figure in figures if figure["id"] == "FIG-0002")
    assert len(reliability_figure["spec"]["values"]) == 28






# --------------------------------------------------------------------------- #
# Execution, immutability and API surface
# --------------------------------------------------------------------------- #


def _ledger_fields(run: dict) -> dict:
    """Stored run fields; ``reproduces``/``evidence_ids`` are computed views."""
    return {key: value for key, value in run.items() if key not in {"reproduces", "evidence_ids"}}


















def test_longitudinal_diagnostics_are_computed_and_attached(dataset: dict) -> None:
    runs = json.loads((ARTIFACT_DIR / "analysis_runs.json").read_text(encoding="utf-8"))
    diagnostics = next(run for run in runs if run["id"] == "RUN-0001")["diagnostics"]
    assert diagnostics["estimator"] == "MIXEDLM_RANDOM_SLOPE"
    assert diagnostics["converged"] is True
    assert len(diagnostics["residual_by_week"]) == 16
    qq = diagnostics["residual_qq"]
    assert len(qq) >= 30
    assert [point["theoretical"] for point in qq] == sorted(point["theoretical"] for point in qq)
    # The only flagged trial is a trial-2 repeat, so it never enters the first-trial model.
    assert diagnostics["sample_context"]["valid_first_trials_used"] == diagnostics["n_observations"]
    assert diagnostics["assumptions"] and diagnostics["limitations"]
    assert diagnostics["baseline_balance"]["ci_low"] < 0 < diagnostics["baseline_balance"]["ci_high"]


















def test_no_generated_artifact_contains_a_placeholder_value(dataset: dict) -> None:
    """Guard against decorative or fabricated numbers creeping into the store."""
    for path in sorted(ARTIFACT_DIR.glob("*.json")):
        text = Path(path).read_text(encoding="utf-8")
        for marker in ("TODO", "FIXME", "PLACEHOLDER", "lorem", "XXX"):
            assert marker not in text, f"{path.name} contains {marker}"


# --------------------------------------------------------------------------- #
# Workbench surfaces: cohort, exploration, lineage path, model, investigations
# --------------------------------------------------------------------------- #


def test_frozen_plan_states_the_difference_in_change_estimand(dataset: dict) -> None:
    study = json.loads((ARTIFACT_DIR / "study.json").read_text(encoding="utf-8"))
    for text in (study["plan"]["primary_estimand"], study["question"]["estimand"], *study["plan"]["planned_contrasts"]):
        assert "difference in change from week 1 to week 10" in text
    frozen = {spec["id"]: spec for spec in study["analysis_specs"] if spec["status"] == "FROZEN"}
    assert {"SPEC-LONG-001", "SPEC-LONG-002", "SPEC-REL-001", "SPEC-IND-001"} <= set(frozen)
    assert frozen["SPEC-LONG-002"]["outcome_metric_id"] == "MET-CMJ-BRAKING-DURATION"








def test_scenario_simulation_extends_the_fitted_model(dataset: dict) -> None:
    fitted = json.loads((ARTIFACT_DIR / "model_run.json").read_text(encoding="utf-8"))
    steady = simulate_scenario(fitted, [300.0] * 8)
    heavy = simulate_scenario(fitted, [600.0] * 8)
    history = [state["modelled_performance"] for state in steady["states"][:16]]
    assert history == pytest.approx(fitted["output"]["modelled_performance"], abs=1e-5)
    assert steady["states"][16]["segment"] == "SCENARIO"
    assert steady["summary"]["scenario_final_performance"] != pytest.approx(heavy["summary"]["scenario_final_performance"])
    again = simulate_scenario(fitted, [300.0] * 8)
    assert again["states"] == steady["states"]
