"""One native review screen for the one-click scientific import (RES-636)."""

from __future__ import annotations

import getpass
import html
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget, QProgressBar,
)

from .. import importer
from . import theme
from .services import DynamisAppService

PRIVACY = ["DEIDENTIFIED", "PSEUDONYMOUS", "IDENTIFIABLE", "NOT_APPLICABLE", "TEST_FIXTURE"]
TEXT_FIELDS = (  # (key, label, required)
    ("source_name", "Source name", True), ("publisher", "Publisher / lab", False),
    ("dataset_identity", "Dataset identity / DOI", False), ("license_or_agreement", "Licence or agreement", True),
    ("redistribution_restrictions", "Redistribution restrictions", True),
    ("manufacturer", "Instrument or app manufacturer", True), ("model", "Instrument or app model", True),
    ("serial_number", "Instrument serial / app version", True), ("calibration_status", "Calibration status", False),
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
        self.family = QComboBox()
        for label, value in (("Choose measurement family", None), ("CMJ summaries", "CMJ_FORCE_PLATFORM"),
                             ("Monitoring records", "ATHLETE_MONITORING"), ("Sprint timing", "SPRINT_TIMING"),
                             ("Force recordings", importer.traces.FAMILY)):
            self.family.addItem(label, value)
        self.family.setCurrentIndex(max(0, self.family.findData(plan["mapping"].get("family"))))
        self.family.setAccessibleName("Measurement family to import")
        form.addRow("Import as", self.family)
        note = QLabel("For mixed CMJ and monitoring columns, explicitly choose one family per import. Import the original again for the other family, then link by confirmed participant IDs. Monitoring must have one record per participant and time point; repeated trials are not silently averaged.")
        note.setWordWrap(True)
        layout.addWidget(note)
        names = [c["name"] for c in plan["columns"]]
        family = plan["mapping"].get("family")
        for target, (group, units, _) in importer.COLUMNS.items():
            wanted = {"CMJ_FORCE_PLATFORM": ("CMJ",), "SPRINT_TIMING": ("SPRINT",), importer.traces.FAMILY: ("TRACE",), "ATHLETE_MONITORING": ("MON",), None: ("CMJ", "MON", "SPRINT", "TRACE")}.get(family, ("CMJ",))
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
        chosen_family = self.family.currentData()
        if chosen_family:
            group = next(g for g, f in importer.FAMILIES.items() if f == chosen_family)
            for target in current:
                if importer.COLUMNS[target][0] not in ("ANY", group):
                    out[target] = None
            for target in list(out):
                if importer.COLUMNS[target][0] not in ("ANY", group):
                    out[target] = None
        return out


class ImportReviewDialog(QDialog):
    open_dataset = Signal(str)

    def __init__(self, service: DynamisAppService, run_task: Callable[[Callable[[], Any], Callable[[Any], None], str], None],
                 on_admitted: Callable[[dict[str, Any]], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task, self.on_admitted = service, run_task, on_admitted
        self.items: list[dict[str, Any]] = []
        self.state, self.busy, self.snapshot_id = "select", False, None
        self.diagnostics: list[str] = []
        self.setWindowTitle("Import data")
        self.setAcceptDrops(True)
        screen = QGuiApplication.primaryScreen().availableGeometry() if QGuiApplication.primaryScreen() else None
        self.setMinimumSize(600, 360)
        self.resize(680, 400)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(12)
        self.heading = QLabel("Import your data")
        font = self.heading.font()
        font.setPointSize(20)
        font.setBold(True)
        self.heading.setFont(font)
        root.addWidget(self.heading)
        top = QHBoxLayout()
        self.path_label = QLabel("Drag a file here, or choose one from your computer.")
        self.path_label.setWordWrap(True)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # long paths wrap, never widen the dialog
        self.file_button, self.folder_button = QPushButton("&Choose file"), QPushButton("Choose &folder…")
        self.file_button.setDefault(True)
        self.file_button.setProperty("primary", True)
        self.folder_button.setFlat(True)
        self.file_button.clicked.connect(self._choose_file)
        self.folder_button.clicked.connect(self._choose_folder)
        top.addWidget(self.path_label, 1)
        root.addLayout(top)
        self.drop = QWidget()
        drop_layout = QVBoxLayout(self.drop)
        drop_text = QLabel("Drop your file here")
        drop_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(drop_text)
        drop_layout.addWidget(self.file_button, 0, Qt.AlignmentFlag.AlignCenter)
        formats = QLabel("CSV · TSV · Excel · Parquet · Arrow · JSON")
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(formats)
        drop_layout.addWidget(self.folder_button, 0, Qt.AlignmentFlag.AlignCenter)
        self.drop.setMinimumHeight(170)
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
        self.stage_label = QLabel()
        self.stage_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName("Import processing")
        root.addWidget(self.stage_label)
        root.addWidget(self.progress)
        self.question_box = QWidget()
        question_layout = QVBoxLayout(self.question_box)
        question_layout.setContentsMargins(0, 0, 0, 0)
        self.question = QLabel()
        self.question.setWordWrap(True)
        self.answer = QLineEdit()
        self.answer_choice = QComboBox()
        self.answer_choice.addItem("Choose…", "")
        for value in PRIVACY:
            self.answer_choice.addItem("Synthetic test fixture" if value == "TEST_FIXTURE" else value.replace("_", " ").title(), value)
        self.continue_button = QPushButton("&Continue")
        self.continue_button.clicked.connect(self._answer_question)
        for widget in (self.question, self.answer, self.answer_choice, self.continue_button):
            question_layout.addWidget(widget)
        root.addWidget(self.question_box)

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
        data_page = QSplitter(Qt.Orientation.Vertical)
        for widget in (self.files, self.preview, self.mapping):
            data_page.addWidget(widget)
        data_page.setSizes([90, 200, 160])

        # Source page: the few facts that matter first, everything else under "More"
        self.privacy = QComboBox()
        self.privacy.addItem("Choose…", "")
        for item in PRIVACY:
            self.privacy.addItem(item, item)
        self.privacy.setAccessibleName("Privacy classification")
        self.edits: dict[str, QLineEdit] = {}
        for key, label, _ in TEXT_FIELDS:
            edit = QLineEdit()
            edit.setAccessibleName(label)
            self.edits[key] = edit
        self.edits["protocol_version"].setText("1.0")
        self.edits["publisher"].setPlaceholderText("defaults to the source name")
        self.edits["dataset_identity"].setPlaceholderText("defaults to the source name")
        self.rights = QCheckBox("I reviewed the licence, permitted uses and redistribution terms.")
        self.reviewer = QLineEdit(getpass.getuser())
        self.reviewer.setAccessibleName("Rights verified by")
        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        essentials = QFormLayout()
        essentials.addRow("This data is", self.privacy)
        for key in ("source_name", "license_or_agreement", "redistribution_restrictions", "manufacturer", "model",
                    "serial_number", "calibration_status", "protocol_name"):
            essentials.addRow(dict((k, lab) for k, lab, _ in TEXT_FIELDS)[key], self.edits[key])
        self.rights_row = QWidget()
        rights_layout = QFormLayout(self.rights_row)
        rights_layout.setContentsMargins(0, 0, 0, 0)
        rights_layout.addRow(self.rights)
        rights_layout.addRow("Rights verified by", self.reviewer)
        essentials.addRow(self.rights_row)
        source_layout.addLayout(essentials)
        self.more_button = QPushButton("More ▾")
        self.more_button.setCheckable(True)
        self.more_button.setFlat(True)
        self.more = QWidget()
        more_layout = QFormLayout(self.more)
        for key in ("publisher", "dataset_identity", "protocol_version", "subject_id", "trial_id", "session_id", "sampling_hz",
                    "coordinate_system"):
            more_layout.addRow(dict((k, lab) for k, lab, _ in TEXT_FIELDS)[key], self.edits[key])
        self.more.setVisible(False)
        self.more_button.toggled.connect(lambda on: (self.more.setVisible(on), self.more_button.setText("Fewer ▴" if on else "More ▾")))
        source_layout.addWidget(self.more_button, 0, Qt.AlignmentFlag.AlignLeft)
        source_layout.addWidget(self.more)
        source_layout.addStretch(1)
        self.privacy.currentIndexChanged.connect(self._rights_visibility)
        self._rights_visibility()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(source_page)

        self.verdict = QTextBrowser()
        self.verdict.setAccessibleName("Detection, QC verdict, warnings and provenance")
        self.detail_tabs = QTabWidget()
        self.detail_tabs.addTab(scroll, "Source")
        self.detail_tabs.addTab(data_page, "Data and mapping")
        self.detail_tabs.addTab(self.verdict, "QC report")
        self.details = QWidget()  # everything the researcher can inspect or change; closed unless attention is needed
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addWidget(self.detail_tabs, 1)
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
        self.details_button = QPushButton("View &details / Advanced")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        self.import_button = QPushButton("&Import")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import)
        bottom.addWidget(self.details_button)
        bottom.addStretch(1)
        self.open_button = QPushButton("&Open dataset")
        self.open_button.setProperty("primary", True)
        self.open_button.clicked.connect(self._open_dataset)
        self.another_button = QPushButton("Import &another")
        self.another_button.clicked.connect(self._reset)
        self.retry_button = QPushButton("&Retry")
        self.retry_button.clicked.connect(lambda: self._continue_import() if self.items else self.load(self.input_path))
        for button in (self.retry_button, self.another_button, self.open_button):
            bottom.addWidget(button)
        bottom.addWidget(self.import_button)
        bottom.addWidget(close)
        root.addLayout(bottom)
        self.setTabOrder(self.file_button, self.folder_button)
        self._update_buttons()
        self._update_summary()

    # ---- input
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not self.busy and event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile() and not self.busy:
            self.load(urls[0].toLocalFile())
            event.acceptProposedAction()

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose data file", "", "Data tables (*.csv *.tsv *.txt *.parquet *.pq *.arrow *.feather *.xlsx *.json *.ndjson *.jsonl)")
        if path:
            self.load(path)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose data folder")
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        if self.busy:
            return
        self._reset()
        self.input_path = path
        self._run(lambda: importer.prepare_import(path), self._probed, "Extracting")

    def _run(self, work: Callable[[], Any], done: Callable[[Any], None], label: str) -> None:
        previous_state, previous_text = self.state, self.summary.text()
        self.busy = True
        self._set_state("processing")
        self.stage_label.setText("Extracting → Validating → Saving → Integrating\n" + label)
        def guarded() -> Any:
            try:
                return work()
            except Exception as error:
                return {"error": f"{type(error).__name__}: {error}"}

        def finished(result: Any) -> None:
            self.busy = False
            if isinstance(result, dict) and "error" in result and len(result) == 1:
                self.diagnostics.append(result["error"])
                self.verdict.setPlainText("\n".join(self.diagnostics))
                self._set_state("failure", "The import could not finish. Your original file is unchanged. "
                                "View details for the cause, then retry.")
            else:
                done(result)
                if not self.busy and self.state == "processing":
                    self._set_state(previous_state, previous_text)

        self.run_task(guarded, finished, label)

    def _probed(self, result: dict[str, Any]) -> None:
        self.path_label.setText(f"{result['path']} — {len(result['files'])} supported file(s)"
                                + (f", {len(result['skipped'])} skipped" if result["skipped"] else ""))
        self.skipped = result["skipped"]
        self.items = [{"plan": p, "staged": None, "decision": None, "preset": None, "drift": None} for p in result["files"]]
        self._run(lambda: [self._lookup(i["plan"]) for i in self.items], self._looked_up, "Validating · checking saved mappings")

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
        profile = first["context"] if first else None
        if profile:  # a saved preset, else the source profile used last: the form is filled, not asked
            self._fill_form(profile.get("fields", {}))
        self._profile_fields = self._fields()
        self.items = [dict(i, plan=self._plan_with_constants(i["plan"])) for i in self.items]
        self._fill_files()
        if self.items:
            self.files.selectRow(0)
            self._show(0)  # currentCellChanged does not fire when row 0 was already current
        self._open_details(False)
        self._continue_import()

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
            rq = staged["receipt"]["row_quarantine"]
            if rq["count"]:
                parts.append(f"<b>{rq['count']:,} records quarantined:</b> {self._reasons(rq)}")
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

    def _message(self, text: str, failed: bool = True) -> None:
        self.verdict.setHtml(text)
        if failed:
            self._set_state("failure", "The operation could not finish. View details for the cause, then retry.")

    def _rights_visibility(self) -> None:
        """A test fixture has no rights to review; real data does."""
        self.rights_row.setVisible(self.privacy.currentData() not in ("TEST_FIXTURE", ""))

    def _toggle_details(self, shown: bool) -> None:
        """Details closed is a compact one-line screen; open gives the full review."""
        self.details.setVisible(shown)
        if shown and self.state in ("partial", "failure"):
            self.detail_tabs.setCurrentIndex(2)
        screen = self.screen()
        available = screen.availableGeometry() if screen else None
        height = int(available.height() * 0.9) if available else 700
        self.resize(self.width(), min(760, height) if shown else max(self.minimumSizeHint().height(), 230))
        if available:
            frame = self.frameGeometry()
            self.move(max(available.left(), min(self.x(), available.right() - frame.width() + 1)),
                      max(available.top(), min(self.y(), available.bottom() - frame.height() + 1)))

    def _open_details(self, show: bool = True) -> None:
        self.details_button.setChecked(show)

    def _attention(self) -> None:
        for index, item in enumerate(self.items):
            staged = item["staged"]
            if item["decision"] or not staged or staged["eligible"]:
                continue
            self.files.selectRow(index)
            if staged["rights_status"] not in ("VERIFIED", "FIXTURE_ONLY"):
                self._ask("rights", "Have you reviewed this source’s licence, permitted uses and redistribution terms?")
                return
            errors = " ".join(map(str, staged["quality"]["errors"]))
            if "calibrat" in errors.lower() and not self.edits["calibration_status"].text().strip():
                self._ask("calibration_status", "What is the documented calibration status of this instrument?")
                return
            self._quarantine()
            return
        if any(i["staged"] and i["staged"]["eligible"] and not i["decision"] for i in self.items):
            self._admit()
        elif any(not i["staged"] and not i["decision"] and i["plan"]["state"] != "UNSUPPORTED" for i in self.items):
            self._continue_import()
        else:
            self._finish_import()

    @staticmethod
    def _rows(n: int) -> str:
        return f"{n:,} row" + ("" if n == 1 else "s")

    @staticmethod
    def _reasons(rq: dict[str, Any]) -> str:
        return html.escape(", ".join(f"{k}: {v}" for k, v in rq["reasons"].items()))

    def _set_state(self, state: str, text: str = "") -> None:
        self.state = state
        titles = {"select": "Import your data", "processing": "Integrating your data…",
                  "ready": "Your data is ready.", "partial": "Your data is ready.",
                  "attention": "One thing needs your attention", "failure": "We couldn’t import your data"}
        self.heading.setText(titles[state])
        self.summary.setText(text)
        self.drop.setVisible(state == "select")
        self.path_label.setVisible(state == "select")
        self.progress.setVisible(state == "processing")
        self.stage_label.setVisible(state == "processing")
        self.question_box.setVisible(state == "attention")
        self.open_button.setVisible(state in ("ready", "partial"))
        self.open_button.setDefault(state in ("ready", "partial"))
        self.another_button.setVisible(state in ("ready", "partial", "failure"))
        self.retry_button.setVisible(state == "failure")
        self.import_button.hide()  # retained only for advanced callers; selecting starts the pipeline
        self.details_button.setText("View issues / Advanced" if state == "partial" else "View &details / Advanced")
        self.details_button.setEnabled(state != "processing")
        self.file_button.setEnabled(not self.busy)
        self.folder_button.setEnabled(not self.busy)
        self.details.setEnabled(not self.busy)

    def _update_summary(self) -> None:
        # Intermediate table refreshes must not turn a pending commit into success.
        if not self.items and not self.busy:
            self._set_state("select")

    def _reset(self) -> None:
        if self.busy:
            return
        self.items, self.snapshot_id, self.diagnostics = [], None, []
        self._open_details(False)
        for edit in self.edits.values():
            edit.clear()
        self.edits["protocol_version"].setText("1.0")
        self.privacy.setCurrentIndex(0)
        self.rights.setChecked(False)
        self._fill_files()
        self._set_state("select")
        self.file_button.setFocus()

    def _open_dataset(self) -> None:
        if self.snapshot_id and not self.busy:
            self.accept()
            self.open_dataset.emit(self.snapshot_id)

    def reject(self) -> None:
        if not self.busy:
            super().reject()

    def closeEvent(self, event) -> None:
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)

    def _ask(self, key: str, question: str) -> None:
        self.question_key = key
        self._set_state("attention", "Your file is safely staged. No pending records have been added.")
        self.question.setText(question)
        self.answer.clear()
        self.answer.setAccessibleName(question)
        self.answer.setVisible(key not in ("privacy_status", "mapping", "rights", "source_confirmation"))
        self.answer_choice.setVisible(key == "privacy_status")
        self.answer_choice.setCurrentIndex(0)
        self.continue_button.setText("Review column mapping…" if key == "mapping" else
                                     "Confirm reviewed rights" if key == "rights" else
                                     "Use these source details" if key == "source_confirmation" else "&Continue")
        self.continue_button.setDefault(True)
        (self.answer_choice if key == "privacy_status" else self.answer).setFocus()

    def _answer_question(self) -> None:
        key = self.question_key
        if key == "mapping":
            self._edit_mapping()
        elif key == "rights":
            self.rights.setChecked(True)
        elif key == "source_confirmation":
            self._current()["context_confirmed"] = True
        elif key == "privacy_status":
            value = self.answer_choice.currentData()
            if not value:
                return
            self.privacy.setCurrentIndex(self.privacy.findData(value))
        else:
            if not self.answer.text().strip():
                self.answer.setFocus()
                return
            self.edits[key].setText(self.answer.text().strip())
        self._continue_import()

    def _continue_import(self) -> None:
        if self.busy:
            return
        if not self.items:
            self._finish_import()
            return
        pending = [i for i in self.items if not i["decision"] and i["plan"]["state"] != "UNSUPPORTED"]
        if not pending:
            self._finish_import()
            return
        if not self.privacy.currentData():
            self._ask("privacy_status", "How is this data classified?")
            return
        for key, label, required in TEXT_FIELDS:
            if required and not self.edits[key].text().strip():
                self._ask(key, f"What is the {label.lower()} for this file?")
                return
        for item in pending:
            self.files.selectRow(self.items.index(item))
            if not item["preset"] and any(i["preset"] for i in self.items) and not item.get("context_confirmed"):
                self._ask("source_confirmation", f"Use the source details for {self.edits['source_name'].text()} "
                          f"for {item['plan']['name']} too? You can change them in Advanced.")
                return
            item["plan"] = self._plan_with_constants(item["plan"])
            plan = item["plan"]
            if item["drift"] and not item.get("mapping_confirmed"):
                self._ask("mapping", "This file’s columns differ from the saved mapping. Confirm the columns and units.")
                return
            if plan["ambiguities"]:
                self._ask("mapping", plan["ambiguities"][0])
                return
            if plan["needs"]:
                need = plan["needs"][0]
                key = next((k for k in importer.CONSTANT_FIELDS if need.startswith(k)), None)
                self._ask(key or "mapping", need)
                return
        self._import()

    def _finish_import(self) -> None:
        admitted = [i for i in self.items if (i["decision"] or "").startswith("ADMITTED")]
        pending = [i for i in self.items if not i["decision"] and i["plan"]["state"] != "UNSUPPORTED"]
        if pending:
            self._attention()
            return
        rejected = [i for i in self.items if i not in admitted]
        if admitted:
            count = sum(i["staged"]["receipt"]["normalized_rows"] for i in admitted)
            quarantined = sum(i["staged"]["receipt"]["row_quarantine"]["count"] for i in self.items if i["staged"])
            names = ", ".join(html.escape(i["plan"]["name"]) for i in admitted)
            text = f"<b>{names}</b><br>{count:,} record{'s' if count != 1 else ''} imported."
            if quarantined:
                text += f" {quarantined:,} record{'s' if quarantined != 1 else ''} quarantined."
            if rejected or getattr(self, "skipped", []):
                text += " Some files were not imported. View issues for details."
            if any(i["staged"]["synthetic_only"] for i in admitted):
                text += "<br>Synthetic test fixture · not empirical research data."
            self._set_state("partial" if quarantined or rejected or getattr(self, "skipped", []) else "ready", text)
        else:
            reasons = [i["plan"].get("reason", "No valid records could be imported.") for i in rejected]
            self._set_state("failure", html.escape(" ".join(reasons) or "No supported files were found."))

    def _inputs(self) -> tuple:
        return (tuple(sorted(self._fields().items())), tuple(sorted(self._constants().items())), self.rights.isChecked())

    def _import(self) -> None:
        """The one explicit click: QC if it has not run, then add every eligible file as an immutable batch."""
        if getattr(self, "_staged_inputs", None) != self._inputs():  # the form changed after QC ran: its result is stale
            for item in self.items:
                if not item["decision"]:
                    item["staged"] = None
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
        fields["publisher"] = fields.get("publisher") or fields.get("source_name", "")
        fields["dataset_identity"] = fields.get("dataset_identity") or fields.get("source_name", "")
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
        item["mapping_confirmed"] = True
        self._fill_files()
        self._show(self.files.currentRow())

    def _plan_with_constants(self, plan: dict[str, Any]) -> dict[str, Any]:
        if plan["state"] == "UNSUPPORTED":
            return plan
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
        changes = {k: v for k, v in self._fields().items() if v != getattr(self, "_profile_fields", {}).get(k)}
        contexts = [importer.build_context({**item["preset"]["context"]["fields"], **changes})
                    if item["preset"] else context for item in todo]
        self._staged_inputs = self._inputs()
        reviewer = self.reviewer.text().strip() if self.rights.isChecked() else ""

        def work() -> list[Any]:
            results = []
            for item, item_context in zip(todo, contexts):
                try:
                    results.append(importer.stage(item["plan"], item_context, rights_reviewed_by=reviewer))
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

        self._run(work, done, "Validating · normalizing and checking records")

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
            errors = []
            for item, record in zip(todo, records):
                if "error" in record:
                    errors.append(record["error"])
                    continue
                item["record"] = record
            if errors:
                self.diagnostics.extend(errors)
                self.verdict.setPlainText("\n".join(self.diagnostics))
                self._set_state("failure", "Saving could not finish. View details and retry; any completed batches are kept.")
                return
            self._integrate()

        self._run(work, done, "Saving · writing validated records")

    def _integrate(self) -> None:
        todo = [i for i in self.items if i.get("record") and not i["decision"]]

        def work() -> None:
            catalogue = {d["id"] for d in self.service.list_workspace()}
            for item in todo:
                record = item["record"]
                snapshot = record.get("dataset_snapshot_id")
                if not record["status"].startswith("ADMITTED") or not snapshot or snapshot not in catalogue:
                    raise ValueError("The saved batch is not available in the dataset catalogue.")
                self.service.get_dataset_detail(snapshot)

        def done(_result: Any) -> None:
            for item in todo:
                record = item["record"]
                item["decision"] = record["status"]
                self.snapshot_id = record["dataset_snapshot_id"]
                self.on_admitted(record)
            self._fill_files()
            self._update_buttons()
            self._show(self.files.currentRow())
            self._attention()

        self._run(work, done, "Integrating · checking dataset availability")

    def _quarantine(self) -> None:
        item = self._current()

        def done(result: dict[str, Any]) -> None:
            item["decision"] = "QUARANTINED"
            if result.get("admission_record"):
                self.on_admitted(result["admission_record"])
            self._fill_files()
            self._update_buttons()
            self._show(self.files.currentRow())
            self._attention()

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
                          f"{preset['schema_fingerprint']}. A later file with exactly this schema reuses it; any other schema is reviewed.", failed=False)

        self._run(lambda: importer.save_preset(name, plan, context), done, "Saving preset")
