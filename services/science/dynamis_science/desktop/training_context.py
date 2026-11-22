"""Native source review and dated observations for Training Exposure & Testing Context."""

from __future__ import annotations

import json

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMenu, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, Signal

from .. import context_timeline as timeline, measurement_trust
from . import theme
from .context_source_dialog import ContextSourceDialog, ERRORS
from .individual_research import fit_dialog
from .investigation_timeline import EvidencePanel, InvestigationChart, LANES, date_label, heading, readable, wrapping_label

class TrainingContextPanel(QWidget):
    tool_requested = Signal(str, object)
    athlete_record_requested = Signal(str)

    def __init__(self, run_task, settings=None):
        super().__init__()
        self.run_task = run_task
        self.settings = settings
        self.workspace = self.revision = None
        self.revision_numbers = {}
        self.generation = 0
        self.view = self.saved = self.pair = self.comparison = None
        self._live_model = self._live_result = self._live_pair = None
        self._selection_by_scope = {}
        self._event_selections = {}
        self._stale = self._outcome_message = ""
        self._import_change = None
        self._refresh_after_import = False
        self.visible_rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(8)
        context_row = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.setAccessibleName("Athlete or cohort")
        self.scope.setMinimumContentsLength(12)
        self.scope.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.scope.currentIndexChanged.connect(self._scope_changed)
        self.mode = QLabel()
        self.mode.setObjectName('InvestigationMode')
        self.mode.setAccessibleName("Investigation mode and data revision")
        heading(self.mode, 11)
        self.pinned_scope = QLabel()
        heading(self.pinned_scope, 11)
        self.first = QComboBox()
        self.second = QComboBox()
        for picker, name in ((self.first, "Reference assessment"), (self.second, "Follow-up assessment")):
            picker.setAccessibleName(name)
            picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            picker.activated.connect(self._pair_changed)
        self.comparison_controls = QWidget()
        dates = QHBoxLayout(self.comparison_controls)
        dates.setContentsMargins(0, 0, 0, 0)
        dates.addWidget(QLabel("Assessments"))
        dates.addWidget(self.first)
        dates.addWidget(QLabel("→"))
        dates.addWidget(self.second)
        self.pinned_dates = QLabel()
        self.add_source = QPushButton("Import context…")
        self.add_source.clicked.connect(self._import)
        self.open_view = QPushButton("Frozen history…")
        self.open_view.clicked.connect(self._open)
        self.live_view = QPushButton("Return to live")
        self.live_view.clicked.connect(self._live)
        for widget in (self.scope, self.pinned_scope, self.mode, self.comparison_controls, self.pinned_dates):
            context_row.addWidget(widget)
        context_row.addStretch(1)
        for action in (self.add_source, self.open_view, self.live_view):
            context_row.addWidget(action)
        layout.addLayout(context_row)

        self.finding = QLabel()
        self.finding.setObjectName('InvestigationFinding')
        self.finding.setTextFormat(Qt.TextFormat.PlainText)
        self.finding.setWordWrap(True)
        heading(self.finding, 23)
        layout.addWidget(self.finding)
        finding_row = QHBoxLayout()
        self.comparison_summary = wrapping_label()
        finding_row.addWidget(self.comparison_summary, 1)
        self.compare_button = QPushButton("Compare assessments")
        self.compare_button.setProperty("primary", True)
        self.compare_button.clicked.connect(self._compare)
        finding_row.addWidget(self.compare_button)
        layout.addLayout(finding_row)
        self.import_outcome = wrapping_label()
        self.import_outcome.hide()
        layout.addWidget(self.import_outcome)

        split = QHBoxLayout()
        timeline_layout = QVBoxLayout()
        timeline_header = QHBoxLayout()
        title = QLabel("Training and testing timeline")
        heading(title, 13)
        timeline_header.addWidget(title)
        timeline_header.addStretch(1)
        timeline_header.addWidget(QLabel("◆ Assessment    ▲ Modified    × Missing or unusable"))
        timeline_layout.addLayout(timeline_header)
        self.chart = InvestigationChart()
        timeline_layout.addWidget(self.chart, 1)
        self.values_chart = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(utcOffset=0)})
        self.values_chart.setAccessibleName("Dated values for the selected athlete")
        self.values_chart.setMaximumHeight(135)
        self.values_chart.setXLink(self.chart)
        timeline_layout.addWidget(self.values_chart)
        self.summary = wrapping_label()
        timeline_layout.addWidget(self.summary)
        split.addLayout(timeline_layout, 3)
        self.evidence = EvidencePanel()
        self.evidence.selected.connect(self._select_observation)
        self.evidence.followup.clicked.connect(self._open_evidence_tool)
        self.chart.selected.connect(self._select_observation)
        split.addWidget(self.evidence, 1)
        layout.addLayout(split, 1)

        footer = QHBoxLayout()
        self.research_actions = QPushButton("Research actions")
        research = QMenu(self.research_actions)
        self.athlete_record_action = research.addAction("Open athlete record")
        self.athlete_record_action.triggered.connect(self._request_athlete_record)
        research.addSeparator()
        for title, name in (("Plan", "Protocol"), ("Record visits", "Visits and timeline"), ("Run analysis", "Analysis"),
                            ("Saved analyses", "Results"), ("Compare with cohort", "Compare with cohort"),
                            ("Scenarios", "Scenarios"), ("Assessment data", "Data")):
            research.addAction(title, lambda _checked=False, name=name: self.tool_requested.emit(name, None))
        self.research_actions.setMenu(research)
        self.configure = QPushButton("Timeline options")
        options = QMenu(self.configure)
        self.configure_action = options.addAction("Timeline settings…", self._settings)
        self.save_view = QPushButton("Freeze current view…", self)
        self.save_view.hide()
        self.save_view.clicked.connect(self._freeze)
        self.freeze_action = options.addAction("Freeze current view…", self.save_view.click)
        self.method_details = options.addAction("Comparison details…", self._comparison_details)
        self.configure.setMenu(options)
        footer.addWidget(self.research_actions)
        footer.addWidget(self.configure)
        footer.addStretch(1)
        layout.addLayout(footer)

        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Timeline settings")
        form = QFormLayout(self.settings_dialog)
        self.kind = QComboBox()
        self.kind.addItem("All observations", None)
        for key, value in LANES.items():
            self.kind.addItem(value[0], key)
        self.outcome = QComboBox()
        self.source_version = QComboBox()
        self.plots = QComboBox()
        self.date_from = QLineEdit()
        self.date_to = QLineEdit()
        self.week_one = QLineEdit()
        self.offset = QLineEdit("+00:00")
        self._calendar_fields = (self.date_from, self.date_to, self.week_one, self.offset)
        for label, field in (
            ("Show events", self.kind), ("Assessment outcome", self.outcome), ("Source version", self.source_version),
            ("Additional value plot", self.plots), ("Start date", self.date_from), ("End date", self.date_to),
            ("Documented Week 1", self.week_one), ("Calendar UTC offset", self.offset),
        ):
            form.addRow(label, field)
            field.setAccessibleName(label)
        for field in self._calendar_fields[:-1]:
            field.setPlaceholderText("YYYY-MM-DD")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.settings_dialog.accept)
        buttons.rejected.connect(self.settings_dialog.reject)
        form.addRow(buttons)
        self.plots.currentIndexChanged.connect(self._plot_values)
        self._render()

    def _request_athlete_record(self) -> None:
        subject = self.scope.currentData()
        if self.view and not self.saved and subject and not subject.startswith("cohort:"):
            self.athlete_record_requested.emit(subject)

    def set_theme(self, theme):
        self.chart.set_theme(theme)
        self._draw_chart()

    def _settings(self):
        fields = (self.kind, self.outcome, self.source_version, self.plots, *self._calendar_fields)
        previous = [item.currentIndex() if isinstance(item, QComboBox) else item.text() for item in fields]
        if self.settings_dialog.exec() == QDialog.DialogCode.Accepted:
            self._query(save_calendar=True)
        else:
            for item, value in zip(fields, previous):
                if isinstance(item, QComboBox):
                    item.setCurrentIndex(value)
                else:
                    item.setText(value)

    def set_context(self, workspace: str | None, revision: str | None, subject: str | None = None,
                    revision_numbers: dict | None = None):
        if revision_numbers is not None:
            self.revision_numbers = revision_numbers
        if (workspace, revision) == (self.workspace, self.revision):
            if subject and (self.saved or self.scope.currentData() != subject):
                self.saved = None
                index = self.scope.findData(subject)
                if index >= 0 and self.scope.currentIndex() != index:
                    self.scope.setCurrentIndex(index)
                else:
                    self.reload(subject)
            return
        changed_workspace = workspace != self.workspace
        if changed_workspace:
            self.scope.blockSignals(True)
            self.scope.clear()
            self.scope.blockSignals(False)
            self._selection_by_scope.clear()
            self._event_selections.clear()
            self._live_model = self._live_result = self._live_pair = None
            self._outcome_message = self._stale = ""
            self._import_change = None
            self._refresh_after_import = False
            for field in self._calendar_fields[:-1]:
                field.clear()
            self.week_one.setText(self.settings.value(f"timeline/{workspace}/week-one", "") if self.settings and workspace else "")
            self.offset.setText(self.settings.value(f"timeline/{workspace}/offset", "+00:00") if self.settings and workspace else "+00:00")
            for picker in (self.kind, self.outcome, self.source_version, self.plots):
                picker.setCurrentIndex(0)
            self.saved = None
        self.workspace, self.revision = workspace, revision
        self.generation += 1
        if self.saved:
            return
        self.view = self.pair = self.comparison = None
        self._render()
        if workspace and revision:
            remembered = self.settings.value(f"timeline/{workspace}/scope", None) if changed_workspace and self.settings else None
            self.reload(subject or remembered, reset=changed_workspace and subject is None and remembered is None)

    @staticmethod
    def _fill(combo, items, selection):
        combo.blockSignals(True)
        combo.clear()
        for label, identity in items:
            combo.addItem(label, identity)
        combo.setCurrentIndex(max(0, combo.findData(selection)))
        combo.blockSignals(False)

    def reload(self, subject: str | None = None, *, reset=False):
        workspace, revision = self.workspace, self.revision
        if not workspace or not revision:
            self._render()
            return
        selection = subject if subject is not None else self.scope.currentData()
        self.generation += 1
        token = self.generation
        self._loading()

        def present(value):
            if token != self.generation or self.saved:
                return
            people, cohorts = value["participants"], value["cohorts"]
            selected = people[0] if reset and selection not in people and people else selection
            if subject is not None and self.settings and subject in people:
                self.settings.setValue(f"timeline/{workspace}/scope", subject)
            self._fill(self.scope, [(f"All athletes ({len(people)})", None),
                *[(f"Athlete {item}", item) for item in people],
                *[(f"Cohort · {row['name']}", f"cohort:{row['id']}") for row in cohorts]], selected)
            self._fill(self.outcome, [("Default assessment outcome", None),
                *[(f"{row['label']} ({row['unit']})", row["id"]) for row in value["metrics"]]], self.outcome.currentData())
            self._fill(self.source_version, [("Latest versions of context sources", None),
                *[(f"{row['source']['name']} · v{row['version']}", row["id"]) for row in reversed(value["sources"])]],
                self.source_version.currentData())
            self._query()

        def load():
            try:
                return timeline.options(workspace, revision), None
            except ERRORS as error:
                return None, str(error)

        def loaded(result):
            if token != self.generation or self.saved:
                return
            options, error = result
            if error:
                self._unavailable(error)
            else:
                present(options)

        self.run_task(load, loaded, "Loading investigation")

    def _loading(self):
        self.view = self.pair = self.comparison = None
        self._render()
        self.finding.setText("Loading investigation…")
        self.comparison_summary.clear()

    def _unavailable(self, message):
        self.view = self.pair = self.comparison = None
        self._render()
        self.finding.setText("Investigation unavailable")
        self.comparison_summary.setText(message)

    def _scope_changed(self, *_):
        if self.settings and self.workspace and self.scope.count() and not self.saved:
            self.settings.setValue(f"timeline/{self.workspace}/scope", self.scope.currentData() or "")
        self._query()

    def _query(self, *_, save_calendar=False):
        if not self.revision or self.saved:
            return
        scope = self.scope.currentData()
        cohort_id = scope.removeprefix("cohort:") if scope and scope.startswith("cohort:") else None
        source = self.source_version.currentData()
        self.generation += 1
        token, workspace, revision = self.generation, self.workspace, self.revision
        try:
            query = timeline.TimelineQuery(
                subject_id=None if cohort_id else scope, cohort_id=cohort_id,
                metric_id=self.outcome.currentData(), kind=self.kind.currentData(),
                source_versions=[source] if source else None,
                start=self.date_from.text().strip() or None, end=self.date_to.text().strip() or None,
                week_one=self.week_one.text().strip() or None, local_offset=self.offset.text().strip(),
            )
            timeline._calendar(query)
        except ValueError as error:
            self._unavailable(str(error))
            return
        self._loading()

        def load():
            try:
                return timeline.build(workspace, revision, query), None
            except ERRORS as error:
                return None, str(error)

        def present(result):
            if token != self.generation or self.saved:
                return
            view, error = result
            if error:
                self._unavailable(error)
                return
            old = self._live_model
            old_pair, old_result = self._live_pair, self._live_result
            same_scope = old and all(old["query"][field] == view["query"][field] for field in (
                "subject_id", "cohort_id", "metric_id"))
            approved_import = self._refresh_after_import
            self._refresh_after_import = False
            self.view = self._live_model = view
            if save_calendar and self.settings:
                self.settings.setValue(f"timeline/{workspace}/week-one", self.week_one.text().strip())
                self.settings.setValue(f"timeline/{workspace}/offset", query.local_offset)
            if not same_scope:
                self._stale = ""
            if same_scope and old != view and (old_result or self._stale) and not approved_import:
                self._stale = self._stale_reason(old, view)
            if old == view:
                self.pair, self.comparison = old_pair, old_result
            self._live_pair, self._live_result = self.pair, self.comparison
            self._render()
            if self.comparison_controls.isVisibleTo(self) and not self.comparison and not self._stale:
                self._compare()
            if approved_import:
                self._show_import_outcome(old, old_result)

        self.run_task(load, present, "Aligning training and testing")

    @staticmethod
    def _stale_reason(old, view):
        if old["revision_id"] != view["revision_id"]:
            return "The data revision changed."
        if old["query"] != view["query"]:
            return "The timeline settings changed."
        return "The source records or protocol conduct changed."

    def _import(self):
        dialog = ContextSourceDialog(self.workspace, self.revision, self)
        if not dialog.choose_file() or dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._import_change = None
        if dialog.held:
            self._outcome_message = f"Quarantined {dialog.held['filename']}. The investigation is unchanged."
            self._set_import_outcome()
            return
        receipt = dialog.attachment
        self._outcome_message = f"Imported {receipt['source']['name']} · version {receipt['version']}."
        self._refresh_after_import = not bool(self._stale)
        self.reload()

    def _show_import_outcome(self, prior_view, prior_result):
        if prior_result and self.comparison and prior_view:
            def loads(view, result):
                identities = {item["id"]: item["source"]["id"] for item in view["sources"]}
                return {identities[key]: item["recorded_load_sum_au"]
                        for key, item in result["between_exclusive_dates_by_source"].items()}
            before, after = loads(prior_view, prior_result), loads(self.view, self.comparison)
            for identity, value in after.items():
                if value is not None and before.get(identity) is not None and before[identity] != value:
                    names = {item["source"]["id"]: item["source"]["name"] for item in self.view["sources"]}
                    change = f"{before[identity]:,.8g} → {value:,.8g} AU"
                    self._import_change = (self.revision, self.pair, f"{names[identity]} · recorded load between assessments {change}.")
        self._set_import_outcome()

    def _set_import_outcome(self):
        message = self._outcome_message if not self.saved else ""
        if message and self._import_change and self._import_change[:2] == (self.revision, self.pair):
            message += " " + self._import_change[2]
        self.import_outcome.setText(message)
        self.import_outcome.setVisible(bool(message))

    def _revision_label(self, revision):
        number = self.revision_numbers.get(revision)
        return f"Revision {number}" if number is not None else "Data revision" if revision else "No data"

    def _controls(self):
        frozen = bool(self.saved)
        ready = bool(self.view)
        self.scope.setVisible(not frozen)
        self.scope.setEnabled(bool(self.revision and self.scope.count() and not frozen))
        self.pinned_scope.setVisible(frozen)
        self.pinned_dates.setVisible(frozen and bool(self.comparison))
        self.configure.setEnabled(ready)
        self.configure_action.setVisible(not frozen)
        self.configure_action.setEnabled(ready and not frozen)
        scope = self.scope.currentData()
        self.research_actions.setVisible(not frozen)
        self.research_actions.setEnabled(bool(ready and scope and not scope.startswith("cohort:")))
        self.add_source.setVisible(not frozen)
        self.add_source.setEnabled(ready and not frozen)
        self.live_view.setVisible(frozen)
        self.open_view.setVisible(not frozen)
        self.open_view.setEnabled(bool(self.workspace))
        can_freeze = bool(ready and self.view["events"] and not self._stale and not frozen)
        self.save_view.setEnabled(can_freeze)
        self.freeze_action.setVisible(not frozen)
        self.freeze_action.setEnabled(can_freeze)
        revision = self.view["revision_id"] if frozen else self.revision
        self.mode.setText(f"{'FROZEN' if frozen else 'LIVE'} · {self._revision_label(revision)}")
        self.mode.setToolTip(revision or "")
        self.mode.setProperty("frozen", frozen)
        theme.repolish(self.mode)
        if frozen:
            view = self.view
            label = (view.get("cohort") or {}).get("name") or (
                f"Athlete {view['subject_ids'][0]}" if len(view["subject_ids"]) == 1 else f"{len(view['subject_ids'])} athletes")
            self.pinned_scope.setText(label)
        self._set_import_outcome()

    def _render(self):
        self._controls()
        view = self.view or {}
        kind = view.get("query", {}).get("kind")
        self.visible_rows = [row for row in view.get("events", []) if not kind or row["kind"] == kind]
        self._assessments()
        self._draw_chart()
        self.evidence.load(self.visible_rows)
        reference = self.comparison["reference"]["id"] if self.comparison else self.first.currentData()
        if self.visible_rows:
            selected = self._event_selections.get(self._event_scope())
            saved_index = next((i for i, row in enumerate(self.visible_rows) if self._event_key(row) == selected), None)
            first_assessment = next((i for i, row in enumerate(self.visible_rows) if row.get("id") == reference), 0)
            self._select_observation(first_assessment if saved_index is None else saved_index)
        if self.view:
            self._plot_options(self.visible_rows)
        else:
            self.values_chart.hide()
        notes = view.get("notes", [])
        note = notes[0] if notes else (
            "Actual conduct appears only at documented visits." if any(row["kind"] == "VISIT" for row in self.visible_rows) else "")
        self.summary.setText(note)
        self.summary.setToolTip("\n".join(notes))
        self._show_comparison()

    def _draw_chart(self):
        view = self.view or {}
        pair = self.pair
        if self.comparison:
            pair = (self.comparison["reference"]["id"], self.comparison["comparison"]["id"])
        self.chart.render(self.visible_rows, view.get("query", {}).get("local_offset", "+00:00"), pair or ())
        if hasattr(self, "evidence"):
            self.chart.highlight(self.evidence.picker.currentIndex())

    def _event_scope(self):
        return (self.view["revision_id"], self.saved["id"] if self.saved else None, self._scope_key())

    @staticmethod
    def _event_key(row):
        period = row.get("period") or {}
        return (row["kind"], row["subject_id"], row.get("id"), row.get("record_id"), row.get("investigation_id"),
                (row.get("visit") or {}).get("id"), period.get("label"), row.get("source_name"))

    def _open_evidence_tool(self):
        index = self.evidence.picker.currentIndex()
        if self.saved or not 0 <= index < len(self.visible_rows):
            return
        row = self.visible_rows[index]
        name = {"PLAN": "Protocol", "VISIT": "Visits and timeline"}.get(row["kind"])
        if name:
            self.tool_requested.emit(name, row)

    def _select_observation(self, index):
        if not 0 <= index < len(self.visible_rows):
            return
        self.evidence.picker.blockSignals(True)
        self.evidence.picker.setCurrentIndex(index)
        self.evidence.picker.blockSignals(False)
        row = self.visible_rows[index]
        self._event_selections[self._event_scope()] = self._event_key(row)
        self.evidence.show_row(row, self.view)
        followup = {"PLAN": "Review protocol…", "VISIT": "Review recorded visit…"}.get(row["kind"])
        self.evidence.followup.setVisible(bool(followup and not self.saved))
        if followup:
            self.evidence.followup.setText(followup)
        self.chart.highlight(index)

    def _plot_options(self, events):
        selected = self.plots.currentData()
        self.value_series = {}
        if self.view and len(self.view["subject_ids"]) == 1:
            for row in events:
                kind = row["kind"]
                if kind == "ASSESSMENT" and row["value"] is not None:
                    key, label, unit, value = ("assessment", row["measure"]), row["measure"], row["unit"], row["value"]
                elif kind == "TRAINING" and row["session_load_au"] is not None:
                    key = ("load", row["context_source_id"])
                    label, unit, value = f"Session load · {row['source_name']}", "AU", row["session_load_au"]
                elif kind == "WELLNESS" and row["value"] is not None:
                    key = ("wellness", row["context_source_id"], row["questionnaire"], row["questionnaire_version"], row["measure"])
                    label = f"{row['measure']} · {row['questionnaire']} v{row['questionnaire_version']} · {row['source_name']}"
                    unit, value = row["unit"], row["value"]
                else:
                    continue
                series = self.value_series.setdefault(key, {"label": label, "unit": unit, "kind": kind, "points": []})
                series["points"].append((row["axis_time"], value))
        self._fill(self.plots, [("Timeline only", None), *[
            (f"{series['label']} ({series['unit']})", key) for key, series in self.value_series.items()]], selected)
        self._plot_values()

    def _plot_values(self, *_):
        key = self.plots.currentData()
        series = self.value_series.get(tuple(key)) if key else None
        self.values_chart.clear()
        self.values_chart.setVisible(bool(series))
        if series:
            x, y = zip(*series["points"])
            self.values_chart.getAxis("bottom").utcOffset = self.chart.getAxis("bottom").utcOffset
            self.values_chart.setLabel("left", series["unit"])
            self.values_chart.plot(x, y, pen=None, symbol="o", symbolBrush=self.chart.lane_color(series["kind"]), symbolSize=7)

    @staticmethod
    def _assessment_key(row):
        return row["subject_id"], row["session_id"]

    def _scope_key(self):
        query = self.view["query"]
        return query["subject_id"], query["cohort_id"], query["metric_id"]

    def _assessments(self):
        events = [row for row in (self.view or {}).get("events", []) if row["kind"] == "ASSESSMENT"]
        can_compare = bool(self.view and len(self.view["subject_ids"]) == 1 and len(events) >= 2 and not self.saved)
        self.comparison_controls.setVisible(can_compare)
        self.compare_button.setVisible(False)
        if not can_compare:
            return
        saved = self._selection_by_scope.get(self._scope_key())
        for position, picker in enumerate((self.first, self.second)):
            target = saved[position] if saved else self._assessment_key(events[0 if position == 0 else -1])
            selected = next((row["id"] for row in events if self._assessment_key(row) == target), None)
            items = [(date_label(row["date"]), row["id"]) for row in events]
            self._fill(picker, [("Choose assessment", None), *items] if selected is None else items, selected)

    def _pair_changed(self):
        if self._stale:
            return
        self._compare()

    def _compare(self):
        if not self.view or self.saved:
            return
        pair = (self.first.currentData(), self.second.currentData())
        self.pair = self.comparison = self._live_pair = self._live_result = None
        try:
            result = timeline.compare(self.view, *pair)
        except ValueError as error:
            self.finding.setText("Choose a comparable assessment pair")
            self.comparison_summary.setText(str(error))
            self._draw_chart()
            return
        self._stale = ""
        self.pair = self._live_pair = pair
        self.comparison = self._live_result = result
        self._selection_by_scope[self._scope_key()] = tuple(self._assessment_key(result[key]) for key in ("reference", "comparison"))
        self._controls()
        self._show_comparison()
        self._draw_chart()
        for index, row in enumerate(self.visible_rows):
            if row.get("id") == pair[0]:
                self._select_observation(index)
                break

    def _show_comparison(self):
        result = self.comparison
        self.method_details.setEnabled(bool(self.view))
        self.compare_button.setVisible(bool(self._stale and not self.saved and self.comparison_controls.isVisibleTo(self)))
        self.compare_button.setText("Recompute comparison" if self._stale else "Compare assessments")
        if not result:
            if self.saved:
                self.finding.setText(self.saved["title"])
                self.comparison_summary.setText("This frozen view contains timeline evidence without a saved comparison.")
            elif self._stale and self.view:
                self.finding.setText("Comparison needs an update")
                suffix = " Recompute for the selected assessments." if self.compare_button.isVisibleTo(self) else " Two dated assessments are required."
                self.comparison_summary.setText(self._stale + suffix)
            else:
                self.finding.setText("Athlete investigation")
                self.comparison_summary.setText("Choose one athlete with two dated assessments to see observed change."
                                                if self.revision else "Attach research data with a participant roster to start.")
            return
        first, second = result["reference"], result["comparison"]
        metric = (self.view.get("metric") or {}).get("label", "")
        outcome = f"CMJ {metric.lower()}" if (self.view.get("metric") or {}).get("id") == measurement_trust.METRIC else metric.lower()
        dates = f"{date_label(first['date'])} → {date_label(second['date'])}"
        self.pinned_dates.setText(dates)
        assessments = {row["id"]: row for row in self.view["events"] if row["kind"] == "ASSESSMENT"}
        sessions = [assessments.get(item["id"], {}) for item in (first, second)]
        synthetic = any(row.get("acquisition", {}).get("rights_status") == "FIXTURE_ONLY" for row in sessions)
        if result["change"] is None:
            self.finding.setText(f"Comparison unavailable · {outcome}")
            message = " ".join(result["reasons"])
            left, right = (row.get("n_trials") for row in sessions)
            if left is not None and right is not None and left != right:
                message += f" Reference trials {left} · Follow-up trials {right}."
            if synthetic:
                message += " Synthetic fixture."
        else:
            self.finding.setText(f"{result['change']:+.3g} {result['unit']} · observed {outcome} change")
            message = "Comparable for this descriptive comparison. Meaningful change has not been established."
            if synthetic:
                message = "Comparable for description · synthetic fixture. Meaningful change has not been established."
        values = (f"Session means · {first['value']:g} → {second['value']:g} {result['unit']}\n"
                  if first["value"] is not None and second["value"] is not None else "")
        sources = {item["id"]: item for item in self.view["sources"]}
        loads = []
        for key, item in result["between_exclusive_dates_by_source"].items():
            if item["recorded_load_sum_au"] is not None:
                name = sources[key]["source"]["name"]
                loads.append(f"{name} · {item['recorded_load_sum_au']:,.8g} AU over {item['sessions_with_load']} sessions")
        title = f"{self.saved['title']}\n" if self.saved else ""
        self.comparison_summary.setText(f"{title}{values}{message}" + (
            "\nBetween assessment dates · " + "  |  ".join(loads) if loads else ""))

    def _comparison_details(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Comparison details and limitations")
        layout = QVBoxLayout(dialog)
        text = QTextBrowser()
        lines = [self.finding.text(), self.comparison_summary.text(), *self.view["limitations"], *self.view["notes"]]
        if self.comparison:
            names = {item["id"]: item["source"]["name"] for item in self.view["sources"]}
            for key, item in self.comparison["between_exclusive_dates_by_source"].items():
                lines.append(names[key] + "\n" + "\n".join(
                    f"{value} · {readable(name)}" for name, value in item["counts"].items()))
        if self.saved:
            lines.extend((self.saved["id"], f"SHA-256 {self.saved['content_hash']}"))
        text.setPlainText("\n\n".join(lines))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        fit_dialog(dialog, 700, 460)
        dialog.exec()

    def _freeze(self):
        if not self.view or self.saved or self._stale:
            return
        title, confirmed = QInputDialog.getText(self, "Freeze investigation", "Saved investigation name")
        if not confirmed:
            return
        view, pair, token = self.view, self.pair, self.generation
        self.run_task(lambda: timeline.freeze(view, title, pair),
                      lambda record: self._show_saved(record) if token == self.generation else None,
                      "Freezing investigation")

    def _open(self):
        workspace, token = self.workspace, self.generation

        scope = self.scope.currentData()

        def choose(records):
            if workspace != self.workspace or token != self.generation:
                return
            if scope and not scope.startswith("cohort:"):
                records = [row for row in records if json.loads(row["participants"] or "[]") == [scope]]
            if not records:
                self.summary.setText("No frozen investigations for this selection. The Study archive shows all saved views.")
                return
            labels = {
                f"{row['title']} · {self._revision_label(row['revision_id'])} · "
                f"{row['created_at'][:10]} ({i})": row["id"] for i, row in enumerate(records, 1)}
            selected, confirmed = QInputDialog.getItem(self, "Frozen investigations", "Open a saved investigation",
                                                        list(labels), editable=False)
            if confirmed:
                self.open_saved(labels[selected])

        self.run_task(lambda: timeline.history(workspace), choose, "Reading frozen investigations")

    def open_saved(self, view_id):
        workspace = self.workspace
        self.generation += 1
        token = self.generation
        self.run_task(lambda: timeline.reopen(workspace, view_id),
                      lambda record: self._show_saved(record) if token == self.generation else None,
                      "Opening frozen investigation")

    def _show_saved(self, record):
        if self.workspace != record["view"]["workspace_id"]:
            return
        self.generation += 1
        self.saved, self.view = record, record["view"]
        self.pair, self.comparison = None, record["comparison"]
        self._render()
        self.live_view.setFocus()

    def _live(self):
        self.saved = None
        self.reload()
        self.scope.setFocus()
