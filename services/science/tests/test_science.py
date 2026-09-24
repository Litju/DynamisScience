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
from fastapi.testclient import TestClient

from dynamis_science.analysis import (
    _group_longitudinal,
    _individual_change,
    _reliability,
    simulate_training_response,
)
from dynamis_science.api import app
from dynamis_science.generate import ARTIFACT_DIR, PARQUET_DIR, SNAPSHOT_ID, generate_data

WEEKS = range(1, 17)


@pytest.fixture(scope="module")
def dataset() -> dict:
    return generate_data()


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


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


def test_trial_lookup_returns_phases_and_method_contract(client: TestClient) -> None:
    response = client.get("/force/trials/CMJ-001-10-1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_available"] is True
    assert set(payload["boundaries"]) == {"movement_onset", "unweighting_end", "braking_end", "takeoff", "landing"}
    assert payload["method"]["algorithm"] == "cmj-metrics"
    assert payload["method"]["sample_rate_hz"] == 1000
    assert client.get("/force/trials/NOPE").status_code == 404


def test_trial_browser_filters_by_subject_and_week(client: TestClient) -> None:
    payload = client.get("/force/trials", params={"subject_id": "SUB-004", "week": 6}).json()
    assert {row["trial_id"] for row in payload} == {"CMJ-004-06-1", "CMJ-004-06-2"}
    assert any(row["quality_state"] == "EXCLUDED" for row in payload)


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
    for row in baseline:
        by_subject.setdefault(row["subject_id"], []).append(row["concentric_impulse_n_s_kg"])
    values = np.array([by_subject[key] for key in sorted(by_subject)], dtype=float)
    means = values.mean(axis=1)
    ms_within = float(np.sum((values - means[:, None]) ** 2) / (values.shape[0] * (values.shape[1] - 1)))
    # Typical error is the within-subject SD, i.e. sqrt(MSE) - not the standard error of the mean.
    assert result["typical_error"] == pytest.approx(math.sqrt(ms_within), rel=1e-9)
    ms_between = float(values.shape[1] * np.sum((means - means.mean()) ** 2) / (values.shape[0] - 1))
    expected_icc = (ms_between - ms_within) / (ms_between + (values.shape[1] - 1) * ms_within)
    assert result["icc_3_1"] == pytest.approx(expected_icc, rel=1e-9)
    assert len(result["cv_percent_by_subject"]) == 28


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


def test_lineage_traverses_report_back_to_the_generator(client: TestClient) -> None:
    payload = client.get("/lineage/REPORT-001").json()
    node_ids = {node["id"] for node in payload["nodes"]}
    edge_pairs = {(edge["source"], edge["target"]) for edge in payload["edges"]}
    for required in ("GEN-001", SNAPSHOT_ID, "COHORT-001", "SPEC-LONG-001", "RUN-0001", "EVID-0001", "FIG-0001", "REPORT-001", "MET-CMJ-IMPULSE", "TRIAL-INDEX"):
        assert required in node_ids, required
    for required in (
        ("GEN-001", SNAPSHOT_ID),
        (SNAPSHOT_ID, "COHORT-001"),
        ("COHORT-001", "RUN-0001"),
        ("SPEC-LONG-001", "RUN-0001"),
        ("RUN-0001", "EVID-0001"),
        ("EVID-0001", "FIG-0001"),
        ("EVID-0001", "REPORT-001"),
    ):
        assert required in edge_pairs, required
    assert payload["focus"]["id"] == "REPORT-001"
    assert payload["focus"]["kind"] == "report"


def test_lineage_nodes_carry_inspectable_metadata(client: TestClient) -> None:
    payload = client.get("/lineage/EVID-0001").json()
    evidence_node = next(node for node in payload["nodes"] if node["id"] == "EVID-0001")
    assert evidence_node["detail"]["analysis_run_id"] == "RUN-0001"
    assert evidence_node["detail"]["dataset_snapshot_id"] == SNAPSHOT_ID
    snapshot_node = next(node for node in payload["nodes"] if node["id"] == SNAPSHOT_ID)
    assert snapshot_node["detail"]["checksums"]["cmj_trials.parquet"]


# --------------------------------------------------------------------------- #
# Execution, immutability and API surface
# --------------------------------------------------------------------------- #


def test_executed_analysis_appends_a_new_run_with_evidence_and_lineage(client: TestClient) -> None:
    before = client.get("/runs").json()
    before_ids = {run["id"] for run in before}
    response = client.post(
        "/analyses/execute",
        json={"method_id": "METH-LONG", "outcome_metric_id": "MET-CMJ-IMPULSE", "parameters": {"reference_week": 1, "contrast_week": 10}},
    )
    assert response.status_code == 200
    created = response.json()
    assert created["id"] not in before_ids
    assert created["status"] == "COMPLETED"
    assert created["snapshot_id"] == SNAPSHOT_ID
    assert created["seed"] == 20260924
    assert created["duration_ms"] > 0
    assert created["software_versions"]["service"]
    assert created["reproducibility_key"].startswith(SNAPSHOT_ID)

    evidence_id = created["evidence_artifact"]["id"]
    assert evidence_id in created["output_artifact_ids"]
    assert created["evidence_artifact"]["analysis_run_id"] == created["id"]

    after = client.get("/runs").json()
    assert len(after) == len(before) + 1
    # Historical runs must be untouched.
    for original in before:
        assert next(run for run in after if run["id"] == original["id"]) == original

    lineage = client.get(f"/lineage/{created['id']}").json()
    node_ids = {node["id"] for node in lineage["nodes"]}
    assert created["id"] in node_ids and evidence_id in node_ids
    assert (created["id"], evidence_id) in {(edge["source"], edge["target"]) for edge in lineage["edges"]}

    detail = client.get(f"/evidence/{evidence_id}").json()
    assert detail["source_runs"][0]["id"] == created["id"]
    assert detail["lineage"]["focus"]["id"] == evidence_id


def test_executed_analysis_spec_captures_the_configuration(client: TestClient) -> None:
    created = client.post(
        "/analyses/execute",
        json={"method_id": "METH-REL", "outcome_metric_id": "MET-CMJ-IMPULSE"},
    ).json()
    spec = created["execution"]["analysis_spec"]
    assert spec["method_id"] == "METH-REL"
    assert spec["snapshot_id"] == SNAPSHOT_ID
    assert spec["status"] == "EXPLORATORY"
    assert created["evidence_artifact"]["kind"] == "RELIABILITY"
    assert 0 < created["evidence_artifact"]["value"] <= 1


def test_executed_analysis_rejects_unknown_metrics(client: TestClient) -> None:
    response = client.post("/analyses/execute", json={"method_id": "METH-LONG", "outcome_metric_id": "MET-NOT-REAL"})
    assert response.status_code == 422


def test_primary_routes_respond(client: TestClient) -> None:
    for path in (
        "/health",
        "/overview",
        "/studies",
        "/studies/STUDY-001",
        "/subjects",
        "/subjects/SUB-001/longitudinal",
        "/force/trials?subject_id=SUB-001&week=10",
        "/match/MATCH-SYNTH-001",
        "/match/MATCH-SYNTH-001/tracking",
        "/match/MATCH-SYNTH-001/pose?athlete_id=PLAYER-14",
        "/registry",
        "/registry/metrics",
        "/registry/protocols",
        "/runs",
        "/runs/RUN-0001",
        "/evidence",
        "/evidence/EVID-0001",
        "/figures",
        "/report",
        "/lineage",
        "/models/training-response",
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"


def test_pose_stream_is_graceful_for_untracked_players(client: TestClient) -> None:
    available = client.get("/match/MATCH-SYNTH-001/pose", params={"athlete_id": "PLAYER-14"}).json()
    assert available["available"] is True
    assert available["frame_count"] == 1800
    assert available["pose_athletes"] == ["PLAYER-07", "PLAYER-09", "PLAYER-11", "PLAYER-14"]

    missing = client.get("/match/MATCH-SYNTH-001/pose", params={"athlete_id": "PLAYER-01"})
    assert missing.status_code == 200
    payload = missing.json()
    assert payload["available"] is False
    assert payload["frames"] == []
    assert payload["pose_athletes"] == ["PLAYER-07", "PLAYER-09", "PLAYER-11", "PLAYER-14"]


def test_match_tracking_is_synchronized_with_pose_and_events(client: TestClient) -> None:
    tracking = client.get("/match/MATCH-SYNTH-001/tracking").json()
    pose = client.get("/match/MATCH-SYNTH-001/pose", params={"athlete_id": "PLAYER-14"}).json()
    assert tracking["frame_count"] == 1800
    assert pose["frame_count"] == 1800
    assert tracking["frames"][900]["time_s"] == pose["frames"][900]["time_s"]
    assert len(tracking["events"]) == 4
    for event in tracking["events"]:
        assert 0 <= event["start_s"] < event["end_s"] <= tracking["duration_s"]
    # The ball and both teams must be present in every frame.
    teams = {entity["team"] for entity in tracking["frames"][0]["entities"]}
    assert teams == {"HOME", "AWAY", "BALL"}


def test_longitudinal_series_uses_both_trials_and_flags_missingness(client: TestClient) -> None:
    payload = client.get("/subjects/SUB-009/longitudinal", params={"metric_id": "MET-CMJ-IMPULSE"}).json()
    assert len(payload["observations"]) == 16
    assert payload["metric"]["unit"] == "N·s·kg⁻¹"
    weeks = {row["week"]: row for row in payload["observations"]}
    assert weeks[1]["n_trials"] == 2
    # SUB-009 (ATH-009) loses the second trial in every match-congestion week.
    for week in (4, 8, 12, 15):
        assert weeks[week]["n_trials"] == 1
        assert weeks[week]["missing_trials"] == 1
        assert weeks[week]["quality_state"] == "WARNING"
    assert payload["individual"]["baseline_mean"] is not None
    assert payload["individual"]["typical_error"] > 0
    assert isinstance(payload["individual"]["exceeds_typical_error"], bool)


def test_data_health_is_computed_not_asserted(client: TestClient) -> None:
    health = client.get("/overview").json()["data_health"]
    assert health["valid_measurements"] == 883
    assert health["excluded_measurements"] == 1
    assert health["missing_observations"] == 12
    assert 0 < health["provenance_completeness"] <= 100
    assert health["complete_records"] <= health["total_records"]


def test_registry_keeps_distinct_definitions_for_the_same_quantity(client: TestClient) -> None:
    metrics = client.get("/registry/metrics").json()
    by_id = {metric["id"]: metric for metric in metrics}
    assert {"MET-CMJ-IMPULSE", "MET-CMJ-HEIGHT", "MET-CMJ-HEIGHT-IMPULSE", "MET-CMJ-BRAKING-DURATION", "MET-CMJ-POWER", "MET-CMJ-DEPTH", "MET-CMJ-RSI-MOD"} <= set(by_id)
    flight = by_id["MET-CMJ-HEIGHT"]
    impulse = by_id["MET-CMJ-HEIGHT-IMPULSE"]
    assert flight["unit"] == impulse["unit"] == "cm"
    assert flight["canonical_id"] != impulse["canonical_id"]
    assert flight["method"] != impulse["method"]
    for metric in metrics:
        assert metric["unit"] and metric["method"] and metric["algorithm"] and metric["version"]
        assert metric["known_limitations"]
    assert by_id["MET-CMJ-IMPULSE"]["usage_count"] >= 3
    assert by_id["MET-CMJ-HEIGHT-IMPULSE"]["usage_count"] == 0


def test_report_artifact_links_evidence_and_figures(client: TestClient) -> None:
    report = client.get("/report").json()
    assert report["id"] == "REPORT-001"
    assert {item["id"] for item in report["evidence"]} == {"EVID-0001", "EVID-0002", "EVID-0003"}
    assert {figure["id"] for figure in report["figures"]} == {"FIG-0001", "FIG-0002"}
    assert report["snapshot"]["id"] == SNAPSHOT_ID
    assert len(report["longitudinal_signal"]) == 32
    assert report["data_health"]["valid_measurements"] > 0


def test_no_generated_artifact_contains_a_placeholder_value(dataset: dict) -> None:
    """Guard against decorative or fabricated numbers creeping into the store."""
    for path in sorted(ARTIFACT_DIR.glob("*.json")):
        text = Path(path).read_text(encoding="utf-8")
        for marker in ("TODO", "FIXME", "PLACEHOLDER", "lorem", "XXX"):
            assert marker not in text, f"{path.name} contains {marker}"
