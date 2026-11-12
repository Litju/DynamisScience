"""RES-647 native Individuals Explorer and Individual Research surface inside the persistent workspace.

The panel lives in the research workbench; selecting a participant never opens a second application or project.
Every asynchronous completion is checked against the captured workspace/investigation/revision before it renders.
"""

from __future__ import annotations

import html
import json
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..longitudinal import HORIZON_UNITS, NOT_QUALIFIED, PERIOD_KINDS, PROTOCOL_DESIGNS, SCENARIO_KINDS
from .services import DynamisAppService

RunTask = Callable[[Callable[[], Any], Callable[[Any], None], str], None]


def _number(value: Any, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def _table(headers: list[str], name: str) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAccessibleName(name)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _fill(table: QTableWidget, rows: list[list[Any]], editable: bool = False) -> None:
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            item = QTableWidgetItem(_number(value))
            if not editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, column, item)


def _cell(table: QTableWidget, row: int, column: int) -> str:
    item = table.item(row, column)
    return item.text().strip() if item else ""


def fit_dialog(dialog: QDialog, width: int, height: int) -> None:
    screen = dialog.screen()
    if screen is not None:
        available = screen.availableGeometry()
        width, height = min(width, available.width() - 32), min(height, available.height() - 64)
    dialog.resize(width, height)


class IndividualResearchPanel(QWidget):
    """Data, analysis, results, protocol, scenarios and cohort comparison for one individual investigation."""

    analysis_saved = Signal(dict)

    def __init__(self, service: DynamisAppService, run_task: RunTask, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task = service, run_task
        self.workspace_id: str | None = None
        self.investigation_id: str | None = None
        self.payload: dict[str, Any] = {}
        self.generation = 0
        layout = QVBoxLayout(self)
        self.header = QLabel("Open an athlete from the squad to start individual research.")
        self.header.setObjectName("IndividualResearchHeader")
        self.header.setWordWrap(True)
        self.header.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.header)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_data()
        self._build_analysis()
        self._build_results()
        self._build_protocol()
        self._build_scenarios()
        self._build_compare()
        self.setEnabled(False)

    # ------------------------------------------------------------------ context

    def context(self) -> tuple[str | None, str | None, str | None]:
        return self.workspace_id, self.investigation_id, self.payload.get("data_revision_id")

    def set_investigation(self, workspace_id: str | None, investigation_id: str | None) -> None:
        self.workspace_id, self.investigation_id = workspace_id, investigation_id
        self.payload = {}
        # Clear first so another participant's measurements are never shown while loading.
        for table in (self.data_table, self.period_table, self.compare_table):
            table.setRowCount(0)
        for view in (self.result_view, self.scenario_view, self.compare_notes, self.period_view):
            view.clear()
        self.run_picker.clear()
        self.setEnabled(bool(investigation_id))
        if not investigation_id:
            self.header.setText("Main line · observed data. Create or choose a branch above to run individual analyses, protocols and scenarios.")
            return
        self.header.setText("Loading individual research…")
        self.reload()

    def reload(self) -> None:
        if not self.investigation_id:
            return
        self.generation += 1
        generation, investigation_id = self.generation, self.investigation_id
        self.run_task(lambda: self.service.individual_research(investigation_id),
                      lambda value: self._loaded(value) if generation == self.generation and investigation_id == self.investigation_id else None,
                      "Loading individual research")

    def _loaded(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        investigation, metric, axis = payload["investigation"], payload["metric"], payload["axis"]
        observed = [point for point in payload["points"] if point["n_trials"]]
        self.header.setText(
            f"<b>Participant {html.escape(investigation['scope']['subject_id'])}</b> · {html.escape(investigation['title'])} "
            f"<span>({html.escape(investigation['id'])} v{investigation['version']})</span><br>"
            f"Data revision {payload['data_revision_number']} · {html.escape(str(payload['data_revision_id']))} · "
            f"{len(observed)}/{len(payload['points'])} {axis}s observed · {sum(p['n_trials'] for p in observed)} trials · "
            f"{html.escape(metric['label'])} ({html.escape(metric['unit'])})<br>"
            f"<i>{html.escape(investigation.get('question') or 'No scientific question recorded.')}</i>")
        _fill(self.data_table, [[point[axis], point["status"], point["n_trials"], ", ".join(f"{v:.2f}" for v in point["values"]) or "—",
                                 point["mean"], point["within_session_sd"], metric["unit"], point["empty_values"],
                                 ", ".join(point["quality_flags"]) or "—"] for point in payload["points"]])
        self.method_picker.clear()
        for method in payload["eligibility"]:
            if method["status"] != "REJECTED":
                self.method_picker.addItem(f"{method['name']} · {method['status'].lower()}", method)
        self.method_picker.setCurrentIndex(max(0, next((i for i in range(self.method_picker.count())
                                                        if self.method_picker.itemData(i)["status"] == "ELIGIBLE"), 0)))
        self._method_changed()
        self.run_picker.clear()
        for run in reversed(payload["runs"]):
            current = run.get("data_revision_id") == payload["data_revision_id"]
            self.run_picker.addItem(f"{run['id']} · {run['method_id']} · {'active revision' if current else 'earlier revision (read-only)'}", run)
        if not payload["runs"]:
            self.result_view.setPlainText("No saved analysis for this investigation yet. Run an eligible method in Analysis.")
        self._show_protocol(investigation.get("protocol") or {})
        self._show_periods(payload["periods"])
        self._show_scenarios(payload["scenarios"])
        self.model_picker.clear()
        self.model_picker.addItem("No model referenced", None)
        for run in payload["runs"]:
            self.model_picker.addItem(f"{run['id']} · {run['method_id']}", run["id"])

    # ------------------------------------------------------------------ data

    def _build_data(self) -> None:
        self.data_table = _table(["Occasion", "Status", "Trials", "Repeated trial values", "Session mean", "Within-session SD",
                                  "Unit", "Empty values", "Quality flags"], "Individual observations")
        self.tabs.addTab(self.data_table, "Data")

    # ------------------------------------------------------------------ analysis

    def _build_analysis(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel("Individual observational analyses describe one participant's measured trajectory. They are not "
                      "personalized causal estimates, forecasts or injury-risk assessments.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.method_picker = QComboBox()
        self.method_picker.setAccessibleName("Individual analysis method")
        self.method_picker.currentIndexChanged.connect(self._method_changed)
        layout.addWidget(self.method_picker)
        self.method_detail = QTextBrowser()
        layout.addWidget(self.method_detail, 1)
        self.run_button = QPushButton("Run individual analysis on the active revision")
        self.run_button.clicked.connect(self.execute)
        layout.addWidget(self.run_button)
        self.tabs.addTab(page, "Analysis")

    def _method_changed(self) -> None:
        method = self.method_picker.currentData()
        self.run_button.setEnabled(bool(method and method["status"] == "ELIGIBLE"))
        if not method:
            self.method_detail.clear()
            return
        issues = "".join(f"<li>{html.escape(item)}</li>" for item in method["issues"])
        self.method_detail.setHtml(
            f"<p><b>{html.escape(method['name'])}</b> · {html.escape(method['qualification']['status'])}</p>"
            + (f"<p>Unavailable for this participant:</p><ul>{issues}</ul>" if issues else "<p>Data sufficiency checks passed.</p>")
            + f"<p>Missing data: {html.escape(method['missingness'])}</p>"
            + "".join(f"<p>· {html.escape(item)}</p>" for item in method["constraints"]))

    def execute(self) -> None:
        method = self.method_picker.currentData()
        if not method or method["status"] != "ELIGIBLE" or not self.payload:
            return
        workspace_id, investigation_id, revision = self.context()
        subject = self.payload["investigation"]["scope"]["subject_id"]
        request = {"method_id": method["method_id"], "outcome_metric_id": self.payload["metric"]["id"], "parameters": {},
                   "data_revision_id": revision,
                   "scope": {"kind": "INDIVIDUAL", "subject_id": subject, "investigation_id": investigation_id}}

        def finished(run: dict[str, Any]) -> None:
            if (workspace_id, investigation_id, revision) != self.context() or run.get("data_revision_id") != revision:
                return  # The researcher moved to another participant; the run stays in its own history.
            self.analysis_saved.emit(run)
            self.reload()
            self.tabs.setCurrentWidget(self.results_page)

        self.run_task(lambda: self.service.execute_analysis_isolated(workspace_id, request), finished, "Running individual analysis")

    # ------------------------------------------------------------------ results

    def _build_results(self) -> None:
        self.results_page = QWidget()
        layout = QVBoxLayout(self.results_page)
        self.run_picker = QComboBox()
        self.run_picker.setAccessibleName("Saved individual analyses")
        self.run_picker.currentIndexChanged.connect(self._show_run)
        layout.addWidget(self.run_picker)
        self.result_tabs = QTabWidget()
        self.result_view = QTextBrowser()
        self.result_tabs.addTab(self.result_view, "Result")
        self.figure_holder = QWidget()
        QVBoxLayout(self.figure_holder)
        self.result_tabs.addTab(self.figure_holder, "Trajectory")
        layout.addWidget(self.result_tabs, 1)
        self.tabs.addTab(self.results_page, "Results")

    def _show_run(self) -> None:
        run = self.run_picker.currentData()
        if not run:
            return
        result, diagnostics = run["result"], run.get("diagnostics", {})
        axis = result.get("axis", "week")
        rows = "".join(f"<tr><td>{point[axis]}</td><td>{point['status']}</td><td>{point['n_trials']}</td><td>{_number(point['mean'])}</td>"
                       f"<td>{_number(point['within_session_sd'])}</td></tr>" for point in result.get("points", []))
        limitations = "".join(f"<li>{html.escape(item)}</li>" for item in result.get("limitations", []))
        self.result_view.setHtml(
            f"<p><b>{html.escape(run['id'])}</b> · {html.escape(run['method_id'])} v{html.escape(run['method_version'])} · "
            f"{html.escape(run['method_status']['state'])} · revision {html.escape(str(run.get('data_revision_id')))}</p>"
            f"<table border='1' cellpadding='4'><tr><th>{axis.title()}</th><th>Status</th><th>Trials</th><th>Mean ({html.escape(result.get('unit', ''))})</th>"
            f"<th>Within-session SD</th></tr>{rows}</table>"
            f"<p>Observed change {result.get('first')} → {result.get('last')}: <b>{_number(result.get('change_first_to_last'), 3)} {html.escape(result.get('unit', ''))}</b> "
            f"({_number(result.get('percent_change_first_to_last'), 1)}%). Trial-noise SE: {_number(result.get('change_trial_noise_se'), 3)}.</p>"
            f"<p>{html.escape(result.get('error_note', ''))}</p><p>Missing occasions: {html.escape(', '.join(map(str, result.get('missing_occasions', []))) or 'none')}</p>"
            f"<p>Limitations:</p><ul>{limitations}</ul><p class='meta'>Digest {html.escape(run.get('result_digest', ''))} · "
            f"reproducibility {html.escape(run.get('reproducibility_key', ''))}</p><pre>{html.escape(json.dumps(diagnostics, indent=2, default=str))}</pre>")
        from .plots import ScientificFigureWidget, run_figure

        layout = self.figure_holder.layout()
        if layout.count() == 0:
            layout.addWidget(ScientificFigureWidget())
        layout.itemAt(0).widget().show_figure(run_figure(run))

    # ------------------------------------------------------------------ protocol

    def _build_protocol(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.protocol_note = QLabel("A repeated-measurement history alone is retrospective observational tracking. An N-of-1 "
                                    "experiment needs prespecified, replicated intervention and comparison periods with documented assignment.")
        self.protocol_note.setWordWrap(True)
        layout.addWidget(self.protocol_note)
        form = QFormLayout()
        self.design_picker = QComboBox()
        for key, label in PROTOCOL_DESIGNS.items():
            self.design_picker.addItem(label, key)
        self.assignment = QLineEdit()
        self.assignment.setPlaceholderText("e.g. randomized ABAB sequence")
        self.prespecified = QCheckBox("Periods were prespecified before the outcome measurements")
        self.blinding = QLineEdit()
        self.testing_occasions = QLineEdit()
        self.testing_occasions.setPlaceholderText("e.g. 1, 2, 3")
        form.addRow("Design", self.design_picker)
        form.addRow("Assignment", self.assignment)
        form.addRow("", self.prespecified)
        form.addRow("Blinding", self.blinding)
        form.addRow("Testing occasions", self.testing_occasions)
        layout.addLayout(form)
        self.period_table = _table(["Kind", "Label", "Start", "End", "Adherence %", "Deviations", "Notes"], "Experimental periods")
        layout.addWidget(self.period_table, 1)
        row = QHBoxLayout()
        add = QPushButton("Add period")
        add.clicked.connect(lambda: self._add_period({}))
        remove = QPushButton("Remove period")
        remove.clicked.connect(lambda: self.period_table.removeRow(self.period_table.currentRow()))
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        self.changes = QPlainTextEdit()
        self.changes.setPlaceholderText("Protocol changes, one per line: <occasion>: <description>")
        self.changes.setMaximumHeight(60)
        layout.addWidget(self.changes)
        self.save_protocol_button = QPushButton("Save protocol version")
        self.save_protocol_button.clicked.connect(self.save_protocol)
        layout.addWidget(self.save_protocol_button)
        self.period_view = QTextBrowser()
        self.period_view.setMaximumHeight(90)
        layout.addWidget(self.period_view)
        self.tabs.addTab(page, "Protocol")

    def _add_period(self, period: dict[str, Any], adherence: dict[str, Any] | None = None) -> None:
        row = self.period_table.rowCount()
        self.period_table.insertRow(row)
        kind = QComboBox()
        kind.addItems(PERIOD_KINDS)
        kind.setCurrentText(period.get("kind", "BASELINE"))
        self.period_table.setCellWidget(row, 0, kind)
        adherence = adherence or {}
        for column, value in enumerate((period.get("label", ""), period.get("start", ""), period.get("end", ""),
                                        adherence.get("adherence_percent", ""), adherence.get("deviations", ""), period.get("notes", "")), start=1):
            self.period_table.setItem(row, column, QTableWidgetItem("" if value is None else str(value)))

    def _show_protocol(self, protocol: dict[str, Any]) -> None:
        self.design_picker.setCurrentIndex(max(0, self.design_picker.findData(protocol.get("design", "OBSERVATIONAL_TRACKING"))))
        self.assignment.setText(protocol.get("assignment", ""))
        self.prespecified.setChecked(bool(protocol.get("prespecified")))
        self.blinding.setText(protocol.get("blinding", ""))
        self.testing_occasions.setText(", ".join(map(str, protocol.get("testing_occasions", []))))
        self.period_table.setRowCount(0)
        adherence = {item["period"]: item for item in protocol.get("adherence", [])}
        for period in protocol.get("periods", []):
            self._add_period(period, adherence.get(period["label"]))
        self.changes.setPlainText("\n".join(f"{item['at']}: {item['description']}" for item in protocol.get("changes", [])))

    def _show_periods(self, periods: list[dict[str, Any]]) -> None:
        self.period_view.setPlainText("\n".join(f"{item['label']} ({item['kind'].lower()}): occasions {', '.join(map(str, item['occasions'])) or 'none'} "
                                                f"· {item['trials']} observed trials" for item in periods) or "No documented periods.")

    def protocol_from_form(self) -> dict[str, Any]:
        periods, adherence = [], []
        for row in range(self.period_table.rowCount()):
            label = _cell(self.period_table, row, 1) or f"Period {row + 1}"
            periods.append({"kind": self.period_table.cellWidget(row, 0).currentText(), "label": label,
                            "start": _cell(self.period_table, row, 2), "end": _cell(self.period_table, row, 3),
                            "notes": _cell(self.period_table, row, 6)})
            percent, deviations = _cell(self.period_table, row, 4), _cell(self.period_table, row, 5)
            if percent or deviations:
                adherence.append({"period": label, "adherence_percent": float(percent) if percent else None, "deviations": deviations})
        changes = []
        for line in self.changes.toPlainText().splitlines():
            if line.strip():
                at, _, description = line.partition(":")
                changes.append({"at": int(at), "description": description})
        occasions = [int(value) for value in self.testing_occasions.text().replace(",", " ").split()]
        return {"design": self.design_picker.currentData(), "periods": periods, "adherence": adherence, "changes": changes,
                "testing_occasions": occasions, "assignment": self.assignment.text(), "prespecified": self.prespecified.isChecked(),
                "blinding": self.blinding.text()}

    def save_protocol(self) -> None:
        if not self.payload:
            return
        try:
            protocol = self.protocol_from_form()
        except ValueError:
            QMessageBox.warning(self, "Protocol", "Occasions, adherence and protocol-change positions must be numbers.")
            return
        investigation_id, version = self.investigation_id, self.payload["investigation"]["version"]
        self.run_task(lambda: self.service.save_protocol(investigation_id, protocol, version),
                      lambda _: self.reload() if investigation_id == self.investigation_id else None, "Saving protocol version")

    # ------------------------------------------------------------------ scenarios

    def _build_scenarios(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        banner = QLabel(f"<b>HYPOTHETICAL</b> · Scenario definitions are not observations or evidence. {NOT_QUALIFIED}")
        banner.setObjectName("HypotheticalBanner")
        banner.setWordWrap(True)
        layout.addWidget(banner)
        self.scenario_view = QTextBrowser()
        layout.addWidget(self.scenario_view, 1)
        form = QFormLayout()
        self.scenario_kind = QComboBox()
        for key, label in SCENARIO_KINDS.items():
            self.scenario_kind.addItem(label, key)
        self.scenario_title = QLineEdit()
        self.model_picker = QComboBox()
        horizon = QHBoxLayout()
        self.horizon_value = QDoubleSpinBox()
        self.horizon_value.setRange(0.0, 520.0)
        self.horizon_value.setValue(4.0)
        self.horizon_unit = QComboBox()
        self.horizon_unit.addItems(HORIZON_UNITS)
        self.horizon_unit.setCurrentText("weeks")
        horizon.addWidget(self.horizon_value)
        horizon.addWidget(self.horizon_unit)
        self.adverse = QLineEdit()
        self.adverse.setPlaceholderText("Required for a worst-case stress test")
        self.assumptions = QPlainTextEdit()
        self.assumptions.setPlaceholderText("One explicit assumption per line")
        self.assumptions.setMaximumHeight(60)
        form.addRow("Type", self.scenario_kind)
        form.addRow("Title", self.scenario_title)
        form.addRow("Model reference", self.model_picker)
        form.addRow("Time horizon", horizon)
        form.addRow("Adverse outcome", self.adverse)
        form.addRow("Assumptions", self.assumptions)
        layout.addLayout(form)
        self.bounds = _table(["Parameter", "Lower", "Upper", "Unit"], "Scenario parameter bounds")
        self.bounds.setRowCount(1)
        self.bounds.setMaximumHeight(90)
        layout.addWidget(self.bounds)
        save = QPushButton("Save hypothetical scenario")
        save.clicked.connect(self.save_scenario)
        layout.addWidget(save)
        self.tabs.addTab(page, "Scenarios")

    def _show_scenarios(self, scenarios: list[dict[str, Any]]) -> None:
        def describe(item: dict[str, Any]) -> str:
            bounds = "; ".join(f"{b['name']} {b['lower']:g}–{b['upper']:g} {b['unit']}" for b in item["parameter_bounds"])
            model = (item.get("model_run") or {}).get("id", "none")
            adverse = f"Adverse outcome: {html.escape(item['adverse_outcome'])}<br>" if item["adverse_outcome"] else ""
            return (f"<p><b>HYPOTHETICAL · {html.escape(item['kind_label'])}</b> · {html.escape(item['title'])} (v{item['version']})<br>"
                    f"Revision {html.escape(str(item['data_revision_id']))} · model {html.escape(str(model))} · "
                    f"{html.escape(item['outcome_label'])} ({html.escape(item['unit'])}) · horizon {item['horizon']['value']:g} {item['horizon']['unit']}<br>"
                    f"Bounds: {html.escape(bounds)}<br>{adverse}Assumptions: {html.escape('; '.join(item['assumptions']))}<br>"
                    f"<b>{html.escape(item['qualification']['message'])}</b></p>")

        self.scenario_view.setHtml("".join(describe(item) for item in scenarios) or "<p>No scenario defined.</p>")

    def scenario_from_form(self) -> dict[str, Any]:
        bounds = []
        for row in range(self.bounds.rowCount()):
            if _cell(self.bounds, row, 0):
                bounds.append({"name": _cell(self.bounds, row, 0), "lower": float(_cell(self.bounds, row, 1)),
                               "upper": float(_cell(self.bounds, row, 2)), "unit": _cell(self.bounds, row, 3)})
        return {"kind": self.scenario_kind.currentData(), "title": self.scenario_title.text(),
                "model_run_id": self.model_picker.currentData(), "data_revision_id": self.payload.get("data_revision_id"),
                "outcome_metric_id": self.payload["metric"]["id"], "parameter_bounds": bounds,
                "horizon": {"value": self.horizon_value.value(), "unit": self.horizon_unit.currentText()},
                "adverse_outcome": self.adverse.text(), "assumptions": self.assumptions.toPlainText().splitlines()}

    def save_scenario(self) -> None:
        if not self.payload:
            return
        try:
            scenario = self.scenario_from_form()
        except ValueError:
            QMessageBox.warning(self, "Scenario", "Parameter bounds must be numbers.")
            return
        investigation_id, version = self.investigation_id, self.payload["investigation"]["version"]
        self.run_task(lambda: self.service.save_scenario(investigation_id, scenario, version),
                      lambda _: self.reload() if investigation_id == self.investigation_id else None, "Saving hypothetical scenario")

    # ------------------------------------------------------------------ compare

    def _build_compare(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        button = QPushButton("Compare observed values with cohort context")
        button.clicked.connect(self.compare)
        layout.addWidget(button)
        self.compare_table = _table(["Occasion", "Individual observed mean", "Trials", "Within-session SD", "Cohort n",
                                     "Cohort mean", "Cohort SD", "Cohort 95% CI", "Comparable"], "Individual and cohort comparison")
        layout.addWidget(self.compare_table, 1)
        self.compare_notes = QTextBrowser()
        self.compare_notes.setMaximumHeight(140)
        layout.addWidget(self.compare_notes)
        self.tabs.addTab(page, "Compare with cohort")

    def compare(self) -> None:
        if not self.payload:
            return
        expected = self.context()
        workspace_id, investigation_id, revision = expected
        subject = self.payload["investigation"]["scope"]["subject_id"]
        self.run_task(lambda: self.service.compare_with_cohort(workspace_id, subject),
                      lambda value: self._compared(value) if expected == self.context() and value.get("data_revision_id") == revision else None, "Comparing with cohort")

    def _compared(self, value: dict[str, Any]) -> None:
        axis = value["axis"]
        _fill(self.compare_table, [[row[axis], row["individual_mean"], row["individual_trials"], row["individual_within_session_sd"],
                                    row["cohort_n"], row["cohort_mean"], row["cohort_sd"],
                                    f"{_number(row['cohort_ci_low'])} – {_number(row['cohort_ci_high'])}", "yes" if row["comparable"] else "no"]
                                   for row in value["rows"]])
        modeled = "".join(f"<li>{html.escape(item['run_id'])} · {html.escape(item['method_id'])}: {html.escape(item['label'])}</li>"
                          for item in value["modeled_estimates"]) or "<li>No qualified modeled estimate on this revision.</li>"
        scenarios = "".join(f"<li>HYPOTHETICAL · {html.escape(item['title'])}: {html.escape(item['qualification'])}</li>"
                            for item in value["hypothetical_scenarios"]) or "<li>None.</li>"
        self.compare_notes.setHtml(
            f"<p><b>Individual observed values</b> vs <b>cohort descriptive summaries</b>: {html.escape(value['cohort_definition'])}. "
            f"{html.escape(value['compatibility'])} {html.escape(value['metric']['label'])} in {html.escape(value['metric']['unit'])}.</p>"
            f"<p><b>Qualified modeled estimates</b></p><ul>{modeled}</ul><p><b>Hypothetical scenario outputs</b></p><ul>{scenarios}</ul>"
            + "".join(f"<p>· {html.escape(item)}</p>" for item in value["limitations"]))
