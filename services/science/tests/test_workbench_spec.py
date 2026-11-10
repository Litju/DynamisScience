from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QApplication

from dynamis_science.desktop.workbench import data_models as dm
from dynamis_science.desktop.workbench.spec import AnalysisSpec, method_status

TYPES = {
    "subject_id": "identifier", "occasion": "ordinal", "cmj_height_cm": "numerical",
    "fz_peak_n": "numerical", "quality_state": "categorical", "phase": "categorical",
}


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


class FakeService:
    """Same two methods as DynamisAppService; records every page request."""

    def __init__(self, n=1000):
        self.n, self.calls = n, []

    def read_table_page(self, snapshot_id, table, offset=0, limit=500):
        assert 1 <= limit <= 500
        self.calls.append((offset, limit))
        rows = []
        for i in range(offset, min(self.n, offset + limit)):
            rows.append({"subject_id": f"MEN-{i // 4:02d}", "occasion": i % 4 + 1,
                         "cmj_height_cm": None if i == 5 else 30.0 + i, "quality_state": "OK"})
        return {"total_rows": self.n, "columns": ["subject_id", "occasion", "cmj_height_cm", "quality_state"], "rows": rows}

    def get_dataset_detail(self, snapshot_id):
        cols = [("subject_id", "string", 0), ("occasion", "int64", 0), ("cmj_height_cm", "double", 5),
                ("quality_state", "string", 0), ("isometric_relative_peak_force_n_kg", "double", 0),
                ("quality_flags", "list<item: string>", 0)]
        return {"tables": [{"name": "cmj_occasions", "rows": 100,
                            "columns": [{"name": n, "dtype": d, "null_count": k} for n, d, k in cols]}]}


def spec(kind, **kw):
    kw.setdefault("variable_types", TYPES)
    return AnalysisSpec(kind=kind, **kw)


def mixed(**opt):
    return spec("mixed_model", table="cmj_occasions", options=opt,
                roles={"outcome": ["cmj_height_cm"], "subject": ["subject_id"], "occasion": ["occasion"]})


def rel(**opt):
    return spec("reliability", table="signal_trials", options=opt,
                roles={"outcome": ["fz_peak_n"], "subject": ["subject_id"]})


# ---- types and validation -------------------------------------------------
def test_variable_classification():
    c = dm.classify_variable
    assert c("subject_id", "string") == "identifier"
    assert c("occasion", "int64") == "ordinal"
    assert c("cmj_height_cm", "double") == "numerical"
    assert c("quality_state", "string") == "categorical"
    assert c("quality_flags", "list<item: string>") == "categorical"


def test_identifier_only_as_subject():
    s = mixed()
    assert s.can_accept("subject", "subject_id") is None
    assert "only be used as the subject" in s.can_accept("outcome", "subject_id")
    assert "numerical" in s.can_accept("outcome", "quality_state")


def test_valid_specs_have_no_errors():
    assert mixed().validate() == []
    assert rel().validate() == []


def test_validation_messages():
    s = mixed()
    s.roles["outcome"] = ["subject_id"]
    s.roles["covariates"] = ["fz_peak_n"]
    msgs = " | ".join(i["message"] for i in s.validate())
    assert "identifier" in msgs and "no covariates" in msgs
    assert any("at least 1" in i["message"] for i in spec("mixed_model", table="cmj_occasions").validate())
    assert any("max_trials" in i["message"] for i in rel(max_trials=12).validate())
    assert any("contrast_occasion" in i["message"] for i in mixed(contrast_occasion=1).validate())
    unregistered = spec("mixed_model", table="cmj_occasions", variable_types={**TYPES, "x": "numerical"},
                        roles={"outcome": ["x"], "subject": ["subject_id"], "occasion": ["occasion"]})
    assert any("registered metric" in i["message"] for i in unregistered.validate())


# ---- hash -----------------------------------------------------------------
def test_hash_stable_and_sensitive():
    assert mixed().spec_hash() == mixed().spec_hash()
    assert mixed().spec_hash() == mixed(contrast_occasion=4).spec_hash()  # explicit default == implicit
    assert mixed().spec_hash() != mixed(contrast_occasion=3).spec_hash()
    other = mixed()
    other.roles["outcome"] = ["fz_peak_n"]
    assert other.spec_hash() != mixed().spec_hash()
    assert len(mixed().spec_hash()) == 64


# ---- status, syntax, payload ---------------------------------------------
def test_method_status_from_codebase():
    assert method_status("mixed_model")["status"] == "qualified"
    assert method_status("mixed_model")["method_id"] == "METH-REAL-TREND"
    assert method_status("reliability")["promotable"] is True
    for k in ("ttest", "anova", "regression"):
        assert method_status(k)["status"] == "not qualified" and not method_status(k)["promotable"]
    for k in ("descriptives", "frequencies", "athlete_change"):
        assert method_status(k)["status"] == "descriptive"


def test_mixed_payload_and_syntax():
    p = mixed().to_run_payload()
    assert p == {"method_id": "METH-REAL-TREND", "outcome_metric_id": "MET-REAL-CMJ-HEIGHT",
                 "excluded_subject_ids": [],
                 "parameters": {"reference_occasion": 1, "contrast_occasion": 4, "alpha": 0.05}}
    code = mixed().to_python_syntax()
    assert 'execute_analysis_isolated("STUDY-REAL-001"' in code and "random intercept + occasion slope" in code
    assert "ML" in code and json.dumps(p, indent=4) in code


def test_reliability_payload_and_syntax():
    p = rel(max_trials=5).to_run_payload()
    assert p["method_id"] == "METH-REAL-RELIABILITY" and p["outcome_metric_id"] == "MET-REAL-FZ-PEAK"
    assert p["parameters"] == {"activity": "Walking", "max_trials": 5}
    assert "ICC(3,1)" in rel().to_python_syntax() and "STUDY-REAL-002" in rel().to_python_syntax()


def test_payload_refused_when_invalid_or_unsupported():
    with pytest.raises(ValueError):
        spec("mixed_model", table="cmj_occasions").to_run_payload()
    with pytest.raises(ValueError):
        spec("ttest").to_run_payload()


def test_payload_keys_match_service_contract():
    # execute_analysis_run reads method_id, outcome_metric_id, excluded_subject_ids, parameters.
    assert set(mixed().to_run_payload()) == {"method_id", "outcome_metric_id", "excluded_subject_ids", "parameters"}


def test_syntax_per_analysis():
    d = spec("descriptives", roles={"outcome": ["cmj_height_cm"], "factors": ["occasion"]})
    assert d.to_python_syntax().endswith('data.groupby("occasion")[["cmj_height_cm"]].describe()')
    assert "DESCRIPTIVE" in d.to_python_syntax()
    f = spec("frequencies", roles={"factors": ["quality_state"]})
    assert "value_counts(dropna=False)" in f.to_python_syntax()
    a = spec("athlete_change", roles={"outcome": ["cmj_height_cm"], "subject": ["subject_id"], "occasion": ["occasion"]})
    assert "pivot" in a.to_python_syntax() and "DESCRIPTIVE" in a.to_python_syntax()
    r = spec("regression", roles={"outcome": ["cmj_height_cm"], "covariates": ["phase"]})
    assert "NOT QUALIFIED" in r.to_python_syntax() and "C(phase)" in r.to_python_syntax()
    tt = spec("ttest", options={"level_1": 1, "level_2": 4},
              roles={"outcome": ["cmj_height_cm"], "occasion": ["occasion"], "subject": ["subject_id"]})
    assert "NOT QUALIFIED" in tt.to_python_syntax() and "ttest_rel" in tt.to_python_syntax()
    an = spec("anova", roles={"outcome": ["cmj_height_cm"], "occasion": ["occasion"], "subject": ["subject_id"]})
    assert "NOT QUALIFIED" in an.to_python_syntax() and "AnovaRM" in an.to_python_syntax()


# ---- models ---------------------------------------------------------------
def test_rows_model_pages_and_is_bounded():
    svc = FakeService(1000)
    m = dm.RowsModel(svc, "S", "cmj_occasions", page_size=200, max_rows=500)
    assert m.rowCount() == 0 and m.canFetchMore()
    m.fetchMore()
    assert m.rowCount() == 200 and m.columnCount() == 4 and m.total_rows == 1000
    while m.canFetchMore():
        m.fetchMore()
    assert m.rowCount() == 500 and m.truncated  # capped, never unbounded
    assert max(limit for _, limit in svc.calls) <= 200
    assert [o for o, _ in svc.calls] == [0, 200, 400]


def test_rows_model_missing_is_visible_not_blank():
    m = dm.RowsModel(FakeService(10), "S", "t")
    m.fetchMore()
    idx = m.index(5, 2)
    assert m.data(idx, dm.MissingRole) is True
    assert m.data(idx, Qt.ItemDataRole.DisplayRole) == dm.MISSING_TEXT
    assert m.data(m.index(4, 2), dm.MissingRole) is False
    assert not m.canFetchMore()


def test_variables_model():
    m = dm.VariablesModel.from_service(FakeService(), "S", "cmj_occasions")
    by = {v.name: v for v in m.variables()}
    assert by["subject_id"].type == "identifier" and by["occasion"].type == "ordinal"
    assert by["cmj_height_cm"].unit == "cm" and by["cmj_height_cm"].missing == 5
    assert by["cmj_height_cm"].n == 95 and by["cmj_height_cm"].quality == "some missing"
    assert by["isometric_relative_peak_force_n_kg"].unit == "N/kg"
    assert by["quality_flags"].type == "categorical"
    row = [v.name for v in m.variables()].index("cmj_height_cm")
    assert m.data(m.index(row, 5)) == "5.0%" and m.data(m.index(row, 4), dm.MissingRole) is True
    assert m.variable_types()["occasion"] == "ordinal"


def test_variable_mime_roundtrip():
    m = dm.VariablesModel.from_service(FakeService(), "S", "cmj_occasions")
    assert m.mimeTypes() == ["application/x-dynamis-variable"]
    assert m.flags(m.index(0, 0)) & Qt.ItemFlag.ItemIsDragEnabled
    mime = m.mimeData([m.index(2, 0), m.index(2, 1)])
    assert dm.variables_from_mime(mime) == ["cmj_height_cm"]
    assert dm.variables_from_mime(QMimeData()) == []


def test_unknown_missing_count_is_not_zero():
    detail = {"tables": [{"name": "t", "rows": 10, "columns": [{"name": "x", "dtype": "double"}]}]}
    v = dm.variables_from_detail(detail, "t")[0]
    assert v.missing is None and v.quality == "unknown"


def test_by_athlete_pivot_shows_missing_and_sorts():
    m = dm.ByAthleteModel(FakeService(40), "S", "t", "subject_id", "occasion", "cmj_height_cm")
    assert m.rowCount() == 10 and m.columnCount() == 4
    # row i == 5 is athlete MEN-01, occasion 2: missing, not blank
    assert m.data(m.index(1, 1), dm.MissingRole) is True
    assert m.data(m.index(1, 1)) == dm.MISSING_TEXT
    assert m.data(m.index(1, 0)) == "34.0"  # cm at 0.1
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(m)
    proxy.setSortRole(dm.SortRole)
    proxy.sort(0, Qt.SortOrder.DescendingOrder)
    assert proxy.data(proxy.index(0, 0), dm.SortRole) == 66.0
    capped = dm.ByAthleteModel(FakeService(2000), "S", "t", "subject_id", "occasion", "cmj_height_cm", max_rows=600)
    assert capped.truncated and capped.rowCount() <= 150
