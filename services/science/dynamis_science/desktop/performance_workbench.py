"""Native Qt workspaces for the existing Performance OS domain functions."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QDate, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHeaderView,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import RecordTableModel
from .theme import tokens
from .performance_navigation import PERFORMANCE_PAGE_KEYS, PERFORMANCE_PAGE_NAMES


def _record_view() -> tuple[QTableView, RecordTableModel]:
    view = QTableView()
    view.setAlternatingRowColors(True)
    view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
    model = RecordTableModel()
    view.setModel(model)
    return view, model


def _pretty(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


class SessionDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Log training session")
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.session_type = QLineEdit("Field")
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0.1, 600)
        self.duration.setValue(75)
        self.rpe = QDoubleSpinBox()
        self.rpe.setRange(0, 10)
        self.rpe.setValue(6)
        self.attendance = QSpinBox()
        self.attendance.setRange(0, 200)
        self.attendance.setValue(28)
        self.notes = QLineEdit()
        form = QFormLayout(self)
        for label, widget in (
            ("Date", self.date),
            ("Session type", self.session_type),
            ("Duration (min)", self.duration),
            ("Session RPE (0–10)", self.rpe),
            ("Attendance", self.attendance),
            ("Notes", self.notes),
        ):
            form.addRow(label, widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def payload(self) -> dict[str, Any]:
        return {
            "date": self.date.date().toString("yyyy-MM-dd"),
            "session_type": self.session_type.text().strip(),
            "duration_min": self.duration.value(),
            "session_rpe": self.rpe.value(),
            "attendance": self.attendance.value(),
            "notes": self.notes.text().strip(),
        }


class PlanDialog(QDialog):
    columns = ("id", "day", "type", "focus", "planned_load_au", "duration_min", "group")

    def __init__(self, plan: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit microcycle")
        microcycle = next(
            (row for row in plan.get("microcycles", []) if row["week"] == plan["current_week"] + 1),
            None,
        )
        if microcycle is None:
            microcycle = {"week": plan["current_week"] + 1, "sessions": []}
        self.week = QSpinBox()
        self.week.setRange(1, 52)
        self.week.setValue(microcycle["week"])
        self.focus = QLineEdit(microcycle.get("focus", ""))
        self.testing = QLineEdit(microcycle.get("testing_window", ""))
        self.sessions = QTableWidget(0, len(self.columns))
        self.sessions.setHorizontalHeaderLabels(self.columns)
        self.sessions.horizontalHeader().setStretchLastSection(True)
        for session in microcycle.get("sessions", []):
            self._append_session(session)
        form = QFormLayout()
        form.addRow("Week", self.week)
        form.addRow("Microcycle focus", self.focus)
        form.addRow("Testing window", self.testing)
        tools = QHBoxLayout()
        add = QPushButton("Add session")
        remove = QPushButton("Remove selected")
        add.clicked.connect(lambda: self._append_session({}))
        remove.clicked.connect(self._remove_session)
        tools.addWidget(add)
        tools.addWidget(remove)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(tools)
        layout.addWidget(self.sessions)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _append_session(self, values: dict[str, Any]) -> None:
        row = self.sessions.rowCount()
        self.sessions.insertRow(row)
        defaults = {
            "id": f"MC-SESSION-{row + 1}",
            "day": "Mon",
            "type": "Training",
            "focus": "",
            "planned_load_au": 0,
            "duration_min": 0,
            "group": "Squad",
        }
        defaults.update(values)
        for column, name in enumerate(self.columns):
            self.sessions.setItem(row, column, QTableWidgetItem(str(defaults.get(name, ""))))

    def _remove_session(self) -> None:
        row = self.sessions.currentRow()
        if row >= 0:
            self.sessions.removeRow(row)

    def payload(self) -> dict[str, Any]:
        sessions = []
        for row in range(self.sessions.rowCount()):
            values = {
                name: self.sessions.item(row, column).text().strip()
                for column, name in enumerate(self.columns)
            }
            values["planned_load_au"] = float(values["planned_load_au"])
            values["duration_min"] = float(values["duration_min"])
            sessions.append(values)
        return {
            "week": self.week.value(),
            "focus": self.focus.text().strip(),
            "testing_window": self.testing.text().strip(),
            "sessions": sessions,
        }


class ReportDialog(QDialog):
    def __init__(self, athletes: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compose practitioner report")
        self.audience = QComboBox()
        for item in ("coach", "athlete", "medical", "board"):
            self.audience.addItem(item.title(), item)
        self.athlete = QComboBox()
        for row in athletes:
            self.athlete.addItem(row["display_id"], row["display_id"])
        self.role = QLineEdit("Head of Performance")
        form = QFormLayout(self)
        form.addRow("Audience", self.audience)
        form.addRow("Athlete (for athlete report)", self.athlete)
        form.addRow("Author role", self.role)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def payload(self) -> dict[str, Any]:
        return {
            "audience": self.audience.currentData(),
            "athlete_id": self.athlete.currentData() if self.audience.currentData() == "athlete" else None,
            "role": self.role.text().strip(),
        }


class PerformanceHeader(QWidget):
    search_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PerformanceHeader")
        self.setFixedHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)
        self.menu_button = QToolButton()
        self.menu_button.setText("D")
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        mark = self.menu_button
        mark.setObjectName("PerformanceBrandMark")
        layout.addWidget(mark)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        name = QLabel("Dynamis Performance OS")
        name.setObjectName("PerformanceBrandName")
        descriptor = QLabel("SPORTS SCIENCE")
        descriptor.setObjectName("PerformanceBrandDescriptor")
        brand.addWidget(name)
        brand.addWidget(descriptor)
        layout.addLayout(brand)
        layout.addSpacing(6)
        self.club = QLabel("Northside FC")
        self.club.setObjectName("PerformanceClub")
        self.squad = QLabel("U21")
        self.squad.setObjectName("PerformanceMuted")
        layout.addWidget(self.club)
        layout.addWidget(self.squad)
        slash = QLabel("/")
        slash.setObjectName("PerformanceMuted")
        layout.addWidget(slash)
        mode = QLabel("Performance")
        mode.setObjectName("PerformanceMuted")
        layout.addWidget(mode)
        self.season = QLabel("2026/27 · WEEK 16 · BUILD")
        self.season.setObjectName("PerformanceSeason")
        layout.addWidget(self.season)
        layout.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName("PerformanceSearch")
        self.search.setPlaceholderText("Search athletes, sessions, tests")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(210)
        self.search.setMaximumWidth(270)
        self.search.returnPressed.connect(
            lambda: self.search_requested.emit(self.search.text().strip())
        )
        layout.addWidget(self.search)
        role = QLabel("ROLE")
        role.setObjectName("PerformanceRoleLabel")
        layout.addWidget(role)
        self.role = QLabel("Head of Performance")
        self.role.setObjectName("PerformanceRole")
        layout.addWidget(self.role)
        self.avatar = QLabel("HP")
        self.avatar.setObjectName("PerformanceAvatar")
        layout.addWidget(self.avatar)

    def set_menu_actions(self, actions) -> None:
        menu = QMenu(self.menu_button)
        menu.addActions(actions)
        self.menu_button.setMenu(menu)

    def set_context(self, context: dict[str, Any]) -> None:
        club = context.get("club", {})
        if isinstance(club, dict):
            self.club.setText(str(club.get("name", "Northside FC")))
            self.squad.setText(str(club.get("squad", "U21")))
        season = context.get("season", {})
        if isinstance(season, dict):
            self.season.setText(
                f"{season.get('label', '')} · WEEK {season.get('current_week', '—')} · {season.get('phase', '—')}"
            )


class PerformanceRail(QWidget):
    page_selected = Signal(str)
    pages = (
        ("Daily", (("Today", "today", "LIVE"), ("Plan", "plan", "W16"), ("Monitor", "monitor", "28"), ("Test", "test", "CMJ"))),
        ("Evidence", (("Research", "research", ""), ("Reports", "report", ""))),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PerformanceRail")
        self.setMinimumWidth(196)
        self.setMaximumWidth(232)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 9)
        layout.setSpacing(12)
        club = QHBoxLayout()
        crest = QLabel("NFC")
        crest.setObjectName("PerformanceCrest")
        identity = QVBoxLayout()
        identity.setSpacing(1)
        self.club_name = QLabel("Northside FC")
        self.club_name.setObjectName("PerformanceRailClub")
        self.squad_summary = QLabel("U21 · 28 athletes")
        self.squad_summary.setObjectName("PerformanceRailMeta")
        identity.addWidget(self.club_name)
        identity.addWidget(self.squad_summary)
        club.addWidget(crest)
        club.addLayout(identity, 1)
        layout.addLayout(club)
        self.buttons: dict[str, QPushButton] = {}
        for group_name, items in self.pages:
            group = QVBoxLayout()
            group.setSpacing(1)
            label = QLabel(group_name.upper())
            label.setObjectName("PerformanceRailGroup")
            group.addWidget(label)
            for name, key, tag in items:
                button = QPushButton()
                button.setObjectName("PerformanceRailItem")
                button.setAccessibleName(name)
                button.setCheckable(True)
                row = QHBoxLayout(button)
                row.setContentsMargins(5, 3, 5, 3)
                title = QLabel(name)
                title.setObjectName("PerformanceRailItemName")
                row.addWidget(title)
                row.addStretch(1)
                tag_label = QLabel(tag)
                tag_label.setObjectName("PerformanceRailTag")
                row.addWidget(tag_label)
                button.clicked.connect(lambda _checked=False, selected=key: self.select(selected))
                self.buttons[key] = button
                group.addWidget(button)
            layout.addLayout(group)
        layout.addStretch(1)
        footer = QFrame()
        footer.setObjectName("PerformanceSquadFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(2, 8, 2, 0)
        footer_layout.setSpacing(3)
        footer_heading = QLabel("SQUAD AVAILABILITY")
        footer_heading.setObjectName("PerformanceRailGroup")
        footer_layout.addWidget(footer_heading)
        self.availability = QLabel("28 / 28 active")
        self.availability.setObjectName("PerformanceAvailability")
        footer_layout.addWidget(self.availability)
        bar = QHBoxLayout()
        bar.setSpacing(2)
        for _ in range(14):
            segment = QFrame()
            segment.setObjectName("PerformanceAvailabilitySegment")
            segment.setFixedHeight(3)
            bar.addWidget(segment, 1)
        footer_layout.addLayout(bar)
        self.availability_note = QLabel("No injury table admitted. Roster status only.")
        self.availability_note.setWordWrap(True)
        self.availability_note.setObjectName("PerformanceRailNote")
        footer_layout.addWidget(self.availability_note)
        layout.addWidget(footer)
        self.squad_name = "U21"
        self.select("today")

    def select(self, page: str) -> None:
        self.set_current(page)
        self.page_selected.emit(page)

    def set_current(self, page: str) -> None:
        for key, button in self.buttons.items():
            button.setChecked(key == page)

    def update_summary(self, today: dict[str, Any]) -> None:
        pulse = today.get("pulse", {})
        self.availability.setText(
            f"{pulse.get('roster_active', '—')} / {pulse.get('roster_total', '—')} active"
        )
        self.squad_summary.setText(
            f"{self.squad_name} · {pulse.get('roster_total', '—')} athletes"
        )

    def set_context(self, context: dict[str, Any]) -> None:
        club = context.get("club", {})
        if isinstance(club, dict):
            self.club_name.setText(str(club.get("name", self.club_name.text())))
            self.squad_name = str(club.get("squad", self.squad_name))
            total = context.get("availability", {}).get("total")
            if total is not None:
                self.squad_summary.setText(f"{self.squad_name} · {total} athletes")


class PerformanceContextPanel(QWidget):
    back_to_daily = Signal()
    open_full_athlete = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PerformanceContextPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.views = QStackedWidget(self)
        root.addWidget(self.views)
        self.daily_view = QWidget()
        self.views.addWidget(self.daily_view)
        layout = QVBoxLayout(self.daily_view)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(0)
        self.checklist = QVBoxLayout()
        self.checklist.setSpacing(4)
        self.readiness_bar = QHBoxLayout()
        self.readiness_bar.setSpacing(2)
        self.readiness_segments: list[QFrame] = []
        for band in range(4):
            segment = QFrame()
            segment.setObjectName("PerformanceReadinessSegment")
            segment.setProperty("band", band)
            segment.setFixedHeight(7)
            self.readiness_bar.addWidget(segment)
            self.readiness_segments.append(segment)
        self.readiness_legend = QLabel()
        self.readiness_legend.setObjectName("PerformanceContextMuted")
        self.quality = QLabel("Waiting for the synthetic fixture summary.")
        self.quality.setObjectName("PerformanceContextMono")
        self.injury = QLabel("Injury module unavailable · no injury or exposure table admitted.")
        self.injury.setObjectName("PerformanceCalloutWarning")
        self.movement = QLabel("Movement scope is a bounded segment, not full-match distance.")
        self.movement.setObjectName("PerformanceCalloutInfo")
        self.injury.setWordWrap(True)
        self.movement.setWordWrap(True)
        for title, widget in (
            ("TODAY'S CHECKLIST", self.checklist),
            ("READINESS DISTRIBUTION", self.readiness_bar),
        ):
            self._add_heading(layout, title)
            if isinstance(widget, QVBoxLayout):
                layout.addLayout(widget)
            else:
                row = QHBoxLayout()
                row.addLayout(widget, 1)
                layout.addLayout(row)
        layout.addWidget(self.readiness_legend)
        self._add_heading(layout, "DATA ADMISSION")
        layout.addWidget(self.quality)
        layout.addWidget(self.injury)
        layout.addWidget(self.movement)
        layout.addStretch(1)
        footer = QLabel("Synthetic fixture · DS-SYNTH-001 · no real athletes or measurements")
        footer.setObjectName("PerformanceContextFooter")
        footer.setWordWrap(True)
        layout.addWidget(footer)

        self.athlete_view = QWidget()
        athlete_layout = QVBoxLayout(self.athlete_view)
        athlete_layout.setContentsMargins(10, 10, 10, 10)
        athlete_layout.setSpacing(7)
        self.athlete_identity = QLabel("ATHLETE 360")
        self.athlete_identity.setObjectName("PerformanceAthleteIdentity")
        self.athlete_position = QLabel("Select an athlete from the squad command queue.")
        self.athlete_position.setObjectName("PerformanceContextMuted")
        athlete_layout.addWidget(self.athlete_identity)
        athlete_layout.addWidget(self.athlete_position)
        self.athlete_metrics: dict[str, QLabel] = {}
        metric_grid = QGridLayout()
        metric_grid.setSpacing(5)
        for row, items in enumerate(
            (("readiness", "READINESS"), ("sleep", "SLEEP"), ("load", "LOAD RATIO"), ("change", "CMJ CHANGE"))
        ):
            key, title = items
            card = QFrame()
            card.setObjectName("PerformanceMiniMetric")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 5, 6, 5)
            card_layout.setSpacing(2)
            caption = QLabel(title)
            caption.setObjectName("PerformanceMetricLabel")
            value = QLabel("—")
            value.setObjectName("PerformanceMiniMetricValue")
            card_layout.addWidget(caption)
            card_layout.addWidget(value)
            metric_grid.addWidget(card, row // 2, row % 2)
            self.athlete_metrics[key] = value
        athlete_layout.addLayout(metric_grid)
        self.athlete_baseline = QLabel("")
        self.athlete_baseline.setWordWrap(True)
        self.athlete_baseline.setObjectName("PerformanceModuleNote")
        athlete_layout.addWidget(self.athlete_baseline)
        self.athlete_notes = QLabel("")
        self.athlete_notes.setWordWrap(True)
        self.athlete_notes.setObjectName("PerformanceContextMuted")
        athlete_layout.addWidget(self.athlete_notes)
        self.athlete_limitations = QLabel(
            "Availability is roster-only. Individual change is descriptive, with no causal attribution."
        )
        self.athlete_limitations.setWordWrap(True)
        self.athlete_limitations.setObjectName("PerformanceCalloutInfo")
        athlete_layout.addWidget(self.athlete_limitations)
        athlete_layout.addStretch(1)
        actions = QHBoxLayout()
        back = QPushButton("Daily context")
        back.clicked.connect(self.back_to_daily.emit)
        full_profile = QPushButton("Open full profile →")
        full_profile.setObjectName("PerformanceLinkButton")
        full_profile.clicked.connect(self._open_full_profile)
        actions.addWidget(back)
        actions.addWidget(full_profile)
        athlete_layout.addLayout(actions)
        self.views.addWidget(self.athlete_view)
        self.current_athlete: dict[str, Any] | None = None

    @staticmethod
    def _add_heading(layout: QVBoxLayout, text: str) -> None:
        heading = QLabel(text)
        heading.setObjectName("PerformanceContextHeading")
        layout.addWidget(heading)

    def update_today(self, today: dict[str, Any]) -> None:
        while self.checklist.count():
            item = self.checklist.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for item in today.get("checklist", []):
            row = QHBoxLayout()
            check = QLabel("✓" if item.get("done") else "·")
            check.setObjectName("PerformanceChecklistDone" if item.get("done") else "PerformanceContextMuted")
            title = QLabel(str(item.get("label", "")))
            title.setObjectName("PerformanceChecklistLabel")
            status = QLabel(str(item.get("status", "")))
            status.setObjectName("PerformanceChecklistStatus")
            row.addWidget(check)
            row.addWidget(title, 1)
            row.addWidget(status)
            self.checklist.addLayout(row)
        bands = today.get("readiness_bands", {})
        labels = ("<5.5", "5.5–6.5", "6.5–7.5", "≥7.5")
        values = [int(bands.get(key, 0)) for key in ("l1", "l2", "l3", "l4")]
        for index, count in enumerate(values):
            stretch = max(count, 1)
            self.readiness_bar.setStretch(index, stretch)
        self.readiness_legend.setText(
            "   ·   ".join(f"{label}  {count}" for label, count in zip(labels, values))
        )
        quality = today.get("data_quality", {})
        snapshot = today.get("study", {}).get("snapshot_id", "DS-SYNTH-001")
        force = today.get("force_trial", {}) or {}
        self.quality.setText(
            f"Snapshot    {snapshot}\nType         SYNTHETIC\n"
            f"Valid trials {quality.get('valid_trials', '—')} / {quality.get('present_trials', '—')}\n"
            f"Missing      {quality.get('missing_slots', '—')}\n"
            f"Force rate   {force.get('sample_rate_hz', 1000)} Hz"
        )
        movement = today.get("movement", {})
        note = movement.get("quality", {}).get("note")
        self.movement.setText(str(note or "Movement scope is a bounded segment, not full-match distance."))

    def show_athlete(self, detail: dict[str, Any]) -> None:
        self.current_athlete = detail
        subject = detail["subject"]
        current = detail["current"]
        change = detail["individual_change"]
        athlete_id = subject["display_id"]
        self.athlete_identity.setText(athlete_id)
        self.athlete_position.setText(
            f"{subject.get('position', 'Athlete')} · age {subject.get('age', '—')} · "
            f"week {current.get('week', '—')} · {detail['availability']['status']}"
        )
        self.athlete_metrics["readiness"].setText(
            "—" if current.get("readiness") is None else f"{current['readiness']:.1f} / 10"
        )
        self.athlete_metrics["sleep"].setText(
            "—" if current.get("sleep_hours") is None else f"{current['sleep_hours']:.1f} h"
        )
        self.athlete_metrics["load"].setText(
            "—" if current.get("load_ratio") is None else f"{current['load_ratio']:.2f}"
        )
        self.athlete_metrics["change"].setText(
            "—" if change.get("percent_change") is None else f"{change['percent_change']:+.1f}%"
        )
        self.athlete_baseline.setText(
            f"CMJ baseline {change.get('baseline_mean', '—')} cm  →  current {change.get('current_mean', '—')} cm\n"
            f"{change.get('method', 'Descriptive change')} · n={change.get('n_weeks', '—')} weeks"
        )
        notes = detail.get("notes", [])
        self.athlete_notes.setText(
            "Recent practitioner note: " + str(notes[-1].get("text", ""))
            if notes
            else "No practitioner notes recorded."
        )
        self.views.setCurrentWidget(self.athlete_view)

    def show_daily(self) -> None:
        self.views.setCurrentWidget(self.daily_view)

    def _open_full_profile(self) -> None:
        if self.current_athlete:
            self.open_full_athlete.emit(self.current_athlete["subject"]["display_id"])


class PerformanceWorkbench(QWidget):
    """Native operational workspaces backed by the qualified Python functions."""

    open_research_study = Signal(str)
    athlete_inspected = Signal(object)
    page_names = PERFORMANCE_PAGE_NAMES
    page_keys = PERFORMANCE_PAGE_KEYS

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        # plots take the theme active at creation; changeEvent restyles them on a theme switch
        pg.setConfigOption("background", tokens()["base"])
        pg.setConfigOption("foreground", tokens()["dim_text"])
        pg.setConfigOption("antialias", True)
        self.window = window
        self.service = window.service
        self.context_panel = PerformanceContextPanel(window)
        self.current_page = "today"
        self.loaded_pages: set[str] = set()
        self.athletes: list[dict[str, Any]] = []
        self.report_records: list[dict[str, Any]] = []
        self.match_roster: dict[str, Any] = {}
        self.tabs = QTabWidget(self)
        self.tabs.tabBar().hide()
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self._build_today()
        self._build_athlete()
        self._build_plan()
        self._build_monitor()
        self._build_test()
        self._build_match()
        self._build_research()
        self._build_report()
        self.tabs.currentChanged.connect(self._tab_changed)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.PaletteChange:  # theme switch: plot canvases follow the tokens
            t = tokens()
            pg.setConfigOption("background", t["base"])
            pg.setConfigOption("foreground", t["dim_text"])
            for plot in self.findChildren(pg.PlotWidget):
                plot.setBackground(t["base"])
                for name in ("left", "bottom"):
                    axis = plot.getPlotItem().getAxis(name)
                    axis.setPen(pg.mkPen(t["line2"]))
                    axis.setTextPen(pg.mkPen(t["dim_text"]))
    def select_page(self, page: str) -> None:
        if page not in self.page_keys:
            return
        index = self.page_keys.index(page)
        if self.tabs.currentIndex() == index:
            self._load_page(page)
        else:
            self.tabs.setCurrentIndex(index)

    def show_page(self, page: str) -> None:
        self.window.show_performance_page(page)

    def _tab_changed(self, index: int) -> None:
        if index < 0:
            return
        page = self.page_keys[index]
        self.current_page = page
        self._load_page(page)

    def _page(self, name: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.tabs.addTab(page, name)
        return page, layout

    @staticmethod
    def _heading(layout: QVBoxLayout, title: str, note: str = "") -> None:
        label = QLabel(title if not note else f"{title}  ·  {note}")
        label.setWordWrap(True)
        layout.addWidget(label)

    @staticmethod
    def _module(title: str, note: str = "") -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("PerformanceModule")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(9, 7, 9, 8)
        layout.setSpacing(6)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("PerformanceModuleTitle")
        frame.title_label = title_label
        heading.addWidget(title_label)
        detail = QLabel(note)
        detail.setObjectName("PerformanceModuleNote")
        frame.note_label = detail
        heading.addWidget(detail, 1)
        layout.addLayout(heading)
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(5)
        layout.addLayout(body, 1)
        return frame, body

    @staticmethod
    def _pulse_cell(title: str, unit: str = "", note: str = "") -> tuple[QFrame, QLabel, QLabel]:
        cell = QFrame()
        cell.setObjectName("PerformancePulseCell")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(9, 6, 9, 7)
        layout.setSpacing(1)
        label = QLabel(title.upper())
        label.setObjectName("PerformanceMetricLabel")
        value = QLabel("—")
        value.setObjectName("PerformanceMetricValue")
        if unit:
            value.setText(f"— <span class='unit'>{unit}</span>")
        detail = QLabel(note)
        detail.setObjectName("PerformanceMetricNote")
        layout.addWidget(label)
        layout.addWidget(value)
        layout.addWidget(detail)
        return cell, value, detail

    def _build_today(self) -> None:
        page, layout = self._page(self.page_names[0])
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(1)
        self.today_kicker = QLabel("SQUAD COMMAND · LOADING FIXTURE")
        self.today_kicker.setObjectName("PerformanceKicker")
        title = QLabel("Squad command")
        title.setObjectName("PerformancePageTitle")
        self.today_summary = QLabel("Who needs attention, what changed, and what should happen next?")
        self.today_summary.setObjectName("PerformancePageDescription")
        title_block.addWidget(self.today_kicker)
        title_block.addWidget(title)
        title_block.addWidget(self.today_summary)
        heading.addLayout(title_block, 1)
        actions = QHBoxLayout()
        plan_button = QPushButton("Open week plan")
        plan_button.clicked.connect(lambda: self.show_page("plan"))
        session_button = QPushButton("＋  Log session")
        session_button.setObjectName("PerformancePrimaryButton")
        session_button.clicked.connect(self._log_session)
        actions.addWidget(plan_button)
        actions.addWidget(session_button)
        heading.addLayout(actions)
        layout.addLayout(heading)

        pulse = QFrame()
        pulse.setObjectName("PerformancePulse")
        pulse_layout = QHBoxLayout(pulse)
        pulse_layout.setContentsMargins(0, 0, 0, 0)
        pulse_layout.setSpacing(0)
        self.pulse_values: dict[str, tuple[QLabel, QLabel]] = {}
        for key, name in (
            ("roster", "Roster active"),
            ("readiness", "Readiness"),
            ("load_ratio", "Load ratio"),
            ("cmj", "CMJ height"),
            ("quality", "Data quality"),
        ):
            cell, value, note = self._pulse_cell(name)
            pulse_layout.addWidget(cell, 1)
            self.pulse_values[key] = (value, note)
        layout.addWidget(pulse)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        attention, attention_body = self._module("Athletes to review", "today · ranked by readiness, load and CMJ")
        self.attention_card = attention
        self.today_view, self.today_model = _record_view()
        self.today_view.setObjectName("PerformanceAttentionTable")
        self.today_view.verticalHeader().hide()
        self.today_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.today_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.today_view.doubleClicked.connect(lambda _index: self._open_selected_athlete())
        self.today_view.setMaximumHeight(182)
        attention_body.addWidget(self.today_view)
        review_actions = QHBoxLayout()
        review_actions.addStretch(1)
        athlete_button = QPushButton("Open selected Athlete 360 →")
        athlete_button.setObjectName("PerformanceLinkButton")
        athlete_button.clicked.connect(self._open_selected_athlete)
        review_actions.addWidget(athlete_button)
        attention_body.addLayout(review_actions)
        grid.addWidget(attention, 0, 0)

        load_card, load_body = self._module("Weekly training impulse", "team mean · AU · 16 weeks")
        self.today_load_plot = pg.PlotWidget()
        self.today_load_plot.setMinimumHeight(190)
        self.today_load_plot.setLabel("left", "Load", units="AU")
        self.today_load_plot.setLabel("bottom", "Study week")
        self.today_load_plot.showGrid(x=False, y=True, alpha=0.16)
        load_body.addWidget(self.today_load_plot, 1)
        self.today_load_caption = QLabel("Descriptive reference; not an injury predictor.")
        self.today_load_caption.setObjectName("PerformanceModuleNote")
        load_body.addWidget(self.today_load_caption)
        grid.addWidget(load_card, 0, 1)

        force_card, force_body = self._module("CMJ force–time", "audit trial · 1000 Hz")
        self.today_force_plot = pg.PlotWidget()
        self.today_force_plot.setMinimumHeight(170)
        self.today_force_plot.setLabel("left", "Vertical force", units="N")
        self.today_force_plot.setLabel("bottom", "Time", units="s")
        self.today_force_plot.showGrid(x=False, y=True, alpha=0.16)
        force_body.addWidget(self.today_force_plot, 1)
        metrics = QHBoxLayout()
        metrics.setSpacing(4)
        self.today_force_metrics: dict[str, QLabel] = {}
        for key, label in (
            ("height", "JUMP HEIGHT"),
            ("peak_force", "PEAK FORCE"),
            ("impulse", "CONCENTRIC IMPULSE"),
            ("rsi", "RSI MODIFIED"),
        ):
            metric = QFrame()
            metric.setObjectName("PerformanceMiniMetric")
            metric_layout = QVBoxLayout(metric)
            metric_layout.setContentsMargins(6, 4, 6, 4)
            metric_layout.setSpacing(1)
            heading = QLabel(label)
            heading.setObjectName("PerformanceMetricLabel")
            value = QLabel("—")
            value.setObjectName("PerformanceMiniMetricValue")
            metric_layout.addWidget(heading)
            metric_layout.addWidget(value)
            metrics.addWidget(metric, 1)
            self.today_force_metrics[key] = value
        force_body.addLayout(metrics)
        grid.addWidget(force_card, 1, 0)

        research_card, research_body = self._module("Research & next actions", "evidence → decision")
        self.today_research_title = QLabel("Loading linked study…")
        self.today_research_title.setObjectName("PerformanceResearchTitle")
        self.today_research_body = QLabel("")
        self.today_research_body.setWordWrap(True)
        self.today_research_body.setObjectName("PerformanceModuleNote")
        self.today_decision = QLabel("")
        self.today_decision.setWordWrap(True)
        self.today_decision.setObjectName("PerformanceDecisionCard")
        open_research = QPushButton("Open research →")
        open_research.setObjectName("PerformanceLinkButton")
        open_research.clicked.connect(self._open_linked_study)
        movement_button = QPushButton("Open bounded movement segment →")
        movement_button.setObjectName("PerformanceLinkButton")
        movement_button.clicked.connect(lambda: self.show_page("match"))
        research_caption = QLabel("LINKED STUDY · SYNTHETIC")
        research_caption.setObjectName("PerformanceModuleNote")
        research_body.addWidget(research_caption)
        research_body.addWidget(self.today_research_title)
        research_body.addWidget(self.today_research_body)
        research_body.addWidget(open_research)
        research_body.addWidget(self.today_decision)
        research_body.addStretch(1)
        research_body.addWidget(movement_button)
        grid.addWidget(research_card, 1, 1)
        layout.addLayout(grid, 1)

    def _build_athlete(self) -> None:
        _, layout = self._page(self.page_names[1])
        controls = QHBoxLayout()
        self.athlete_picker = QComboBox()
        self.athlete_picker.currentTextChanged.connect(self._load_athlete)
        controls.addWidget(QLabel("Athlete"))
        controls.addWidget(self.athlete_picker, 1)
        note_button = QPushButton("Add practitioner note…")
        note_button.clicked.connect(self._add_athlete_note)
        controls.addWidget(note_button)
        back_to_today = QPushButton("Today")
        back_to_today.clicked.connect(lambda: self.show_page("today"))
        controls.addWidget(back_to_today)
        layout.addLayout(controls)
        split = QSplitter(Qt.Orientation.Vertical)
        self.athlete_detail = QTextBrowser()
        split.addWidget(self.athlete_detail)
        charts = QWidget()
        chart_layout = QHBoxLayout(charts)
        self.athlete_trend = pg.PlotWidget(title="Observed CMJ trend · cm · weeks 1–16")
        self.athlete_trend.setLabel("left", "Jump height", units="cm")
        self.athlete_trend.setLabel("bottom", "Study week")
        self.force_trace = pg.PlotWidget(title="Force–time trace · synthetic fixture")
        self.force_trace.setLabel("left", "Force", units="N")
        self.force_trace.setLabel("bottom", "Time", units="s")
        chart_layout.addWidget(self.athlete_trend)
        chart_layout.addWidget(self.force_trace)
        split.addWidget(charts)
        split.setSizes([280, 400])
        layout.addWidget(split, 1)
        self.athlete_note = QLabel("Notes are practitioner-entered operational records, not clinical records.")
        layout.addWidget(self.athlete_note)

    def _build_plan(self) -> None:
        _, layout = self._page(self.page_names[2])
        self._heading(layout, "Training and periodization", "planned sessions stay separate from measured load")
        self.plan_summary = QLabel("Loading periodization…")
        self.plan_summary.setWordWrap(True)
        layout.addWidget(self.plan_summary)
        self.plan_view, self.plan_model = _record_view()
        layout.addWidget(self.plan_view, 1)
        self.plan_chart = pg.PlotWidget(title="Observed squad training impulse · AU · 16 weeks")
        self.plan_chart.setLabel("left", "Training impulse", units="AU")
        self.plan_chart.setLabel("bottom", "Study week")
        layout.addWidget(self.plan_chart, 1)
        actions = QHBoxLayout()
        edit = QPushButton("Edit next microcycle…")
        edit.clicked.connect(self._edit_plan)
        publish = QPushButton("Publish next microcycle")
        publish.clicked.connect(self._publish_plan)
        actions.addWidget(edit)
        actions.addWidget(publish)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _build_monitor(self) -> None:
        _, layout = self._page(self.page_names[3])
        self._heading(layout, "Load, wellness and readiness", "estimates are descriptive; no injury-risk prediction")
        self.monitor_summary = QLabel("Loading weekly monitoring data…")
        self.monitor_summary.setWordWrap(True)
        layout.addWidget(self.monitor_summary)
        split = QSplitter(Qt.Orientation.Vertical)
        self.monitor_view, self.monitor_model = _record_view()
        split.addWidget(self.monitor_view)
        self.session_view, self.session_model = _record_view()
        split.addWidget(self.session_view)
        layout.addWidget(split, 1)
        button = QPushButton("Log training session…")
        button.clicked.connect(self._log_session)
        actions = QHBoxLayout()
        actions.addWidget(button)
        match_button = QPushButton("Open match & pose segment")
        match_button.clicked.connect(lambda: self.show_page("match"))
        actions.addWidget(match_button)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _build_test(self) -> None:
        _, layout = self._page(self.page_names[4])
        self._heading(layout, "Performance testing", "admitted metrics, visible exclusions and reliability diagnostics")
        self.test_summary = QLabel("Loading testing windows…")
        self.test_summary.setWordWrap(True)
        layout.addWidget(self.test_summary)
        self.test_view, self.test_model = _record_view()
        layout.addWidget(self.test_view, 1)
        self.trial_picker = QComboBox()
        self.trial_picker.currentIndexChanged.connect(self._load_force_trial)
        layout.addWidget(self.trial_picker)
        self.test_trace = pg.PlotWidget(title="CMJ force–time signal · decimated per plate")
        self.test_trace.setLabel("left", "Force", units="N")
        self.test_trace.setLabel("bottom", "Time", units="s")
        layout.addWidget(self.test_trace, 1)
        action = QPushButton("Run and append reliability assessment")
        action.clicked.connect(self._run_reliability)
        layout.addWidget(action)

    def _build_match(self) -> None:
        _, layout = self._page(self.page_names[5])
        self._heading(layout, "Match tracking and pose", "10 Hz synthetic segment; not a full-match or validated kinematics product")
        controls = QHBoxLayout()
        self.match_player = QComboBox()
        self.match_player.currentIndexChanged.connect(
            lambda _index: self._load_match_path(self.match_player.currentData())
        )
        controls.addWidget(QLabel("Player"))
        controls.addWidget(self.match_player)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 1799)
        self.frame_slider.setValue(900)
        self.frame_slider.valueChanged.connect(self._schedule_match_frame)
        controls.addWidget(QLabel("Frame"))
        controls.addWidget(self.frame_slider, 1)
        self.frame_label = QLabel("90.0 s")
        controls.addWidget(self.frame_label)
        back_to_monitor = QPushButton("Back to Monitor")
        back_to_monitor.clicked.connect(lambda: self.show_page("monitor"))
        controls.addWidget(back_to_monitor)
        layout.addLayout(controls)
        plots = QHBoxLayout()
        self.match_field = pg.PlotWidget(title="Field path · 105 × 68 m")
        self.match_field.setLabel("left", "Field width", units="m")
        self.match_field.setLabel("bottom", "Field length", units="m")
        self.match_field.setAspectLocked(True)
        self.pose_plot = pg.PlotWidget(title="Sagittal pose · x–z · metres")
        self.pose_plot.setLabel("left", "Height", units="m")
        self.pose_plot.setLabel("bottom", "x relative to hip", units="m")
        self.pose_plot.setAspectLocked(True)
        plots.addWidget(self.match_field, 2)
        plots.addWidget(self.pose_plot, 1)
        layout.addLayout(plots, 2)
        self.match_status = QLabel("Pose confidence and segment-only scope will appear here.")
        self.match_frame_item = None
        layout.addWidget(self.match_status)
        self.event_view, self.event_model = _record_view()
        layout.addWidget(self.event_view, 1)
        self._match_timer = QTimer(self)
        self._match_timer.setSingleShot(True)
        self._match_timer.timeout.connect(self._load_match_frame)

    def _build_research(self) -> None:
        _, layout = self._page(self.page_names[6])
        self._heading(layout, "Operational-to-scientific research links", "only qualified evidence is presented as scientific evidence")
        self.research_summary = QTextBrowser()
        layout.addWidget(self.research_summary, 1)
        self.units_view, self.units_model = _record_view()
        self.metrics_view, self.metrics_model = _record_view()
        tables = QSplitter(Qt.Orientation.Vertical)
        tables.addWidget(self.units_view)
        tables.addWidget(self.metrics_view)
        layout.addWidget(tables, 1)
        button = QPushButton("Open linked research study")
        button.clicked.connect(self._open_linked_study)
        layout.addWidget(button)

    def _build_report(self) -> None:
        _, layout = self._page(self.page_names[7])
        self._heading(layout, "Practitioner reports", "audience-specific report engine · source DS-SYNTH-001")
        split = QSplitter(Qt.Orientation.Horizontal)
        self.report_view, self.report_model = _record_view()
        split.addWidget(self.report_view)
        self.report_preview = QTextBrowser()
        self.report_preview.setObjectName("PerformanceReportPreview")
        split.addWidget(self.report_preview)
        self.report_view.clicked.connect(self._select_report)
        layout.addWidget(split, 1)
        actions = QHBoxLayout()
        create = QPushButton("Compose report…")
        create.clicked.connect(self._create_report)
        freeze = QPushButton("Freeze selected report")
        freeze.clicked.connect(self._freeze_report)
        export = QPushButton("Export HTML…")
        export.clicked.connect(self._export_report)
        for button in (create, freeze, export):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _load_page(self, page: str) -> None:
        if page in self.loaded_pages:
            return
        self.current_page = page
        self.window.run_task(
            lambda: self.service.performance_page_data(page),
            lambda values: self._page_succeeded(page, values),
            f"Loading Performance OS · {page}",
        )

    def _page_succeeded(self, page: str, values: dict[str, Any]) -> None:
        self.loaded_pages.add(page)
        self._page_loaded(page, values)

    def _page_loaded(self, page: str, values: dict[str, Any]) -> None:
        if page == "today":
            today = values["today"]
            pulse = today["pulse"]
            self.athletes = values["athletes"]
            self.today_data = today
            self.context_panel.update_today(today)
            self.window.performance_rail.update_summary(today)
            self.today_kicker.setText(
                f"{str(today.get('as_of', ''))[:10]} · WEEK {today['week']} · {today['phase']}"
            )
            attention = today["attention"]
            self.today_summary.setText(
                "One screen for the daily performance question: who needs attention, what changed, and what do we do next?"
            )
            self.attention_card.note_label.setText(
                f"today · top {len(attention)} of {today['triage_count']} flags"
            )
            self.today_model.set_rows(
                [
                    {
                        "athlete_id": row["athlete_id"],
                        "position": row["position"],
                        "flag": row["flag"]["label"],
                        "readiness": (
                            "—" if row.get("readiness") is None else f"{row['readiness']:.1f}"
                        ),
                        "load_ratio": (
                            "—" if row.get("load_ratio") is None else f"{row['load_ratio']:.2f}"
                        ),
                        "cmj_change": (
                            "—"
                            if row.get("cmj_delta_pct") is None
                            else f"{row['cmj_delta_pct']:+.1f}%"
                        ),
                    }
                    for row in attention
                ]
            )
            for index, width in enumerate((60, 32, 85, 50, 50, 64)):
                self.today_view.setColumnWidth(index, width)
            self.pulse_values["roster"][0].setText(
                f"{pulse['roster_active']} / {pulse['roster_total']}"
            )
            self.pulse_values["roster"][1].setText("0 unavailable · roster only")
            self.pulse_values["readiness"][0].setText(f"{pulse['readiness']:.1f} / 10")
            self.pulse_values["readiness"][1].setText(
                f"{pulse['readiness_below']} below 5.5 · n={pulse['readiness_n']}"
            )
            self.pulse_values["load_ratio"][0].setText(f"{pulse['load_ratio']:.2f} AU")
            self.pulse_values["load_ratio"][1].setText(
                f"{pulse['load_ratio_above']} above 1.30 · 4-week baseline"
            )
            self.pulse_values["cmj"][0].setText(f"{pulse['cmj_height_cm']:.2f} cm")
            self.pulse_values["cmj"][1].setText(
                f"{pulse['cmj_delta_pct']:+.1f}% vs baseline · n={pulse['cmj_n']}"
            )
            quality = pulse["quality"]
            self.pulse_values["quality"][0].setText(
                f"{quality['valid_trials']} / {quality['present_trials']}"
            )
            self.pulse_values["quality"][1].setText(
                f"{quality['missing_slots']} missing · {quality['excluded_trials']} excluded"
            )
            weeks = today["weekly"]
            self.today_load_plot.clear()
            self.today_load_plot.plot(
                [row["week"] for row in weeks],
                [row["training_impulse_au"] for row in weeks],
                pen=pg.mkPen("#5fd4e8", width=2),
                symbol="o",
                symbolSize=5,
                symbolBrush="#5fd4e8",
                autoDownsample=True,
                downsampleMethod="peak",
            )
            self.today_load_caption.setText(
                f"Week {today['week']}  {weeks[-1]['training_impulse_au']:.1f} AU    ·    "
                f"{pulse['load_ratio_reference']}    ·    "
                "Descriptive, not an injury predictor"
            )
            study = today["study"]
            self.linked_study_id = study["id"]
            self.today_research_title.setText(study["title"])
            self.today_research_body.setText(
                f"{study['participants']} athletes · weeks {study['weeks'][0]}–{study['weeks'][1]} · "
                f"snapshot {study['snapshot_id']} · {study['evidence_count']} evidence item(s)."
            )
            self.today_decision.setText(
                f"TODAY'S DECISION · Review {len(attention)} top flags before the session. "
                "A review flag is not a diagnosis or an injury prediction."
            )
            force_trial = today.get("force_trial") or {}
            self.today_force_metrics["height"].setText(
                f"{force_trial.get('jump_height_cm', '—')} cm"
            )
            self.today_force_metrics["peak_force"].setText(
                f"{force_trial.get('peak_force_n', '—')} N"
            )
            self.today_force_metrics["impulse"].setText(
                f"{force_trial.get('concentric_impulse_n_s_kg', '—')} N·s·kg⁻¹"
            )
            self.today_force_metrics["rsi"].setText(
                f"{force_trial.get('rsi_mod', '—')} cm·s⁻¹"
            )
            if today.get("force_trial_id"):
                trial_id = today["force_trial_id"]
                self.window.run_task(
                    lambda: self.service.get_signal_waveform("DS-SYNTH-001", trial_id, 1000),
                    self._draw_today_force,
                    f"Loading audit force trial · {trial_id}",
                )
            self.athlete_picker.blockSignals(True)
            self.athlete_picker.clear()
            self.athlete_picker.addItems([row["display_id"] for row in self.athletes])
            self.athlete_picker.blockSignals(False)
        elif page == "athlete":
            self.athletes = values["athletes"]
            self.athlete_picker.blockSignals(True)
            self.athlete_picker.clear()
            self.athlete_picker.addItems([row["display_id"] for row in self.athletes])
            self.athlete_picker.blockSignals(False)
            if self.athlete_picker.count():
                self._load_athlete(self.athlete_picker.currentText())
        elif page == "plan":
            plan = values["plan"]
            self.current_plan = plan
            club = plan.get("club", {})
            season = plan.get("season", "")
            club_name = club.get("name", club.get("id", "Performance OS")) if isinstance(club, dict) else str(club)
            season_label = season.get("label", "") if isinstance(season, dict) else str(season)
            self.plan_summary.setText(
                f"{club_name} · {season_label} · week {plan['current_week']} · "
                f"{plan['status']} v{plan['version']} · source: {plan['source_label']}\n"
                + "Periodization: "
                + "; ".join(
                    f"{block['label']} W{block['start_week']}–{block['end_week']} {block['phase']} ({block['status']})"
                    for block in plan.get("periodization", [])
                )
            )
            self.plan_model.set_rows(plan.get("microcycles", []))
            weeks = plan.get("actual_weekly", [])
            self.plan_chart.clear()
            self.plan_chart.plot(
                [row["week"] for row in weeks],
                [row["training_impulse_au"] for row in weeks],
                pen=pg.mkPen("#4fc4b6", width=2),
                symbol="o",
                symbolSize=5,
            )
        elif page == "monitor":
            load = values["load"]
            self.monitor_summary.setText(
                f"Current week {load['current']['week']} · mean load {load['current']['training_impulse_au']:.1f} AU · "
                f"4-week reference {load['reference']['value']:.2f} AU (observed-data reference, not a prescribed plan)."
            )
            self.monitor_model.set_rows(load["weekly"])
            self.session_model.set_rows(load["session_logs"])
            self.movement = values["movement"]
        elif page == "test":
            tests = values["tests"]
            window = tests["window"]
            self.test_summary.setText(
                f"{window['label']} · {window['valid']}/{window['trials']} valid trials · "
                f"{window['excluded']} excluded · {window['protocol']['sample_rate_hz']} Hz. "
                + " | ".join(
                    f"{metric['label']}: ICC {metric['icc']} [{metric['icc_ci_low']}, {metric['icc_ci_high']}]"
                    for metric in tests["reliability"]
                )
                + "\nUnavailable tests: "
                + "; ".join(item["name"] + " — " + item["note"] for item in tests["battery"] if item["status"] == "UNAVAILABLE")
            )
            self.test_model.set_rows(tests["trials"])
            self.trial_picker.blockSignals(True)
            self.trial_picker.clear()
            for trial in tests["trials"]:
                if trial["trace_available"]:
                    self.trial_picker.addItem(
                        f"{trial['display_id']} · {trial['trial_id']} · {trial['quality_state']}",
                        trial["trial_id"],
                    )
            self.trial_picker.blockSignals(False)
            self._load_force_trial()
        elif page == "match":
            self.match_roster = values["roster"]
            movement = values["movement"]
            self.match_status.setText(
                f"{movement['window_label']} · {movement['scope']} · {movement['quality']['note']}"
            )
            self.match_player.blockSignals(True)
            self.match_player.clear()
            pose_players = set(self.match_roster["pose_players"])
            for row in self.match_roster["players"]:
                suffix = " · pose" if row["player_id"] in pose_players else " · pose unavailable"
                self.match_player.addItem(row["player_id"] + suffix, row["player_id"])
            preferred_player = next(
                (player for player in self.match_roster["pose_players"] if self.match_player.findData(player) >= 0),
                None,
            )
            if preferred_player:
                self.match_player.setCurrentIndex(self.match_player.findData(preferred_player))
            self.match_player.blockSignals(False)
            self.event_model.set_rows(self.match_roster["events"])
            if self.match_player.count():
                self._load_match_path(self.match_player.currentData())
                self._load_match_frame()
        elif page == "research":
            research = values["research"]
            self.linked_study_id = research["study"]["id"]
            self.research_summary.setPlainText(_pretty(research))
            self.units_model.set_rows(values["units"]["units"])
            self.metrics_model.set_rows(values["metrics"])
        elif page == "report":
            self.report_records = values["reports"]
            if not self.athletes:
                self.athletes = values["athletes"]
            self.report_model.set_rows(self.report_records)
            if self.report_records:
                self._show_report(self.report_records[0])

    def _refresh_page(self, page: str) -> None:
        self.loaded_pages.discard(page)
        self._load_page(page)

    def _open_selected_athlete(self) -> None:
        selected = self.today_view.selectionModel().selectedRows()
        if selected:
            athlete_id = self.today_model.rows[selected[0].row()].get("athlete_id")
        else:
            athlete_id = self.today_model.rows[0].get("athlete_id") if self.today_model.rows else None
        if not athlete_id:
            return
        self.window.run_task(
            lambda: self.service.performance_athlete(athlete_id),
            self._athlete_inspected,
            f"Opening Athlete 360 · {athlete_id}",
        )

    def _athlete_inspected(self, detail: dict[str, Any]) -> None:
        athlete_id = detail["subject"]["display_id"]
        self.athlete_picker.blockSignals(True)
        index = self.athlete_picker.findText(athlete_id)
        if index < 0:
            self.athlete_picker.addItem(athlete_id)
            index = self.athlete_picker.findText(athlete_id)
        self.athlete_picker.setCurrentIndex(index)
        self.athlete_picker.blockSignals(False)
        self._athlete_loaded(detail)
        self.athlete_inspected.emit(detail)

    def _load_athlete(self, athlete_id: str) -> None:
        if not athlete_id or not hasattr(self, "athlete_detail"):
            return
        self.window.run_task(
            lambda: self.service.performance_athlete(athlete_id),
            self._athlete_loaded,
            f"Opening Athlete 360 · {athlete_id}",
        )

    def _athlete_loaded(self, detail: dict[str, Any]) -> None:
        self.athlete_detail.setPlainText(_pretty(detail))
        weeks = detail["weeks"]
        self.athlete_trend.clear()
        self.athlete_trend.plot(
            [row["week"] for row in weeks],
            [np.nan if row.get("cmj_height_cm") is None else row["cmj_height_cm"] for row in weeks],
            pen=pg.mkPen("#4fc4b6", width=2),
            symbol="o",
            symbolSize=5,
        )
        trial_id = detail.get("force_trial_id")
        if trial_id:
            self.window.run_task(
                lambda: self.service.get_signal_waveform("DS-SYNTH-001", trial_id, 1000),
                self._draw_force,
                f"Loading force trace · {trial_id}",
            )

    def _draw_force(self, waveform: dict[str, Any]) -> None:
        self.force_trace.clear()
        for series in waveform["series"]:
            rows = series["rows"]
            x_name, y_name = series["time_column"], series["value_column"]
            self.force_trace.plot(
                [row[x_name] for row in rows],
                [row[y_name] for row in rows],
                name=series["label"],
                pen=pg.mkPen("#e3a74e", width=1.2),
                autoDownsample=True,
                downsampleMethod="peak",
            )

    def _draw_today_force(self, waveform: dict[str, Any]) -> None:
        self.today_force_plot.clear()
        for series in waveform["series"]:
            rows = series["rows"]
            x_name, y_name = series["time_column"], series["value_column"]
            self.today_force_plot.plot(
                [row[x_name] for row in rows],
                [row[y_name] for row in rows],
                name=series["label"],
                pen=pg.mkPen("#c8f36b", width=1.3),
                autoDownsample=True,
                downsampleMethod="peak",
            )

    def _add_athlete_note(self) -> None:
        athlete_id = self.athlete_picker.currentText()
        text, accepted = QInputDialog.getMultiLineText(self, "Practitioner note", athlete_id, "")
        if not accepted or not text.strip():
            return
        self.window.run_task(
            lambda: self.service.performance_add_athlete_note(athlete_id, {"text": text.strip()}),
            lambda _note: self._load_athlete(athlete_id),
            f"Saving practitioner note · {athlete_id}",
        )

    def _edit_plan(self) -> None:
        if not hasattr(self, "current_plan"):
            return
        dialog = PlanDialog(self.current_plan, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        self.window.run_task(
            lambda: self.service.performance_update_plan(payload),
            lambda _plan: self._refresh_page("plan"),
            "Saving microcycle plan",
        )

    def _publish_plan(self) -> None:
        self.window.run_task(
            self.service.performance_publish_plan,
            lambda _plan: self._refresh_page("plan"),
            "Publishing next microcycle",
        )

    def _log_session(self) -> None:
        dialog = SessionDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.window.run_task(
            lambda: self.service.performance_log_session(dialog.payload()),
            lambda _record: self._refresh_page("monitor"),
            "Saving coach-entered session log",
        )

    def _run_reliability(self) -> None:
        self.window.run_task(
            self.service.performance_run_reliability,
            lambda _record: self._refresh_page("test"),
            "Computing and recording ICC(3,1) reliability",
        )

    def _load_force_trial(self, _index: int = -1) -> None:
        trial_id = self.trial_picker.currentData()
        if not trial_id:
            return
        self.window.run_task(
            lambda: self.service.get_signal_waveform("DS-SYNTH-001", trial_id, 1000),
            self._draw_test_trace,
            f"Loading CMJ trace · {trial_id}",
        )

    def _draw_test_trace(self, waveform: dict[str, Any]) -> None:
        self.test_trace.clear()
        for series in waveform["series"]:
            rows = series["rows"]
            x_name, y_name = series["time_column"], series["value_column"]
            self.test_trace.plot(
                [row[x_name] for row in rows],
                [row[y_name] for row in rows],
                name=series["label"],
                pen=pg.mkPen("#4fc4b6", width=1.2),
                autoDownsample=True,
                downsampleMethod="peak",
            )

    def _load_match_path(self, player_id: str) -> None:
        if not player_id:
            return
        self.window.run_task(
            lambda: self.service.performance_tracking(player_id, 1800),
            self._draw_match_path,
            f"Loading bounded tracking path · {player_id}",
        )

    def _draw_match_path(self, data: dict[str, Any]) -> None:
        rows = data["rows"]
        self.match_field.clear()
        self.match_frame_item = None
        self.match_path_item = self.match_field.plot(
            [row["x_m"] for row in rows], [row["y_m"] for row in rows],
            pen=pg.mkPen("#4fc4b6", width=1.5),
            autoDownsample=True,
            downsampleMethod="peak",
        )
        self.match_field.setXRange(0, 105, padding=0.02)
        self.match_field.setYRange(0, 68, padding=0.02)
        self._load_match_frame()

    def _schedule_match_frame(self, frame_number: int) -> None:
        self.frame_label.setText(f"{frame_number / 10:.1f} s")
        self._match_timer.start(120)

    def _load_match_frame(self) -> None:
        player_id = self.match_player.currentData()
        if not player_id:
            return
        frame_number = self.frame_slider.value()
        self.window.run_task(
            lambda: self.service.performance_match_frame(frame_number, player_id),
            self._draw_match_frame,
            f"Loading match frame {frame_number}",
        )

    def _draw_match_frame(self, data: dict[str, Any]) -> None:
        tracking = data["tracking"]
        if self.match_frame_item is not None:
            self.match_field.removeItem(self.match_frame_item)
        self.match_frame_item = self.match_field.plot(
            [row["x_m"] for row in tracking], [row["y_m"] for row in tracking],
            pen=None,
            symbol="o",
            symbolSize=6,
            symbolBrush=["#e3a74e" if row["team"] == "AWAY" else "#4fc4b6" if row["team"] == "HOME" else "#f3f6f7" for row in tracking],
        )
        joints = {row["joint"]: row for row in data["pose"] if row["joint"] not in {"knee", "ankle"}}
        anchor = joints.get("hip")
        self.pose_plot.clear()
        if anchor:
            connections = (
                ("hip", "left_hip"), ("hip", "right_hip"), ("left_hip", "left_knee"),
                ("left_knee", "left_ankle"), ("right_hip", "right_knee"),
                ("right_knee", "right_ankle"), ("hip", "shoulder"),
                ("shoulder", "left_shoulder"), ("shoulder", "right_shoulder"),
                ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
                ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
            )
            line_x = []
            line_z = []
            for left, right in connections:
                if left in joints and right in joints:
                    line_x.extend(
                        [
                            joints[left]["x_m"] - anchor["x_m"],
                            joints[right]["x_m"] - anchor["x_m"],
                            float("nan"),
                        ]
                    )
                    line_z.extend([joints[left]["z_m"], joints[right]["z_m"], float("nan")])
            self.pose_plot.plot(
                line_x,
                line_z,
                pen=pg.mkPen("#5fd4e8", width=2),
                connect="finite",
            )
            points = list(joints.values())
            self.pose_plot.plot(
                [row["x_m"] - anchor["x_m"] for row in points],
                [row["z_m"] for row in points],
                pen=None,
                symbol="o",
                symbolSize=7,
                symbolBrush=["#f3f6f7" if row["confidence"] >= 0.85 else "#7d8a92" for row in points],
            )
            confidence = float(np.mean([row["confidence"] for row in points]))
            self.match_status.setText(
                f"{data['frame']} · {data['time_s']:.1f} s · {len(points)} joints · "
                f"mean confidence {confidence:.1%}. Synthetic pose geometry; no validated joint-angle estimate."
            )
        else:
            self.match_status.setText(
                f"{data['frame']} · {data['time_s']:.1f} s · pose unavailable for {self.match_player.currentData()}."
            )

    def _open_linked_study(self) -> None:
        if getattr(self, "linked_study_id", None):
            self.open_research_study.emit(self.linked_study_id)

    def _create_report(self) -> None:
        dialog = ReportDialog(self.athletes, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.window.run_task(
            lambda: self.service.performance_create_report(dialog.payload()),
            lambda report: self._report_created(report),
            "Composing audience-specific practitioner report",
        )

    def _report_created(self, report: dict[str, Any]) -> None:
        self.loaded_pages.discard("report")
        self.window.run_task(
            lambda: self.service.performance_page_data("report"),
            lambda values: self._page_loaded("report", values),
            "Refreshing report history",
        )
        self._show_report(report)

    def _select_report(self, index) -> None:
        if index.isValid() and index.row() < len(self.report_records):
            self._show_report(self.report_records[index.row()])

    def _show_report(self, report: dict[str, Any]) -> None:
        self.selected_report_id = report["id"]
        self.report_preview.setHtml(self.service.performance_render_report(report))

    def _freeze_report(self) -> None:
        report_id = getattr(self, "selected_report_id", None)
        if not report_id:
            QMessageBox.information(self, "Freeze report", "Select a report first.")
            return
        self.window.run_task(
            lambda: self.service.performance_freeze_report(report_id),
            self._report_created,
            f"Freezing performance report · {report_id}",
        )

    def _export_report(self) -> None:
        report_id = getattr(self, "selected_report_id", None)
        if not report_id:
            QMessageBox.information(self, "Export report", "Select a report first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export practitioner report", f"{report_id}.html", "HTML report (*.html)"
        )
        if not path:
            return
        self.window.run_task(
            lambda: self.service.performance_export_report(report_id, path),
            lambda output: self.window.statusBar().showMessage(f"Report exported: {output}", 8000),
            "Exporting practitioner report",
        )
