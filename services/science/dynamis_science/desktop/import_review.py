"""One native review screen for the one-click scientific import (RES-636)."""

from __future__ import annotations

import getpass
import html
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

from .. import importer
from . import theme
from .services import DynamisAppService

PRIVACY = ["DEIDENTIFIED", "PSEUDONYMOUS", "IDENTIFIABLE", "NOT_APPLICABLE", "TEST_FIXTURE"]
TEXT_FIELDS = (  # (key, label, required)
    ("source_name", "Source name", True), ("publisher", "Publisher / lab", True),
    ("dataset_identity", "Dataset identity / DOI", True), ("license_or_agreement", "Licence or agreement", True),
    ("redistribution_restrictions", "Redistribution restrictions", True),
    ("manufacturer", "Instrument manufacturer", True), ("model", "Instrument model", True),
    ("serial_number", "Instrument serial number", True), ("calibration_status", "Calibration status", False),
    ("protocol_name", "Protocol name", True), ("protocol_version", "Protocol version", True),
    ("subject_id", "Subject ID (single-trace file)", False), ("trial_id", "Trial ID (single-trace file)", False),
    ("session_id", "Session ID (if not in file)", False), ("sampling_hz", "Sampling rate Hz (if not in file)", False),
    ("coordinate_system", "Coordinate convention (sprint)", False),
)
QC_TEXT = {"ADMITTED": "QC passed", "ADMITTED_WITH_WARNINGS": "QC passed with warnings", "REJECTED": "QC rejected",
           "QUARANTINED": "QC quarantined"}  # QC outcome, not yet an admission: the Admit click is what stores a snapshot
UNIT_TEXT = {"n": "N", "kn": "kN", "hz": "Hz", "w/kg": "W/kg", "ns/kg": "N·s/kg"}
STATE_TEXT = {"READY": "Mapped", "REVIEW": "Needs review", "UNSUPPORTED": "Unsupported"}


class MappingEditor(QDialog):
    """Edit which file column feeds each canonical column and in which unit."""

    def __init__(self, plan: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit mapping")
        self.plan, self.rows = plan, {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose the file column and unit for each target. Units are converted deterministically; "
                                "nothing is assumed."))
        form = QFormLayout()
        names = [c["name"] for c in plan["columns"]]
        family = plan["mapping"].get("family")
        for target, (group, units, _) in importer.COLUMNS.items():
            wanted = {"CMJ_FORCE_PLATFORM": ("CMJ",), "SPRINT_TIMING": ("SPRINT",), importer.traces.FAMILY: ("TRACE",)}.get(family, ("CMJ",))
            if group not in ("ANY", *wanted) and not (target == "time_s" and family == importer.traces.FAMILY):
                continue
            source, unit = QComboBox(), QComboBox()
            source.addItem("— not mapped —", None)
            for name in names:
                source.addItem(name, name)
            unit.addItems(sorted(units or {""}, key=str))
            current = plan["mapping"]["columns"].get(target)
            if current:
                source.setCurrentIndex(source.findData(current["source"]))
                unit.setCurrentText(current["unit"])
            source.setAccessibleName(f"{target} source column")
            unit.setAccessibleName(f"{target} unit")
            unit.setEnabled(units is not None)
            row = QHBoxLayout()
            row.addWidget(source, 3)
            row.addWidget(unit, 1)
            form.addRow(target, row)
            self.rows[target] = (source, unit)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        ok, cancel = QPushButton("Apply mapping"), QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def edits(self) -> dict[str, dict[str, Any] | None]:
        current = self.plan["mapping"]["columns"]
        out: dict[str, dict[str, Any] | None] = {}
        for target, (source, unit) in self.rows.items():
            chosen = source.currentData()
            if chosen is None:
                if target in current:
                    out[target] = None
            elif target not in current or (current[target]["source"], current[target]["unit"]) != (chosen, unit.currentText()):
                out[target] = {"source": chosen, "unit": unit.currentText()}
        return out


class ImportReviewDialog(QDialog):
    def __init__(self, service: DynamisAppService, run_task: Callable[[Callable[[], Any], Callable[[Any], None], str], None],
                 on_admitted: Callable[[dict[str, Any]], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task, self.on_admitted = service, run_task, on_admitted
        self.items: list[dict[str, Any]] = []
        self.setWindowTitle("Import data")
        self.setAcceptDrops(True)
        screen = QGuiApplication.primaryScreen().availableGeometry() if QGuiApplication.primaryScreen() else None
        self.setMinimumSize(640, 440)
        self.resize(min(1180, int(screen.width() * 0.92)) if screen else 1100, min(760, int(screen.height() * 0.9)) if screen else 700)

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.path_label = QLabel("Drop a CSV or Parquet file or folder here, or choose one.")
        self.path_label.setWordWrap(True)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # long paths wrap, never widen the dialog
        self.file_button, self.folder_button = QPushButton("Choose file…"), QPushButton("Choose folder…")
        self.file_button.clicked.connect(self._choose_file)
        self.folder_button.clicked.connect(self._choose_folder)
        top.addWidget(self.path_label, 1)
        top.addWidget(self.file_button)
        top.addWidget(self.folder_button)
        root.addLayout(top)
        self.drop = QLabel("Drop a CSV or Parquet file or folder here")
        self.drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop.setMinimumHeight(56)
        self.drop.setObjectName("DropZone")
        self.drop.setStyleSheet("#DropZone { border: 2px dashed palette(mid); border-radius: 8px; padding: 10px; }")
        self.drop.setAccessibleName("Drop zone")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setAccessibleName("Import summary")
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        root.addWidget(self.drop)
        root.addWidget(self.summary)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QSplitter(Qt.Orientation.Vertical)
        self.files = QTableWidget(0, 3)
        self.files.setHorizontalHeaderLabels(["File", "Detected", "Status"])
        self.files.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.files.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.files.setAccessibleName("Files to import")
        self.files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files.currentCellChanged.connect(lambda row, *_: self._show(row))
        self.preview = QTableWidget()
        self.preview.setAccessibleName("Data preview")
        self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mapping = QTableWidget(0, 5)
        self.mapping.setHorizontalHeaderLabels(["Target", "File column", "Unit", "Confidence", "Origin"])
        self.mapping.setAccessibleName("Mapping decisions")
        self.mapping.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mapping.horizontalHeader().setStretchLastSection(True)
        for widget in (self.files, self.preview, self.mapping):
            left.addWidget(widget)
        left.setSizes([110, 200, 160])
        split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Source and instrument — confirmed by you")
        form = QFormLayout(box)
        self.privacy = QComboBox()
        self.privacy.addItem("Choose…", "")
        for item in PRIVACY:
            self.privacy.addItem(item, item)
        self.privacy.setAccessibleName("Privacy classification")
        form.addRow("Data class", self.privacy)
        self.edits: dict[str, QLineEdit] = {}
        for key, label, _ in TEXT_FIELDS:
            edit = QLineEdit()
            edit.setAccessibleName(label)
            self.edits[key] = edit
            form.addRow(label, edit)
        self.edits["protocol_version"].setText("1.0")
        self.rights = QCheckBox("I reviewed the licence, permitted uses and redistribution terms.")
        self.reviewer = QLineEdit(getpass.getuser())
        self.reviewer.setAccessibleName("Rights verified by")
        form.addRow(self.rights)
        form.addRow("Rights verified by", self.reviewer)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(box)
        right_layout.addWidget(scroll, 1)
        split.addWidget(right)
        split.setSizes([620, 420])
        self.verdict = QTextBrowser()
        self.verdict.setAccessibleName("Detection, QC verdict, warnings and provenance")
        self.verdict.setMinimumHeight(80)
        vertical = QSplitter(Qt.Orientation.Vertical)  # the researcher can trade preview space for verdict space
        vertical.addWidget(split)
        vertical.addWidget(self.verdict)
        vertical.setStretchFactor(0, 3)
        vertical.setStretchFactor(1, 2)
        self.details = QWidget()  # everything the researcher can inspect or change; closed unless attention is needed
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addWidget(vertical, 1)
        self.details.setVisible(False)
        root.addWidget(self.details, 1)
        root.addStretch(0)

        buttons = QHBoxLayout()
        self.qc_button = QPushButton("Run &QC")
        self.edit_button = QPushButton("&Edit mapping…")
        self.preset_button = QPushButton("Save &preset…")
        self.quarantine_button = QPushButton("Qua&rantine")
        self.admit_button = QPushButton("&Admit")
        close = QPushButton("Close")
        self.qc_button.clicked.connect(self._run_qc)
        self.edit_button.clicked.connect(self._edit_mapping)
        self.preset_button.clicked.connect(self._save_preset)
        self.quarantine_button.clicked.connect(self._quarantine)
        self.admit_button.clicked.connect(self._admit)
        close.clicked.connect(self.reject)
        for button in (self.qc_button, self.edit_button, self.preset_button, self.quarantine_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.admit_button)
        details_layout.addLayout(buttons)
        bottom = QHBoxLayout()
        self.details_button = QPushButton("&Details")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self.details.setVisible)
        self.import_button = QPushButton("&Import")
        self.import_button.setDefault(True)
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import)
        bottom.addWidget(self.details_button)
        bottom.addStretch(1)
        bottom.addWidget(self.import_button)
        bottom.addWidget(close)
        root.addLayout(bottom)
        self.setTabOrder(self.file_button, self.folder_button)
        self._update_buttons()
        self._update_summary()

    # ---- input
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.load(urls[0].toLocalFile())

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose data file", "", "Data tables (*.csv *.parquet *.pq)")
        if path:
            self.load(path)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose data folder")
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        self.path_label.setText(f"Reading {path}…")
        self._run(lambda: importer.probe(path), self._probed, "Detecting format and schema")

    def _run(self, work: Callable[[], Any], done: Callable[[Any], None], label: str) -> None:
        def guarded() -> Any:
            try:
                return work()
            except ValueError as error:  # includes ImportBlocked: shown in the review, not a crash
                return {"error": str(error)}

        def finished(result: Any) -> None:
            if isinstance(result, dict) and "error" in result and len(result) == 1:
                self._message(f"<b>Cannot continue.</b> {html.escape(result['error'])}")
            else:
                done(result)

        self.run_task(guarded, finished, label)

    def _probed(self, result: dict[str, Any]) -> None:
        self.path_label.setText(f"{result['path']} — {len(result['files'])} supported file(s)"
                                + (f", {len(result['skipped'])} skipped" if result["skipped"] else ""))
        self.skipped = result["skipped"]
        self.items = [{"plan": p, "staged": None, "decision": None, "preset": None, "drift": None} for p in result["files"]]
        self._run(lambda: [self._lookup(i["plan"]) for i in self.items], self._looked_up, "Checking saved presets")

    def _lookup(self, plan: dict[str, Any]) -> tuple[Any, Any]:
        if plan["state"] == "UNSUPPORTED":
            return None, None
        preset = importer.match_preset(plan)
        return preset, None if preset else importer.schema_drift(plan)

    def _looked_up(self, found: list[tuple[Any, Any]]) -> None:
        for item, (preset, drift) in zip(self.items, found):
            item["preset"], item["drift"] = preset, drift
            if preset:
                item["plan"] = dict(item["plan"], mapping=preset["mapping"], ambiguities=[], preset=preset["id"])
                importer._refresh_state(item["plan"])
        first = next((i["preset"] for i in self.items if i["preset"]), None)
        profile = first["context"] if first else importer.last_profile()
        if profile:  # a saved preset, else the source profile used last: the form is filled, not asked
            self._fill_form(profile.get("fields", {}))
        self.items = [dict(i, plan=self._plan_with_constants(i["plan"])) for i in self.items]
        self._fill_files()
        if self.items:
            self.files.selectRow(0)
            self._show(0)  # currentCellChanged does not fire when row 0 was already current
        self._open_details(False)
        if self._form_errors() == [] and any(i["plan"]["state"] == "READY" for i in self.items):
            self._run_qc()  # nothing is missing: QC runs now, Import is the one click left
        else:
            if self.items and self._form_errors():
                self.summary.setText(self.summary.text() + "<br><i>First import from this source: confirm who it belongs to "
                                     "and which instrument produced it once; it is remembered.</i>")
            self._attention()

    # ---- display
    def _fill_files(self) -> None:
        self.files.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            plan = item["plan"]
            detected = plan.get("mapping", {}).get("family") or plan.get("reason", "unrecognised")
            staged = item["staged"]
            status = ("Admitted" if (item["decision"] or "").startswith("ADMITTED") else item["decision"] and item["decision"].title()
                      or (staged and (QC_TEXT[staged["quality"]["status"]] + (" · duplicate" if staged["duplicate_of"] else "")))
                      or STATE_TEXT[plan["state"]])
            for col, text in enumerate((plan["name"], f"{plan.get('format', '?')} · {detected}", str(status))):
                self.files.setItem(row, col, QTableWidgetItem(text))

    def _current(self) -> dict[str, Any] | None:
        row = self.files.currentRow()
        return self.items[row] if 0 <= row < len(self.items) else None

    def _show(self, row: int) -> None:
        item = self._current()
        self._update_buttons()
        if item is None:
            return
        plan = item["plan"]
        preview = plan.get("preview", {"columns": [], "rows": []})
        self.preview.setColumnCount(len(preview["columns"]))
        self.preview.setHorizontalHeaderLabels(preview["columns"])
        self.preview.setRowCount(len(preview["rows"]))
        for r, values in enumerate(preview["rows"]):
            for c, text in enumerate(values):
                self.preview.setItem(r, c, QTableWidgetItem(text))
        columns = plan.get("mapping", {}).get("columns", {})
        self.mapping.setRowCount(len(columns))
        for r, (target, entry) in enumerate(columns.items()):
            for c, text in enumerate((target, entry["source"], UNIT_TEXT.get(entry["unit"], entry["unit"]) or "—", f"{entry['confidence']:.0%}", entry["origin"])):
                self.mapping.setItem(r, c, QTableWidgetItem(text))
        for table in (self.preview, self.mapping):
            table.resizeColumnsToContents()
        self.verdict.setHtml(self._verdict_html(item))

    def _verdict_html(self, item: dict[str, Any]) -> str:
        plan, staged = item["plan"], item["staged"]
        t = theme.tokens()
        esc = html.escape
        if plan["state"] == "UNSUPPORTED":
            return f"<b>Unsupported.</b> {esc(plan['reason'])}"
        parts = [f"<b>Detected</b> {plan['format']}"
                 + (f", delimiter {esc(repr(plan['delimiter']))}" if "delimiter" in plan else "")
                 + f", {plan['rows']} rows, {len(plan['columns'])} columns · family "
                 f"<b>{esc(plan['mapping'].get('family') or 'not recognised')}</b> · adapter {plan['adapter']}"]
        if item["preset"]:
            parts.append(f"<b>Saved preset</b> {esc(item['preset']['name'])} v{item['preset']['version']} matches this exact schema.")
        elif item["drift"]:
            parts.append(f"<span style='color:{t['warn']}'><b>Schema drift.</b> Differs from preset "
                         f"{esc(item['drift']['preset_name'])} (missing {esc(', '.join(item['drift']['missing_columns']))}). "
                         "The saved mapping is not reused; review below.</span>")
        for text in plan["ambiguities"]:
            parts.append(f"<span style='color:{t['warn']}'>Needs your decision: {esc(text)}</span>")
        for text in plan["needs"]:
            parts.append(f"<span style='color:{t['warn']}'>Missing: {esc(text)}</span>")
        if staged:
            q = staged["quality"]
            parts.append(f"<b>QC verdict: {QC_TEXT[q['status']]}</b> ({esc(q['status'])}) — {esc(', '.join(f'{k} {v}' for k, v in q['counts'].items()))}")
            for key, label in (("errors", "Error"), ("warnings", "Warning")):
                parts += [f"{label}: {esc(str(v))}" for v in q[key]]
            if staged["duplicate_of"]:
                parts.append(f"Duplicate of source artifact {esc(staged['duplicate_of'])}; it will not be admitted again.")
            if staged["rights_status"] not in ("VERIFIED", "FIXTURE_ONLY"):
                parts.append("Source rights are not verified: tick the rights review to continue.")
            if staged["synthetic_only"]:
                parts.append("<b>SYNTHETIC_ONLY test fixture</b>: simulated instrument, no physical calibration, no empirical "
                             "validity, not eligible as real scientific evidence.")
            r = staged["receipt"]
            parts.append(f"<b>Provenance</b> raw SHA-256 {r['raw_sha256'][:16]}… · schema {r['schema_fingerprint']} · "
                         f"mapping by {plan['adapter']} · ignored columns: {esc(', '.join(r['dropped_columns']) or 'none')}")
            if item["decision"] and item["decision"].startswith("ADMITTED"):
                parts.append(f"<b>Stored:</b> immutable snapshot {importer.expected_snapshot_id(staged)} with provenance manifest.")
            elif staged["eligible"]:
                parts.append(f"<b>Admit will store:</b> immutable snapshot {importer.expected_snapshot_id(staged)}, "
                             f"{r['normalized_rows']} rows, Parquet + provenance manifest. Raw file is kept unchanged.")
            else:
                parts.append("<b>Not eligible for admission.</b> Quarantine keeps the raw file and records the outcome; no snapshot is created.")
        else:
            parts.append("Enter the source and instrument details, then press Run QC.")
        return "<br>".join(parts)

    def _message(self, text: str) -> None:
        self.verdict.setHtml(text)
        self._open_details()

    def _open_details(self, show: bool = True) -> None:
        self.details_button.setChecked(show)

    def _attention(self) -> None:
        """Open the details only when something needs the researcher: missing facts, drift, or a file that cannot be imported."""
        needs = any(not i["decision"] and (i["plan"]["state"] in ("REVIEW", "UNSUPPORTED") or (i["staged"] and not i["staged"]["eligible"]))
                    for i in self.items)
        if needs or self._form_errors():
            self._open_details()

    @staticmethod
    def _reasons(rq: dict[str, Any]) -> str:
        return html.escape(", ".join(f"{k}: {v}" for k, v in rq["reasons"].items()))

    def _update_summary(self) -> None:
        t, esc = theme.tokens(), html.escape
        if not self.items:
            self.summary.setText("Nothing loaded yet. DynamisScience detects the format, columns, units and identifiers, "
                                 "checks every row, and adds the clean rows to your dataset.")
            self.import_button.setEnabled(False)
            return
        lines = []
        for item in self.items:
            plan, staged, name = item["plan"], item["staged"], esc(item["plan"]["name"])
            decision = item["decision"] or ""
            if plan["state"] == "UNSUPPORTED":
                lines.append(f"<span style='color:{t['bad']}'>✗</span> <b>{name}</b> — {esc(plan['reason'])}")
            elif decision.startswith("ADMITTED"):
                rq = staged["receipt"]["row_quarantine"]
                note = f"; {rq['count']} row(s) quarantined ({self._reasons(rq)})" if rq["count"] else ""
                lines.append(f"<span style='color:{t['ok']}'>✓</span> <b>{name}</b> — imported {staged['receipt']['normalized_rows']:,} rows{note}")
            elif decision == "QUARANTINED":
                lines.append(f"<span style='color:{t['warn']}'>⚠</span> <b>{name}</b> — quarantined; no data was added")
            elif staged:
                rq = staged["receipt"]["row_quarantine"]
                if staged["eligible"]:
                    note = f"; {rq['count']} row(s) will be quarantined ({self._reasons(rq)})" if rq["count"] else ""
                    lines.append(f"<span style='color:{t['ok']}'>✓</span> <b>{name}</b> — {staged['receipt']['normalized_rows']:,} rows ready{note}")
                else:
                    why = (staged["quality"]["errors"] or staged["quality"]["warnings"] or
                           (["duplicate content"] if staged["duplicate_of"] else ["source rights are not verified"]))[0]
                    lines.append(f"<span style='color:{t['bad']}'>✗</span> <b>{name}</b> — cannot be imported: {esc(str(why))}")
            else:
                need = "; ".join(plan["needs"] + plan["ambiguities"])
                family = esc(str(plan["mapping"].get("family") or "unrecognised"))
                lines.append(f"• <b>{name}</b> — {plan['rows']:,} rows · {family}"
                             + (f" · <span style='color:{t['warn']}'>needs: {esc(need)}</span>" if need else ""))
        if any(i["plan"].get("session_from_filename") and i["plan"]["state"] != "UNSUPPORTED" for i in self.items):
            lines.append("<i>The file has no session column: each file is treated as one session, named after the file. "
                         "Type a Session ID in Details to change it.</i>")
        if any(i["staged"] and i["staged"]["synthetic_only"] for i in self.items):
            lines.append("<i>SYNTHETIC_ONLY test fixture: not real measurements, not eligible as scientific evidence.</i>")
        self.summary.setText("<br>".join(lines))
        pending = [i for i in self.items if not i["decision"] and i["plan"]["state"] != "UNSUPPORTED" and (i["staged"] is None or i["staged"]["eligible"])]
        self.import_button.setEnabled(bool(pending))
        self.import_button.setText(f"&Import {len(pending)} files" if len(pending) > 1 else "&Import")

    def _import(self) -> None:
        """The one explicit click: QC if it has not run, then add every eligible file as an immutable batch."""
        if any(i["staged"] is None and not i["decision"] and i["plan"]["state"] != "UNSUPPORTED" for i in self.items):
            self._run_qc(then=self._admit)
        else:
            self._admit()

    def _update_buttons(self) -> None:
        item = self._current()
        staged = item and item["staged"]
        done = bool(item and item["decision"])
        self.edit_button.setEnabled(bool(item) and item["plan"]["state"] != "UNSUPPORTED" and not done)
        self.qc_button.setEnabled(bool(item) and item["plan"]["state"] != "UNSUPPORTED" and not done)
        self.preset_button.setEnabled(bool(staged))
        self.quarantine_button.setEnabled(bool(staged) and not done)
        self.admit_button.setEnabled(any(i["staged"] and i["staged"]["eligible"] and not i["decision"] for i in self.items))
        self._update_summary()

    # ---- form
    def _fields(self) -> dict[str, Any]:
        fields = {key: edit.text().strip() for key, edit in self.edits.items() if key not in importer.CONSTANT_FIELDS}
        fields["privacy_status"] = self.privacy.currentData() or ""
        return fields

    def _fill_form(self, fields: dict[str, Any]) -> None:
        for key, edit in self.edits.items():
            if fields.get(key) not in (None, ""):
                edit.setText(str(fields[key]))
        index = self.privacy.findData(fields.get("privacy_status", ""))
        if index >= 0:
            self.privacy.setCurrentIndex(index)

    def _form_errors(self) -> list[str]:
        missing = [label for key, label, required in TEXT_FIELDS if required and not self.edits[key].text().strip()]
        if not self.privacy.currentData():
            missing.append("Data class")
        return missing

    def _constants(self) -> dict[str, Any]:
        return {k: self.edits[k].text().strip() for k in importer.CONSTANT_FIELDS if self.edits[k].text().strip()}

    # ---- actions
    def _edit_mapping(self) -> None:
        item = self._current()
        editor = MappingEditor(item["plan"], self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            item["plan"] = importer.edit_mapping(item["plan"], editor.edits(), self._constants())
        except ValueError as error:
            self._message(f"<b>Mapping not applied.</b> {html.escape(str(error))}")
            return
        item["staged"] = None
        self._fill_files()
        self._show(self.files.currentRow())

    def _plan_with_constants(self, plan: dict[str, Any]) -> dict[str, Any]:
        merged = {**plan["mapping"].get("constants", {}), **self._constants()}
        derived = False
        if plan["state"] != "UNSUPPORTED" and "session_id" not in plan["mapping"]["columns"] and not str(merged.get("session_id", "")).strip():
            merged["session_id"] = Path(plan["name"]).stem  # one file, one session, unless you say otherwise; shown in the summary
            derived = True
        updated = dict(plan, mapping=dict(plan["mapping"], constants=merged), session_from_filename=derived)
        importer._refresh_state(updated)
        return updated

    def _run_qc(self, then: Any = None) -> None:
        missing = self._form_errors()
        if missing:
            self._message("<b>Complete before QC:</b> " + html.escape(", ".join(missing)))
            return
        for item in self.items:
            item["plan"] = self._plan_with_constants(item["plan"])
        todo = [i for i in self.items if i["plan"]["state"] == "READY" and not i["decision"]]
        if not todo:
            self._show(self.files.currentRow())
            return
        context = importer.build_context(self._fields())
        reviewer = self.reviewer.text().strip() if self.rights.isChecked() else ""

        def work() -> list[Any]:
            results = []
            for item in todo:
                try:
                    results.append(importer.stage(item["plan"], context, rights_reviewed_by=reviewer))
                except ValueError as error:
                    results.append({"error": str(error)})
            return results

        def done(results: list[Any]) -> None:
            errors = []
            for item, result in zip(todo, results):
                if "error" in result:
                    errors.append(f"{item['plan']['name']}: {result['error']}")
                else:
                    item["staged"] = result
            self._fill_files()
            self._show(self.files.currentRow())
            if errors:
                self._message("<b>QC could not run.</b><br>" + "<br>".join(map(html.escape, errors)))
            elif then and any(i["staged"] and i["staged"]["eligible"] and not i["decision"] for i in self.items):
                then()
            else:
                self._attention()

        self._run(work, done, "Normalizing and running quality control")

    def _admit(self) -> None:
        todo = [i for i in self.items if i["staged"] and i["staged"]["eligible"] and not i["decision"]]

        def work() -> list[Any]:
            out = []
            for item in todo:
                try:
                    out.append(importer.admit(item["staged"]))
                except ValueError as error:
                    out.append({"error": str(error)})
            return out

        def done(records: list[Any]) -> None:
            for item, record in zip(todo, records):
                if "error" in record:
                    self._message("<b>Not admitted.</b> " + html.escape(record["error"]))
                    continue
                item["decision"] = record["status"]
                self.on_admitted(record)
            self._fill_files()
            self._update_buttons()
            self._show(self.files.currentRow())
            self._attention()

        self._run(work, done, "Admitting validated snapshots")

    def _quarantine(self) -> None:
        item = self._current()

        def done(result: dict[str, Any]) -> None:
            item["decision"] = "QUARANTINED"
            if result.get("admission_record"):
                self.on_admitted(result["admission_record"])
            self._fill_files()
            self._update_buttons()
            self._show(self.files.currentRow())

        self._run(lambda: importer.quarantine(item["staged"], "quarantined from the import review"), done, "Quarantining file")

    def _save_preset(self) -> None:
        item = self._current()
        missing = self._form_errors()
        if missing:
            self._message("<b>Complete before saving a preset:</b> " + html.escape(", ".join(missing)))
            return
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name (source / instrument / protocol)")
        if not ok or not name.strip():
            return
        plan = self._plan_with_constants(item["plan"])
        context = importer.build_context(self._fields())

        def done(preset: dict[str, Any]) -> None:
            self._message(f"<b>Preset saved:</b> {html.escape(preset['name'])} v{preset['version']}, bound to schema "
                          f"{preset['schema_fingerprint']}. A later file with exactly this schema reuses it; any other schema is reviewed.")

        self._run(lambda: importer.save_preset(name, plan, context), done, "Saving preset")
