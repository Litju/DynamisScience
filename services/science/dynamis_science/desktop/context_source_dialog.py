"""File-first review for versioned training and wellness sources."""

from __future__ import annotations

import getpass
from pathlib import Path

import polars as pl
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QScrollArea, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import admission, context_import, researchstore as store, training_context as context
from .individual_research import fit_dialog
from .investigation_timeline import EvidencePanel, date_label, heading, readable, wrapping_label

ERRORS = (ValueError, OSError, LookupError, RuntimeError, pl.exceptions.PolarsError)


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
        self.error = wrapping_label()
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
    def __init__(self, workspace, revision, parent):
        super().__init__(parent)
        self.workspace, self.revision = workspace, revision
        self.file = self.file_sha256 = self.preview = self.reviewed = self.attachment = self.held = None
        self.column_overrides = None
        self.aliases = {}
        self.error = ""
        self.setWindowTitle("Import training and wellness context")

        layout = QVBoxLayout(self)
        self.title = QLabel("Preview suggested mapping")
        heading(self.title, 17)
        layout.addWidget(self.title)
        self.filename = wrapping_label()
        layout.addWidget(self.filename)
        form = QFormLayout()
        source_row = QHBoxLayout()
        self.sources = QComboBox()
        self.sources.setAccessibleName("Authorized source")
        source_row.addWidget(self.sources, 1)
        register = QPushButton("Register source…")
        register.clicked.connect(self._register)
        source_row.addWidget(register)
        form.addRow("Authorized source", source_row)
        self.reviewer = QLineEdit(getpass.getuser())
        self.reviewer.setAccessibleName("Reviewed by")
        form.addRow("Reviewed by", self.reviewer)
        layout.addLayout(form)
        self.rights = wrapping_label()
        layout.addWidget(self.rights)
        self.mapping_summary = wrapping_label()
        layout.addWidget(self.mapping_summary)
        self.column_button = QPushButton("Review column mapping…")
        self.column_button.clicked.connect(self._edit_columns)
        layout.addWidget(self.column_button)

        self.identity_scroll = QScrollArea()
        self.identity_scroll.setWidgetResizable(True)
        self.identity_scroll.setMaximumHeight(130)
        layout.addWidget(self.identity_scroll)
        self.details = QTextBrowser()
        self.details.setAccessibleName("Import conflicts, quality and proposed changes")
        self.details.setMinimumHeight(120)
        layout.addWidget(self.details, 1)
        self.message = wrapping_label()
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.quarantine_button = buttons.addButton("Quarantine…", QDialogButtonBox.ButtonRole.ActionRole)
        self.preview_button = buttons.addButton("Review changes", QDialogButtonBox.ButtonRole.ActionRole)
        self.attach_button = buttons.addButton("Approve and update timeline", QDialogButtonBox.ButtonRole.AcceptRole)
        self.preview_button.clicked.connect(self._preview)
        self.attach_button.clicked.connect(self._attach)
        self.quarantine_button.clicked.connect(self._quarantine)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sources()
        self.sources.currentIndexChanged.connect(self._source_changed)
        self.reviewer.textChanged.connect(self._reviewer_changed)
        fit_dialog(self, 760, 600)

    def _sources(self, selected=None):
        self.sources.blockSignals(True)
        self.sources.clear()
        self.sources.addItem("Choose the source of this file", None)
        self._policies = {}
        for source in admission.list_sources():
            if (source["rights_status"] in {"VERIFIED", "FIXTURE_ONLY"}
                    and "research" in {str(use).strip().lower() for use in source["permitted_uses"]}):
                identity = source["id"]
                self._policies[identity] = source
                self.sources.addItem(source["name"], identity)
        self.sources.setCurrentIndex(max(0, self.sources.findData(selected)))
        self.sources.blockSignals(False)

    def _register(self):
        dialog = SourceRegistration(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._sources(dialog.source["id"])
            self._source_changed()

    def choose_file(self):
        filename, _ = QFileDialog.getOpenFileName(self.parentWidget(), "Choose training or wellness export",
                                                  filter="Context files (*.csv *.tsv *.xlsx *.parquet *.pq)")
        if not filename:
            return False
        self.file = Path(filename)
        self.filename.setText(self.file.name)
        try:
            self.file_sha256 = context_import.fingerprint(self.file)
        except ERRORS as error:
            self.error = str(error)
            self.details.setPlainText(self.error)
            self._buttons()
            return True
        self._load_mapping(suggest_source=True)
        return True

    def _source_changed(self):
        self._load_mapping()

    def _load_mapping(self, *, suggest_source=False):
        self.reviewed = self.preview = None
        self.error = ""
        self.message.clear()
        try:
            if not self.file_sha256:
                raise ValueError("Choose a supported, readable context file.")
            self.preview = context_import.mapping_preview(self.workspace, self.revision, self.file,
                                                          self.sources.currentData(), self.column_overrides,
                                                          suggest_source=suggest_source)
            if self.preview["file_sha256"] != self.file_sha256:
                self.preview = None
                raise store.ResearchConflict("The file changed during mapping. Cancel and choose it again.")
        except ERRORS as error:
            self.error = str(error)
        if self.preview and suggest_source and self.preview["source_id"] in self._policies:
            self._sources(self.preview["source_id"])
        selected_source = self._policies.get(self.sources.currentData())
        if selected_source:
            rights = "Synthetic fixture" if selected_source["rights_status"] == "FIXTURE_ONLY" else "Research use verified"
            self.rights.setText(f"{rights} · {selected_source['license_or_agreement']}")
        else:
            self.rights.setText("Choose a registered source to confirm permission for research use.")
        preview = self.preview or {}
        columns = preview.get("columns", {})
        labels = context_import.COLUMN_LABELS
        important = (*context.REQUIRED, "occurred_at", "scheduled_at")
        mapping = "  ·  ".join(f"{labels[key]} ← {columns[key]}" for key in important if key in columns)
        units = "  ·  ".join(f"{labels[key]} {', '.join(values[:6])}" for key, values in preview.get("units", {}).items() if values)
        self.mapping_summary.setText("\n".join(filter(None, (mapping, units))))
        self.column_button.setEnabled(bool(preview))
        self._identity_fields()
        self._show_mapping_status()

    def _identity_fields(self):
        details = QWidget()
        form = QFormLayout(details)
        self.aliases = {}
        if self.preview:
            for external, known in self.preview["identities"].items():
                if known is not None:
                    continue
                picker = QComboBox()
                picker.addItem("Choose workspace athlete", None)
                picker.addItems(self.preview["athletes"])
                picker.setAccessibleName(f"Workspace athlete for {external}")
                picker.currentIndexChanged.connect(self._show_mapping_status)
                self.aliases[external] = picker
                form.addRow(external, picker)
        self.identity_scroll.setWidget(details)
        self.identity_scroll.setVisible(bool(self.aliases))

    def _show_mapping_status(self):
        self.reviewed = None
        self.error = self.error if self.preview is None else ""
        self.title.setText("Preview suggested mapping")
        preview = self.preview or {}
        lines = [self.error] if self.error else list(preview.get("problems", []))
        if self.aliases:
            lines.append("Confirm the workspace athlete for each unrecognized identifier.")
        identities = preview.get("identities", {})
        reused = [f"{key} → {value}" for key, value in identities.items() if value and key != value]
        matched = sum(value is not None for value in identities.values())
        if matched:
            lines.append(f"{matched} athlete identifiers matched to this workspace.")
        if reused:
            lines.append("Previously confirmed aliases · " + ", ".join(reused[:8]))
        self.details.setPlainText("\n\n".join(lines) or "Review the mapped columns before checking file quality.")
        self._buttons()

    def _reviewer_changed(self):
        self._buttons()

    def _buttons(self):
        has_source = bool(self.sources.currentData() and self.reviewer.text().strip())
        resolved = all(item.currentIndex() > 0 for item in self.aliases.values())
        self.preview_button.setEnabled(bool(has_source and self.preview and not self.preview["problems"] and resolved))
        self.preview_button.setVisible(not self.reviewed)
        self.mapping_summary.setVisible(not self.reviewed)
        self.attach_button.setEnabled(bool(has_source and self.reviewed))
        self.attach_button.setVisible(bool(self.reviewed))
        self.quarantine_button.setEnabled(bool(has_source and self.file_sha256))
        if self.reviewed:
            self.attach_button.setDefault(True)
        elif self.preview_button.isEnabled():
            self.preview_button.setDefault(True)

    def _edit_columns(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Map source columns")
        layout = QVBoxLayout(dialog)
        layout.addWidget(wrapping_label("Match the fields to columns in the file. Leave an optional field empty when the file has no matching column."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        fields = QWidget()
        form = QFormLayout(fields)
        picks = {}
        for key, label in context_import.COLUMN_LABELS.items():
            box = QComboBox()
            box.setAccessibleName(label)
            if key not in self.preview["available_columns"]:
                box.addItem("Choose column" if key in context.REQUIRED else "No matching column", None)
            box.addItems(self.preview["available_columns"])
            chosen = self.preview["columns"].get(key)
            if chosen or key in self.preview["available_columns"]:
                box.setCurrentText(chosen or key)
            else:
                box.setCurrentIndex(0)
            picks[key] = box
            form.addRow(label, box)
        scroll.setWidget(fields)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        fit_dialog(dialog, 640, 530)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.column_overrides = {key: box.currentText() for key, box in picks.items()
                                     if box.currentIndex() > 0 or key in self.preview["available_columns"]}
            self._load_mapping()

    @staticmethod
    def _show_change(before, after):
        when = after["occurred_at"] or after["scheduled_at"]
        fields = {
            "duration_min": ("Duration", " min"), "rpe": ("Session RPE", ""), "rpe_scale": ("RPE scale", ""),
            "session_load_au": ("Session load", " AU"), "value": ("Wellness value", f" {after.get('unit') or ''}"),
            "status": ("Status", ""), "occurred_at": ("Actual date and time", ""),
            "scheduled_at": ("Scheduled date and time", ""), "recorded_at": ("Recorded date and time", ""),
            "adherence": ("Adherence", ""), "deviation": ("Deviation", ""), "reason": ("Reason", ""),
            "unit": ("Wellness unit", ""), "questionnaire_version": ("Questionnaire version", ""),
            "duration_unit": ("Recorded duration unit", ""), "duration": ("Recorded duration", ""),
        }

        def value(raw, unit):
            if raw is None:
                return "unrecorded"
            return f"{raw:g}{unit}" if isinstance(raw, (int, float)) else f"{raw}{unit}"

        changes = [f"{name}  {value(before.get(key), unit)} → {value(after.get(key), unit)}"
                   for key, (name, unit) in fields.items() if before.get(key) != after.get(key)]
        return f"{after['subject_id']} · {date_label(when)}\n" + "\n".join(changes)

    def _preview(self):
        self.reviewed = None
        self.message.clear()
        source = self.sources.currentData()
        overrides = {key: box.currentText() for key, box in self.aliases.items() if box.currentIndex() > 0}
        mapping = context.SourceMapping(columns=self.preview["columns"], participants=overrides)
        try:
            receipt, rows, changed = context_import.review(self.workspace, self.revision, source, self.file, mapping)
            if receipt["raw_sha256"] != self.preview["file_sha256"]:
                raise store.ResearchConflict("The file changed during mapping. Cancel and choose it again.")
        except ERRORS as error:
            self.error = str(error)
            self.title.setText("Review conflicts")
            self.details.setPlainText(self.error)
            self._buttons()
            return
        self.error = ""
        self.reviewed = mapping, receipt
        self.title.setText("Review changes before approval")
        counts = receipt["changes"]
        lines = [(
            f"{receipt['row_count']:,} observations · Proposed source version {receipt['version']}\n"
            f"{counts.get('new', 0):,} new · {counts.get('changed', 0):,} changed · {counts.get('unchanged', 0):,} unchanged"
        )]
        lines.extend(self._show_change(old, new) for old, new in changed)
        if counts.get("changed", 0) > len(changed):
            lines.append(f"Showing {len(changed)} of {counts['changed']:,} changed observations.")
        lines.append("Quality and missingness\n" + (
            "\n".join(f"{count:,} · {readable(flag)}" for flag, count in receipt["qc"].items())
            if receipt["qc"] else "No flagged observations."))
        if counts.get("new", 0) and not changed:
            lines.append("Sample observations\n" + "\n".join(
                f"{row.subject_id} · {date_label(row.occurred_at or row.scheduled_at)} · "
                + EvidencePanel._context_value(row.model_dump()).split("\n")[0] for row in rows[:4]))
        self.details.setPlainText("\n\n".join(lines))
        self.details.moveCursor(QTextCursor.MoveOperation.Start)
        self._buttons()
        self.attach_button.setFocus()

    def _attach(self):
        if not self.reviewed or not self.attach_button.isEnabled():
            return
        mapping, receipt = self.reviewed
        try:
            self.attachment = context.attach(self.workspace, self.revision, self.sources.currentData(),
                                             self.file, mapping, receipt, self.reviewer.text())
        except ERRORS as error:
            self.reviewed = None
            self.error = str(error)
            self.title.setText("Review conflicts")
            self.details.setPlainText(self.error)
            self._buttons()
            return
        self.accept()

    def _quarantine(self):
        if not self.quarantine_button.isEnabled():
            return
        reason, confirmed = QInputDialog.getText(self, "Quarantine context file", "Reason for holding this file",
                                                text=self.error)
        if not confirmed:
            return
        try:
            self.held = context_import.quarantine(self.workspace, self.revision, self.sources.currentData(),
                                                  self.file, self.file_sha256, self.reviewer.text(), reason)
        except ERRORS as error:
            self.message.setText(str(error))
            return
        self.accept()
