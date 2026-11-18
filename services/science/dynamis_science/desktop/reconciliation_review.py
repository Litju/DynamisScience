"""Native follow-up review embedded in Data Workspace."""

from __future__ import annotations

import getpass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from .. import importer, reconciliation
from .import_review import MappingEditor


def _label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _table(name: str) -> QTableWidget:
    table = QTableWidget()
    table.setAccessibleName(name)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(25)
    return table


def _display(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.9g}"
    if isinstance(value, list):
        return "; ".join(f"{item['name']} ({item['dtype']})" if isinstance(item, dict) else str(item)
                         for item in value)
    if isinstance(value, dict):
        return " · ".join(f"{key} {val}" for key, val in value.items())
    return str(value)


def _fill(table: QTableWidget, headers: tuple | list, rows: list[tuple], *, stretch: bool = False) -> None:
    table.setRowCount(0)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            cell = QTableWidgetItem(_display(value))
            cell.setToolTip(cell.text())
            table.setItem(row, column, cell)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    if stretch:
        for column in range(1, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 178)


def _buttons(dialog: QDialog, layout: QVBoxLayout, text: str) -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return buttons


class IdentityEditor(QDialog):
    def __init__(self, entry: dict, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Map athletes and sessions")
        self.resize(620, 420)
        self.controls = {}
        layout = QVBoxLayout(self)
        layout.addWidget(_label("Use the roster and testing log to match the incoming IDs. "
                                "For a new session, enter its canonical ID."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        fields = QWidget()
        form = QFormLayout(fields)
        for kind, label in (("athletes", "Athlete"), ("sessions", "Session")):
            for row in entry["identity_preview"].get(kind, []):
                if row["bound"]:
                    continue
                source = row["source"]
                picker = QComboBox()
                picker.setAccessibleName(f"{label} mapping for {source}")
                picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                picker.setMinimumContentsLength(16)
                picker.setEditable(kind == "sessions")
                picker.addItem("")
                picker.addItems(entry["identity_options"][kind])
                if row["target"]:
                    picker.setCurrentText(row["target"])
                form.addRow(_label(f"{label} {source}"), picker)
                self.controls[kind, source] = picker
        scroll.setWidget(fields)
        layout.addWidget(scroll, 1)
        _buttons(self, layout, "Save identity mapping")

    def mappings(self) -> dict:
        values: dict[str, dict] = {"athletes": {}, "sessions": {}}
        for (kind, source), picker in self.controls.items():
            target = picker.currentText().strip()
            if target:
                values[kind][source] = target
        return values


class ContextEditor(QDialog):
    def __init__(self, entry: dict, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm source context")
        layout = QVBoxLayout(self)
        layout.addWidget(_label("Check the source, instrument and protocol IDs against the testing log. "
                                "Enter the observed IDs if they differ."))
        form = QFormLayout()
        self.fields = {}
        self.constants = {}
        for key in reconciliation.CONTEXT_FIELDS:
            expected = entry["context"][key]
            field = QLineEdit(entry["declared"].get(key, ""))
            field.setMaxLength(150)
            label = key.replace("_id", "").title() + " ID"
            field.setAccessibleName(label)
            field.setPlaceholderText(expected)
            form.addRow(label, field)
            self.fields[key] = field
        mapping = entry["plan"]["mapping"]
        for key, label in (("session_id", "Session ID from testing log"),
                           ("sampling_hz", "Sampling rate from testing log (Hz)")):
            if key not in mapping["columns"]:
                field = QLineEdit(str(mapping.get("constants", {}).get(key, "")))
                field.setMaxLength(150)
                field.setAccessibleName(label)
                form.addRow(label, field)
                self.constants[key] = field
        layout.addLayout(form)
        reference = QPushButton("Use IDs from reference")
        def use_reference():
            for key, field in self.fields.items():
                field.setText(entry["context"][key])
        reference.clicked.connect(use_reference)
        layout.addWidget(reference)
        _buttons(self, layout, "Save source context")

    def declaration(self) -> dict:
        return {key: field.text().strip() for key, field in self.fields.items() if field.text().strip()}

    def measured_context(self) -> dict:
        return {key: field.text().strip() for key, field in self.constants.items()}


class ReconciliationReview(QWidget):
    def __init__(self, workspace_id, run_task, open_analysis, parent=None) -> None:
        super().__init__(parent)
        self.workspace_id, self.run_task, self.open_analysis = workspace_id, run_task, open_analysis
        self.busy = False
        self.events: list[dict] = []
        self.entry: dict = {}
        self.approved_in_session = False
        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.choose = QPushButton("Choose follow-up file…")
        self.choose.clicked.connect(self._choose)
        self.history = QComboBox()
        self.history.setAccessibleName("Reconciliation proposal and decision history")
        self.history.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.history.setMinimumContentsLength(12)
        self.history.currentIndexChanged.connect(self._show_selected)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        toolbar.addWidget(self.choose)
        toolbar.addWidget(self.history, 1)
        toolbar.addWidget(refresh)
        self.refresh_button = refresh
        root.addLayout(toolbar)

        self.status = _label("Choose a follow-up export to compare against the active data revision.")
        self.status.setAccessibleName("Reconciliation status")
        self.context = _label()
        self.context.setAccessibleName("Source rights, protocol, instrument and QC")
        root.addWidget(self.status)
        root.addWidget(self.context)

        self.tables = QTabWidget()
        self.differences = _table("Detected source discrepancies")
        self.identities = _table("Athlete and session identity differences")
        self.qc = _table("Per-session quality checks")
        self.measurements = _table("Trial changes and measurement preview")
        self.measurements.setToolTip("All proposed corrections and a sample of new or repeated trials.")
        self.source_preview = _table("Original source preview")
        for table, title in ((self.differences, "Discrepancies"), (self.identities, "Identities"),
                             (self.qc, "Session QC"), (self.measurements, "Trial changes"),
                             (self.source_preview, "Source preview")):
            self.tables.addTab(table, title)
        root.addWidget(self.tables, 1)

        actions = QHBoxLayout()
        self.mapping = QPushButton("Edit column mapping…")
        self.mapping.clicked.connect(self._edit_mapping)
        self.identity = QPushButton("Map identities…")
        self.identity.clicked.connect(self._edit_identity)
        self.declare = QPushButton("Confirm source context…")
        self.declare.clicked.connect(self._edit_context)
        for button in (self.mapping, self.identity, self.declare):
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)

        decisions = QHBoxLayout()
        self.reviewer = QLineEdit(getpass.getuser())
        self.reviewer.setAccessibleName("Decision reviewer")
        self.reviewer.setPlaceholderText("Reviewer")
        self.reviewer.setMaxLength(150)
        self.reviewer.setMaximumWidth(145)
        self.reason = QLineEdit()
        self.reason.setAccessibleName("Reason for reconciliation decision")
        self.reason.setPlaceholderText("Decision reason or evidence reference")
        self.reason.setMaxLength(2000)
        self.approve = QPushButton("&Approve")
        self.reject = QPushButton("&Reject")
        self.quarantine = QPushButton("&Quarantine")
        self.analyze = QPushButton("Open revision in Analysis")
        for action, button in (("APPROVED", self.approve), ("REJECTED", self.reject), ("QUARANTINED", self.quarantine)):
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, value=action: self._decide(value))
        self.analyze.clicked.connect(lambda: self.open_analysis(self.entry["decision"]["revision_id"]))
        for widget in (self.reviewer, self.reason, self.approve, self.reject, self.quarantine, self.analyze):
            decisions.addWidget(widget, 1 if widget == self.reason else 0)
        self.reviewer.textChanged.connect(self._buttons)
        self.reason.textChanged.connect(self._buttons)
        root.addLayout(decisions)
        self._buttons()

    def refresh(self) -> None:
        key = self._key(self.entry)
        self._run(lambda: reconciliation.history(self.workspace_id), lambda rows: self._history(rows, key),
                  "Reading reconciliation history")

    def _choose(self) -> None:
        suffixes = " ".join(f"*{suffix}" for suffix in importer.SUFFIXES)
        path, _ = QFileDialog.getOpenFileName(self, "Choose follow-up file", "", f"Data files ({suffixes});;All files (*)")
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        self._run(lambda: reconciliation.propose(self.workspace_id, Path(path)), self._updated, "Checking the follow-up export")

    def _run(self, operation, done, status: str) -> None:
        if self.busy:
            return
        self.busy = True
        self._buttons()
        self.status.setText(status + "…")

        def guarded():
            try:
                return operation(), None
            except Exception as error:
                return None, str(error)

        def finished(result):
            self.busy = False
            value, error = result
            if error is not None:
                self.status.setText(error)
                self._buttons()
            else:
                done(value)
        self.run_task(guarded, finished, status)

    @staticmethod
    def _key(event: dict) -> tuple:
        return event.get("id"), event.get("version")

    def _history(self, rows: list[dict], selected: tuple) -> None:
        self.events = rows
        self.history.blockSignals(True)
        self.history.clear()
        for event in self.events:
            action = event["state"].capitalize()
            self.history.addItem(f"{event['filename']}  ·  v{event['version']}  ·  {action}", self._key(event))
        index = self.history.findData(selected)
        self.history.setCurrentIndex(max(0, index))
        self.history.blockSignals(False)
        self._show_selected()

    def _updated(self, entry: dict) -> None:
        if entry["state"] == "APPROVED" and not entry.get("repeat_file"):
            self.approved_in_session = True
        self.reason.clear()
        key = self._key(entry)
        # Refresh from SQLite so previous decisions are available even after opening a new file in another window.
        self._run(lambda: reconciliation.history(self.workspace_id), lambda rows: self._after_update(rows, key, entry),
                  "Loading the saved review")

    def _after_update(self, rows: list[dict], key: tuple, entry: dict) -> None:
        self._history(rows, key)
        if entry.get("repeat_file"):
            self.status.setText(f"Duplicate file · {entry['repeat_filename']}. {self.status.text()}")

    def _show_selected(self) -> None:
        index = self.history.currentIndex()
        self.entry = self.events[index] if index >= 0 else {}
        entry = self.entry
        context, decision = entry.get("context", {}), entry.get("decision", {})
        if entry:
            current = "Ready for a decision" if entry["ready"] else "Needs review"
            if decision:
                current = f"{entry['state'].capitalize()} by {decision['reviewer']} · {decision['reason']}"
            counts = entry["counts"]
            tally = (f" · {counts['new']} new · {counts['correction']} corrections · {counts['duplicate']} repeated trials"
                     if counts else "")
            self.status.setText(f"{entry['filename']} · {current}{tally}")
        else:
            self.status.setText("No follow-up reviews yet. Choose a source export.")
        facts = []
        if context:
            facts = [f"{context['source_name']} · {context['rights']}",
                     f"{context['protocol']} v{context['protocol_version']} · {context['sampling_hz']:g} Hz",
                     f"{context['instrument']} · calibration {context['calibration'].lower()}"]
        if entry.get("quality"):
            quality = entry["quality"]
            facts.append("Admission QC " + quality["status"].replace("_", " ").lower())
            facts.extend(quality["errors"] + quality["warnings"])
        facts.extend(entry.get("plan", {}).get("warnings", []))
        self.context.setText("   |   ".join(facts))
        if entry:
            self.context.setToolTip(f"Base revision {entry['base_revision']}\nSHA-256 {entry['raw_sha256']}")
        else:
            self.context.setToolTip("")
        issues = entry.get("discrepancies", [])
        _fill(self.differences, ("Discrepancy", "Reference", "Incoming"), [
            (("Blocked · " if row["blocked"] else "") + row["kind"].replace("_", " ").capitalize(),
             row["reference"], row["incoming"]) for row in issues[:100]], stretch=True)
        if not issues and entry:
            _fill(self.differences, ("Discrepancy", "Reference", "Incoming"),
                  [("No discrepancies", "Compatible reference", "Ready for researcher decision")], stretch=True)
        preview = entry.get("identity_preview", {})
        _fill(self.identities, ("Identity", "Incoming ID", "Workspace ID"), [
            (kind, row["source"], row["target"]) for kind, rows in preview.items() for row in rows[:150]], stretch=True)
        _fill(self.qc, ("Session", "Study week", "Date", "Rows", "Flagged", "QC reasons"),
              [(r["session"], r["weeks"], r.get("dates", []), r["rows"], r["flagged"], r["reasons"])
               for r in entry.get("sessions_qc", [])])
        _fill(self.measurements, ("Trial", "Athlete", "Session", "Classification", "Measure (canonical)", "Previous", "Incoming"), [
            (row["trial"], row["athlete"], row["session"], row["classification"], name, *values)
            for row in entry.get("rows_preview", []) for name, values in (row["changes"] or {"—": [None, None]}).items()])
        for column in (2, 3, 4):
            self.measurements.setColumnWidth(column, 128)
        source = entry.get("plan", {}).get("preview", {})
        _fill(self.source_preview, source.get("columns", []), source.get("rows", []))
        self._buttons()

    def _buttons(self) -> None:
        self.choose.setEnabled(not self.busy)
        self.history.setEnabled(not self.busy and bool(self.events))
        self.refresh_button.setEnabled(not self.busy)
        entry = self.entry
        latest = next((item for item in self.events if item["id"] == entry.get("id")), {})
        active = not self.busy and bool(entry) and self._key(entry) == self._key(latest)
        pending = active and entry["state"] == "PROPOSED"
        editable = active and entry["state"] in {"PROPOSED", "QUARANTINED"}
        readable = entry.get("plan", {}).get("state") in {"READY", "REVIEW"}
        self.mapping.setEnabled(editable and readable)
        identities = [row for rows in entry.get("identity_preview", {}).values() for row in rows if not row["bound"]]
        self.identity.setEnabled(editable and 0 < len(identities) <= 200)
        self.identity.setToolTip("Split the export if more than 200 incoming IDs need confirmation." if len(identities) > 200 else "")
        self.declare.setEnabled(editable and readable and bool(entry.get("context")))
        can_decide = pending and bool(self.reason.text().strip() and self.reviewer.text().strip())
        self.approve.setEnabled(can_decide and entry["ready"])
        self.reject.setEnabled(can_decide)
        self.quarantine.setEnabled(can_decide)
        self.analyze.setVisible(entry.get("state") == "APPROVED")
        self.analyze.setEnabled(not self.busy and entry.get("state") == "APPROVED")

    def _revise(self, **changes) -> None:
        batch, version = self._key(self.entry)
        self._run(lambda: reconciliation.revise(self.workspace_id, batch, version, **changes),
                  self._updated, "Rechecking the proposal")

    def _edit_mapping(self) -> None:
        dialog = MappingEditor(self.entry["plan"], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._revise(edits=dialog.edits())

    def _edit_identity(self) -> None:
        dialog = IdentityEditor(self.entry, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._revise(**dialog.mappings())

    def _edit_context(self) -> None:
        dialog = ContextEditor(self.entry, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._revise(declared=dialog.declaration(), constants=dialog.measured_context())

    def _decide(self, action: str) -> None:
        batch, version = self._key(self.entry)
        reviewer, reason = self.reviewer.text(), self.reason.text()
        self._run(lambda: reconciliation.decide(self.workspace_id, batch, version, action, reviewer=reviewer, reason=reason),
                  self._updated, "Recording the decision")
