from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from dynamis_science import admission, dataworkspace, importer
from dynamis_science.desktop.data_workspace import DataWorkspaceDialog
from dynamis_science.desktop.services import DynamisAppService

from test_importer import FIXTURE, HEADER, ROWS, _file
from test_traces import _csv, _two_traces, CONST


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    app = DynamisAppService()
    app.ensure_initialized()
    return app


def _admit_cmj(tmp_path):
    text = HEADER + ROWS + "A3,T3,,70,1500\n"
    plan = importer.edit_mapping(importer.probe_file(_file(tmp_path, "w.csv", text)), {}, {"session_id": "S1", "sampling_hz": 1000})
    return importer.admit(importer.stage(plan, importer.build_context(FIXTURE)))["dataset_snapshot_id"]


def _admit_trace(tmp_path):
    plan = importer.edit_mapping(importer.probe_file(_csv(tmp_path, "tr.csv", _two_traces(600))), {}, CONST)
    return importer.admit(importer.stage(plan, importer.build_context({**FIXTURE, "source_name": "Trace lab"})))["dataset_snapshot_id"]


def test_page_filter_sort_columns_and_limits(service, tmp_path):
    sid = _admit_cmj(tmp_path)
    tables = service._workspace_tables(sid)
    path = tables["cmj_trials"]
    full = dataworkspace.page(path)
    assert full["total_rows"] == 3 and "jump_height_cm" in full["columns"]
    high = dataworkspace.page(path, filters=[{"column": "jump_height_cm", "op": ">", "value": "39"}])
    assert high["total_rows"] == 1
    assert dataworkspace.page(path, filters=[{"column": "subject_id", "op": "contains", "value": "a2"}])["total_rows"] == 1
    assert dataworkspace.page(path, filters=[{"column": "jump_height_cm", "op": "is empty"}])["total_rows"] == 1
    ordered = dataworkspace.page(path, sort="peak_force_n", descending=True, columns=["subject_id", "peak_force_n"])
    assert [r[0] for r in ordered["rows"]] == ["A1", "A2", "A3"] and ordered["columns"] == ["subject_id", "peak_force_n"]
    assert dataworkspace.page(path, offset=2, limit=1)["rows"][0][0] == "A3"
    for bad in ({"column": "nope", "op": "="}, {"column": "jump_height_cm", "op": ">", "value": "x"}, {"column": "subject_id", "op": "DROP"}):
        with pytest.raises(ValueError):
            dataworkspace.page(path, filters=[bad])
    with pytest.raises(ValueError):
        dataworkspace.page(path, limit=dataworkspace.MAX_PAGE + 1)


def test_profile_reports_units_types_and_missingness(service, tmp_path):
    sid = _admit_cmj(tmp_path)
    columns = {c["name"]: c for c in service.table_profile(sid, "cmj_trials")["columns"]}
    assert columns["jump_height_cm"]["unit"] == "cm" and columns["jump_height_cm"]["missing"] == 1
    assert columns["body_mass_kg"]["unit"] == "kg" and columns["peak_force_n"]["unit"] == "N"
    assert columns["body_mass_kg"]["dtype"].startswith("Float") and columns["subject_id"]["dtype"] in {"String", "Utf8"}
    assert columns["peak_force_n"]["min"] == 1500.0 and columns["peak_force_n"]["max"] == 1800.0


@pytest.mark.parametrize("sql", [
    "DROP TABLE cmj_trials", "SELECT 1; SELECT 2", "SELECT * FROM read_csv('C:/x.csv')", "SELECT * FROM 'C:/data/x.parquet'",
    "INSERT INTO cmj_trials VALUES (1)", "WITH a AS (SELECT 1) CREATE TABLE b AS SELECT * FROM a", "SELECT * FROM cmj_trials -- x",
    "COPY cmj_trials TO 'x'", "", "SET threads = 1"])
def test_queries_are_read_only(service, tmp_path, sql):
    sid = _admit_cmj(tmp_path)
    with pytest.raises(ValueError):
        service.run_readonly_query(sid, sql)


def test_read_only_query_results_and_limit(service, tmp_path):
    sid = _admit_cmj(tmp_path)
    result = service.run_readonly_query(sid, "SELECT subject_id, jump_height_cm FROM cmj_trials ORDER BY subject_id", limit=2)
    assert result["columns"] == ["subject_id", "jump_height_cm"] and len(result["rows"]) == 2 and result["truncated"]
    agg = service.run_readonly_query(sid, "SELECT COUNT(*) AS n, AVG(peak_force_n) AS mean_f FROM cmj_trials")
    assert agg["rows"][0][0] == 3
    with pytest.raises(ValueError, match="Query failed"):
        service.run_readonly_query(sid, "SELECT missing_column FROM cmj_trials")
    before = Path(service._workspace_tables(sid)["cmj_trials"]).read_bytes()
    service.run_readonly_query(sid, "SELECT * FROM cmj_trials")
    assert Path(service._workspace_tables(sid)["cmj_trials"]).read_bytes() == before


def test_trace_dataset_pages_samples_and_queries_aggregates(service, tmp_path):
    sid = _admit_trace(tmp_path)
    page = service.query_table(sid, "force_signals", 0, 5, sort="time_s", descending=True)
    assert page["total_rows"] == 1200 and len(page["rows"]) == 5
    result = service.run_readonly_query(sid, "SELECT trial_id, COUNT(*) AS n, MAX(time_s) AS t FROM force_signals GROUP BY trial_id ORDER BY trial_id")
    assert [r[:2] for r in result["rows"]] == [("T1", 600), ("T2", 600)]


def test_inspector_exposes_rights_qc_provenance_and_receipt(service, tmp_path):
    sid = _admit_cmj(tmp_path)
    info = service.dataset_inspector(sid)
    assert info["admission_class"] == "SYNTHETIC_ONLY" and info["quality"]["status"].startswith("ADMITTED")
    assert info["receipts"][0]["raw_filename"] == "w.csv" and info["source"]["rights_status"] == "FIXTURE_ONLY"
    assert info["provenance"]["instrument_metadata"][0]["calibration_status"] == "SIMULATED"
    assert info["checksums"]


def test_dialog_browse_filter_query_inspect_and_continue_into_analysis(service, tmp_path, qtbot):
    cmj, trace = _admit_cmj(tmp_path), _admit_trace(tmp_path)
    chosen = []
    dialog = DataWorkspaceDialog(service, lambda op, done, label="": done(op()), chosen.append)
    qtbot.addWidget(dialog)
    dialog.open(cmj)
    assert dialog.catalogue.count() >= 2 and dialog.snapshot_id == cmj
    assert dialog.table_picker.currentText() == "cmj_trials" and dialog.rows_model.rowCount() == 3
    assert "Rows 1–3 of 3" in dialog.page_label.text()
    assert any("(cm)" in c for c in dialog.rows_model.columns)  # units shown with the data
    dialog.filter_column.setCurrentText("peak_force_n")
    dialog.filter_op.setCurrentText(">=")
    dialog.filter_value.setText("1700")
    dialog._add_filter()
    assert dialog.rows_model.rowCount() == 2 and "(filtered)" in dialog.page_label.text()
    dialog._clear_filters()
    dialog._sort_by(dialog.rows_model.columns.index(next(c for c in dialog.rows_model.columns if c.startswith("peak_force_n"))))
    assert dialog.rows_model.rows[0][dialog.rows_model.columns.index(next(c for c in dialog.rows_model.columns if c.startswith("peak_force_n")))] == 1500.0
    assert dialog.profile_model.rowCount() == len(dialog.profile_columns) > 5
    dialog.query_text.setPlainText("SELECT COUNT(*) AS n FROM cmj_trials")
    dialog._run_query()
    assert dialog.query_model.rows == [(3,)] and "1 rows" in dialog.query_status.text()
    dialog.query_text.setPlainText("DROP TABLE cmj_trials")
    dialog._run_query()
    assert "not allowed" in dialog.query_status.text() or "Only SELECT" in dialog.query_status.text()
    text = dialog.inspector.toPlainText()
    assert "SYNTHETIC_ONLY" in text and "FIXTURE_ONLY" in text and "w.csv" in text and "Exclusions" in text
    dialog.search.setText("trace lab")
    assert dialog.catalogue.count() == 1
    dialog.search.clear()
    dialog.catalogue.setCurrentRow([dialog.catalogue.item(i).data(Qt_UserRole()) for i in range(dialog.catalogue.count())].index(trace))
    dialog.tabs.setCurrentIndex(2)
    assert dialog.signals is not None and dialog.signals.waveform["sample_count"] == 600  # first recording is plotted, not an empty tab
    dialog._analyze()
    assert chosen == [trace]


def Qt_UserRole():
    from PySide6.QtCore import Qt
    return Qt.ItemDataRole.UserRole


def test_logical_dataset_unions_batches_per_source(service, tmp_path, qtbot):
    ctx = importer.build_context(FIXTURE)
    ids = [importer.admit(importer.stage(importer.edit_mapping(importer.probe_file(_file(tmp_path, f"b{i}.csv", HEADER + f"A{i},T{i},4{i},80,1800\n")), {}, {"session_id": "S1", "sampling_hz": 1000}), ctx))["dataset_snapshot_id"] for i in (1, 2)]
    other = importer.build_context({**FIXTURE, "source_name": "Other lab"})
    importer.admit(importer.stage(importer.edit_mapping(importer.probe_file(_file(tmp_path, "o.csv", HEADER + "Z1,T1,41,80,1800\n")), {}, {"session_id": "S1", "sampling_hz": 1000}), other))
    logical = [g for g in service.logical_datasets()]
    assert len(logical) == 2  # one per source profile
    group = next(g for g in logical if len(g["batches"]) == 2)
    assert group["row_counts"] == {"cmj_trials": 2} and [b["id"] for b in group["batches"]] == ids
    page = service.query_table(group["id"], "cmj_trials")
    assert page["total_rows"] == 2 and "batch_id" in page["columns"]
    assert {r[page["columns"].index("batch_id")] for r in page["rows"]} == set(ids)
    result = service.run_readonly_query(group["id"], "SELECT batch_id, COUNT(*) AS n FROM cmj_trials GROUP BY batch_id ORDER BY batch_id")
    assert [r[1] for r in result["rows"]] == [1, 1]
    assert service.dataset_inspector(group["id"])["batches"][0]["receipts"]
    # a new file of the same source grows the logical dataset; earlier batches are untouched
    importer.admit(importer.stage(importer.edit_mapping(importer.probe_file(_file(tmp_path, "b3.csv", HEADER + "A3,T3,43,80,1800\n")), {}, {"session_id": "S1", "sampling_hz": 1000}), ctx))
    assert next(g for g in service.logical_datasets() if g["id"] == group["id"])["row_counts"] == {"cmj_trials": 3}
    dialog = DataWorkspaceDialog(service, lambda op, done, label="": done(op()), lambda sid: None)
    qtbot.addWidget(dialog)
    dialog.open(group["id"])
    assert dialog.snapshot_id == group["id"] and not dialog.analyze_button.isEnabled()
    assert dialog.rows_model.rowCount() == 3 and "Logical dataset" in dialog.inspector.toPlainText()
    batch_row = next(i for i in range(dialog.catalogue.count()) if dialog.catalogue.item(i).data(0x0100) == ids[0])
    dialog.catalogue.setCurrentRow(batch_row)
    assert dialog.analyze_button.isEnabled()
