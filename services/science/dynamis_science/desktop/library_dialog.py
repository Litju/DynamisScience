"""Read-only native view of scientific definitions and their status."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QSplitter,
    QTabWidget,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .models import RecordTableModel


class ScientificLibraryDialog(QDialog):
    def __init__(self, library: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.setWindowTitle("Scientific definition library")
        self.resize(1180, 760)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Read-only definitions used by the workbench. Prototype and unavailable "
                "entries are shown with their recorded status and limitations."
            )
        )
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.sections: dict[str, dict[str, Any]] = {}
        for key, label in (
            ("metrics", "Metrics"),
            ("protocols", "Protocols"),
            ("methods", "Methods"),
            ("models", "Models"),
        ):
            records = library.get(key, [])
            page = QWidget()
            page_layout = QVBoxLayout(page)
            splitter = QSplitter(Qt.Orientation.Horizontal)
            table = QTableView()
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
            table.setSortingEnabled(False)
            table.setModel(RecordTableModel([self._row(record) for record in records]))
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)
            detail = QTextBrowser()
            detail.setOpenExternalLinks(False)
            splitter.addWidget(table)
            splitter.addWidget(detail)
            splitter.setStretchFactor(0, 2)
            splitter.setStretchFactor(1, 3)
            page_layout.addWidget(splitter)
            self.tabs.addTab(page, f"{label} · {len(records)}")
            self.sections[key] = {"records": records, "table": table, "detail": detail}
            table.selectionModel().currentRowChanged.connect(
                lambda current, _previous, section=key: self._show_definition(
                    section, current.row()
                )
            )
            if records:
                table.selectRow(0)
                self._show_definition(key, 0)
            else:
                detail.setPlainText("No definitions are available in the bundled registry.")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _row(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: record.get(key)
            for key in ("id", "name", "status", "version", "unit", "kind", "frequency")
            if key in record
        }

    def _show_definition(self, section: str, row: int) -> None:
        data = self.sections[section]
        records = data["records"]
        if not 0 <= row < len(records):
            data["detail"].clear()
            return
        record = records[row]
        detail = dict(record)
        if section == "methods":
            detail["algorithm_definition"] = next(
                (
                    item
                    for item in self._all_algorithms
                    if item["id"] == record.get("algorithm")
                ),
                None,
            )
        elif section == "models":
            detail["model_specification"] = self._model_spec
        data["detail"].setPlainText(
            json.dumps(detail, indent=2, ensure_ascii=False, sort_keys=True, default=str)
        )

    @property
    def _all_algorithms(self) -> list[dict[str, Any]]:
        return getattr(self, "library", {}).get("algorithms", [])

    @property
    def _model_spec(self) -> dict[str, Any]:
        return getattr(self, "library", {}).get("model_spec", {})
