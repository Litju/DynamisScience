"""Native source review and dated observations for Training Exposure & Testing Context."""

from __future__ import annotations

import getpass
import json
from pathlib import Path

import polars as pl
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from .. import admission, context_timeline as timeline, measurement_trust, researchstore as store, training_context as context
from .individual_research import fit_dialog
from .investigation_timeline import EvidencePanel, InvestigationChart, LANES, date_label, heading, readable, wrapping_label

ERRORS = (ValueError, OSError, LookupError, RuntimeError, pl.exceptions.PolarsError)

def _describe(row: dict) -> str:
    if row["kind"] == "PLAN":
        period = row["period"]
        return f"{period['label']} · weeks {period['start']}–{period['end']}"
    if row["kind"] == "VISIT":
        visit = row["visit"]
        observed = (row["observed_period"] or {}).get("label", "Outside plan")
        adherence = f" · {visit['adherence_percent']:g}% adherence" if visit["adherence_percent"] is not None else ""
        return f"Planned {row['period']['label']} · observed {observed} · {visit['exposure']}{adherence}"
    if row["kind"] == "ASSESSMENT":
        value = f"{row['value']:.3g} {row['unit']}" if row["value"] is not None else "Score unavailable"
        return f"{row['session_id']} · {row['measure']} · {value} · {row['valid_trials']}/{row['n_trials']} trials"
    if row["status"] != "OBSERVED":
        return row.get("reason") or row["status"].title()
    if row["kind"] == "TRAINING":
        parts = []
        if row["duration"] is not None:
            parts.append(f"{row['duration']:g} {row['duration_unit']}")
        if row["rpe"] is not None:
            parts.append(f"RPE {row['rpe']:g} {row['rpe_scale']}")
        if row["session_load_au"] is not None:
            parts.append(f"load {row['session_load_au']:g} AU")
        return " · ".join(parts) or "Session recorded"
    return f"{row['measure']} · {row['value']:g} {row['unit']}"


def _pairs(text: str) -> dict[str, str]:
    pairs = {}
    for assignment in filter(str.strip, text.split(";")):
        key, separator, value = assignment.partition("=")
        if not separator or not key.strip() or not value.strip() or key.strip() in pairs:
            raise ValueError("Enter unique field=value pairs separated by semicolons.")
        pairs[key.strip()] = value.strip()
    return pairs


class SourceRegistration(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Register a context source")
        layout = QFormLayout(self)
        fields = (
            ("id", "Source identifier"), ("name", "Source label"), ("publisher", "Provider"),
            ("dataset_identity", "Dataset identity"), ("version", "Provider version"),
            ("license_or_agreement", "Licence or agreement"),
            ("redistribution_restrictions", "Redistribution terms"),
        )
        self.fields = {key: QLineEdit() for key, _ in fields}
        for key, label in fields:
            layout.addRow(label, self.fields[key])
        self.privacy = QComboBox()
        self.privacy.addItems(["DEIDENTIFIED", "PSEUDONYMOUS", "IDENTIFIABLE", "TEST_FIXTURE"])
        layout.addRow("Source classification", self.privacy)
        self.reviewer = QLineEdit(getpass.getuser())
        layout.addRow("Rights reviewer", self.reviewer)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton("Confirm research rights and register", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.register)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        fit_dialog(self, 640, 380)

    def register(self):
        reviewer = self.reviewer.text().strip()
        if not reviewer:
            self.error.setText("Enter the researcher who reviewed the source permissions.")
            return
        fields = {key: field.text().strip() for key, field in self.fields.items()}
        privacy = self.privacy.currentText()
        try:
            self.source = admission.register_source({
                **fields, "privacy_status": privacy, "acquisition_method": context.SOURCE_METHOD,
                "permitted_uses": ["research"],
                "rights_status": "FIXTURE_ONLY" if privacy == "TEST_FIXTURE" else "VERIFIED",
                "rights_verified_by": reviewer, "rights_verified_at": store._now(),
            })
        except ERRORS as error:
            self.error.setText(str(error))
            return
        self.accept()


class ContextSourceDialog(QDialog):
    def __init__(self, workspace: str, revision: str, parent):
        super().__init__(parent)
        self.workspace, self.revision = workspace, revision
        self.file = None
        self.reviewed = None
        self.setWindowTitle("Review training and wellness source")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.sources = QComboBox()
        source_row = QHBoxLayout()
        source_row.addWidget(self.sources, 1)
        register = QPushButton("Register source…")
        register.clicked.connect(self._register)
        source_row.addWidget(register)
        form.addRow("Authorized source", source_row)
        self.file_button = QPushButton("Choose source file…")
        self.file_button.clicked.connect(self._choose)
        form.addRow("Export", self.file_button)
        self.columns = QLineEdit()
        self.columns.setPlaceholderText("Optional, e.g. participant=Athlete; occurred_at=Timestamp")
        form.addRow("Column mapping", self.columns)
        self.participants = QLineEdit()
        self.participants.setPlaceholderText("Optional, e.g. External07=A07")
        form.addRow("Confirmed athlete aliases", self.participants)
        self.reviewer = QLineEdit(getpass.getuser())
        form.addRow("Reviewed by", self.reviewer)
        layout.addLayout(form)
        self.details = QTextBrowser()
        layout.addWidget(self.details, 1)
        self.details.setPlainText(
            "Required columns: participant, record_id, kind, status. Use TRAINING or WELLNESS. "
            "Provide actual time for observed data and scheduled time plus reason for missing or omitted data. "
            "Timestamp values require an explicit UTC offset. Use min or s for duration and CR10 for session RPE. "
            "Wellness uses measure, value, unit, questionnaire and questionnaire_version. "
            "Each source revision includes its previous record IDs.\n\n"
            "Optional fields: " + ", ".join(context.OPTIONAL)
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.preview_button = buttons.addButton("Preview QC and mappings", QDialogButtonBox.ButtonRole.ActionRole)
        self.attach_button = buttons.addButton("Approve attachment", QDialogButtonBox.ButtonRole.AcceptRole)
        self.attach_button.setEnabled(False)
        buttons.rejected.connect(self.reject)
        self.preview_button.clicked.connect(self._preview)
        self.attach_button.clicked.connect(self._attach)
        layout.addWidget(buttons)
        self._sources()
        for field in (self.columns, self.participants, self.reviewer):
            field.textChanged.connect(self._invalidate)
        self.sources.currentIndexChanged.connect(self._invalidate)
        fit_dialog(self, 800, 570)

    def _sources(self, selected=None):
        self.sources.clear()
        self.sources.addItem("Choose a research source", None)
        for source in admission.list_sources():
            if (source["rights_status"] in {"VERIFIED", "FIXTURE_ONLY"}
                    and "research" in {str(use).strip().lower() for use in source["permitted_uses"]}):
                self.sources.addItem(f"{source['name']} · {source['rights_status']} · {source['id']}", source["id"])
        if selected:
            self.sources.setCurrentIndex(self.sources.findData(selected))

    def _register(self):
        dialog = SourceRegistration(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._sources(dialog.source["id"])

    def _invalidate(self):
        self.reviewed = None
        self.attach_button.setEnabled(False)

    def _choose(self):
        file, _ = QFileDialog.getOpenFileName(self, "Choose training or wellness export",
                                               filter="Context files (*.csv *.tsv *.xlsx *.parquet *.pq)")
        if file:
            self.file = Path(file)
            self.file_button.setText(self.file.name)
            self._invalidate()

    def _preview(self):
        self._invalidate()
        try:
            if not self.file or not self.sources.currentData() or not self.reviewer.text().strip():
                raise ValueError("Choose a file and authorized source, and enter the reviewer.")
            mapping = context.SourceMapping(columns=_pairs(self.columns.text()), participants=_pairs(self.participants.text()))
            receipt, rows = context.preview(self.workspace, self.revision, self.sources.currentData(), self.file, mapping)
        except ERRORS as error:
            self.details.setPlainText(str(error))
            return
        self.reviewed = (mapping, receipt)
        self.attach_button.setEnabled(True)
        policy = receipt["source"]
        self.details.setPlainText(
            f"{receipt['row_count']:,} rows · Proposed source version {receipt['version']}\n"
            f"{policy['name']} · {policy['rights_status']} · {policy['license_or_agreement']}\n"
            f"SHA-256 {receipt['raw_sha256']}\n"
            f"Change from prior source version: {receipt['changes']}\n"
            f"QC and missingness: {receipt['qc'] or 'No flagged rows'}\n"
            f"Unused columns: {', '.join(receipt['unused_columns']) or 'None'}\n\n"
            + "\n".join(f"{item.external_id} → {item.subject_id}" for item in {
                row.external_id: row for row in rows}.values())
            + "\n\nSource observations\n"
            + "\n".join(f"{row.kind} · {row.record_id} · {_describe(row.model_dump())}" for row in rows[:25])
        )

    def _attach(self):
        if not self.reviewed:
            return
        mapping, receipt = self.reviewed
        try:
            self.attachment = context.attach(self.workspace, self.revision, self.sources.currentData(),
                                             self.file, mapping, receipt, self.reviewer.text())
        except ERRORS as error:
            self.details.setPlainText(str(error))
            self._invalidate()
            return
        self.accept()


class TrainingContextPanel(QWidget):
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
        self._stale = self._outcome_message = ""
        self._refresh_after_import = False
        self.visible_rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        context_row = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.setAccessibleName("Athlete or cohort")
        self.scope.setMinimumContentsLength(12)
        self.scope.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.scope.currentIndexChanged.connect(self._query)
        self.mode = QLabel()
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
        self.finding.setTextFormat(Qt.TextFormat.PlainText)
        heading(self.finding, 21)
        layout.addWidget(self.finding)
        finding_row = QHBoxLayout()
        self.comparison_summary = wrapping_label()
        finding_row.addWidget(self.comparison_summary, 1)
        self.compare_button = QPushButton("Compare assessments")
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
        self.chart.selected.connect(self._select_observation)
        split.addWidget(self.evidence, 1)
        layout.addLayout(split, 1)

        footer = QHBoxLayout()
        self.configure = QPushButton("Timeline settings…")
        self.configure.clicked.connect(self._settings)
        self.save_view = QPushButton("Freeze current view…")
        self.save_view.clicked.connect(self._freeze)
        self.method_details = QPushButton("Comparison details…")
        self.method_details.clicked.connect(self._comparison_details)
        for action in (self.configure, self.save_view, self.method_details):
            footer.addWidget(action)
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
            if subject and self.scope.findData(subject) >= 0 and not self.saved:
                self.scope.setCurrentIndex(self.scope.findData(subject))
            return
        changed_workspace = workspace != self.workspace
        if changed_workspace:
            self.scope.clear()
            self._selection_by_scope.clear()
            self._live_model = self._live_result = self._live_pair = None
            self._outcome_message = self._stale = ""
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
            self.reload(subject, reset=changed_workspace)

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
        if dialog.exec() == QDialog.DialogCode.Accepted:
            receipt = dialog.attachment
            self._outcome_message = f"Imported {receipt['source']['name']} · version {receipt['version']}."
            self._refresh_after_import = not bool(self._stale)
            self.reload()

    def _show_import_outcome(self, prior_view, prior_result):
        if prior_result and self.comparison and prior_view:
            def loads(view, result):
                names = {item["id"]: item["source"]["name"] for item in view["sources"]}
                return {names[key]: item["recorded_load_sum_au"]
                        for key, item in result["between_exclusive_dates_by_source"].items()}
            before, after = loads(prior_view, prior_result), loads(self.view, self.comparison)
            for name, value in after.items():
                if value is not None and before.get(name) is not None and before[name] != value:
                    self._outcome_message += f" {name} · recorded load between assessments {before[name]:,.0f} → {value:,.0f} AU."
        self._set_import_outcome()

    def _set_import_outcome(self):
        message = self._outcome_message if not self.saved else ""
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
        self.configure.setVisible(not frozen)
        self.configure.setEnabled(ready and not frozen)
        self.add_source.setVisible(not frozen)
        self.add_source.setEnabled(ready and not frozen)
        self.live_view.setVisible(frozen)
        self.open_view.setVisible(not frozen)
        self.open_view.setEnabled(bool(self.workspace))
        self.save_view.setVisible(not frozen)
        self.save_view.setEnabled(bool(ready and self.view["events"] and not self._stale and not frozen))
        revision = self.view["revision_id"] if frozen else self.revision
        self.mode.setText(f"{'FROZEN' if frozen else 'LIVE'} · {self._revision_label(revision)}")
        self.mode.setToolTip(revision or "")
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
        first_assessment = next((i for i, row in enumerate(self.visible_rows) if row.get("id") == reference), 0)
        if self.visible_rows:
            self._select_observation(first_assessment)
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

    def _select_observation(self, index):
        if not 0 <= index < len(self.visible_rows):
            return
        self.evidence.picker.blockSignals(True)
        self.evidence.picker.setCurrentIndex(index)
        self.evidence.picker.blockSignals(False)
        self.evidence.show_row(self.visible_rows[index], self.view)
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
        values = (f" · {first['value']:g} → {second['value']:g} {result['unit']}"
                  if first["value"] is not None and second["value"] is not None else "")
        sources = {item["id"]: item for item in self.view["sources"]}
        loads = []
        for key, item in result["between_exclusive_dates_by_source"].items():
            if item["recorded_load_sum_au"] is not None:
                name = sources[key]["source"]["name"]
                loads.append(f"{name} · {item['recorded_load_sum_au']:,.0f} AU over {item['sessions_with_load']} sessions")
        title = f"{self.saved['title']} · " if self.saved else ""
        self.comparison_summary.setText(f"{title}{dates}{values}\n{message}" + (
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

        def choose(records):
            if workspace != self.workspace or token != self.generation:
                return
            if not records:
                self.summary.setText("There are no frozen investigations in this workspace.")
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
