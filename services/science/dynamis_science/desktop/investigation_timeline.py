"""Linked visual timeline and evidence reader for an investigation."""

from datetime import datetime
import json

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from . import theme
from .individual_research import fit_dialog

LANES = {
    "PLAN": ("Planned phases", "#916020"), "VISIT": ("Actual conduct", "#2977ab"),
    "TRAINING": ("Training", "#148175"), "WELLNESS": ("Wellness", "#7852b9"),
    "ASSESSMENT": ("Testing", "#b64158"),
}
GOOD = {"OBSERVED", "MEASURED", "PLANNED"}
PHASE_COLORS = {"BASELINE": "#65756d", "INTERVENTION": "#916020", "COMPARISON": "#396d61"}


def readable(text):
    return str(text).replace("_", " ").lower()


def date_label(value):
    day = datetime.fromisoformat(value)
    return f"{day.day} {day:%b %Y}"


def wrapping_label(text=""):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def heading(label, size):
    font = QFont(label.font())
    font.setPointSize(size)
    font.setBold(True)
    label.setFont(font)


class InvestigationChart(pg.PlotWidget):
    selected = Signal(int)

    def __init__(self):
        super().__init__(axisItems={"bottom": pg.DateAxisItem(utcOffset=0)})
        self.setAccessibleName("Investigation timeline. Use the observation selector to inspect points with the keyboard.")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumHeight(245)
        self.setMouseEnabled(x=True, y=False)
        self.setMenuEnabled(False)
        self.hideButtons()
        self.getAxis("left").setTicks([[(i, lane[0]) for i, lane in enumerate(LANES.values(), 1)]])
        self.showGrid(x=True, y=True, alpha=.13)
        self.rows = []
        self.labels: list[tuple[int, float, pg.TextItem]] = []
        self.selection = None
        self.dark = False
        self.set_theme(theme.current_theme())
        self.getViewBox().sigXRangeChanged.connect(self._fit_labels)
        self.getViewBox().sigResized.connect(self._fit_labels)

    def set_theme(self, name):
        self.dark = name == "dark"
        colors = theme.tokens(name)
        self.ink = colors["text"]
        self.setBackground(colors["base"])
        for side in ("left", "bottom"):
            axis = self.getAxis(side)
            axis.setPen(self.ink)
            axis.setTextPen(self.ink)
            axis.setStyle(tickFont=QFont("Segoe UI", 10))

    def lane_color(self, key):
        color = QColor(LANES[key][1])
        return color.lighter(165) if self.dark else color

    def render(self, rows, offset, pair):
        self.rows = rows
        self.labels.clear()
        self.clear()
        axis = self.getAxis("bottom")
        axis.utcOffset = -datetime.fromisoformat(f"2000-01-01T00:00:00{offset}").utcoffset().total_seconds()
        self.setLabel("bottom", f"Study dates · UTC{offset}", color=self.ink)
        self.setYRange(.45, 5.6, padding=0)
        single_athlete = len({row["subject_id"] for row in rows}) == 1
        # Only mark documented actual visits. Their dates do not establish a continuous actual phase.
        for lane, key in enumerate(LANES, 1):
            color = self.lane_color(key)
            entries = [(i, row) for i, row in enumerate(rows) if row["kind"] == key]
            if key == "PLAN":
                for index, row in entries:
                    start, end = row["axis_time"], row["axis_end"]
                    phase_color = QColor(PHASE_COLORS.get(row["period"]["kind"], color))
                    if self.dark:
                        phase_color = phase_color.lighter(150)
                    bar = self.plot([start, end], [lane, lane], pen=pg.mkPen(phase_color, width=6))
                    bar.setCurveClickable(True, width=18)
                    bar.sigClicked.connect(lambda _, __, i=index: self.selected.emit(i))
                    for boundary in (start, end):
                        self.plot([boundary, boundary], [lane - .14, lane + .14], pen=pg.mkPen(self.ink, width=1))
                    if single_athlete:
                        self._label(row["period"]["label"], (start + end) / 2, lane)
                continue
            spots = []
            previous_phase = None
            for index, row in entries:
                valid = row["status"] in GOOD
                changed = row.get("adherence") == "MODIFIED" or (
                    key == "VISIT" and row.get("observed_period") != row.get("period"))
                symbol = "x" if not valid else "d" if key == "ASSESSMENT" else "t1" if changed else "o"
                compared = row.get("id") in pair
                spots.append(dict(pos=(row["axis_time"], lane), data=index, symbol=symbol,
                                  pen=pg.mkPen(color, width=2), brush=color, size=14 if compared else 10))
                if key == "VISIT" and single_athlete:
                    observed = row.get("observed_period")
                    phase = observed["label"] if observed else None
                    if valid and phase and phase != previous_phase:
                        self._label(phase, row["axis_time"], lane)
                        previous_phase = phase
                elif compared:
                    label = "Reference" if row["id"] == pair[0] else "Follow-up"
                    self._label(label, row["axis_time"], lane)
            if spots:
                scatter = pg.ScatterPlotItem(spots=spots, hoverable=True, hoverSize=15, tip=self._point_tip)
                scatter.sigClicked.connect(self._pick_point)
                self.addItem(scatter)
        self.selection = pg.ScatterPlotItem(symbol="o", size=20, brush=None, pen=pg.mkPen(self.ink, width=1.5))
        self.addItem(self.selection, ignoreBounds=True)
        self.enableAutoRange(axis="x")
        self._fit_labels()

    def _label(self, text, x, lane):
        item = pg.TextItem(text, color=self.ink, anchor=(.5, 1))
        self.addItem(item, ignoreBounds=True)
        item.setPos(x, lane + .13)
        self.labels.append((lane, x, item))

    def _fit_labels(self, *_args):
        view = self.getViewBox()
        lower, upper = view.viewRange()[0]
        width = view.width()
        if upper <= lower or width <= 0:
            return
        right_by_lane = {}
        for lane, date, item in sorted(self.labels, key=lambda entry: entry[:2]):
            center = (date - lower) * width / (upper - lower)
            half = item.textItem.boundingRect().width() / 2
            left, right = center - half, center + half
            visible = left >= right_by_lane.get(lane, 0) and right <= width
            item.setVisible(visible)
            if visible:
                right_by_lane[lane] = right + 8

    def _point_tip(self, _x, _y, index):
        row = self.rows[index]
        text = f"{LANES[row['kind']][0]} · {row['subject_id']} · {readable(row['status'])}"
        visit = row.get("visit") or {}
        if row.get("observed_period"):
            text += f"\n{row['observed_period']['label']}"
        if visit.get("adherence_percent") is not None:
            text += f" · {visit['adherence_percent']:g}% adherence"
        return text

    def _pick_point(self, _scatter, points, event):
        if points:
            self.selected.emit(points[0].data())
            event.accept()

    def highlight(self, index):
        if self.selection is None:
            return
        if not 0 <= index < len(self.rows):
            self.selection.clear()
            return
        row = self.rows[index]
        x = (row["axis_time"] + row.get("axis_end", row["axis_time"])) / 2
        self.selection.setData([x], [list(LANES).index(row["kind"]) + 1])


class EvidencePanel(QWidget):
    selected = Signal(int)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        title = QLabel("Observation evidence")
        heading(title, 13)
        layout.addWidget(title)
        self.picker = QComboBox()
        self.picker.setAccessibleName("Inspect timeline observation")
        self.picker.setMinimumContentsLength(18)
        self.picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.picker.currentIndexChanged.connect(self.selected)
        layout.addWidget(self.picker)
        self.details = QTextBrowser()
        self.details.setAccessibleName("Selected observation evidence")
        self.details.setMinimumHeight(105)
        layout.addWidget(self.details, 1)
        self.followup = QPushButton()
        self.followup.hide()
        layout.addWidget(self.followup)
        self.provenance_button = QPushButton("Details / Provenance…")
        self.provenance_button.clicked.connect(self._open_provenance)
        layout.addWidget(self.provenance_button)
        self.provenance = None
        self.setMinimumWidth(270)

    def load(self, rows):
        self.picker.blockSignals(True)
        self.picker.clear()
        for row in rows:
            kind = LANES[row["kind"]][0]
            name = row["period"]["label"] if row["kind"] == "PLAN" else kind
            self.picker.addItem(f"{row['calendar_date'][5:]} · {name} · {row['subject_id']}")
        self.picker.setCurrentIndex(-1)
        self.picker.blockSignals(False)
        self.picker.setEnabled(bool(rows))
        self.followup.hide()
        self.show_row(None, None)

    def show_row(self, row, view):
        self.provenance_button.setEnabled(bool(row))
        self.provenance = None
        if not row:
            self.details.setPlainText("Select a point on the timeline or choose an observation here.")
            return
        kind = row["kind"]
        time = row.get("occurred_at") or row.get("scheduled_at")
        when = date_label(row["calendar_date"])
        if time:
            recorded = datetime.fromisoformat(time)
            when = f"{date_label(time)} · {recorded:%H:%M} UTC{recorded:%z}"
        receipt = next((item for item in view["sources"] if item["id"] == row.get("context_source_id")), None)
        source = row["source_name"] or "Source unresolved"
        flags = row.get("qc") or row.get("quality") or []
        if kind == "ASSESSMENT":
            receipt = [item for item in view["performance"]["sources"] if item["artifact_id"] in row["artifact_ids"]]
            value = f"{row['value']:g} {row['unit']}" if row["value"] is not None else "Score unavailable"
            observed = f"{row['measure']} · {value}\n{row['valid_trials']} of {row['n_trials']} eligible trials · session mean"
            files = sorted({item["filename"] for origin in receipt for item in origin["retained_exports"]})
            if files:
                source += f"\n{', '.join(files)}"
            status = "Session score available" if row["value"] is not None else "Unusable session score"
            if row["acquisition"].get("rights_status") == "FIXTURE_ONLY":
                status += " · synthetic fixture"
        elif kind == "PLAN":
            period = row["period"]
            observed = f"{period['label']} · {readable(period['kind'])}\nThrough {date_label(row['end_date'])} · weeks {period['start']}–{period['end']}"
            status = "Planned"
        elif kind == "VISIT":
            visit = row["visit"]
            actual = (row["observed_period"] or {}).get("label", "Outside plan")
            planned = (row["period"] or {}).get("label", "Unspecified")
            adherence = visit["adherence_percent"]
            observed = f"Planned phase · {planned}\nPhase at actual visit · {actual}"
            if adherence is not None:
                observed += f" · {adherence:g}% adherence"
            observed += "".join(f"\n{visit[key]}" for key in ("exposure", "deviations") if visit.get(key))
            status = readable(row["status"]).capitalize()
        else:
            observed = self._context_value(row)
            status = readable(row["status"]).capitalize()
        if receipt and isinstance(receipt, dict):
            source += f" · version {receipt['version']}\n{receipt['filename']}"
            if receipt["source"]["rights_status"] == "FIXTURE_ONLY":
                status += " · synthetic fixture"
        qc = f"Quality · {status}"
        if flags:
            qc += "\n" + ", ".join(map(readable, flags)).capitalize()
        self.details.setPlainText(f"{when} · {row['subject_id']}\n\n{observed}\n\n{qc}\n\nSource · {source}")
        self.provenance = {"observation": row, "source_receipt": receipt, "alignment_notes": view["notes"],
                           "limitations": view["limitations"]}

    @staticmethod
    def _context_value(row):
        if row["kind"] == "WELLNESS":
            name = readable(row["measure"]).capitalize()
            value = f"{row['value']:g} {row['unit']}" if row["value"] is not None else "No measurement"
            return f"{name} · {value}\n{row['questionnaire']} v{row['questionnaire_version']}" + (
                f"\n{row['reason']}" if row.get("reason") else "")
        values = []
        if row["session_load_au"] is not None:
            values.append(f"{row['session_load_au']:g} AU session load")
        if row["duration_min"] is not None:
            values.append(f"{row['duration_min']:g} min")
        if row["rpe"] is not None:
            values.append(f"RPE {row['rpe']:g} ({row['rpe_scale']})")
        text = " · ".join(values) or "No measured training load"
        if row.get("adherence"):
            text += f"\nAdherence · {readable(row['adherence'])}"
        return text + "".join(f"\n{row[key]}" for key in ("deviation", "reason") if row.get(key))

    def _open_provenance(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Observation details / provenance")
        layout = QVBoxLayout(dialog)
        text = QTextBrowser()
        text.setPlainText(json.dumps(self.provenance, indent=2, default=str))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        fit_dialog(dialog, 760, 520)
        dialog.exec()
