"""RES-647 native Individuals Explorer and Individual Research surface inside the persistent workspace.

The panel lives in the research workbench; selecting a participant never opens a second application or project.
Every asynchronous completion is checked against the captured workspace/investigation/revision before it renders.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
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
    QScrollArea,
    QSizePolicy,
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
from .method_selector import method_html, binding_html

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
            item.setToolTip('—' if value is None else str(value))
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
    context_changed = Signal()
    reports_requested = Signal()
    export_requested = Signal()

    def __init__(self, service: DynamisAppService, run_task: RunTask, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task = service, run_task
        self.workspace_id: str | None = None
        self.investigation_id: str | None = None
        self.payload: dict[str, Any] = {}
        self.generation = 0
        self.protocol_dirty = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
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
        self._build_experiment()
        self._build_scenarios()
        self._build_compare()
        self.tabs.currentChanged.connect(self._fit_current_tab)
        self.tabs.currentChanged.connect(lambda _: self.context_changed.emit())
        self._fit_current_tab()
        self.setEnabled(False)

    def _fit_current_tab(self, *_args) -> None:
        for index in range(self.tabs.count()):
            policy = QSizePolicy.Policy.Preferred if index == self.tabs.currentIndex() else QSizePolicy.Policy.Ignored
            self.tabs.widget(index).setSizePolicy(policy, policy)

    # ------------------------------------------------------------------ context

    def context(self) -> tuple[str | None, str | None, str | None]:
        return self.workspace_id, self.investigation_id, self.payload.get("data_revision_id")

    def set_investigation(self, workspace_id: str | None, investigation_id: str | None) -> None:
        self.workspace_id, self.investigation_id = workspace_id, investigation_id
        self.payload = {}
        self.protocol_dirty = False
        self.result_diagnostics.clear()
        # Clear first so another participant's measurements are never shown while loading.
        for table in (self.data_table, self.period_table, self.compare_table, self.timeline_table, self.visit_history):
            table.setRowCount(0)
        for view in (self.result_view, self.scenario_view, self.compare_notes, self.period_view):
            view.clear()
        figure_layout = self.figure_holder.layout()
        while figure_layout.count():
            widget = figure_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.run_picker.clear()
        self.analysis_protocol.clear()
        self.protocol_history.clear()
        self.visit_revision.clear()
        self.experiment_summary.clear()
        self.protocol_outcome.clear()
        self.visit_schedule.clear()
        self.visit_supersedes.clear()
        for field in (self.protocol_question, self.assignment, self.blinding, self.testing_occasions,
                      self.amendment_reason, self.visit_exposure, self.visit_adherence, self.visit_missing,
                      self.visit_deviations, self.visit_occasion, self.onset_starts, self.onset_baseline,
                      self.onset_intervention, self.onset_suitability):
            field.clear()
        self.onset_dates.clear()
        self.onset_acknowledge.setChecked(False)
        self.visit_condition.setCurrentIndex(0)
        self.prespecified.setChecked(False)
        self.changes.clear()
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
            f"<b>Participant {html.escape(investigation['scope']['subject_id'])}</b> · {html.escape(metric['label'])} ({html.escape(metric['unit'])}) · Data revision {payload['data_revision_number']} · "
            f"{len(observed)}/{len(payload['points'])} {axis}s · {sum(p['n_trials'] for p in observed)} trials"
            + (f"<br>{html.escape(investigation['question'])}" if investigation.get("question") else ""))
        self.header.setToolTip(f"{investigation['id']} v{investigation['version']} · {payload['data_revision_id']}")
        _fill(self.data_table, [[point[axis], point["status"], point["n_trials"], ", ".join(f"{v:.2f}" for v in point["values"]) or "—",
                                 point["mean"], point["within_session_sd"], metric["unit"], point["empty_values"],
                                 ", ".join(point["quality_flags"]) or "—"] for point in payload["points"]])
        self.method_picker.clear()
        for method in payload["eligibility"]:
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
        self._show_experiment(payload)
        self.analysis_protocol.clear()
        for timeline in payload.get('experiment_history', []):
            p = timeline['protocol']
            self.analysis_protocol.addItem(f"Experimental protocol v{p['version']} · {p['question']}", timeline)
        self.analysis_protocol.setCurrentIndex(self.analysis_protocol.count()-1)
        self._method_changed()
        self._show_scenarios(payload["scenarios"])
        self.model_picker.clear()
        self.model_picker.addItem("No model referenced", None)
        for run in payload["runs"]:
            self.model_picker.addItem(f"{run['id']} · {run['method_id']}", run["id"])
        self.context_changed.emit()

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
        inference_note = QLabel('Randomized-onset inference requires a saved prospective allocation and complete faithful conduct. Phase differences remain descriptive.')
        inference_note.setWordWrap(True)
        layout.addWidget(inference_note)
        self.method_picker = QComboBox()
        self.method_picker.setAccessibleName("Individual analysis method")
        self.method_picker.currentIndexChanged.connect(self._method_changed)
        layout.addWidget(self.method_picker)
        self.analysis_protocol = QComboBox()
        self.analysis_protocol.setAccessibleName('Experimental analysis protocol version')
        self.analysis_protocol.currentIndexChanged.connect(self._method_changed)
        self.analysis_protocol.currentIndexChanged.connect(lambda _: self.context_changed.emit())
        layout.addWidget(self.analysis_protocol)
        self.method_advanced = QCheckBox('Show full statistical contract and assumptions')
        self.method_advanced.toggled.connect(self._method_changed)
        layout.addWidget(self.method_advanced)
        self.method_detail = QTextBrowser()
        layout.addWidget(self.method_detail, 1)
        self.run_button = QPushButton("Run individual analysis on the active revision")
        self.run_button.clicked.connect(self.execute)
        layout.addWidget(self.run_button)
        self.tabs.addTab(page, "Analysis")

    def _selected_method(self) -> dict | None:
        method = self.method_picker.currentData()
        if method and method['method_id'] in {'METH-EXPERIMENT-DESC', 'METH-ONSET-EXACT'} and self.analysis_protocol.currentData():
            timeline = self.analysis_protocol.currentData()
            return timeline.get('onset_eligibility') if method['method_id'] == 'METH-ONSET-EXACT' else timeline['eligibility']
        return method

    def _method_changed(self) -> None:
        method = self._selected_method()
        self.analysis_protocol.setVisible(bool(method and method['method_id'] in {'METH-EXPERIMENT-DESC', 'METH-ONSET-EXACT'}))
        self.run_button.setEnabled(bool(method and method["status"] == "ELIGIBLE"))
        if not method:
            self.method_detail.clear()
            return
        if self.method_advanced.isChecked():
            self.method_detail.setHtml(method_html(method))
        else:
            p = (self.analysis_protocol.currentData() or {}).get('protocol', {})
            issues = '<br>'.join(html.escape(s) for s in method['issues']) or 'Eligible on the captured protocol and active data revision.'
            self.method_detail.setHtml(f"<h3>{html.escape(method['name'])}</h3>"
                f"<p>{html.escape(p.get('question', ''))}<br>{html.escape(p.get('design_label', ''))} · protocol v{p.get('version', '—')}</p>"
                f"<p><b>{html.escape(method.get('inference_status', method['status']))}</b><br>{issues}</p>"
                f"<p>{html.escape(method['estimand'])}</p><p>{html.escape(method['uncertainty'])}</p>")

    def execute(self) -> None:
        method = self._selected_method()
        if not method or method["status"] != "ELIGIBLE" or not self.payload:
            return
        workspace_id, investigation_id, revision = self.context()
        subject = self.payload["investigation"]["scope"]["subject_id"]
        request = {"method_id": method["method_id"], "outcome_metric_id": self.payload["metric"]["id"], "parameters": {},
                   "data_revision_id": revision,
                   "scope": {"kind": "INDIVIDUAL", "subject_id": subject, "investigation_id": investigation_id,
                             "investigation_version":self.payload['investigation']['version']}}
        if method['method_id'] in {'METH-EXPERIMENT-DESC', 'METH-ONSET-EXACT'}:
            request['parameters'] = {'protocol_version':method['protocol_version']}

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
        report_actions = QHBoxLayout()
        self.export_result = QPushButton('Create report from selected result…')
        self.export_result.clicked.connect(self.export_requested)
        self.frozen_reports = QPushButton('Open frozen reports and analyses')
        self.frozen_reports.clicked.connect(self.reports_requested)
        report_actions.addWidget(self.export_result)
        report_actions.addWidget(self.frozen_reports)
        layout.addLayout(report_actions)
        self.result_tabs = QTabWidget()
        self.result_view = QTextBrowser()
        self.result_tabs.addTab(self.result_view, "Result")
        self.result_diagnostics = QTextBrowser()
        self.figure_holder = QWidget()
        QVBoxLayout(self.figure_holder)
        self.result_tabs.addTab(self.figure_holder, "Trajectory")
        self.result_tabs.addTab(self.result_diagnostics, 'Diagnostics and provenance')
        layout.addWidget(self.result_tabs, 1)
        self.tabs.addTab(self.results_page, "Results")

    def _show_run(self) -> None:
        run = self.run_picker.currentData()
        self.export_result.setEnabled(bool(run and run.get('data_revision_id') == self.payload.get('data_revision_id')
            and run.get('scope', {}).get('investigation_version') == self.payload.get('investigation', {}).get('version')))
        if not run:
            return
        self.context_changed.emit()
        result, diagnostics = run["result"], run.get("diagnostics", {})
        self.result_diagnostics.setHtml('<pre>' + html.escape(json.dumps(diagnostics, indent=2, default=str)) + '</pre>' + binding_html(run))
        if run['method_id'] in {'METH-EXPERIMENT-DESC', 'METH-ONSET-EXACT'}:
            from ..experiments import result_html
            if run['method_id'] == 'METH-ONSET-EXACT':
                from ..randomized_onset import result_html
            self.result_view.setHtml(f"<p>{html.escape(run['id'])} · {html.escape(run['method_id'])} "
                f"v{html.escape(run['method_version'])} · {html.escape(run['method_status']['state'])}</p>"
                + result_html(result))
            self._show_run_figure(run)
            return
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
            f"reproducibility {html.escape(run.get('reproducibility_key', ''))}</p>")
        self._show_run_figure(run)

    def _show_run_figure(self, run: dict) -> None:
        from .plots import ScientificFigureWidget, run_figure

        layout = self.figure_holder.layout()
        if layout.count() == 0:
            layout.addWidget(ScientificFigureWidget())
        layout.itemAt(0).widget().show_figure(run_figure(run))

    # ------------------------------------------------------------------ protocol

    def _build_protocol(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.protocol_note = QLabel('Choose a design suited to the intervention. Randomized onset draws a future start once and keeps treatment persistent; crossover requires replicated comparator periods. Saved allocations cannot be redrawn.')
        self.protocol_note.setWordWrap(True)
        layout.addWidget(self.protocol_note)
        form = QFormLayout()
        self.protocol_question = QLineEdit()
        self.protocol_question.setAccessibleName('Experimental research question')
        self.protocol_outcome = QLabel()
        self.amendment_reason = QLineEdit()
        form.addRow('Research question', self.protocol_question)
        form.addRow('Primary outcome / units', self.protocol_outcome)
        form.addRow('Amendment reason', self.amendment_reason)
        self.design_picker = QComboBox()
        for key, label in PROTOCOL_DESIGNS.items():
            self.design_picker.addItem(label, key)
        self.assignment = QLineEdit()
        self.assignment.setPlaceholderText("Document the actual assignment procedure; never invent randomization")
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
        self.onset_fields = QWidget()
        onset_form = QFormLayout(self.onset_fields)
        self.onset_starts = QLineEdit()
        self.onset_starts.setAccessibleName('Permissible randomized intervention starts')
        self.onset_dates = QPlainTextEdit()
        self.onset_dates.setMaximumHeight(95)
        self.onset_dates.setPlaceholderText('One future ISO timestamp with timezone per scheduled occasion, in the same order')
        self.onset_dates.setAccessibleName('Prespecified measurement timestamps')
        self.onset_baseline = QLineEdit()
        self.onset_intervention = QLineEdit()
        self.onset_suitability = QLineEdit()
        self.onset_acknowledge = QCheckBox('No anticipation/interference; stable measurements; no assignment-dependent co-intervention or missingness')
        self.onset_acknowledge.setToolTip('Required scientific assumptions. Persistent intervention; immediate-level statistic fixed in advance. Delayed effects may be missed.')
        for label,widget in [('Permitted starts (occasions)',self.onset_starts),('Scheduled timestamps',self.onset_dates),
                             ('Baseline condition',self.onset_baseline),('Persistent intervention / dose',self.onset_intervention),
                             ('Suitability / feasibility',self.onset_suitability),('Assumptions',self.onset_acknowledge)]:
            onset_form.addRow(label,widget)
        layout.addWidget(self.onset_fields)
        self.period_table = _table(["Kind", "Label", "Start", "End", "Adherence %", "Deviations", "Notes"], "Experimental periods")
        self.period_table.setColumnHidden(4, True)
        self.period_table.setColumnHidden(5, True)
        layout.addWidget(self.period_table, 1)
        row = QHBoxLayout()
        add = QPushButton("Add period")
        add.clicked.connect(lambda: self._add_period({}))
        remove = QPushButton("Remove period")
        remove.clicked.connect(lambda: self.period_table.removeRow(self.period_table.currentRow()))
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        self.period_actions = QWidget()
        self.period_actions.setLayout(row)
        layout.addWidget(self.period_actions)
        self.changes = QPlainTextEdit()
        self.changes.setPlaceholderText("Legacy tracking notes: <occasion>: <description>. For prospective amendments use Amendment reason above.")
        self.changes.setMaximumHeight(60)
        layout.addWidget(self.changes)
        self.save_protocol_button = QPushButton("Save protocol version")
        self.save_protocol_button.clicked.connect(self.save_protocol)
        self.design_picker.currentIndexChanged.connect(self._design_changed)
        self._design_changed()
        layout.addWidget(self.save_protocol_button)
        self.period_view = QTextBrowser()
        self.period_view.setMaximumHeight(90)
        layout.addWidget(self.period_view)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Protocol")
        for field in (self.protocol_question, self.assignment, self.blinding, self.testing_occasions,
                      self.amendment_reason, self.onset_starts, self.onset_baseline,
                      self.onset_intervention, self.onset_suitability):
            field.textEdited.connect(self._protocol_edited)
        self.period_table.itemChanged.connect(self._protocol_edited)

    def _protocol_edited(self, *_args) -> None:
        if self.payload and not getattr(self, '_rendering_protocol', False):
            self.protocol_dirty = True
            self.context_changed.emit()

    def _design_changed(self) -> None:
        randomized = self.design_picker.currentData() == 'RANDOMIZED_ONSET'
        self.onset_fields.setVisible(randomized)
        self.period_table.setEnabled(not randomized)
        self.period_actions.setVisible(not randomized)
        saved = ((self.payload or {}).get('investigation', {}).get('protocol') or {}).get('allocation')
        self.assignment.setReadOnly(randomized)
        self.design_picker.setEnabled(not bool(saved))
        for field in (self.testing_occasions, self.onset_starts, self.onset_dates,
                      self.onset_baseline, self.onset_intervention):
            field.setReadOnly(bool(saved))
        self.prespecified.setEnabled(not bool(saved))
        self.onset_acknowledge.setEnabled(not bool(saved))
        self.protocol_note.setText(
            'Allocation and measurement schedule are frozen. Amend narrative fields with a reason; '
            'record actual exposure and deviations in Visits and timeline.' if saved else
            'Choose a design suited to the intervention. Randomized onset draws a future start once and keeps '
            'treatment persistent; crossover requires replicated comparator periods. Saved allocations cannot be redrawn.')
        self.save_protocol_button.setText('Save prospective protocol and draw onset' if randomized and not saved else 'Save protocol version')

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
        self._rendering_protocol = True
        self.protocol_question.setText(protocol.get('question', self.payload.get('investigation', {}).get('question', '')))
        metric = self.payload.get('metric', {})
        self.protocol_outcome.setText(f"{metric.get('label', '')} ({metric.get('unit', '')})")
        self.amendment_reason.clear()
        self.design_picker.setCurrentIndex(max(0, self.design_picker.findData(protocol.get("design", "OBSERVATIONAL_TRACKING"))))
        self.assignment.setText(protocol.get("assignment", ""))
        self.prespecified.setChecked(bool(protocol.get("prespecified")))
        self.blinding.setText(protocol.get("blinding", ""))
        c = protocol.get('allocation', {}).get('configuration', {})
        self.onset_starts.setText(', '.join(map(str,c.get('permissible_starts', []))))
        self.onset_dates.setPlainText('\n'.join(c.get('testing_dates', [])))
        self.onset_baseline.setText(c.get('baseline_condition', ''))
        self.onset_intervention.setText(c.get('intervention_condition', ''))
        self.onset_suitability.setText(protocol.get('suitability', ''))
        self.onset_acknowledge.setChecked(c.get('assumptions_confirmed', False))
        self._design_changed()
        self.testing_occasions.setText(", ".join(map(str, protocol.get("testing_occasions", []))))
        self.period_table.setRowCount(0)
        adherence = {item["period"]: item for item in protocol.get("adherence", [])}
        for period in protocol.get("periods", []):
            self._add_period(period, adherence.get(period["label"]))
        self.changes.setPlainText("\n".join(f"{item['at']}: {item['description']}" for item in protocol.get("changes", [])))
        self._rendering_protocol = False
        self.protocol_dirty = False

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
                "prospective": self.design_picker.currentData() in {'N_OF_1_EXPERIMENT', 'RANDOMIZED_ONSET'},
                'permissible_starts':[int(v) for v in self.onset_starts.text().replace(',', ' ').split()],
                'testing_dates':[v.strip() for v in self.onset_dates.toPlainText().splitlines() if v.strip()],
                'baseline_condition':self.onset_baseline.text(), 'intervention_condition':self.onset_intervention.text(),
                'suitability':self.onset_suitability.text(), 'assumptions_confirmed':self.onset_acknowledge.isChecked(),
                "question": self.protocol_question.text(), "outcome_metric_id": self.payload['metric']['id'],
                "unit": self.payload['metric']['unit'], "amendment_reason": self.amendment_reason.text(),
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

    # ------------------------------------------------------------------ observed experimental visits

    def _build_experiment(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel('Save a prospective experimental protocol in Protocol first. Import later measurements into this same '
                      'workspace, then link each actual visit here. Planned exposure is never treated as observed exposure.')
        note.setWordWrap(True)
        layout.addWidget(note)
        inference_note = QLabel('Compare the planned timeline with actual condition, timing and measurements before analysis. Descriptive changes do not establish a treatment effect.')
        inference_note.setWordWrap(True)
        layout.addWidget(inference_note)
        self.protocol_history = QComboBox()
        self.protocol_history.setAccessibleName('Experimental protocol history')
        self.protocol_history.currentIndexChanged.connect(self._experiment_version_changed)
        layout.addWidget(self.protocol_history)
        self.analyze_experiment_button = QPushButton('Analyze this protocol')
        self.analyze_experiment_button.clicked.connect(self._analyze_experiment)
        conduct_actions = QHBoxLayout()
        self.visit_editor_toggle = QPushButton('Record or correct an actual visit…')
        self.visit_editor_toggle.setCheckable(True)
        conduct_actions.addWidget(self.visit_editor_toggle)
        conduct_actions.addWidget(self.analyze_experiment_button)
        layout.addLayout(conduct_actions)
        self.conduct_status = QLabel()
        self.conduct_status.setWordWrap(True)
        layout.addWidget(self.conduct_status)
        self.timeline_table = _table(['Planned occasion', 'Planned period', 'Actual occasion / time', 'Status',
            'Actual exposure', 'Adherence %', 'Deviations / missing reason', 'Mean', 'QC / trials', 'Revision', 'Observed period'],
            'Planned versus observed protocol timeline')
        self.timeline_table.setMinimumHeight(180)
        header = self.timeline_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        for column, width in enumerate((180, 180, 185, 90, 200, 90, 200, 70, 190, 180, 180)):
            self.timeline_table.setColumnWidth(column, width)
        header.moveSection(header.visualIndex(7), 4)
        self.timeline_table.verticalHeader().setDefaultSectionSize(48)
        self.timeline_table.cellDoubleClicked.connect(self._edit_timeline_visit)
        layout.addWidget(self.timeline_table, 1)
        self.experiment_summary = QTextBrowser()
        self.experiment_summary.setMinimumHeight(130)
        self.conduct_details = QCheckBox('Show period summaries and append-only visit history')
        layout.addWidget(self.conduct_details)
        layout.addWidget(self.experiment_summary)
        self.visit_editor = QWidget()
        editor_layout = QVBoxLayout(self.visit_editor)
        form = QFormLayout()
        self.visit_schedule = QComboBox()
        self.visit_schedule.setAccessibleName('Scheduled experimental measurement')
        self.visit_occasion = QLineEdit()
        self.visit_occasion.setAccessibleName('Actual experimental occasion')
        self.visit_schedule.currentIndexChanged.connect(lambda: self.visit_occasion.setText(str(self.visit_schedule.currentData() or '')))
        self.visit_time = QLineEdit(datetime.now().astimezone().isoformat(timespec='seconds'))
        self.visit_revision = QComboBox()
        self.visit_revision.setAccessibleName('Immutable experimental measurement revision')
        self.visit_status = QComboBox()
        self.visit_status.addItems(['MEASURED', 'MISSING'])
        self.visit_exposure = QLineEdit()
        self.visit_condition = QComboBox()
        self.visit_condition.addItem('Unknown / not recorded', None)
        self.visit_condition.addItem('Baseline condition', 'BASELINE')
        self.visit_condition.addItem('Persistent intervention', 'INTERVENTION')
        self.visit_condition.setAccessibleName('Actually recorded experimental condition')
        self.visit_adherence = QLineEdit()
        self.visit_adherence.setPlaceholderText('0–100; blank means unknown')
        self.visit_missing = QLineEdit()
        self.visit_deviations = QLineEdit()
        self.visit_supersedes = QComboBox()
        for label, widget in [('Scheduled measurement', self.visit_schedule), ('Actual occasion', self.visit_occasion),
                ('Actual time (ISO, timezone)', self.visit_time), ('Measurement revision', self.visit_revision),
                ('Measurement status', self.visit_status), ('Actual exposure', self.visit_exposure),
                ('Actual condition (record explicitly)',self.visit_condition),
                ('Adherence %', self.visit_adherence), ('Missing reason', self.visit_missing),
                ('Deviations / correction reason', self.visit_deviations), ('Correct prior visit', self.visit_supersedes)]:
            form.addRow(label, widget)
        editor_layout.addLayout(form)
        self.save_visit_button = QPushButton('Record actual visit')
        self.save_visit_button.clicked.connect(self.save_visit)
        editor_layout.addWidget(self.save_visit_button)
        self.visit_editor_toggle.toggled.connect(self.visit_editor.setVisible)
        self.visit_editor.hide()
        layout.addWidget(self.visit_editor)
        self.visit_history = _table(['Visit', 'Protocol version', 'Scheduled → actual', 'Status', 'Exposure',
                                    'Revision', 'Supersedes', 'Recorded at'], 'Append-only experimental visit history')
        self.visit_history.setMinimumHeight(130)
        layout.addWidget(self.visit_history)
        self.conduct_details.toggled.connect(self.experiment_summary.setVisible)
        self.conduct_details.toggled.connect(self.visit_history.setVisible)
        self.experiment_summary.hide()
        self.visit_history.hide()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, 'Visits and timeline')

    def _show_experiment(self, payload: dict) -> None:
        self.visit_editor_toggle.setChecked(False)
        self.visit_condition.setCurrentIndex(0)
        self.visit_time.setText(datetime.now().astimezone().isoformat(timespec='seconds'))
        self.protocol_history.clear()
        for timeline in payload.get('experiment_history', []):
            p = timeline['protocol']
            self.protocol_history.addItem(f"Protocol v{p['version']} · {p['created_at']} · {p['question']}", timeline)
        self.protocol_history.setCurrentIndex(self.protocol_history.count()-1)
        self.visit_revision.clear()
        for revision in payload.get('data_revisions', []):
            self.visit_revision.addItem(f"Revision {revision['number']} · {revision['id']}", revision['id'])
        self.visit_revision.setCurrentIndex(max(0, self.visit_revision.findData(payload['data_revision_id'])))
        self.visit_supersedes.clear()
        self.visit_supersedes.addItem('New visit', None)
        visits = payload.get('experiment', {}).get('visits', [])
        replaced = {v.get('supersedes') for v in visits}
        for v in visits:
            if v['id'] not in replaced:
                self.visit_supersedes.addItem(f"Occasion {v['scheduled_occasion']} · {v['id']}", v['id'])
        _fill(self.visit_history, [[v['id'], v['protocol_version'], f"{v['scheduled_occasion']} → {v['occasion']}",
             v['measurement_status'], v['exposure'], v['data_revision_id'], v.get('supersedes') or '—', v['created_at']]
             for v in visits])
        for field in (self.visit_exposure, self.visit_adherence, self.visit_missing, self.visit_deviations):
            field.clear()
        self._experiment_version_changed()

    def _experiment_version_changed(self) -> None:
        timeline = self.protocol_history.currentData()
        self.visit_schedule.clear()
        self.save_visit_button.setEnabled(bool(timeline))
        self.analyze_experiment_button.setEnabled(bool(timeline))
        self.visit_editor_toggle.setEnabled(bool(timeline))
        if not timeline:
            self.timeline_table.setRowCount(0)
            self.experiment_summary.setPlainText('No prospective experiment saved. Experimental inference: NOT_QUALIFIED.')
            self.conduct_status.setText('Save a prospective protocol before recording actual visits.')
            return
        plan = timeline['protocol']
        for at in plan['testing_occasions']:
            self.visit_schedule.addItem(str(at), at)
        rows = []
        for r in timeline['rows']:
            v = r['visit'] or {}
            m = v.get('measurement') or v.get('qc') or {}
            rows.append([r['scheduled_occasion'], f"{r['period']['label']} ({r['period']['kind']})",
                f"{v.get('occasion', '—')}\n{v.get('occurred_at', '—')}", r['status'],
                (f"{v.get('actual_condition') or 'Unknown condition'} · " if plan.get('allocation') and v else '') + v.get('exposure', '—'),
                v.get('adherence_percent'), ' / '.join(filter(None, [v.get('deviations'), v.get('missing_reason')])),
                r['mean'], f"{m.get('n_trials', 0)} valid; {', '.join(m.get('quality_flags', [])) or 'no flags'}; {m.get('empty_values', 0)} excluded",
                v.get('data_revision_id', '—'), (r['observed_period'] or {}).get('label', 'Outside plan' if v else '—')])
        _fill(self.timeline_table, rows)
        measured = sum(r['mean'] is not None for r in timeline['rows'])
        missing = sum(r['status'] == 'MISSING' for r in timeline['rows'])
        deviations = sum(bool((r['visit'] or {}).get('deviations')) for r in timeline['rows'])
        planned = sum(not r['visit'] for r in timeline['rows'])
        self.conduct_status.setText(f"Protocol v{plan['version']} · {measured} measured · {missing} missing · "
            f"{planned} unrecorded · {deviations} deviations. Double-click a row to record or explicitly correct its visit.")
        if plan.get('allocation'):
            dates = plan['allocation']['configuration']['testing_dates']
            for row,date in enumerate(dates):
                item = self.timeline_table.item(row,0)
                item.setText(f"{plan['testing_occasions'][row]}\n{date}")
                item.setToolTip(item.text())
        changes = ''.join(f"<li>{html.escape(c['period'])}: n={c['n']}, mean {_number(c['mean'])}, "
                          f"change from baseline {_number(c['change_from_baseline'])} {html.escape(c['unit'])}</li>"
                          for c in timeline['changes'])
        receipt = timeline.get('onset_eligibility') or {}
        inference = (f"{receipt.get('inference_status', 'NOT_QUALIFIED')} · " + ('; '.join(receipt.get('issues', [])) or 'Sharp-null test only, conditional on the saved scientific assumptions.')) if plan.get('allocation') else ('NOT_QUALIFIED · ' + timeline['inference']['reason'])
        self.experiment_summary.setHtml(f"<b>{html.escape(plan['question'])}</b><br>"
            f"{html.escape(plan['outcome_label'])} ({html.escape(plan['unit'])}) · participant {html.escape(plan['subject_id'])}<br>"
            f"Assignment: {html.escape(plan['assignment'])}<br>Amendment: {html.escape(plan['amendment_reason'])}<br>"
            f"Descriptive session means by actual occasion period; actual exposure is recorded separately. No causal estimate.<ul>{changes}</ul>"
            f"Protocol v{plan['version']} · {html.escape(plan['design_label'])}<br><b>{html.escape(inference)}</b>")
        self.context_changed.emit()

    def _edit_timeline_visit(self, row: int, _column: int) -> None:
        timeline = self.protocol_history.currentData()
        if not timeline or row >= len(timeline['rows']):
            return
        observation = timeline['rows'][row]
        self.visit_schedule.setCurrentIndex(self.visit_schedule.findData(observation['scheduled_occasion']))
        self.visit_occasion.setText(str(observation['scheduled_occasion']))
        self.visit_time.setText(datetime.now().astimezone().isoformat(timespec='seconds'))
        self.visit_revision.setCurrentIndex(self.visit_revision.findData(self.payload['data_revision_id']))
        self.visit_status.setCurrentText('MEASURED')
        visit = observation['visit']
        self.visit_supersedes.setCurrentIndex(0)
        self.visit_condition.setCurrentIndex(0)
        for field in (self.visit_exposure, self.visit_adherence, self.visit_missing, self.visit_deviations):
            field.clear()
        if visit:
            self.visit_occasion.setText(str(visit['occasion']))
            self.visit_time.setText(visit['occurred_at'])
            self.visit_revision.setCurrentIndex(self.visit_revision.findData(visit['data_revision_id']))
            self.visit_status.setCurrentText(visit['measurement_status'])
            self.visit_supersedes.setCurrentIndex(self.visit_supersedes.findData(visit['id']))
            self.visit_exposure.setText(visit['exposure'])
            self.visit_adherence.setText('' if visit['adherence_percent'] is None else str(visit['adherence_percent']))
            self.visit_missing.setText(visit['missing_reason'])
            self.visit_condition.setCurrentIndex(max(0, self.visit_condition.findData(visit.get('actual_condition'))))
        self.visit_editor_toggle.setChecked(True)
        self.visit_deviations.setFocus() if visit else self.visit_exposure.setFocus()
        self.tabs.currentWidget().ensureWidgetVisible(self.visit_editor)

    def _analyze_experiment(self) -> None:
        timeline = self.protocol_history.currentData()
        if not timeline:
            return
        version = timeline['protocol']['version']
        for i in range(self.analysis_protocol.count()):
            if self.analysis_protocol.itemData(i)['protocol']['version'] == version:
                self.analysis_protocol.setCurrentIndex(i)
                break
        identity = 'METH-ONSET-EXACT' if timeline['protocol'].get('allocation') else 'METH-EXPERIMENT-DESC'
        for i in range(self.method_picker.count()):
            if self.method_picker.itemData(i)['method_id'] == identity:
                self.method_picker.setCurrentIndex(i)
                break
        self.tabs.setCurrentIndex(next(i for i in range(self.tabs.count()) if self.tabs.tabText(i) == 'Analysis'))

    def save_visit(self) -> None:
        timeline = self.protocol_history.currentData()
        if not timeline or not self.payload:
            return
        try:
            percent = self.visit_adherence.text().strip()
            visit = dict(protocol_version=timeline['protocol']['version'],
                scheduled_occasion=self.visit_schedule.currentData(), occasion=int(self.visit_occasion.text()),
                occurred_at=self.visit_time.text(), data_revision_id=self.visit_revision.currentData(),
                measurement_status=self.visit_status.currentText(), exposure=self.visit_exposure.text(),
                actual_condition=self.visit_condition.currentData(),
                adherence_percent=float(percent) if percent else None, missing_reason=self.visit_missing.text(),
                deviations=self.visit_deviations.text(), supersedes=self.visit_supersedes.currentData())
        except ValueError:
            QMessageBox.warning(self, 'Visit', 'Actual occasion and adherence must be numbers.')
            return
        context = self.context()
        investigation_id, version = self.investigation_id, self.payload['investigation']['version']
        self.run_task(lambda: self.service.record_experimental_visit(investigation_id, visit, version),
                      lambda _: self.reload() if context == self.context() else None, 'Recording experimental visit')

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
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Scenarios")

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
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        button = QPushButton("Compare observed values")
        button.clicked.connect(self.compare)
        actions = QHBoxLayout()
        actions.addWidget(button)
        details = QPushButton("Interpretation and limitations…")
        details.clicked.connect(self._comparison_details)
        actions.addWidget(details)
        layout.addLayout(actions)
        self.compare_table = _table(["Occasion", "Own mean", "Trials", "Trial SD", "Cohort n",
                                     "Mean", "SD", "95% CI", "Aligned"], "Individual and cohort comparison")
        layout.addWidget(self.compare_table, 1)
        self.compare_notes = QTextBrowser(page)
        self.compare_notes.hide()
        self.tabs.addTab(page, "Compare with cohort")

    def _comparison_details(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Comparison interpretation and limitations")
        fit_dialog(dialog, 700, 450)
        layout = QVBoxLayout(dialog)
        notes = QTextBrowser()
        notes.setHtml(self.compare_notes.toHtml())
        layout.addWidget(notes)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

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
