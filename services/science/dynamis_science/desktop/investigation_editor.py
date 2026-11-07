"""Native authoring surface for versioned research investigations."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..researchstore import ResearchValidation, validate_investigation_blocks


class InvestigationEditor(QWidget):
    def __init__(self, service, run_task: Callable, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.run_task = run_task
        self.study_id: str | None = None
        self.records: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.blocks: list[dict[str, Any]] = []
        self._editing_block_id: str | None = None
        self._loading = False
        self._generation = 0

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.investigations = QComboBox()
        self.investigations.currentIndexChanged.connect(self._select_investigation)
        self.new_button = QPushButton("New")
        self.new_button.clicked.connect(self._new_investigation)
        self.fork_button = QPushButton("Fork")
        self.fork_button.clicked.connect(self._fork_investigation)
        controls.addWidget(QLabel("Investigation"))
        controls.addWidget(self.investigations, 1)
        controls.addWidget(self.new_button)
        controls.addWidget(self.fork_button)
        layout.addLayout(controls)

        self.title = QLineEdit()
        self.title.setPlaceholderText("Investigation title")
        layout.addWidget(self.title)

        editor = QSplitter(Qt.Orientation.Horizontal)
        self.block_list = QListWidget()
        self.block_list.currentRowChanged.connect(self._select_block)
        editor.addWidget(self.block_list)

        state_panel = QWidget()
        state_layout = QVBoxLayout(state_panel)
        self.block_title = QLineEdit()
        self.block_title.setPlaceholderText("Selected block title")
        self.state = QPlainTextEdit()
        self.state.setPlaceholderText("Block state as a JSON object")
        self.state.setTabChangesFocus(True)
        state_layout.addWidget(QLabel("Selected block"))
        state_layout.addWidget(self.block_title)
        state_layout.addWidget(QLabel("Block configuration · JSON"))
        state_layout.addWidget(self.state, 1)
        editor.addWidget(state_panel)
        editor.setStretchFactor(0, 1)
        editor.setStretchFactor(1, 2)
        layout.addWidget(editor, 1)

        actions = QHBoxLayout()
        self.block_type = QComboBox()
        self.block_type.addItems(
            [
                "question", "dataset", "cohort", "schedule", "table", "explore",
                "force_trial", "match_event", "analysis", "diagnostics", "evidence",
                "model", "figure", "interpretation", "report_section",
            ]
        )
        self.add_block_button = QPushButton("Add block")
        self.add_block_button.clicked.connect(self._add_block)
        self.remove_block_button = QPushButton("Remove")
        self.remove_block_button.clicked.connect(self._remove_block)
        self.move_up_button = QPushButton("Move up")
        self.move_up_button.clicked.connect(lambda: self._move_block(-1))
        self.move_down_button = QPushButton("Move down")
        self.move_down_button.clicked.connect(lambda: self._move_block(1))
        self.save_button = QPushButton("Save version")
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.block_type)
        actions.addWidget(self.add_block_button)
        actions.addWidget(self.remove_block_button)
        actions.addWidget(self.move_up_button)
        actions.addWidget(self.move_down_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

        self.status = QLabel("Open a persisted study to author its investigation.")
        layout.addWidget(self.status)
        self._set_editable(False)

    def set_study(self, study_id: str, select_id: str | None = None) -> None:
        self._generation += 1
        generation = self._generation
        self.study_id = study_id
        self.records = []
        self.current = None
        self.blocks = []
        self._loading = True
        self.investigations.clear()
        self.block_list.clear()
        self.title.clear()
        self.state.clear()
        self._loading = False
        self.status.setText("Loading saved investigations…")
        self.run_task(
            lambda: self.service.list_investigations(study_id),
            lambda records: self._set_records(generation, records, select_id),
            "Loading research investigations",
        )

    def _set_records(
        self,
        generation: int,
        records: list[dict[str, Any]],
        select_id: str | None = None,
    ) -> None:
        if generation != self._generation:
            return
        self.records = records
        self._loading = True
        self.investigations.clear()
        for record in records:
            self.investigations.addItem(
                f"{record['title']} · v{record['version']}", record["id"]
            )
        self._loading = False
        if records:
            target = next((item for item in records if item["id"] == select_id), records[0])
            self._loading = True
            self.investigations.setCurrentIndex(
                self.investigations.findData(target["id"])
            )
            self._loading = False
            self._show_record(target)
        else:
            self._show_record(None)

    def _select_investigation(self, index: int) -> None:
        if self._loading or index < 0:
            return
        investigation_id = self.investigations.itemData(index)
        self._show_record(
            next((item for item in self.records if item["id"] == investigation_id), None)
        )

    def _show_record(self, record: dict[str, Any] | None) -> None:
        self.current = record
        self.blocks = [dict(block) for block in (record or {}).get("blocks", [])]
        self._editing_block_id = None
        self.title.setText((record or {}).get("title", ""))
        self._loading = True
        self.block_list.clear()
        for block in self.blocks:
            self.block_list.addItem(f"{block['type']} · {block['title']} · {block['id']}")
        self._loading = False
        self.state.clear()
        self.block_title.clear()
        self._refresh_permissions()
        if self.blocks:
            self.block_list.setCurrentRow(0)
        else:
            self.status.setText("No blocks yet. Add a block, then save a new version.")

    def _select_block(self, row: int) -> None:
        if self._loading:
            return
        if self._editing_block_id is not None and not self._flush_selected_block():
            self._loading = True
            previous = next(
                (i for i, block in enumerate(self.blocks) if block["id"] == self._editing_block_id),
                -1,
            )
            self.block_list.setCurrentRow(previous)
            self._loading = False
            return
        if row < 0 or row >= len(self.blocks):
            self._editing_block_id = None
            self.state.clear()
            self.block_title.clear()
            return
        block = self.blocks[row]
        self._editing_block_id = block["id"]
        self.block_title.setText(block["title"])
        self.state.setPlainText(json.dumps(block.get("state", {}), indent=2, ensure_ascii=False))

    def _flush_selected_block(self) -> bool:
        if self._editing_block_id is None:
            return True
        try:
            value = json.loads(self.state.toPlainText() or "{}")
            if not isinstance(value, dict):
                raise ValueError("Block state must be a JSON object")
        except (json.JSONDecodeError, ValueError) as error:
            self.status.setText(str(error))
            return False
        block = next(
            (item for item in self.blocks if item["id"] == self._editing_block_id), None
        )
        if block is None:
            return True
        block["title"] = self.block_title.text().strip() or block["type"].replace("_", " ").title()
        block["state"] = value
        row = next(
            (i for i, item in enumerate(self.blocks) if item["id"] == self._editing_block_id),
            -1,
        )
        if row >= 0:
            self.block_list.item(row).setText(
                f"{block['type']} · {block['title']} · {block['id']}"
            )
        return True

    def _refresh_permissions(self) -> None:
        authored = bool(self.study_id and self.study_id.startswith(("STUDY-U-", "PROG-U-")))
        real = bool(self.current and self.current["id"].startswith("INV-REAL-"))
        editable = bool(self.current and (authored or real))
        self._set_editable(editable)
        self.new_button.setEnabled(authored)
        self.fork_button.setEnabled(bool(authored and self.current))
        self.status.setText(
            f"{self.current['id']} · version {self.current['version']} · {self.current['status']}"
            if self.current
            else ("Create a persisted study before authoring an investigation." if not authored else "Create an investigation to start a scratchpad.")
        )

    def _set_editable(self, editable: bool) -> None:
        self.title.setEnabled(editable)
        self.block_title.setEnabled(editable)
        self.state.setEnabled(editable)
        self.block_type.setEnabled(editable)
        for button in (
            self.add_block_button,
            self.remove_block_button,
            self.move_up_button,
            self.move_down_button,
            self.save_button,
        ):
            button.setEnabled(editable)

    def _add_block(self) -> None:
        if not self._flush_selected_block():
            return
        block_type = self.block_type.currentText()
        block = {
            "id": f"B-{uuid.uuid4().hex[:8].upper()}",
            "type": block_type,
            "title": block_type.replace("_", " ").title(),
            "state": {},
            "collapsed": False,
        }
        self.blocks.append(block)
        self._refresh_blocks(len(self.blocks) - 1)

    def _remove_block(self) -> None:
        row = self.block_list.currentRow()
        if row < 0 or not self._flush_selected_block():
            return
        self.blocks.pop(row)
        self._editing_block_id = None
        self._refresh_blocks(min(row, len(self.blocks) - 1))

    def _move_block(self, offset: int) -> None:
        row = self.block_list.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < len(self.blocks) or not self._flush_selected_block():
            return
        self.blocks[row], self.blocks[target] = self.blocks[target], self.blocks[row]
        self._editing_block_id = None
        self._refresh_blocks(target)

    def _refresh_blocks(self, selected_row: int) -> None:
        self._loading = True
        self.block_list.clear()
        for block in self.blocks:
            self.block_list.addItem(f"{block['type']} · {block['title']} · {block['id']}")
        self._loading = False
        if self.blocks:
            self.block_list.setCurrentRow(selected_row)
        else:
            self.state.clear()
            self.block_title.clear()

    def _new_investigation(self) -> None:
        if not self.study_id:
            return
        study_id = self.study_id
        title = self.title.text().strip() or "Untitled investigation"
        self.run_task(
            lambda: self.service.create_investigation(study_id, title),
            lambda record: self._reload_after_write(study_id, record),
            "Creating research investigation",
        )

    def _fork_investigation(self) -> None:
        if not self.current:
            return
        investigation_id = self.current["id"]
        study_id = self.study_id or ""
        self.run_task(
            lambda: self.service.fork_investigation(investigation_id),
            lambda record: self._reload_after_write(study_id, record),
            "Forking investigation version",
        )

    def _save(self) -> None:
        if not self.current or not self._flush_selected_block():
            return
        try:
            validate_investigation_blocks(self.blocks)
        except ResearchValidation as error:
            self.status.setText(str(error))
            return
        investigation_id = self.current["id"]
        study_id = self.study_id or ""
        version = int(self.current["version"])
        title = self.title.text().strip()
        blocks = [dict(block) for block in self.blocks]
        self.run_task(
            lambda: self.service.update_investigation(
                investigation_id, blocks, version, title
            ),
            lambda record: self._reload_after_write(study_id, record),
            "Saving investigation version",
        )

    def _reload_after_write(self, study_id: str, record: dict[str, Any]) -> None:
        if self.study_id == study_id:
            self.set_study(study_id, record.get("id"))
