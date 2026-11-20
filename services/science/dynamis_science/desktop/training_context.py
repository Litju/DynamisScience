"""Native source review and dated observations for Training Exposure & Testing Context."""

from __future__ import annotations

import getpass
import json
from pathlib import Path

import polars as pl
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from .. import admission, researchstore as store, training_context as context
from .individual_research import fit_dialog

TITLE = "Training Exposure & Testing Context"
ERRORS = (ValueError, OSError, LookupError, RuntimeError, pl.exceptions.PolarsError)
LANES = {"TRAINING": ("Training", "#38a69d"), "WELLNESS": ("Wellness", "#9784db")}


def _describe(row: dict) -> str:
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
        self.subject_ids = []
        self.rows = []
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
        controls.addWidget(self.scope, 2)
        controls.addWidget(self.kind, 1)
        controls.addStretch()
        controls.addWidget(self.add_source)
        layout.addLayout(controls)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.chart = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(utcOffset=0)})
        self.chart.setAccessibleName("Dated training and wellness observations")
        self.chart.setLabel("bottom", "UTC")
        self.chart.setMouseEnabled(x=True, y=False)
        self.chart.setMaximumHeight(220)
        self.chart.getAxis("left").setTicks([[(i + 1, item[0]) for i, item in enumerate(LANES.values())]])
        self.chart.setYRange(0.5, 2.5, padding=0)
        layout.addWidget(self.chart)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Recorded event time", "Athlete", "Type", "Observation", "QC", "Source"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.table)
        self.details = QTextBrowser()
        self.details.setAccessibleName("Observation provenance")
        splitter.addWidget(self.details)
        splitter.setSizes([850, 300])
        layout.addWidget(splitter, 1)
        self.scope.currentIndexChanged.connect(self._render)
        self.kind.currentIndexChanged.connect(self._render)
        self.table.currentCellChanged.connect(self._detail)
        self.set_context(None, None)

    def set_context(self, workspace: str | None, revision: str | None, subject: str | None = None):
        if (workspace, revision) == (self.workspace, self.revision) and workspace:
            if subject:
                self.scope.setCurrentIndex(max(0, self.scope.findData(subject)))
            return
        self.workspace, self.revision = workspace, revision
        self.add_source.setEnabled(False)
        self.scope.clear()
        self.subject_ids, self.rows = [], []
        self._render()
        if workspace and revision:
            self.reload(subject)

    def reload(self, subject: str | None = None):
        workspace, revision = self.workspace, self.revision
        if not workspace or not revision:
            return
        selection = subject or self.scope.currentData()

        def load():
            _, record = context.workspace_revision(workspace, revision)
            participants = context.roster(record)
            sources, rows = context.observations(workspace, revision, participants)
            return participants, sources, rows

        def present(value):
            if (workspace, revision) != (self.workspace, self.revision):
                return
            self.subject_ids, self.sources, self.rows = value
            self.scope.blockSignals(True)
            self.scope.clear()
            self.scope.addItem(f"All participants ({len(self.subject_ids)})", None)
            for item in self.subject_ids:
                self.scope.addItem(item, item)
            self.scope.setCurrentIndex(max(0, self.scope.findData(selection)))
            self.scope.blockSignals(False)
            self.add_source.setEnabled(True)
            self._render()

        self.run_task(load, present, "Loading training and wellness context")

    def _import(self):
        dialog = ContextSourceDialog(self.workspace, self.revision, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _render(self, *_):
        subject, kind = self.scope.currentData(), self.kind.currentData()
        filtered = [row for row in self.rows if (not subject or row["subject_id"] == subject)
                    and (not kind or row["kind"] == kind)]
        self.visible_rows = filtered[:1000]
        self.chart.clear()
        for index, (key, (_, color)) in enumerate(LANES.items(), 1):
            for observed in (True, False):
                points = [context.instant(row["occurred_at"] or row["scheduled_at"]).timestamp() for row in filtered
                          if row["kind"] == key and (row["status"] == "OBSERVED") == observed]
                if points:
                    self.chart.plot(points, [index] * len(points), pen=None, symbol="o" if observed else "x",
                                    symbolBrush=color, symbolPen=color, symbolSize=8)
        self.chart.enableAutoRange(axis="x")
        self.table.setRowCount(len(self.visible_rows))
        for index, row in enumerate(self.visible_rows):
            values = (row["occurred_at"] or row["scheduled_at"], row["subject_id"], LANES[row["kind"]][0],
                      _describe(row), ", ".join(row["qc"]) or "Passed", row["source_name"])
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        if filtered:
            limit = " · First 1,000 rows shown" if len(filtered) > 1000 else ""
            self.summary.setText(f"{len(filtered):,} records{limit} · × marks scheduled missing or omitted observations")
        elif self.revision:
            self.summary.setText("No context observations for this selection. Import an authorized training or wellness export.")
        else:
            self.summary.setText("Attach research data with an existing participant roster to start a timeline.")
        if not self.visible_rows:
            self.details.clear()
        else:
            self.table.setCurrentCell(0, 0)
            self._detail()

    def _detail(self, *_):
        index = self.table.currentRow()
        if not 0 <= index < len(self.visible_rows):
            return
        row = self.visible_rows[index]
        receipt = next((item for item in self.sources if item["id"] == row["context_source_id"]), {})
        self.details.setPlainText(json.dumps({"observation": row, "source_receipt": receipt}, indent=2, default=str))
