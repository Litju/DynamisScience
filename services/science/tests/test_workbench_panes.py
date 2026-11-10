from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QByteArray, QMimeData, Qt
from PySide6.QtWidgets import QApplication

from dynamis_science.desktop.workbench import data_models as dm
from dynamis_science.desktop.workbench.controller import WorkbenchController
from dynamis_science.desktop.workbench.data_pane import DataPane, PivotTrendModel
from dynamis_science.desktop.workbench.options_pane import OptionsPane
from dynamis_science.desktop.workbench.shell import WorkbenchShell


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


class FakeService:
    def read_table_page(self, snapshot_id, table, offset=0, limit=500):
        rows = [
            {"subject_id": f"MEN-{i // 4:02d}", "occasion": i % 4 + 1, "cmj_height_cm": None if i == 5 else 30.0 + i}
            for i in range(offset, min(40, offset + limit))
        ]
        return {"total_rows": 40, "columns": ["subject_id", "occasion", "cmj_height_cm"], "rows": rows}

    def get_dataset_detail(self, snapshot_id):
        cols = [("subject_id", "string", 0), ("occasion", "int64", 0), ("cmj_height_cm", "double", 1)]
        return {"tables": [{"name": "cmj_occasions", "rows": 40,
                            "columns": [{"name": n, "dtype": d, "null_count": k} for n, d, k in cols]}]}


@pytest.fixture
def wb():
    shell = WorkbenchShell()
    data = DataPane(FakeService())
    options = OptionsPane()
    shell.set_data_widget(data)
    shell.set_options_widget(options)
    ctl = WorkbenchController(shell, data, options)
    shell.select_analysis("mixed_models")
    data.set_dataset("DS-X", FakeService().get_dataset_detail("DS-X"))
    return shell, data, options, ctl


def test_no_spec_or_syntax_before_a_dataset():
    shell, data, options = WorkbenchShell(), DataPane(FakeService()), OptionsPane()
    ctl = WorkbenchController(shell, data, options)
    assert ctl.current_spec() is None and shell.syntax.toPlainText() == ""
    assert shell.run_label.text() == "No results yet" and shell.provenance_label.text() == ""


def test_views_models_and_missing_marks(wb):
    _, data, _, _ = wb
    assert data.variable_types() == {"subject_id": "identifier", "occasion": "ordinal", "cmj_height_cm": "numerical"}
    data.set_view("By athlete")
    model = data.athlete_view.model().sourceModel()
    assert isinstance(model, PivotTrendModel)
    assert model.rowCount() == 10 and model.columnCount() == 4 + 3
    row = next(r for r in range(10) if model.data(model.index(r, 0)) == "MEN-01")
    assert model.data(model.index(row, 2), dm.MissingRole) is True  # i == 5 is MEN-01 occasion 2
    assert model.data(model.index(row, 5), dm.MissingRole) is False  # delta uses occasions 1 and 4, both present
    # trend carries None for the gap, never an imputed number
    assert model.data(model.index(row, model.trend_column), 0x100 + 10)[1] is None
    # values and delta at the unit's precision (cm: 0.1), unit under the header
    assert model.data(model.index(row, 1)) == "34.0" and model.data(model.index(row, 5)) == "+3.0"
    assert model.headerData(5, Qt.Orientation.Horizontal) == "Δ\ncm"


def test_by_athlete_without_occasion_explains_instead_of_blank(wb):
    _, data, _, _ = wb
    data.set_view("By athlete")
    assert data.athlete_view.model() is not None
    data.table = "signal_trials"
    data._variables_model = dm.VariablesModel([dm.Variable("subject_id", "identifier", "", 1, 0, 0, "complete"),
                                               dm.Variable("force_file_count", "numerical", "", 1, 0, 0, "complete")])
    data.set_view("By athlete")
    assert data.athlete_view.model() is None and "no occasion column" in data.athlete_note.text()


def test_header_click_selects_variable(wb):
    _, data, _, _ = wb
    seen = []
    data.variable_selected.connect(seen.append)
    data.rows_view.horizontalHeader().sectionClicked.emit(2)
    assert seen == ["cmj_height_cm"]


def test_variables_drag_mime(wb):
    _, data, _, _ = wb
    model = data.variables_view.model()
    mime = model.mimeData([model.index(2, 0)])
    assert dm.variables_from_mime(mime) == ["cmj_height_cm"]


def test_assignment_syntax_and_run_state(wb):
    shell, data, options, ctl = wb
    assert "complete the role assignment" in shell.syntax.toPlainText()
    for role, name in (("outcome", "cmj_height_cm"), ("subject", "subject_id"), ("occasion", "occasion")):
        mime = QMimeData()
        mime.setData(dm.VARIABLE_MIME, QByteArray(name.encode()))
        options.slots[role].box.dropped.emit(dm.variables_from_mime(mime))
    spec = ctl.current_spec()
    assert spec.role("outcome") == ["cmj_height_cm"] and options.role_names("subject") == ["subject_id"]
    assert "execute_analysis_isolated" in shell.syntax.toPlainText()
    assert shell.provenance_label.text() == "" and shell.run_label.text() == "No results yet"
    runs = []
    ctl.run_requested.connect(runs.append)
    shell.action_run.trigger()
    assert runs == [spec] and shell.run_label.text().startswith("Running")
    ctl.set_last_run_hash(spec.spec_hash(), "RUN-1", "abcd")
    assert shell.run_label.text() == "Results up to date" and "result digest abcd" in shell.provenance_label.text()
    options.option_changed.emit("alpha", 0.1)
    assert shell.run_label.text() == "Specification changed"  # stale
    options.option_changed.emit("alpha", 0.05)
    assert shell.run_label.text() == "Results up to date"


def test_rejection_message_and_shake(wb):
    shell, _, options, _ = wb
    messages = []
    options.message.connect(messages.append)
    options.slots["outcome"].box.dropped.emit(["subject_id"])
    assert messages and "identifier" in messages[0]
    assert options.slots["outcome"].shaking and options.role_names("outcome") == []
    options.slots["covariates"].box.dropped.emit(["cmj_height_cm"])
    assert "not available" in messages[-1]


def test_keyboard_assignment_and_delete(wb):
    _, _, options, ctl = wb
    options.slots["subject"].box.focused.emit()  # focus makes it the active role
    idx = options.model.index(0, 0)  # subject_id
    options.var_list.setCurrentIndex(idx)
    options.var_list.selectionModel().select(idx, options.var_list.selectionModel().SelectionFlag.Select)
    options.assign_selected()
    assert ctl.current_spec().role("subject") == ["subject_id"]
    box = options.slots["subject"].box
    box.setCurrentRow(0)
    box.remove_requested.emit("subject_id")
    assert ctl.current_spec().role("subject") == []


def test_switching_dataset_clears_specs_and_run_state(wb):
    shell, data, options, ctl = wb
    options.slots["outcome"].box.dropped.emit(["cmj_height_cm"])
    ctl.set_last_run_hash(ctl.current_spec().spec_hash(), "RUN-1", "abcd")
    data.set_dataset("DS-Y", FakeService().get_dataset_detail("DS-Y"))
    assert ctl.current_spec().role("outcome") == [] and shell.run_label.text() == "No results yet"
    data.clear()
    assert ctl.current_spec() is None and shell.syntax.toPlainText() == ""


def test_method_status_chip_follows_analysis(wb):
    shell, _, options, _ = wb
    assert "QUALIFIED" in options.method_line.text() and shell.method_chip.text() == "QUALIFIED"
    shell.select_analysis("regression")
    assert shell.method_chip.text() == "NOT QUALIFIED" and "exploratory" in options.method_line.text()
