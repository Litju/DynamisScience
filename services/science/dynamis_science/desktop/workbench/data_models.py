"""Bounded Qt table models for the workbench Data pane (Rows, Variables, By athlete).

All data comes from DynamisAppService.read_table_page / get_dataset_detail (or any object
with the same two methods).  Rows are paged, never loaded unbounded.  Missing values
are exposed through MissingRole and displayed as a dash; they are never blank or imputed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QByteArray, QMimeData, QModelIndex, Qt

from .spec import CATEGORICAL, IDENTIFIER, NUMERICAL, ORDINAL

MISSING_TEXT = "—"
VARIABLE_MIME = "application/x-dynamis-variable"
MissingRole = Qt.ItemDataRole.UserRole + 1  # bool: value is missing
SortRole = Qt.ItemDataRole.UserRole + 2  # raw comparable value (None sorts as missing)
VariableRole = Qt.ItemDataRole.UserRole + 3  # Variable dataclass (Variables model) / column name
PAGE_SIZE = 200  # service limit is 500
MAX_LOADED_ROWS = 20_000  # hard cap per model; `truncated` is set when reached

_ID_NAMES = {"source_row", "native_subject_id"}
_ORDINAL_NAMES = {"occasion", "trial_number", "phase", "session_number", "trial"}
# longest suffix first; units follow the canonical column naming in real_mendeley / real_movesmart
_UNIT_SUFFIXES = (
    ("_n_kg", "N/kg"), ("_kg_kg", "kg/kg"), ("_n_s", "N s"), ("_m_s", "m/s"), ("_years", "years"),
    ("_cm", "cm"), ("_kg", "kg"), ("_hz", "Hz"), ("_n", "N"), ("_m", "m"), ("_s", "s"), ("_g", "g"),
)


# display decimals per unit (design E4: cm and kg to 0.1, seconds to 0.01); unknown units: 2
UNIT_DECIMALS = {"cm": 1, "kg": 1, "years": 1, "g": 1, "N s": 1, "s": 2, "m": 2, "m/s": 2, "N/kg": 2,
                 "kg/kg": 2, "N": 0, "Hz": 0}


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _unit_for(name: str) -> str:
    try:  # canonical registry first (unit of a metric column is authoritative)
        from ... import realanalysis

        for meta in realanalysis.METRICS.values():
            if meta["column"] == name:
                return meta["unit"]
    except Exception:  # registry unavailable: fall back to the suffix rule
        pass
    return next((u for suffix, u in _UNIT_SUFFIXES if name.lower().endswith(suffix)), "")


def classify_variable(name: str, dtype: str) -> str:
    """numerical / categorical / ordinal / identifier from column name and Arrow dtype."""
    lowered = name.lower()
    if lowered.endswith("_id") or lowered == "id" or lowered in _ID_NAMES:
        return IDENTIFIER
    if lowered in _ORDINAL_NAMES:
        return ORDINAL
    d = dtype.lower()
    if d.startswith(("int", "uint", "float", "double", "decimal")):
        return NUMERICAL
    return CATEGORICAL  # string, bool, list (flags), anything else


@dataclass(frozen=True)
class Variable:
    name: str
    type: str
    unit: str
    n: int | None  # non-missing count; None when unknown
    missing: int | None
    missing_pct: float | None
    quality: str  # complete / some missing / high missing / unknown


def _quality(missing: int | None, total: int) -> str:
    if missing is None:
        return "unknown"
    if missing == 0:
        return "complete"
    return "high missing" if total and missing / total >= 0.2 else "some missing"


def variables_from_detail(detail: dict[str, Any], table: str) -> list[Variable]:
    meta = next(t for t in detail["tables"] if t["name"] == table)
    total = int(meta["rows"])
    out = []
    for col in meta["columns"]:
        nulls = col.get("null_count")  # absent for synthetic tables: unknown, not zero
        out.append(
            Variable(
                col["name"], classify_variable(col["name"], col["dtype"]), _unit_for(col["name"]),
                None if nulls is None else total - nulls, nulls,
                None if nulls is None or not total else 100.0 * nulls / total,
                _quality(nulls, total),
            )
        )
    return out


class RowsModel(QAbstractTableModel):
    """Raw rows, fetched page by page via canFetchMore / fetchMore."""

    def __init__(self, service: Any, snapshot_id: str, table: str, parent=None, page_size: int = PAGE_SIZE,
                 max_rows: int = MAX_LOADED_ROWS) -> None:
        super().__init__(parent)
        self._service, self._snapshot, self._table = service, snapshot_id, table
        self._page, self._max = min(page_size, 500), max_rows
        self._rows: list[dict[str, Any]] = []
        self._columns: list[str] = []
        self.total_rows = 0
        self._started = False

    @property
    def truncated(self) -> bool:
        return len(self._rows) >= self._max and len(self._rows) < self.total_rows

    @property
    def columns(self) -> list[str]:
        return list(self._columns)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def canFetchMore(self, parent=QModelIndex()) -> bool:
        if parent.isValid():
            return False
        return not self._started or (len(self._rows) < min(self.total_rows, self._max))

    def fetchMore(self, parent=QModelIndex()) -> None:
        if not self.canFetchMore(parent):
            return
        limit = min(self._page, self._max - len(self._rows)) if self._started else self._page
        page = self._service.read_table_page(self._snapshot, self._table, len(self._rows), max(1, limit))
        first = not self._started
        self._started = True
        self.total_rows = int(page["total_rows"])
        rows = page["rows"][: self._max - len(self._rows)]
        if first:
            self.beginResetModel()
            self._columns = list(page["columns"])
            self._rows = list(rows)
            self.endResetModel()
        elif rows:
            self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows) + len(rows) - 1)
            self._rows.extend(rows)
            self.endInsertRows()
        else:  # service returned nothing: stop asking
            self.total_rows = len(self._rows)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._columns[section] if orientation == Qt.Orientation.Horizontal else section + 1
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        name = self._columns[index.column()]
        value = self._rows[index.row()].get(name)
        if role == MissingRole:
            return is_missing(value)
        if role == SortRole:
            return None if is_missing(value) else value
        if role == Qt.ItemDataRole.DisplayRole:
            if is_missing(value):
                return MISSING_TEXT
            return f"{value:.6g}" if isinstance(value, float) else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter) if isinstance(value, (int, float)) else None
        return None


VARIABLE_COLUMNS = ("Variable", "Type", "Unit", "N", "Missing", "Missing %", "Quality", "Role", "Distribution")
HistRole = Qt.ItemDataRole.UserRole + 4  # list[int] bin counts of a numeric variable (Distribution column)
HIST_BINS = 12
DISTRIBUTION_ROWS = 2000  # the Distribution column summarises at most this many rows (bounded, not the whole table)


def distribution_of(values: list[Any], vtype: str) -> tuple[list[int] | None, str]:
    """(histogram bins for a numeric variable, text) from the bounded rows; missing values are left out."""
    present = [v for v in values if not is_missing(v)]
    if not present:
        return None, MISSING_TEXT
    if vtype == NUMERICAL:
        lo, hi = min(present), max(present)
        bins = [0] * HIST_BINS
        for v in present:
            bins[min(HIST_BINS - 1, int((v - lo) / (hi - lo) * HIST_BINS)) if hi > lo else 0] += 1
        return bins, f"{lo:.4g} to {hi:.4g}"
    levels = sorted({str(v) for v in present})
    if vtype == IDENTIFIER:
        return None, f"{len(levels)} distinct"
    return None, " · ".join(levels[:4]) + (f" · +{len(levels) - 4}" if len(levels) > 4 else "")


class VariablesModel(QAbstractTableModel):
    """One row per variable.  Rows are draggable (mime VARIABLE_MIME, utf-8 variable name)."""

    def __init__(self, variables: list[Variable] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._vars = list(variables or [])
        self._roles: dict[str, str] = {}
        self._distribution: dict[str, tuple[list[int] | None, str]] = {}

    def set_roles(self, roles: dict[str, str]) -> None:
        """Role column: the current spec's role label per variable ("" for none)."""
        self._roles = dict(roles)
        if self._vars:
            self.dataChanged.emit(self.index(0, 7), self.index(len(self._vars) - 1, 7))

    def set_distribution(self, rows: list[dict[str, Any]]) -> None:
        self._distribution = {v.name: distribution_of([r.get(v.name) for r in rows], v.type) for v in self._vars}
        if self._vars:
            self.dataChanged.emit(self.index(0, 8), self.index(len(self._vars) - 1, 8))

    @classmethod
    def from_service(cls, service: Any, snapshot_id: str, table: str, parent=None) -> "VariablesModel":
        return cls(variables_from_detail(service.get_dataset_detail(snapshot_id), table), parent)

    def variables(self) -> list[Variable]:
        return list(self._vars)

    def variable_types(self) -> dict[str, str]:
        return {v.name: v.type for v in self._vars}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._vars)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(VARIABLE_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return VARIABLE_COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        v = self._vars[index.row()]
        bins, text = self._distribution.get(v.name, (None, MISSING_TEXT))
        cells = (v.name, v.type, v.unit, v.n, v.missing, v.missing_pct, v.quality, self._roles.get(v.name, ""), text)
        raw = cells[index.column()]
        if role == VariableRole:
            return v
        if role == HistRole:
            return bins if index.column() == 8 else None
        if role == MissingRole:  # the Missing columns flag any gap, or unknown counts
            return index.column() in (4, 5) and (raw is None or raw > 0)
        if role == SortRole:
            return raw
        if role == Qt.ItemDataRole.DisplayRole:
            if raw is None:
                return MISSING_TEXT  # unknown is shown, never blank
            if index.column() == 5:
                return f"{raw:.1f}%"
            return str(raw) if raw != "" else MISSING_TEXT
        return None

    def flags(self, index):
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else base

    def mimeTypes(self) -> list[str]:
        return [VARIABLE_MIME]

    def mimeData(self, indexes) -> QMimeData:
        names = list(dict.fromkeys(self._vars[i.row()].name for i in indexes if i.isValid()))
        mime = QMimeData()
        mime.setData(VARIABLE_MIME, QByteArray("\n".join(names).encode("utf-8")))
        return mime

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction


def variables_from_mime(mime: QMimeData) -> list[str]:
    if not mime.hasFormat(VARIABLE_MIME):
        return []
    return bytes(mime.data(VARIABLE_MIME)).decode("utf-8").split("\n")


class ByAthleteModel(QAbstractTableModel):
    """Pivot: athlete (rows) x occasion (columns) for one variable.

    Built from bounded pages (at most `max_rows` source rows; `truncated` says if cut).
    An athlete with no value for an occasion is Missing, never blank.
    """

    def __init__(self, service: Any, snapshot_id: str, table: str, subject: str, occasion: str,
                 value: str, parent=None, max_rows: int = MAX_LOADED_ROWS) -> None:
        super().__init__(parent)
        self.subject, self.occasion, self.value = subject, occasion, value
        self.truncated = False
        cells: dict[tuple[Any, Any], Any] = {}
        offset, total = 0, None
        while total is None or offset < min(total, max_rows):
            page = service.read_table_page(snapshot_id, table, offset, min(500, max_rows - offset))
            total = int(page["total_rows"])
            if not page["rows"]:
                break
            for row in page["rows"]:
                v = row.get(value)
                cells[(row.get(subject), row.get(occasion))] = None if is_missing(v) else v
            offset += len(page["rows"])
        self.truncated = total is not None and offset < total
        self.unit = _unit_for(value)
        floats = any(isinstance(v, float) for v in cells.values())
        self.decimals = UNIT_DECIMALS.get(self.unit, 2) if floats else 0
        self._athletes = sorted({a for a, _ in cells}, key=str)
        self._occasions = sorted({o for _, o in cells}, key=lambda o: (str(type(o)), o))
        self._cells = cells

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._athletes)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._occasions)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return (f"{self.occasion} {self._occasions[section]}" if orientation == Qt.Orientation.Horizontal
                    else str(self._athletes[section]))
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        v = self._cells.get((self._athletes[index.row()], self._occasions[index.column()]))
        if role == MissingRole:
            return v is None
        if role == SortRole:
            return v
        if role == Qt.ItemDataRole.DisplayRole:
            return MISSING_TEXT if v is None else self.format(v)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def format(self, value: Any, signed: bool = False) -> str:
        """``value`` at the variable's display precision (``signed``: always show + or -)."""
        if not isinstance(value, (int, float)):
            return str(value)
        text = f"{value:{'+' if signed else ''},.{self.decimals}f}"
        return f"{0:,.{self.decimals}f}" if float(text.replace(",", "")) == 0 else text  # no "-0.0"
