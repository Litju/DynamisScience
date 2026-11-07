"""Qt model/view adapters for bounded catalogues and lazy Parquet previews."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from .services import DynamisAppService
from .tasks import TaskRunner


class RecordTableModel(QAbstractTableModel):
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self.rows = rows or []
        self.columns = list(dict.fromkeys(key for row in self.rows for key in row))

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.columns = list(dict.fromkeys(key for row in rows for key in row))
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self.rows[index.row()].get(self.columns[index.column()])
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return "" if value is None else str(value)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self.columns[section] if orientation == Qt.Orientation.Horizontal and section < len(self.columns) else str(section + 1)


class ParquetPreviewTableModel(QAbstractTableModel):
    """Fetch at most 500 Arrow rows per request without blocking the GUI thread."""

    def __init__(self, service: DynamisAppService, runner: TaskRunner) -> None:
        super().__init__()
        self.service = service
        self.runner = runner
        self.snapshot_id = ""
        self.table_name = ""
        self.columns: list[str] = []
        self.rows: list[dict[str, Any]] = []
        self.total_rows = 0
        self.loading = False
        self.error: Exception | None = None
        self.generation = 0

    def set_table(self, snapshot_id: str, table_name: str, row_count: int, columns: list[str]) -> None:
        self.beginResetModel()
        self.generation += 1
        self.snapshot_id = snapshot_id
        self.table_name = table_name
        self.columns = columns
        self.rows = []
        self.total_rows = row_count
        self.loading = False
        self.error = None
        self.endResetModel()
        self.fetchMore(QModelIndex())

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self.rows[index.row()].get(self.columns[index.column()])
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return "" if value is None else str(value)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self.columns[section] if orientation == Qt.Orientation.Horizontal and section < len(self.columns) else str(section + 1)

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        return not parent.isValid() and not self.loading and len(self.rows) < self.total_rows

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        if not self.canFetchMore(parent):
            return
        self.loading = True
        offset = len(self.rows)
        generation = self.generation
        snapshot_id = self.snapshot_id
        table_name = self.table_name

        def loaded(page: dict[str, Any]) -> None:
            if generation != self.generation:
                return
            values = page["rows"]
            if values:
                self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows) + len(values) - 1)
                self.rows.extend(values)
                self.endInsertRows()
            self.total_rows = page["total_rows"]
            self.loading = False

        def failed(error: Exception) -> None:
            if generation != self.generation:
                return
            self.error = error
            self.loading = False

        self.runner.submit(
            lambda: self.service.read_table_page(snapshot_id, table_name, offset),
            loaded,
            failed,
        )
