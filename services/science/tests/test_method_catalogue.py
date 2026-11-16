"""RES-716 scientific contracts and execution using isolated synthetic imports."""
import copy

import pytest

from dynamis_science import method_catalogue as mc, researchstore
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
    assert result["population"] == {"subjects": 3, "observed_rows": 11, "missing_rows": 1}


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
