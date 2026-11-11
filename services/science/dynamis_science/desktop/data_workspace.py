"""Native Data Workspace: browse, filter, query and inspect admitted datasets, then continue into analysis (RES-636)."""

from __future__ import annotations

import html
import json
from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit,
    QPushButton, QSplitter, QTableView, QTabWidget, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from .. import dataworkspace
from . import theme
from .workbench.signals_view import SignalsView

PAGE = 200
SIGNAL_TABLES = {"force_signals", "force_traces", "signal_trials", "trace_index"}
EXAMPLE = "SELECT * FROM {table} LIMIT 20"


class RowsModel(QAbstractTableModel):
    """Read-only rows for one fetched page; missing values render as an em dash."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.columns: list[str] = []
        self.rows: list[tuple] = []

    def set_data(self, columns: list[str], rows: list[tuple]) -> None:
        self.beginResetModel()
        self.columns, self.rows = list(columns), list(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section] if orientation == Qt.Orientation.Horizontal else str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return "—" if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (int, float)):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


def _view(name: str) -> QTableView:
    view = QTableView()
    view.setAccessibleName(name)
    view.setAlternatingRowColors(True)
    view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
    view.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
    view.verticalHeader().setDefaultSectionSize(22)
    return view


class DataWorkspaceDialog(QDialog):
    def __init__(self, service: Any, run_task: Callable[[Callable[[], Any], Callable[[Any], None], str], None],
                 on_analyze: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task, self.on_analyze = service, run_task, on_analyze
        self.setWindowTitle("Data workspace")
        self.setMinimumSize(700, 460)
        self.resize(1180, 700)
        self.datasets: list[dict[str, Any]] = []
        self.snapshot_id: str | None = None
        self.table: str | None = None
        self.filters: list[dict[str, Any]] = []
        self.sort: str | None = None
        self.descending = False
        self.offset = 0
        self.total = 0
        self.profile_columns: list[dict[str, Any]] = []
        self.hidden: set[str] = set()
        self.signals: SignalsView | None = None

        root = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search datasets")
        self.search.setAccessibleName("Search datasets")
        self.search.textChanged.connect(self._fill_datasets)
        self.catalogue = QListWidget()
        self.catalogue.setAccessibleName("Dataset catalogue")
        self.catalogue.currentRowChanged.connect(self._dataset_chosen)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.catalogue, 1)
        split.addWidget(left)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._table_tab(), "&Table")
        self.tabs.addTab(self._columns_tab(), "&Columns")
        self.tabs.addTab(self._signals_tab(), "T&races")
        self.tabs.addTab(self._query_tab(), "&Query")
        self.tabs.addTab(self._inspector_tab(), "Quality and &lineage")
        self.tabs.currentChanged.connect(self._tab_changed)
        split.addWidget(self.tabs)
        split.setSizes([260, 900])
        root.addWidget(split, 1)

        self.status = QLabel("Choose a dataset.")
        self.status.setWordWrap(True)
        bottom = QHBoxLayout()
        self.analyze_button = QPushButton("&Analyze this dataset")
        self.analyze_button.setDefault(True)
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self._analyze)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.analyze_button)
        bottom.addWidget(close)
        root.addLayout(bottom)

    # ---- tabs
    def _table_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        top = QHBoxLayout()
        self.table_picker = QComboBox()
        self.table_picker.setAccessibleName("Table")
        self.table_picker.currentIndexChanged.connect(self._table_chosen)
        self.columns_button = QToolButton()
        self.columns_button.setText("Columns ▾")
        self.columns_button.setAccessibleName("Choose visible columns")
        self.columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.columns_menu = QMenu(self.columns_button)
        self.columns_button.setMenu(self.columns_menu)
        top.addWidget(QLabel("Table"))
        top.addWidget(self.table_picker, 1)
        top.addWidget(self.columns_button)
        layout.addLayout(top)
        flt = QHBoxLayout()
        self.filter_column, self.filter_op, self.filter_value = QComboBox(), QComboBox(), QLineEdit()
        self.filter_column.setAccessibleName("Filter column")
        self.filter_op.setAccessibleName("Filter operator")
        self.filter_op.addItems(list(dataworkspace.OPS))
        self.filter_value.setPlaceholderText("value")
        self.filter_value.setAccessibleName("Filter value")
        self.filter_value.returnPressed.connect(self._add_filter)
        add, clear = QPushButton("Add &filter"), QPushButton("Clear filters")
        add.clicked.connect(self._add_filter)
        clear.clicked.connect(self._clear_filters)
        for widget in (self.filter_column, self.filter_op):
            flt.addWidget(widget)
        flt.addWidget(self.filter_value, 1)
        flt.addWidget(add)
        flt.addWidget(clear)
        layout.addLayout(flt)
        self.filter_list = QLabel("No filters")
        self.filter_list.setAccessibleName("Active filters")
        layout.addWidget(self.filter_list)
        self.rows_model = RowsModel(self)
        self.table_view = _view("Rows")
        self.table_view.setModel(self.rows_model)
        self.table_view.horizontalHeader().setSectionsClickable(True)
        self.table_view.horizontalHeader().sectionClicked.connect(self._sort_by)
        layout.addWidget(self.table_view, 1)
        nav = QHBoxLayout()
        self.prev_button, self.next_button = QPushButton("◀ Previous"), QPushButton("Next ▶")
        self.page_label = QLabel("")
        self.prev_button.clicked.connect(lambda: self._move(-PAGE))
        self.next_button.clicked.connect(lambda: self._move(PAGE))
        nav.addWidget(self.prev_button)
        nav.addWidget(self.next_button)
        nav.addWidget(self.page_label, 1)
        layout.addLayout(nav)
        return page

    def _columns_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Types, units (from the canonical column name), missingness and range."))
        self.profile_model = RowsModel(self)
        view = _view("Column profile")
        view.setModel(self.profile_model)
        layout.addWidget(view, 1)
        return page

    def _signals_tab(self) -> QWidget:
        self.signals_page = QWidget()
        self.signals_layout = QVBoxLayout(self.signals_page)
        self.signals_note = QLabel("This dataset has no sample-level recordings.")
        self.signals_layout.addWidget(self.signals_note)
        return self.signals_page

    def _query_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.query_hint = QLabel("Read-only SELECT over this dataset's tables (Polars SQL). No writes, files or scripts.")
        self.query_hint.setWordWrap(True)
        self.query_text = QPlainTextEdit()
        self.query_text.setAccessibleName("SQL query")
        self.query_text.setMaximumHeight(110)
        run = QPushButton("Run &SQL")
        run.clicked.connect(self._run_query)
        self.query_status = QLabel("")
        self.query_model = RowsModel(self)
        view = _view("Query result")
        view.setModel(self.query_model)
        row = QHBoxLayout()
        row.addWidget(run)
        row.addWidget(self.query_status, 1)
        for widget in (self.query_hint, self.query_text):
            layout.addWidget(widget)
        layout.addLayout(row)
        layout.addWidget(view, 1)
        return page

    def _inspector_tab(self) -> QWidget:
        self.inspector = QTextBrowser()
        self.inspector.setAccessibleName("Rights, QC, exclusions, instruments and lineage")
        return self.inspector

    # ---- catalogue
    def open(self, snapshot_id: str | None = None) -> None:
        self._wanted = snapshot_id
        self._guard(self.service.list_datasets, self._catalogue_loaded, "Loading dataset catalogue")

    def _guard(self, work: Callable[[], Any], done: Callable[[Any], None], label: str) -> None:
        def guarded() -> Any:
            try:
                return work()
            except (ValueError, LookupError) as error:  # ImportBlocked, ResearchNotFound, validation
                return {"__error__": str(error)}

        def finished(result: Any) -> None:
            if isinstance(result, dict) and "__error__" in result:
                self.status.setText(result["__error__"])
            else:
                done(result)

        self.run_task(guarded, finished, label)

    def _catalogue_loaded(self, datasets: list[dict[str, Any]]) -> None:
        self.datasets = datasets
        self._fill_datasets()
        wanted = getattr(self, "_wanted", None)
        ids = [self.catalogue.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.catalogue.count())]
        self.catalogue.setCurrentRow(ids.index(wanted) if wanted in ids else 0 if ids else -1)

    def _fill_datasets(self) -> None:
        needle = self.search.text().strip().lower()
        self.catalogue.blockSignals(True)
        self.catalogue.clear()
        for item in self.datasets:
            kind = "REAL" if item.get("real_data") else "SYNTHETIC"
            rows = sum(item.get("row_counts", {}).values())
            source = (item.get("source") or {}).get("name") or ""
            text = f"{source or item.get('label') or item['id']}\n{item.get('label') or ''}\n{kind} · {rows:,} rows · {item['id']}"
            if needle and needle not in (text + " ".join(item.get("tables", []))).lower():
                continue
            entry = QListWidgetItem(text)
            entry.setData(Qt.ItemDataRole.UserRole, item["id"])
            self.catalogue.addItem(entry)
        self.catalogue.blockSignals(False)

    def _dataset_chosen(self, row: int) -> None:
        if row < 0:
            return
        sid = self.catalogue.item(row).data(Qt.ItemDataRole.UserRole)
        dataset = next(d for d in self.datasets if d["id"] == sid)
        self.snapshot_id = sid
        self.analyze_button.setEnabled(True)
        self.status.setText(f"{dataset.get('label') or sid} — {len(dataset.get('tables', []))} table(s)")
        self.table_picker.blockSignals(True)
        self.table_picker.clear()
        self.table_picker.addItems(dataset.get("tables", []))
        self.table_picker.blockSignals(False)
        has_signals = bool(SIGNAL_TABLES & set(dataset.get("tables", [])))
        self.signals_note.setVisible(not has_signals)
        if self.signals is not None:
            self.signals.setVisible(has_signals)
            if has_signals:
                self.signals.set_snapshot(sid)
                self._first_trial(sid, 20)
        self.query_text.setPlainText(EXAMPLE.format(table=(dataset.get("tables") or ["table"])[0]))
        self.query_hint.setText("Read-only SELECT over: " + ", ".join(dataset.get("tables", [])) +
                                ". No writes, files or scripts.")
        self.query_model.set_data([], [])
        self._guard(lambda: self.service.dataset_inspector(sid), self._inspected, "Reading provenance")
        self._table_chosen()

    # ---- table
    def _table_chosen(self) -> None:
        self.table = self.table_picker.currentText() or None
        self.filters, self.sort, self.descending, self.offset, self.hidden = [], None, False, 0, set()
        self._show_filters()
        if not (self.table and self.snapshot_id):
            return
        sid, table = self.snapshot_id, self.table
        self._guard(lambda: self.service.table_profile(sid, table), self._profiled, "Profiling columns")

    def _profiled(self, profile: dict[str, Any]) -> None:
        self.profile_columns = profile["columns"]
        self.profile_model.set_data(
            ["column", "type", "unit", "missing", "missing %", "min", "max"],
            [(c["name"], c["dtype"], c["unit"] or "—", c["missing"], f"{c['missing_pct']:.1f}", c["min"], c["max"])
             for c in profile["columns"]])
        self.filter_column.clear()
        self.filter_column.addItems([c["name"] for c in profile["columns"]])
        self.columns_menu.clear()
        for column in profile["columns"]:
            action = self.columns_menu.addAction(f"{column['name']}" + (f" ({column['unit']})" if column["unit"] else ""))
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(lambda on, name=column["name"]: self._toggle_column(name, on))
        self._fetch()

    def _toggle_column(self, name: str, visible: bool) -> None:
        (self.hidden.discard if visible else self.hidden.add)(name)
        self._fetch()

    def _fetch(self) -> None:
        if not (self.table and self.snapshot_id):
            return
        sid, table, offset = self.snapshot_id, self.table, self.offset
        flt, sort, desc = list(self.filters), self.sort, self.descending
        cols = [c["name"] for c in self.profile_columns if c["name"] not in self.hidden]
        self._guard(lambda: self.service.query_table(sid, table, offset, PAGE, flt, sort, desc, cols), self._page, "Reading rows")

    def _page(self, result: dict[str, Any]) -> None:
        self.total = result["total_rows"]
        units = {c["name"]: c["unit"] for c in self.profile_columns}
        self.rows_model.set_data([f"{c} ({units[c]})" if units.get(c) else c for c in result["columns"]], result["rows"])
        self.table_view.resizeColumnsToContents()
        last = min(self.offset + PAGE, self.total)
        self.page_label.setText(f"Rows {self.offset + 1 if self.total else 0:,}–{last:,} of {self.total:,}"
                                + (f" (filtered)" if self.filters else ""))
        self.prev_button.setEnabled(self.offset > 0)
        self.next_button.setEnabled(last < self.total)

    def _move(self, delta: int) -> None:
        self.offset = max(0, self.offset + delta)
        self._fetch()

    def _sort_by(self, section: int) -> None:
        name = self.rows_model.columns[section].split(" (")[0]
        self.descending = (not self.descending) if self.sort == name else False
        self.sort, self.offset = name, 0
        self._fetch()

    def _add_filter(self) -> None:
        column, op, value = self.filter_column.currentText(), self.filter_op.currentText(), self.filter_value.text()
        if not column or (op not in ("is empty", "is not empty") and not value.strip()):
            self.status.setText("Enter a value for the filter.")
            return
        self.filters.append({"column": column, "op": op, "value": value})
        self.offset = 0
        self.filter_value.clear()
        self._show_filters()
        self._fetch()

    def _clear_filters(self) -> None:
        self.filters, self.offset = [], 0
        self._show_filters()
        self._fetch()

    def _show_filters(self) -> None:
        self.filter_list.setText("Filters: " + "  AND  ".join(f"{f['column']} {f['op']} {f.get('value', '')}".strip()
                                                              for f in self.filters) if self.filters else "No filters")

    # ---- traces / query / inspector
    def _tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index).replace("&", "") != "Traces" or self.snapshot_id is None:
            return
        dataset = next((d for d in self.datasets if d["id"] == self.snapshot_id), {})
        if SIGNAL_TABLES & set(dataset.get("tables", [])):
            if self.signals is None:
                self.signals = SignalsView(self.service, lambda fn, done: self.run_task(fn, done, "Loading signals"))
                self.signals_layout.addWidget(self.signals)
            self.signals.setVisible(True)
            self.signals.set_snapshot(self.snapshot_id)
            self._first_trial(self.snapshot_id, 20)

    def _first_trial(self, snapshot_id: str, attempts: int) -> None:
        """Show the first recording once the trial list has loaded, so the tab is never an empty plot."""
        view = self.signals
        if view is None or snapshot_id != self.snapshot_id or view.waveform is not None:
            return
        if view.trial_list.count():
            view.show_trial(view.trial_list.item(0).data(Qt.ItemDataRole.UserRole))
        elif attempts:
            QTimer.singleShot(150, lambda: self._first_trial(snapshot_id, attempts - 1))

    def _run_query(self) -> None:
        sid, sql = self.snapshot_id, self.query_text.toPlainText()
        if not sid:
            return
        self.query_status.setText("Running…")

        def done(result: dict[str, Any]) -> None:
            self.query_model.set_data(result["columns"], result["rows"])
            self.query_status.setText(f"{len(result['rows']):,} rows" + (f" (limited to {result['limit']:,})" if result["truncated"] else ""))

        def failed(message: str) -> None:
            self.query_status.setText(message)

        def work() -> Any:
            try:
                return self.service.run_readonly_query(sid, sql)
            except ValueError as error:
                return {"__error__": str(error)}

        self.run_task(work, lambda r: failed(r["__error__"]) if "__error__" in r else done(r), "Running read-only query")

    def _inspected(self, info: dict[str, Any]) -> None:
        t, esc = theme.tokens(), html.escape
        quality, record, source = info.get("quality") or {}, info.get("admission") or {}, info.get("source") or {}
        kind = "REAL DATA" if info["real_data"] else "SYNTHETIC"
        parts = [f"<h3>{esc(str(info.get('label') or info['id']))}</h3>",
                 f"<b>{kind}</b> · {esc(info['id'])}" + (f" · <b>{esc(info['admission_class'])}</b>" if info.get("admission_class") else "")]
        if info.get("admission_class"):
            parts.append("Simulated instrument, no physical calibration, no empirical validity, not eligible as real scientific evidence.")
        rights = source.get("rights_status") or record.get("rights_status") or "recorded in the source manifest"
        license_info = source.get("license", {})
        parts.append(f"<b>Rights</b> {esc(str(rights))} · licence {esc(str(license_info.get('name') if isinstance(license_info, dict) else license_info or 'n/a'))}"
                     f" · permitted: {esc(', '.join(source.get('permitted_uses', [])) or 'n/a')}")
        if quality:
            parts.append(f"<b>QC</b> {esc(quality['status'])} — {esc(', '.join(f'{k} {v}' for k, v in quality.get('counts', {}).items()))}")
            parts += [f"<span style='color:{t['bad']}'>Error: {esc(str(e))}</span>" for e in quality.get("errors", [])]
            parts += [f"<span style='color:{t['warn']}'>Warning: {esc(str(w))}</span>" for w in quality.get("warnings", [])]
            excluded = quality.get("rejected_record_ids", []) + quality.get("quarantined_record_ids", [])
            parts.append("<b>Exclusions</b> " + (esc(", ".join(map(str, excluded))) if excluded else "none recorded"))
        for inst in info.get("provenance", {}).get("instrument_metadata", []):
            parts.append(f"<b>Instrument</b> {esc(str(inst.get('id')))} · {esc(str(inst.get('manufacturer')))} {esc(str(inst.get('model')))} · "
                         f"calibration {esc(str(inst.get('calibration_status')))}")
        for receipt in info.get("receipts", []):
            parts.append(f"<b>Import</b> {esc(receipt['raw_filename'])} · raw SHA-256 {esc(receipt['raw_sha256'][:16])}… · adapter "
                         f"{esc(receipt['adapter'])} · schema {esc(receipt['schema_fingerprint'])} · mapping {esc(json.dumps({k: v['source'] for k, v in receipt['mapping']['columns'].items()}))}")
        meta = (info.get("admission") or {})
        parts.append("<b>Tables</b> " + esc(", ".join(f"{n} ({c:,} rows)" for n, c in info.get("row_counts", {}).items())))
        parts.append("<b>Content hashes</b> " + (esc("; ".join(f"{k} {str(v)[:12]}…" for k, v in info.get("checksums", {}).items())) or "n/a"))
        parts.append("<b>Parser</b> " + esc(str(meta.get("parser_version", "n/a"))) + " · schema " + esc(str(meta.get("schema_version", "n/a"))))
        parts.append("<b>Used by studies</b> " + (esc(", ".join(info.get("used_by_studies", []))) or "none"))
        self.inspector.setHtml("<br>".join(parts))

    def _analyze(self) -> None:
        if self.snapshot_id:
            self.on_analyze(self.snapshot_id)
            self.accept()
