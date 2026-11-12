"""RES-647 Squad home: the whole squad as tiles, the researcher's own flag rules and simulations, and an athlete page.

Tapping a tile opens the athlete; from there the researcher opens or branches individual investigations
(the existing IndividualResearchPanel) and runs their own what-if simulations. All definitions are user-configured.
"""

from __future__ import annotations

import html
from datetime import date
from typing import Any, Callable

from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..squad import MEASURES, OPERATORS, TONES, VARIANTS
from . import theme
from .individual_research import IndividualResearchPanel, _table, fit_dialog
from .plots import ScientificFigureWidget
from .services import DynamisAppService

RunTask = Callable[[Callable[[], Any], Callable[[Any], None], str], None]
TILE_WIDTH = 176


def _x(point: Any) -> Any:
    """ISO dates plot on a time axis; occasions and weeks stay numeric."""
    if isinstance(point, str):
        try:
            return date.fromisoformat(point)
        except ValueError:
            return point
    return point


def _fmt(value: Any, digits: int = 1, suffix: str = "") -> str:
    return "—" if value is None else f"{value:+.{digits}f}{suffix}" if suffix == "%" else f"{value:.{digits}f}{suffix}"


def _tone_color(tone: str | None) -> str:
    colors = theme.tokens()
    return {"negative": colors["bad"], "positive": colors["ok"], "neutral": colors["warn"]}.get(tone or "", colors["line2"])


def flag_text(flag: dict[str, Any]) -> str:
    parts = []
    for item in flag["evidence"]:
        threshold = f"{item['threshold']}–{item['threshold2']}" if item["operator"] in ("between", "outside") else item["threshold"]
        parts.append(f"{item['metric']} · {item['measure'].lower()} = {item['value']} ({item['operator']} {threshold})")
    return f"{flag['category']} — rule “{flag['rule']}”: " + "; ".join(parts)


class AthleteTile(QToolButton):
    def __init__(self, athlete: dict[str, Any], time_word: str = "tests", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.athlete = athlete
        flag = athlete["flags"][0] if athlete["flags"] else None
        arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(athlete["trend"], "·")
        lines = [athlete["display_id"], flag["category"] if flag else " ",
                 f"{athlete['tests']}/{athlete['tests_expected']} {time_word} · {arrow} {_fmt(athlete['change_from_baseline_pct'], 1, '%')}"]
        if len(athlete["flags"]) > 1:
            lines[1] += f" +{len(athlete['flags']) - 1}"
        self.setText("\n".join(lines))
        self.setToolTip("\n".join(flag_text(item) for item in athlete["flags"]) or "No rule fired on the observed data.")
        self.setAccessibleName(f"Athlete {athlete['display_id']}: {lines[1]}")
        self.setFixedWidth(TILE_WIDTH)
        self.setMinimumHeight(62)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        colors = theme.tokens()
        edge = _tone_color(flag["tone"]) if flag else colors["line2"]
        self.setStyleSheet(f"QToolButton {{ text-align: left; padding: 8px 10px; border: 1px solid {colors['line2']};"
                           f" border-left: 4px solid {edge}; border-radius: 6px; background: {colors['base']}; color: {colors['text']}; }}"
                           f" QToolButton:hover {{ border-color: {colors['accent']}; border-left: 4px solid {edge}; }}")


class SquadBoard(QWidget):
    athlete_opened = Signal(dict)
    loaded = Signal()
    research_requested = Signal()

    def __init__(self, service: DynamisAppService, run_task: RunTask, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task = service, run_task
        self.workspace_id: str | None = None
        self.board: dict[str, Any] = {}
        self.generation = 0
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.title = QLabel("Open a workspace with data to see the squad.")
        self.title.setWordWrap(True)
        self.group_picker = QComboBox()
        self.group_picker.setAccessibleName("Group athletes by")
        self.group_picker.activated.connect(lambda _: self.reload())
        self.metric_picker = QComboBox()
        self.metric_picker.setAccessibleName("Metric shown on tiles")
        self.metric_picker.activated.connect(lambda _: self.reload())
        self.rules_button = QPushButton("Flag rules…")
        self.rules_button.clicked.connect(self.edit_rules)
        self.simulate_button = QPushButton("Simulate squad…")
        self.simulate_button.clicked.connect(lambda: self.simulate(None))
        bar.addWidget(self.title, 1)
        bar.addWidget(QLabel("Show"))
        bar.addWidget(self.metric_picker)
        bar.addWidget(QLabel("Group by"))
        bar.addWidget(self.group_picker)
        research = QPushButton("Research workbench")
        research.setToolTip("Cohort analyses, evidence and reports")
        research.clicked.connect(self.research_requested.emit)
        bar.addWidget(self.rules_button)
        bar.addWidget(self.simulate_button)
        bar.addWidget(research)
        layout.addLayout(bar)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setObjectName("PaneEmpty")
        layout.addWidget(self.note)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll, 1)
        self.setEnabled(False)

    def set_workspace(self, workspace_id: str | None) -> None:
        self.workspace_id = workspace_id
        self.board = {}
        self.metric_picker.clear()  # a new workspace starts from its own outcome
        self.scroll.takeWidget()
        self.setEnabled(bool(workspace_id))
        if workspace_id:
            self.reload()

    def reload(self) -> None:
        if not self.workspace_id:
            return
        self.generation += 1
        generation, workspace_id = self.generation, self.workspace_id
        group_by = self.group_picker.currentData() or "category"
        metric_id = self.metric_picker.currentData()
        self.run_task(lambda: self.service.squad_board(workspace_id, group_by, metric_id),
                      lambda board: self._loaded(board) if (generation, workspace_id) == (self.generation, self.workspace_id) else None,
                      "Loading squad")

    def _loaded(self, board: dict[str, Any]) -> None:
        self.board = board
        flagged = sum(1 for group in board["groups"] for athlete in group["athletes"] if athlete["flags"])
        total = sum(len(group["athletes"]) for group in board["groups"])
        self.title.setText(f"<b>Squad</b> · {total} athletes · {flagged} flagged · {board['metric']['label']} ({board['metric']['unit']})")
        self.note.setText(board["note"] if board["rules"] else
                          "No flag rules yet. Use Flag rules… to define what counts as ‘in danger’, ‘doing great’ or anything else for your squad.")
        self.group_picker.blockSignals(True)
        self.group_picker.clear()
        labels = {"category": "Flag category", "trend": "Trend"}
        for option in board["group_options"]:
            self.group_picker.addItem(labels.get(option, option.replace("_", " ").capitalize()), option)
        self.group_picker.setCurrentIndex(max(0, self.group_picker.findData(board["group_by"])))
        self.group_picker.blockSignals(False)
        self.metric_picker.blockSignals(True)
        self.metric_picker.clear()
        for metric in board["metrics"]:
            self.metric_picker.addItem(f"{metric['label']} ({metric['unit']})", metric["id"])
        self.metric_picker.setCurrentIndex(max(0, self.metric_picker.findData(board["metric"]["id"])))
        self.metric_picker.blockSignals(False)
        content = QWidget()
        grid = QVBoxLayout(content)
        columns = max(1, (self.scroll.viewport().width() - 16) // (TILE_WIDTH + 10))
        for group in sorted(board["groups"], key=lambda item: (item["name"] == "No rule fired", item["name"])):
            header = QLabel(f"<b>{group['name']}</b> · {len(group['athletes'])}")
            grid.addWidget(header)
            tiles = QGridLayout()
            tiles.setHorizontalSpacing(10)
            tiles.setVerticalSpacing(10)
            for index, athlete in enumerate(group["athletes"]):
                tile = AthleteTile(athlete, board.get("time_word", "tests"))
                tile.clicked.connect(lambda _=False, value=athlete: self.athlete_opened.emit(value))
                tiles.addWidget(tile, index // columns, index % columns, Qt.AlignmentFlag.AlignLeft)
            tiles.setColumnStretch(columns, 1)
            grid.addLayout(tiles)
        grid.addStretch(1)
        self.scroll.setWidget(content)
        self.loaded.emit()

    def tiles(self) -> list[AthleteTile]:
        widget = self.scroll.widget()
        return widget.findChildren(AthleteTile) if widget else []

    def edit_rules(self) -> None:
        if not self.board:
            return
        dialog = RulesDialog(self.board["metrics"], self.board["rules"], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            rules, workspace_id = dialog.rules, self.workspace_id
            self.run_task(lambda: self.service.save_flag_rules(workspace_id, rules), lambda _: self.reload(), "Saving flag rules")

    def simulate(self, subject_id: str | None) -> None:
        if self.board:
            SimulationDialog(self.service, self.run_task, self.workspace_id, self.board, subject_id, self).exec()


class RulesDialog(QDialog):
    """Rules are the researcher's own standards: name, category label, tone and AND/OR conditions."""

    COLUMNS = ["Metric", "Measure", "Operator", "Value", "Second value", "Window / acute", "Chronic"]

    def __init__(self, metrics: list[dict[str, Any]], rules: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Flag rules")
        fit_dialog(self, 980, 560)
        self.metrics, self.rules = metrics, [dict(rule) for rule in rules]
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setAccessibleName("Flag rules")
        self.list.currentRowChanged.connect(self._select)
        add, remove = QPushButton("New rule"), QPushButton("Delete rule")
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        left.addWidget(self.list, 1)
        left.addWidget(add)
        left.addWidget(remove)
        layout.addLayout(left, 1)
        right = QVBoxLayout()
        form = QFormLayout()
        self.name, self.category = QLineEdit(), QLineEdit()
        self.category.setPlaceholderText("In danger")
        self.tone, self.match = QComboBox(), QComboBox()
        for tone in TONES:
            self.tone.addItem({"negative": "Concern (red)", "positive": "Good news (green)", "neutral": "Watch (amber)"}[tone], tone)
        self.match.addItem("All conditions", "all")
        self.match.addItem("Any condition", "any")
        form.addRow("Rule name", self.name)
        form.addRow("Category shown", self.category)
        form.addRow("Tone", self.tone)
        form.addRow("Fires when", self.match)
        right.addLayout(form)
        self.conditions = _table(self.COLUMNS, "Rule conditions")
        right.addWidget(self.conditions, 1)
        row = QHBoxLayout()
        add_condition, remove_condition = QPushButton("Add condition"), QPushButton("Remove condition")
        add_condition.clicked.connect(lambda: self._add_condition({}))
        remove_condition.clicked.connect(lambda: self.conditions.removeRow(self.conditions.currentRow()))
        row.addWidget(add_condition)
        row.addWidget(remove_condition)
        row.addStretch(1)
        right.addLayout(row)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        right.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        layout.addLayout(right, 3)
        self.current = -1
        for rule in self.rules:
            self.list.addItem(rule["name"])
        if not self.rules:
            self._add()
        self.list.setCurrentRow(0)

    def _add(self) -> None:
        self._store()
        self.rules.append({"name": f"Rule {len(self.rules) + 1}", "category": "", "tone": "negative", "match": "all",
                           "conditions": [{"metric_id": self.metrics[0]["id"], "measure": "change_from_baseline_pct", "operator": "<", "value": -5}]})
        self.list.addItem(self.rules[-1]["name"])
        self.list.setCurrentRow(len(self.rules) - 1)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.current = -1
            self.rules.pop(row)
            self.list.takeItem(row)

    def _add_condition(self, condition: dict[str, Any]) -> None:
        row = self.conditions.rowCount()
        self.conditions.insertRow(row)
        for column, (options, key) in enumerate(((([(m["id"], f"{m['label']} ({m['unit']})") for m in self.metrics]), "metric_id"),
                                                 (list(MEASURES.items()), "measure"), ([(op, op) for op in OPERATORS], "operator"))):
            picker = QComboBox()
            for value, label in options:
                picker.addItem(label, value)
            picker.setCurrentIndex(max(0, picker.findData(condition.get(key))))
            self.conditions.setCellWidget(row, column, picker)
        for column, key, default in ((3, "value", ""), (4, "value2", ""), (5, "window", ""), (6, "chronic", "")):
            value = condition.get(key, condition.get("acute") if key == "window" and condition.get("measure") == "acute_chronic_ratio" else default)
            self.conditions.setItem(row, column, QTableWidgetItem("" if value in (None, "") else str(value)))

    def _select(self, row: int) -> None:
        self._store()
        self.current = row
        if row < 0:
            return
        rule = self.rules[row]
        self.name.setText(rule["name"])
        self.category.setText(rule["category"])
        self.tone.setCurrentIndex(max(0, self.tone.findData(rule.get("tone"))))
        self.match.setCurrentIndex(max(0, self.match.findData(rule.get("match"))))
        self.conditions.setRowCount(0)
        for condition in rule["conditions"]:
            self._add_condition(condition)

    def _store(self) -> None:
        if not 0 <= self.current < len(self.rules):
            return
        conditions = []
        for row in range(self.conditions.rowCount()):
            condition = {key: self.conditions.cellWidget(row, column).currentData()
                         for column, key in enumerate(("metric_id", "measure", "operator"))}
            texts = [self.conditions.item(row, column).text().strip() if self.conditions.item(row, column) else "" for column in range(3, 7)]
            condition["value"], condition["value2"] = texts[0], texts[1] or None
            if condition["measure"] == "rolling_mean" and texts[2]:
                condition["window"] = int(texts[2])
            if condition["measure"] == "acute_chronic_ratio":
                condition["acute"], condition["chronic"] = int(texts[2] or 1), int(texts[3] or 4)
            conditions.append(condition)
        self.rules[self.current] = {**self.rules[self.current], "name": self.name.text(), "category": self.category.text(),
                                    "tone": self.tone.currentData(), "match": self.match.currentData(), "conditions": conditions}
        self.list.item(self.current).setText(self.name.text() or "Untitled rule")

    def _save(self) -> None:
        try:
            self._store()
        except ValueError:
            self.error.setText("Window and chronic lengths must be whole numbers.")
            return
        from ..squad import validate_rule

        metrics = {metric["id"]: metric for metric in self.metrics}
        try:
            self.rules = [validate_rule(rule, metrics) for rule in self.rules]
        except Exception as error:  # noqa: BLE001 - validation message is shown to the researcher
            self.error.setText(str(error))
            return
        self.accept()


class SimulationDialog(QDialog):
    """The researcher's own what-if: outcome trend plus drivers and their assumed effects, best/expected/worst."""

    def __init__(self, service: DynamisAppService, run_task: RunTask, workspace_id: str, board: dict[str, Any],
                 subject_id: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task, self.workspace_id, self.subject_id = service, run_task, workspace_id, subject_id
        self.setWindowTitle(f"Simulate · {subject_id}" if subject_id else "Simulate squad")
        fit_dialog(self, 960, 620)
        self.metrics = board["metrics"]
        self.result: dict[str, Any] | None = None
        layout = QVBoxLayout(self)
        banner = QLabel("<b>HYPOTHETICAL</b> · Projects your assumptions from each athlete's latest observed value. "
                        "It is not a model prediction and is never stored as data.")
        banner.setWordWrap(True)
        layout.addWidget(banner)
        form = QFormLayout()
        self.name = QLineEdit("Scenario")
        self.steps = QSpinBox()
        self.steps.setRange(1, 104)
        self.steps.setValue(4)
        self.outcome = QComboBox()
        for metric in self.metrics:
            self.outcome.addItem(f"{metric['label']} ({metric['unit']})", metric["id"])
        self.outcome.setCurrentIndex(max(0, self.outcome.findData(board["metric"]["id"])))
        trend = QHBoxLayout()
        self.trend = {}
        for variant, default in zip(VARIANTS, (1.0, 0.0, -2.0)):
            box = QDoubleSpinBox()
            box.setRange(-100, 100)
            box.setDecimals(2)
            box.setSuffix(" %")
            box.setValue(default)
            box.setAccessibleName(f"Outcome change per step, {variant}")
            self.trend[variant] = box
            trend.addWidget(QLabel(variant.capitalize()))
            trend.addWidget(box)
        form.addRow("Scenario name", self.name)
        form.addRow("Horizon (tests/steps)", self.steps)
        form.addRow("Outcome", self.outcome)
        form.addRow("Outcome change per step", trend)
        layout.addLayout(form)
        layout.addWidget(QLabel("Drivers: how each metric changes per step and the outcome % change you assume per 1% driver change"))
        self.drivers = _table(["Driver metric", "Best %/step", "Expected %/step", "Worst %/step",
                               "Effect best", "Effect expected", "Effect worst"], "Simulation drivers")
        self.drivers.setMaximumHeight(130)
        layout.addWidget(self.drivers)
        row = QHBoxLayout()
        add, remove = QPushButton("Add driver"), QPushButton("Remove driver")
        add.clicked.connect(self._add_driver)
        remove.clicked.connect(lambda: self.drivers.removeRow(self.drivers.currentRow()))
        run, save = QPushButton("Run simulation"), QPushButton("Save scenario")
        run.setProperty("primary", True)
        run.clicked.connect(lambda: self.run(False))
        save.clicked.connect(lambda: self.run(True))
        for button in (add, remove):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(run)
        row.addWidget(save)
        layout.addLayout(row)
        self.results = _table(["Athlete", "Latest observed", "Best at horizon", "Expected at horizon", "Worst at horizon",
                               "Your flags under worst case"], "Simulation results")
        layout.addWidget(self.results, 1)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

    def _add_driver(self) -> None:
        row = self.drivers.rowCount()
        self.drivers.insertRow(row)
        picker = QComboBox()
        for metric in self.metrics:
            picker.addItem(f"{metric['label']} ({metric['unit']})", metric["id"])
        self.drivers.setCellWidget(row, 0, picker)
        for column in range(1, 7):
            self.drivers.setItem(row, column, QTableWidgetItem("0"))

    def scenario(self) -> dict[str, Any]:
        drivers, effects = [], []
        for row in range(self.drivers.rowCount()):
            numbers = [float(self.drivers.item(row, column).text() or 0) for column in range(1, 7)]
            metric_id = self.drivers.cellWidget(row, 0).currentData()
            drivers.append({"metric_id": metric_id, "change_pct_per_step": dict(zip(VARIANTS, numbers[:3]))})
            effects.append({"driver_metric_id": metric_id, "outcome_pct_per_driver_pct": dict(zip(VARIANTS, numbers[3:]))})
        return {"name": self.name.text(), "steps": self.steps.value(), "outcome_metric_id": self.outcome.currentData(),
                "outcome_trend_pct_per_step": {variant: box.value() for variant, box in self.trend.items()},
                "drivers": drivers, "effects": effects}

    def run(self, save: bool) -> None:
        try:
            scenario = self.scenario()
        except ValueError:
            self.summary.setText("Driver changes and effects must be numbers.")
            return
        workspace_id, subjects = self.workspace_id, [self.subject_id] if self.subject_id else None
        operation = (lambda: self.service.save_simulation(workspace_id, scenario)) if save else \
            (lambda: self.service.simulate(workspace_id, scenario, subjects))
        self.run_task(operation, self._shown, "Saving scenario" if save else "Running simulation")

    def _shown(self, result: dict[str, Any]) -> None:
        self.result = result
        worst = result["flags_at_horizon"].get("worst", {})
        rows = [a for a in result["athletes"] if a["status"] == "PROJECTED" and (not self.subject_id or a["subject_id"] == self.subject_id)]
        self.results.setRowCount(len(rows))
        for index, athlete in enumerate(rows):
            values = [athlete["subject_id"], f"{athlete['start']:.2f}", *(f"{athlete['projection'][v][-1]:.2f}" for v in VARIANTS),
                      ", ".join(worst.get(athlete["subject_id"], [])) or "—"]
            for column, value in enumerate(values):
                self.results.setItem(index, column, QTableWidgetItem(value))
        crossing = {variant: len(subjects) for variant, subjects in result["flags_at_horizon"].items()}
        self.summary.setText(f"{result['basis']} Athletes with at least one of your flags at the horizon: "
                             + ", ".join(f"{variant} {count}" for variant, count in crossing.items()) if crossing
                             else result["basis"] + " Define flag rules to see who would cross them.")


class AthletePage(QWidget):
    back_requested = Signal()
    investigation_selected = Signal(str)

    def __init__(self, service: DynamisAppService, run_task: RunTask, panel: IndividualResearchPanel,
                 board: SquadBoard, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task, self.board = service, run_task, board
        self.athlete: dict[str, Any] = {}
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        back = QPushButton("← Squad")
        back.clicked.connect(self.back_requested.emit)
        self.header = QLabel("")
        self.header.setWordWrap(True)
        self.simulate_button = QPushButton("Simulate…")
        self.simulate_button.clicked.connect(lambda: self.board.simulate(self.athlete.get("subject_id")))
        top.addWidget(back)
        top.addWidget(self.header, 1)
        top.addWidget(self.simulate_button)
        layout.addLayout(top)
        body = QHBoxLayout()
        layout.addLayout(body, 1)
        overview = QVBoxLayout()
        body.addLayout(overview, 2)
        self.cards = QHBoxLayout()
        overview.addLayout(self.cards)
        self.flags = QTextBrowser()
        self.flags.setMaximumHeight(80)
        overview.addWidget(self.flags)
        self.figure = ScientificFigureWidget()
        self.figure.setMinimumHeight(220)
        overview.addWidget(self.figure, 1)
        research = QVBoxLayout()
        body.addLayout(research, 3)
        branches = QHBoxLayout()
        branches.addWidget(QLabel("Branches"))
        self.branch_picker = QComboBox()
        self.branch_picker.setAccessibleName("Individual research branches")
        self.branch_picker.activated.connect(lambda _: self._branch_chosen())
        new_branch = QPushButton("New branch…")
        new_branch.clicked.connect(self.new_branch)
        branches.addWidget(self.branch_picker, 1)
        branches.addWidget(new_branch)
        research.addLayout(branches)
        research.addWidget(panel, 1)

    def set_athlete(self, workspace_id: str, athlete: dict[str, Any], investigations: list[dict[str, Any]], current: str | None) -> None:
        self.workspace_id, self.athlete = workspace_id, athlete
        attributes = " · ".join(f"{key.replace('_', ' ').capitalize()}: {value}" for key, value in athlete["attributes"].items() if value not in (None, ""))
        self.header.setText(f"<b>{athlete['display_id']}</b> {attributes}")
        while self.cards.count():
            self.cards.takeAt(0).widget().deleteLater()
        unit = self.board.board["metric"]["unit"]
        for label, value in (("Latest", _fmt(athlete["latest"], 2, f" {unit}")), ("Change from baseline", _fmt(athlete["change_from_baseline_pct"], 1, "%")),
                             (self.board.board.get("time_word", "tests").capitalize(), f"{athlete['tests']}/{athlete['tests_expected']}"), ("Flags", str(len(athlete["flags"])))):
            card = QLabel(f"<span style='font-size:11px'>{label}</span><br><b>{value}</b>")
            card.setObjectName("MetricCard")
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setMargin(6)
            self.cards.addWidget(card)
        self.flags.setPlainText("\n".join(flag_text(flag) for flag in athlete["flags"]) or "None of your rules fired for this athlete.")
        self._plot(athlete)
        self.branch_picker.clear()
        self.branch_picker.addItem("Main line · observed data", None)
        for item in investigations:
            self.branch_picker.addItem(f"Branch · {item['title']}", item["id"])
        self.branch_picker.setCurrentIndex(max(0, self.branch_picker.findData(current)))

    def _plot(self, athlete: dict[str, Any]) -> None:
        figure = Figure(figsize=(5, 3), constrained_layout=True)
        axis = figure.subplots()
        metric = self.board.board["metric"]
        points = [_x(item["point"]) for item in athlete["series"]]
        dense = len(points) > 15
        axis.plot(points, [item["value"] for item in athlete["series"]], marker="." if dense else "o", markersize=4 if dense else 6,
                  color=theme.tokens()["obs"], label=f"{athlete['display_id']} observed")
        squad = {}
        for group in self.board.board["groups"]:
            for other in group["athletes"]:
                for item in other["series"]:
                    squad.setdefault(_x(item["point"]), []).append(item["value"])
        xs = sorted(squad)
        axis.plot(xs, [sum(squad[x]) / len(squad[x]) for x in xs], linestyle="--", color=theme.tokens()["dim"], label="Squad mean")
        axis.set_ylabel(f"{metric['label']} ({metric['unit']})")
        if points and isinstance(points[0], date):
            from matplotlib.dates import AutoDateLocator, ConciseDateFormatter

            locator = AutoDateLocator(maxticks=6)
            axis.xaxis.set_major_locator(locator)
            axis.xaxis.set_major_formatter(ConciseDateFormatter(locator))
        axis.legend(frameon=False, fontsize=8)
        self.figure.show_figure(figure)

    def _branch_chosen(self) -> None:
        self.investigation_selected.emit(self.branch_picker.currentData() or "")

    def new_branch(self) -> None:
        title, accepted = QInputDialog.getText(self, "New branch", f"What do you want to investigate for {self.athlete['display_id']}?")
        if not accepted or not title.strip():
            return
        workspace_id, subject = self.workspace_id, self.athlete["subject_id"]
        self.run_task(lambda: self.service.create_individual_investigation(workspace_id, subject, title),
                      lambda created: self.investigation_selected.emit(created["id"]), "Creating branch")


class SquadHome(QStackedWidget):
    """Board ↔ athlete page within the workspace."""

    def __init__(self, service: DynamisAppService, run_task: RunTask, panel: IndividualResearchPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.board = SquadBoard(service, run_task, self)
        self.athlete_page = AthletePage(service, run_task, panel, self.board, self)
        self.addWidget(self.board)
        self.addWidget(self.athlete_page)
        self.athlete_page.back_requested.connect(lambda: self.setCurrentWidget(self.board))


class EventsFeed(QWidget):
    """What changed in the workspace, newest first, with the athletes who need a follow-up on top."""

    athlete_requested = Signal(str)
    follow_up_requested = Signal(str)
    FILTERS = (("All events", None), ("Flag changes", "flag"), ("New data", "data"), ("Analyses", "analysis"), ("Simulations", "simulation"))

    def __init__(self, service: DynamisAppService, run_task: RunTask, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service, self.run_task = service, run_task
        self.workspace_id: str | None = None
        self.feed: dict[str, Any] = {}
        self.generation = 0
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.title = QLabel("Open a workspace with data to see its events.")
        self.filter = QComboBox()
        self.filter.setAccessibleName("Filter events")
        for label, kind in self.FILTERS:
            self.filter.addItem(label, kind)
        self.filter.activated.connect(lambda _: self._render())
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        bar.addWidget(self.title, 1)
        bar.addWidget(self.filter)
        bar.addWidget(refresh)
        layout.addLayout(bar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll, 1)

    def set_workspace(self, workspace_id: str | None) -> None:
        self.workspace_id, self.feed = workspace_id, {}
        self.scroll.takeWidget()
        if workspace_id:
            self.reload()

    def reload(self) -> None:
        if not self.workspace_id:
            return
        self.generation += 1
        generation, workspace_id = self.generation, self.workspace_id
        self.run_task(lambda: self.service.workspace_events(workspace_id),
                      lambda feed: self._loaded(feed) if (generation, workspace_id) == (self.generation, self.workspace_id) else None,
                      "Loading events")

    def _loaded(self, feed: dict[str, Any]) -> None:
        self.feed = feed
        self._render()

    def _card(self, item: dict[str, Any], action: str | None = None) -> QFrame:
        colors = theme.tokens()
        edge = _tone_color(item["tone"]) if item["kind"] in ("flag", "attention") else colors["line2"]
        card = QFrame()
        card.setObjectName("EventCard")
        card.setStyleSheet(f"QFrame#EventCard {{ background: {colors['base']}; border: 1px solid {colors['line2']};"
                           f" border-left: 4px solid {edge}; border-radius: 6px; }}")
        row = QHBoxLayout(card)
        when = f"<br><span style='color:{colors['dim']}; font-size:11px'>{item['at'][:16].replace('T', ' ')}</span>" if item.get("at") else ""
        text = QLabel(f"<b>{html.escape(item['title'])}</b><br><span style='color:{colors['muted']}'>{html.escape(item['detail'])}</span>{when}")
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(text, 1)
        if item.get("subject_id"):
            open_button = QPushButton("Open athlete")
            open_button.clicked.connect(lambda _=False, subject=item["subject_id"]: self.athlete_requested.emit(subject))
            row.addWidget(open_button)
        if action:
            follow = QPushButton(action)
            follow.setProperty("primary", True)
            follow.clicked.connect(lambda _=False, subject=item["subject_id"]: self.follow_up_requested.emit(subject))
            row.addWidget(follow)
        return card

    def _render(self) -> None:
        if not self.feed:
            return
        kind = self.filter.currentData()
        events = [item for item in self.feed["events"] if kind is None or item["kind"] == kind]
        self.title.setText(f"<b>Events</b> · {len(self.feed['attention'])} need attention · {len(self.feed['events'])} events"
                           + ("" if self.feed["rules"] else " · define flag rules on Squad to track flag changes"))
        content = QWidget()
        layout = QVBoxLayout(content)
        if self.feed["attention"]:
            layout.addWidget(QLabel("<b>Needs attention</b> · your concern rules fired and there is no follow-up branch yet"))
            for item in self.feed["attention"]:
                layout.addWidget(self._card(item, "Start follow-up"))
        layout.addWidget(QLabel("<b>Timeline</b>"))
        for item in events:
            layout.addWidget(self._card(item))
        if not events:
            layout.addWidget(QLabel("Nothing here yet."))
        layout.addStretch(1)
        self.scroll.setWidget(content)

    def cards(self) -> list[QFrame]:
        widget = self.scroll.widget()
        return widget.findChildren(QFrame, "EventCard") if widget else []
