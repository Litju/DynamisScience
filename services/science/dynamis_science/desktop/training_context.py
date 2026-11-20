"""Native source review and dated observations for Training Exposure & Testing Context."""

from __future__ import annotations

import getpass
import json
from datetime import datetime
from pathlib import Path

import polars as pl
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from .. import admission, context_timeline as timeline, researchstore as store, training_context as context
from .individual_research import fit_dialog

TITLE = "Training Exposure & Testing Context"
ERRORS = (ValueError, OSError, LookupError, RuntimeError, pl.exceptions.PolarsError)
LANES = {
    "PLAN": ("Planned phase", "#d5a95f"), "VISIT": ("Conduct", "#50aedd"),
    "TRAINING": ("Training", "#38a69d"), "WELLNESS": ("Wellness", "#9784db"),
    "ASSESSMENT": ("Testing", "#ea8b90"),
}


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
    def __init__(self, run_task):
        super().__init__()
        self.run_task = run_task
        self.workspace = self.revision = None
        self.generation = 0
        self.view = None
        self.saved = None
        self.pair = None
        self.comparison = None
        self.visible_rows = []
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.setAccessibleName("Timeline athlete or cohort")
        self.kind = QComboBox()
        self.kind.setAccessibleName("Observation type")
        self.kind.addItem("All observations", None)
        for key, value in LANES.items():
            self.kind.addItem(value[0], key)
        self.add_source = QPushButton("Import context source…")
        self.add_source.clicked.connect(self._import)
        self.save_view = QPushButton("Freeze view…")
        self.save_view.clicked.connect(self._freeze)
        self.open_view = QPushButton("Open saved view…")
        self.open_view.clicked.connect(self._open)
        self.live_view = QPushButton("Return to live timeline")
        self.live_view.clicked.connect(self._live)
        controls.addWidget(self.scope, 2)
        controls.addWidget(self.kind, 1)
        controls.addWidget(self.add_source)
        controls.addWidget(self.save_view)
        controls.addWidget(self.open_view)
        controls.addWidget(self.live_view)
        layout.addLayout(controls)
        self.filters = QWidget()
        filters = QHBoxLayout(self.filters)
        filters.setContentsMargins(0, 0, 0, 0)
        self.outcome = QComboBox()
        self.outcome.setAccessibleName("Assessment outcome")
        self.source_version = QComboBox()
        self.source_version.setAccessibleName("Context source version")
        self.date_from = QLineEdit()
        self.date_to = QLineEdit()
        self.week_one = QLineEdit()
        self.offset = QLineEdit("+00:00")
        for field, label in ((self.date_from, "Start date"), (self.date_to, "End date"),
                             (self.week_one, "Week 1 date"), (self.offset, "Fixed UTC offset")):
            field.setAccessibleName(label)
            field.setToolTip(label + (" (YYYY-MM-DD)" if field is not self.offset else " such as -03:00"))
            if field is not self.offset:
                field.setPlaceholderText(label)
            field.setMaximumWidth(105)
        apply = QPushButton("Apply date window")
        apply.setToolTip("Apply the date range and optional documented Week 1 start and fixed UTC offset")
        apply.clicked.connect(self._query)
        for widget in (self.outcome, self.source_version, self.date_from, self.date_to, self.week_one, self.offset, apply):
            filters.addWidget(widget, 1 if isinstance(widget, QComboBox) else 0)
        layout.addWidget(self.filters)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.chart = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(utcOffset=0)})
        self.chart.setAccessibleName("Dated training, wellness, testing and planned phases")
        self.chart.setLabel("bottom", "UTC")
        self.chart.setMouseEnabled(x=True, y=False)
        self.chart.setMaximumHeight(220)
        self.chart.getAxis("left").setTicks([[(i + 1, item[0]) for i, item in enumerate(LANES.values())]])
        self.chart.setYRange(0.5, len(LANES) + 0.5, padding=0)
        layout.addWidget(self.chart)
        self.plots = QComboBox()
        self.plots.setAccessibleName("Plot recorded values for the selected athlete")
        self.plots.currentIndexChanged.connect(self._plot_values)
        layout.addWidget(self.plots)
        self.values_chart = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(utcOffset=0)})
        self.values_chart.setAccessibleName("Selected athlete's dated measurement values")
        self.values_chart.setMaximumHeight(150)
        self.values_chart.setXLink(self.chart)
        layout.addWidget(self.values_chart)
        self.comparison_controls = QWidget()
        comparisons = QHBoxLayout(self.comparison_controls)
        comparisons.setContentsMargins(0, 0, 0, 0)
        self.first = QComboBox()
        self.second = QComboBox()
        self.first.setAccessibleName("Reference assessment")
        self.second.setAccessibleName("Comparison assessment")
        self.compare_button = QPushButton("Compare assessments")
        self.compare_button.clicked.connect(self._compare)
        self.first.currentIndexChanged.connect(self._clear_comparison)
        self.second.currentIndexChanged.connect(self._clear_comparison)
        for widget in (self.first, self.second, self.compare_button):
            comparisons.addWidget(widget, 1 if isinstance(widget, QComboBox) else 0)
        layout.addWidget(self.comparison_controls)
        self.comparison_summary = QLabel()
        self.comparison_summary.setWordWrap(True)
        self.comparison_summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.comparison_summary)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Date / time", "Athlete", "Type", "Observation", "QC", "Source"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.table)
        self.details = QTextBrowser()
        self.details.setAccessibleName("Observation provenance")
        splitter.addWidget(self.details)
        splitter.setSizes([850, 300])
        layout.addWidget(splitter, 1)
        for choice in (self.scope, self.kind, self.outcome, self.source_version):
            choice.currentIndexChanged.connect(self._query)
        self.table.currentCellChanged.connect(self._detail)
        self.set_context(None, None)

    def set_context(self, workspace: str | None, revision: str | None, subject: str | None = None):
        if (workspace, revision) == (self.workspace, self.revision) and workspace:
            if subject and not self.saved:
                index = self.scope.findData(subject)
                if index >= 0:
                    self.scope.setCurrentIndex(index)
            return
        if workspace != self.workspace:
            for field in (self.date_from, self.date_to, self.week_one):
                field.clear()
            self.offset.setText("+00:00")
        self.workspace, self.revision = workspace, revision
        self.generation += 1
        self.view = self.saved = self.pair = self.comparison = None
        self._controls()
        self._render()
        if workspace and revision:
            self.reload(subject, reset=True)

    def reload(self, subject: str | None = None, *, reset=False):
        workspace, revision = self.workspace, self.revision
        if not workspace or not revision:
            return
        selection = subject or (None if reset else self.scope.currentData())
        self.generation += 1
        token = self.generation

        def fill(combo, items, selection):
            combo.blockSignals(True)
            combo.clear()
            for label, identity in items:
                combo.addItem(label, identity)
            combo.setCurrentIndex(max(0, combo.findData(selection)))
            combo.blockSignals(False)

        def present(value):
            if token != self.generation:
                return
            people, cohorts = value["participants"], value["cohorts"]
            fill(self.scope, [(f"All participants ({len(people)})", None),
                 *[(f"Cohort · {row['name']}", f"cohort:{row['id']}") for row in cohorts],
                 *[(item, item) for item in people]], selection)
            fill(self.outcome, [("Default assessment outcome", None),
                 *[(f"{row['label']} ({row['unit']})", row["id"]) for row in value["metrics"]]], self.outcome.currentData())
            fill(self.source_version, [("Latest version of each context source", None),
                 *[(f"{row['source']['name']} · v{row['version']}", row["id"]) for row in reversed(value["sources"])]],
                 self.source_version.currentData())
            self._query()

        self.run_task(lambda: timeline.options(workspace, revision), present, "Loading context sources and participants")

    def _query(self, *_):
        if not self.revision or self.saved:
            return
        identity = self.scope.currentData()
        cohort_id = identity.removeprefix("cohort:") if identity and identity.startswith("cohort:") else None
        source = self.source_version.currentData()
        try:
            query = timeline.TimelineQuery(
                subject_id=None if cohort_id else identity, cohort_id=cohort_id,
                metric_id=self.outcome.currentData(), kind=self.kind.currentData(),
                source_versions=[source] if source else None,
                start=self.date_from.text().strip() or None, end=self.date_to.text().strip() or None,
                week_one=self.week_one.text().strip() or None, local_offset=self.offset.text().strip(),
            )
            timeline._calendar(query)
        except ValueError as error:
            self.summary.setText(str(error))
            self.save_view.setEnabled(False)
            return
        self.generation += 1
        token, workspace, revision = self.generation, self.workspace, self.revision
        self.summary.setText("Loading aligned training and testing events…")
        self.save_view.setEnabled(False)

        def load():
            try:
                return timeline.build(workspace, revision, query), None
            except ERRORS as error:
                return None, str(error)

        def present(result):
            if token != self.generation or self.saved:
                return
            self.view, error = result
            self._clear_comparison()
            self._render()
            if error:
                self.summary.setText(error)

        self.run_task(load, present, "Aligning training context with testing")

    def _import(self):
        dialog = ContextSourceDialog(self.workspace, self.revision, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _controls(self):
        live = bool(self.revision and not self.saved)
        for widget in (self.filters, self.scope, self.kind, self.add_source):
            widget.setEnabled(live)
            widget.setVisible(not self.saved)
        self.live_view.setVisible(bool(self.saved))
        self.open_view.setEnabled(bool(self.workspace))
        self.save_view.setEnabled(bool(live and self.view and self.view["events"]))
        self.save_view.setVisible(not self.saved)

    def _render(self):
        self._controls()
        view = self.view or {}
        kind = view.get("query", {}).get("kind")
        filtered = [row for row in view.get("events", []) if not kind or row["kind"] == kind]
        self.visible_rows = filtered[:1000]
        self.chart.clear()
        calendar = view.get("query", {}).get("local_offset", "+00:00")
        offset = datetime.fromisoformat(f"2000-01-01T00:00:00{calendar}").utcoffset()
        self.chart.getAxis("bottom").utcOffset = -offset.total_seconds()
        self.chart.setLabel("bottom", f"Study calendar · UTC{calendar}")
        for index, (key, (_, color)) in enumerate(LANES.items(), 1):
            if key == "PLAN":
                for start, end in {(row["axis_time"], row["axis_end"]) for row in filtered if row["kind"] == key}:
                    self.chart.plot([start, end], [index, index], pen=pg.mkPen(color, width=5))
                continue
            for observed in (True, False):
                points = [row["axis_time"] for row in filtered if row["kind"] == key
                          and (row["status"] in {"OBSERVED", "MEASURED"}) == observed]
                if points:
                    symbol = "d" if key == "ASSESSMENT" else "o"
                    self.chart.plot(points, [index] * len(points), pen=None, symbol=symbol if observed else "x",
                                    symbolBrush=color, symbolPen=color, symbolSize=8)
        self.chart.enableAutoRange(axis="x")
        self.table.setRowCount(len(self.visible_rows))
        for index, row in enumerate(self.visible_rows):
            when = row.get("occurred_at") or row.get("scheduled_at") or row["date"]
            if row.get("end_date"):
                when = f"{when} – {row['end_date']}"
            flags = row.get("qc") or row.get("quality")
            rights = row.get("rights_status") or row.get("acquisition", {}).get("rights_status")
            source = row["source_name"] + (" · synthetic" if rights == "FIXTURE_ONLY" else "")
            values = (when, row["subject_id"], LANES[row["kind"]][0], _describe(row),
                      ", ".join(flags) if flags else row["status"].title(), source)
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        if self.saved:
            scope = (view.get("cohort") or {}).get("name") or (
                view["subject_ids"][0] if len(view["subject_ids"]) == 1 else f"{len(view['subject_ids'])} participants")
            message = (f"{self.saved['title']} · Frozen · {scope} · {len(filtered):,} records · Revision {view['revision_id']} "
                       f"· SHA-256 {self.saved['content_hash']}")
        elif filtered:
            limit = " · First 1,000 rows shown" if len(filtered) > 1000 else ""
            message = f"{len(filtered):,} records{limit} · × marks missing, omitted or unqualified observations"
        elif self.revision:
            message = "No dated observations for this selection. Import an authorized export or broaden the filters."
        else:
            message = "Attach research data with an existing participant roster to start a timeline."
        if view.get("notes"):
            message += "\n" + view["notes"][0]
        self.summary.setText(message)
        self.summary.setToolTip("\n".join([*view.get("notes", []), *view.get("limitations", [])]))
        self._assessments()
        self._plot_options(filtered)
        if not self.visible_rows:
            self.details.clear()
        else:
            self.table.setCurrentCell(0, 0)
            self._detail()

    def _plot_options(self, events):
        self.plots.blockSignals(True)
        previous = self.plots.currentData()
        self.plots.clear()
        self.plots.addItem("Event timeline only", None)
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
        for key, series in self.value_series.items():
            self.plots.addItem(f"{series['label']} ({series['unit']})", key)
        self.plots.setCurrentIndex(max(0, self.plots.findData(previous)))
        self.plots.blockSignals(False)
        self.plots.setVisible(bool(self.value_series))
        self._plot_values()

    def _plot_values(self, *_):
        selected = self.plots.currentData()
        series = self.value_series.get(tuple(selected)) if selected else None
        self.values_chart.clear()
        self.values_chart.setVisible(bool(series))
        if series:
            x, y = zip(*series["points"])
            self.values_chart.getAxis("bottom").utcOffset = self.chart.getAxis("bottom").utcOffset
            self.values_chart.setLabel("left", series["unit"])
            self.values_chart.plot(x, y, pen=None, symbol="o", symbolBrush=LANES[series["kind"]][1], symbolSize=7)

    def _detail(self, *_):
        index = self.table.currentRow()
        if not 0 <= index < len(self.visible_rows):
            return
        row = self.visible_rows[index]
        receipt = next((item for item in self.view["sources"] if item["id"] == row.get("context_source_id")), None)
        if row["kind"] == "ASSESSMENT":
            receipt = [item for item in self.view["performance"]["sources"] if item["artifact_id"] in row["artifact_ids"]]
        self.details.setPlainText(json.dumps({"observation": row, "source_receipt": receipt,
                                             "alignment_notes": self.view["notes"]}, indent=2, default=str))

    def _assessments(self):
        events = [row for row in (self.view or {}).get("events", []) if row["kind"] == "ASSESSMENT"]
        single = len((self.view or {}).get("subject_ids", [])) == 1
        can_compare = bool(single and len(events) >= 2 and not self.saved)
        self.comparison_controls.setVisible(can_compare)
        if not can_compare:
            return
        for picker, empty, default in ((self.first, "Reference assessment", 1),
                                       (self.second, "Comparison assessment", len(events))):
            picker.blockSignals(True)
            picker.clear()
            picker.addItem(empty, None)
            for row in events:
                picker.addItem(f"{row['date']} · {row['session_id']}", row["id"])
            picker.setCurrentIndex(default)
            picker.blockSignals(False)

    def _clear_comparison(self, *_):
        self.comparison = self.pair = None
        self.comparison_summary.clear()

    def _compare(self):
        pair = (self.first.currentData(), self.second.currentData())
        try:
            self.comparison = timeline.compare(self.view, *pair)
        except ValueError as error:
            self.comparison_summary.setText(str(error))
            return
        self.pair = pair
        self._show_comparison()

    def _show_comparison(self):
        result = self.comparison
        if not result:
            self.comparison_summary.clear()
            return
        first, second = result["reference"], result["comparison"]
        if result["change"] is None:
            headline = "Incomparable. " + " ".join(result["reasons"])
        else:
            headline = f"Observed change {result['change']:+.3g} {result['unit']}."
        names = {item["id"]: item["source"]["name"] for item in self.view["sources"]}
        source_lines = []
        for key, info in result["between_exclusive_dates_by_source"].items():
            counts = ", ".join(f"{n} {name.lower()}" for name, n in info["counts"].items())
            load = info["recorded_load_sum_au"]
            source_lines.append(f"{names[key]} · {counts}" +
                                (f" · {load:g} AU across {info['sessions_with_load']} sessions with load" if load is not None else ""))
        self.comparison_summary.setText(
            f"{first['date']} → {second['date']} · {headline}\nBetween those dates: "
            + ("\n".join(source_lines) or "No recorded context observations.") + "\n" + result["limitations"][0]
        )
        self.comparison_summary.setToolTip("\n".join(result["limitations"]))

    def _freeze(self):
        if not self.view or self.saved:
            return
        title, confirmed = QInputDialog.getText(self, "Freeze contextual research view", "View title")
        if not confirmed:
            return
        view, pair = self.view, self.pair
        self.run_task(lambda: timeline.freeze(view, title, pair), self._show_saved, "Freezing contextual Results")

    def _open(self):
        workspace = self.workspace

        def choose(records):
            if workspace != self.workspace:
                return
            if not records:
                self.summary.setText("No saved contextual research views in this workspace.")
                return
            labels = {f"{row['title']} · {row['created_at'][:16]} · {row['id']}": row["id"] for row in records}
            selected, confirmed = QInputDialog.getItem(self, "Open saved contextual Results", "Saved view",
                                                        list(labels), editable=False)
            if confirmed:
                self.open_saved(labels[selected])

        self.run_task(lambda: timeline.history(workspace), choose, "Reading saved contextual Results")

    def open_saved(self, view_id):
        workspace = self.workspace
        self.run_task(lambda: timeline.reopen(workspace, view_id), self._show_saved, "Opening frozen contextual Results")

    def _show_saved(self, record):
        if self.workspace != record["view"]["workspace_id"]:
            return
        self.generation += 1
        self.saved, self.view = record, record["view"]
        self.pair, self.comparison = None, record["comparison"]
        self._render()
        self._show_comparison()

    def _live(self):
        self.saved = None
        self.reload()
