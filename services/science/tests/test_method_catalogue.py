"""RES-716 scientific contracts and execution using isolated synthetic imports."""
import copy
from statistics import NormalDist

import numpy as np
import polars as pl
import pytest

from dynamis_science import method_catalogue as mc, realanalysis, researchstore
from test_longitudinal_research import service, study, run  # noqa: F401


METRIC = {"id": "CMJ", "column": "cmj_height_cm", "table": "cmj_occasions", "unit": "cm"}
ROWS = [{"subject_id": s, "occasion": t, "cmj_height_cm": 30 + i + t}
        for i, s in enumerate(["A", "B", "C"]) for t in range(1, 5)]


def check(rows=None, metric=None, identity="METH-REAL-TREND", **kwargs):
    return mc.eligibility(mc.method_spec(identity), metric or METRIC, ROWS if rows is None else rows,
                          ["A", "B", "C"], kwargs.pop("scope", {"kind": "COHORT"}),
                          kwargs.pop("design", "REPEATED_MEASURES"), kwargs.pop("parameters", {}))


def test_catalogue_is_versioned_detached_and_evidence_bounded():
    for method in mc.catalogue():
        assert all(key in method for key in ("estimand", "units", "uncertainty", "assumptions", "diagnostics",
                                              "supported_designs", "required_shape", "evidence_references", "version",
                                              "method_class", "scopes", "output_schema", "limitations", "timebase"))
    spec = mc.method_spec("METH-REAL-TREND")
    spec["assumptions"].clear()
    assert researchstore.METHODS[spec["id"]]["assumptions"]
    assert mc.method_spec("METH-U-DESC")["method_class"] == "DESCRIPTIVE"
    assert "Synthetic" in mc.method_spec("METH-LONG")["reason"]
    assert mc.method_spec("METH-FORECAST")["method_class"] == "UNAVAILABLE"


@pytest.mark.parametrize("rows,kwargs,reason", [
    (ROWS[:7], {}, "at least 8"),
    (ROWS + [ROWS[0]], {}, "duplicate"),
    ([{**r, "cmj_height_cm": float("inf")} for r in ROWS], {}, "non-finite"),
    ([{**r, "occasion": None} for r in ROWS], {}, "Missing occasion"),
    (ROWS, {"design": "N_OF_1_EXPERIMENT"}, "unsupported"),
    (ROWS, {"scope": {"kind": "INDIVIDUAL"}}, "Cohort-level"),
    (ROWS, {"parameters": {"reference_occasion": 1, "contrast_occasion": 9}}, "observed occasions"),
    (ROWS, {"parameters": {"alpha": 0.1}}, "fixed 95%"),
    (ROWS, {"parameters": {"reference_occasion": "first"}}, "Invalid parameter"),
    (ROWS, {"parameters": {"alpha": float("nan")}}, "Invalid parameter"),
    ([{**r, "occasion": 1.5} for r in ROWS], {}, "finite integer ordinal"),
])
def test_invalid_trend_inputs_are_rejected(rows, kwargs, reason):
    result = check(rows, **kwargs)
    assert result["status"] == "INELIGIBLE"
    assert reason in " ".join(result["issues"])


def test_observed_missingness_is_not_imputed():
    rows = copy.deepcopy(ROWS)
    rows[0]["cmj_height_cm"] = None
    result = check(rows)
    assert result["status"] == "ELIGIBLE"
    assert result["population"] == {"subjects": 3, "observed_rows": 11, "missing_rows": 1,
                                    "athletes_with_repeated_occasions": 3}


def test_disjoint_occasion_groups_cannot_supply_a_longitudinal_slope():
    rows = [{"subject_id": f"S{i}", "occasion": 1 + i // 4, "cmj_height_cm": value}
            for i, value in enumerate((28, 29, 31, 32, 36, 37, 39, 40))]
    subjects = [row["subject_id"] for row in rows]
    # The 8 cm difference comes entirely from two independent group means.
    assert sum(row["cmj_height_cm"] for row in rows[4:]) / 4 - sum(
        row["cmj_height_cm"] for row in rows[:4]) / 4 == 8
    receipt = mc.eligibility(mc.method_spec("METH-REAL-TREND"), METRIC, rows, subjects,
                             {"kind": "COHORT"}, "REPEATED_MEASURES")
    assert receipt["status"] == "INELIGIBLE"
    assert receipt["population"]["athletes_with_repeated_occasions"] == 0
    assert "Only 0 athletes" in " ".join(receipt["issues"])
    with pytest.raises(ValueError, match="not estimable for within-athlete change"):
        realanalysis._fit_trend(pl.DataFrame(rows), METRIC["column"], subjects, 1, 2)


def test_a_missing_second_occasion_cannot_supply_repeated_athlete_support():
    rows = [row for row in ROWS if row["subject_id"] != "C" or row["occasion"] == 1]
    rows.append({"subject_id": "C", "occasion": 2, "cmj_height_cm": None})
    receipt = check(rows)
    assert receipt["population"]["observed_rows"] == 9
    assert receipt["population"]["athletes_with_repeated_occasions"] == 2
    assert receipt["status"] == "INELIGIBLE"


def test_reliability_uses_only_peak_force_and_acquisition_trials():
    rows = [{"subject_id": s, "trial_number": t, "activity": "Walking", "fz_peak_n": 1000 + t}
            for s in ("A", "B", "C") for t in (1, 2)]
    metric = {"id": "FORCE", "table": "signal_trials", "column": "fz_peak_n", "unit": "N"}
    assert check(rows, metric, "METH-REAL-RELIABILITY")["status"] == "ELIGIBLE"
    assert "peak vertical force" in " ".join(check(rows, {**metric, "column": "other"}, "METH-REAL-RELIABILITY")["issues"])
    assert check(rows, metric, "METH-REAL-RELIABILITY", parameters={"max_trials": 1})["status"] == "INELIGIBLE"
    assert check(rows + [rows[0]], metric, "METH-REAL-RELIABILITY")["status"] == "INELIGIBLE"


def test_saved_runs_capture_contract_source_parameters_and_data_revision(service, study):  # noqa: F811
    result = run(service, study["id"], study["rev1"])
    binding = result["execution"]["method_binding"]
    assert binding["method_id"] == result["method_id"]
    assert binding["method_version"] == result["method_version"]
    assert binding["parameters"] == result["parameters"]
    assert binding["data_revision_id"] == study["rev1"]
    assert len(binding["source_revision"]["implementation_sha256"]) == 64
    assert len(binding["source_revision"]["git_head"]) == 40
    assert result["execution"]["eligibility"]["status"] == "ELIGIBLE"
    original = researchstore.get_run(result["id"])
    binding["method_spec"]["version"] = "changed in memory"
    assert researchstore.get_run(result["id"]) == original
    before = len(researchstore.list_runs(study["id"]))
    with pytest.raises(researchstore.ResearchValidation):
        run(service, study["id"], study["rev1"], "METH-REAL-TREND")
    assert len(researchstore.list_runs(study["id"])) == before


def test_existing_mixedlm_and_icc_execution_contracts_on_synthetic_rows(tmp_path, monkeypatch):
    """Exercise the real engine boundary with synthetic inputs; no private sources or qualification run."""
    from dynamis_science.qualification import anova_icc_reference
    subjects = [f"S{i:02}" for i in range(12)]
    rng = np.random.default_rng(716)
    intercepts = rng.normal(35, 3, len(subjects))
    slopes = rng.normal(1, 0.3, len(subjects))
    rows = [{"subject_id": s, "occasion": t, "cmj_height_cm": intercepts[i] + slopes[i] * t + rng.normal(0, 0.5)}
            for i, s in enumerate(subjects) for t in (1, 2, 3, 4)]
    trial_matrix = np.array([[9, 2, 5, 8], [6, 1, 3, 2], [8, 4, 6, 8], [7, 1, 2, 6], [10, 5, 6, 9], [6, 2, 4, 7]], dtype=float)
    trials = [{"subject_id": subjects[i], "trial_number": t + 1, "fz_peak_n": v, "activity": "Walking"}
              for i, values in enumerate(trial_matrix) for t, v in enumerate(values)]
    monkeypatch.setattr(realanalysis, "get_study", lambda _: {"snapshot": {"id": "SYNTHETIC-716", "checksums": {}}, "analysis_specs": []})
    monkeypatch.setattr(realanalysis, "_cohort", lambda *_: {"cohort": {"id": "SYNTHETIC-COHORT", "subject_ids": subjects}})
    monkeypatch.setattr(realanalysis, "read_table", lambda _, table: pl.DataFrame(rows if table == "cmj_occasions" else trials))
    monkeypatch.setattr(realanalysis, "artifact_dir", lambda: tmp_path)
    trend = realanalysis.execute(realanalysis.STUDY_MENDELEY, "METH-REAL-TREND", "MET-REAL-CMJ-HEIGHT", [],
                                 {"reference_occasion": 1, "contrast_occasion": 4, "alpha": 0.05})
    assert trend["execution"]["eligibility"]["status"] == "ELIGIBLE"
    assert trend["execution"]["method_binding"]["method_version"] == "1.2.0"
    assert trend["execution"]["eligibility"]["population"]["athletes_with_repeated_occasions"] == 12
    assert trend["diagnostics"]["sample_context"]["athletes_with_repeated_occasions"] == 12
    assert trend["diagnostics"]["converged"]
    # Balanced athlete/occasion design: compare fixed slope with a separate OLS slope calculation.
    x = np.array([r["occasion"] for r in rows], dtype=float)
    y = np.array([r["cmj_height_cm"] for r in rows])
    changes = y.reshape(-1, 4)
    changes = changes - changes.mean(axis=1, keepdims=True)
    slope = float(np.sum((x - x.mean()) * changes.ravel()) / np.sum((x - x.mean())**2))
    assert trend["result"]["coefficients"]["occasion_slope"]["estimate"] == pytest.approx(slope, abs=0.02)
    reliability = realanalysis.execute(realanalysis.STUDY_MOVESMART, "METH-REAL-RELIABILITY", "MET-REAL-FZ-PEAK", [],
                                      {"activity": "Walking", "max_trials": 4})
    reference = anova_icc_reference(trial_matrix)
    assert reliability["result"]["icc_3_1"] == pytest.approx(reference["icc_3_1"], rel=1e-12)
    assert reliability["result"]["typical_error"] == pytest.approx(reference["typical_error"], rel=1e-12)
    assert reliability["result"]["minimal_detectable_change_95"] == pytest.approx(NormalDist().inv_cdf(0.975) * np.sqrt(2) * reference["typical_error"])
    assert reliability["execution"]["method_binding"]["method_version"] == "1.1.0"
    with pytest.raises(ValueError, match="peak vertical force"):
        realanalysis.execute(realanalysis.STUDY_MOVESMART, "METH-REAL-RELIABILITY", "MET-REAL-IMU-ACCEL", [], {})
