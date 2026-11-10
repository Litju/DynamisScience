"""Signal inspection for the workbench "Signals" ribbon key (pyqtgraph).

Trials come from ``DynamisAppService.list_signal_trials`` and waveforms from
``get_signal_waveform`` (min/max-decimated per channel, so peaks survive). Every trace is
an observed signal: graphite, channels told apart by dash style rather than by a claim or
provenance hue. Zoom and pan are pyqtgraph's (wheel / drag, right-drag to stretch);
"Reset zoom" restores the full trial. Reference lines (baseline, peak) are the values
recorded on the trial row; events are drawn when the waveform carries an ``events`` list.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import theme

ALL = "All"
DASHES = (Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine)
REFERENCES = (("fz_baseline_n", "baseline"), ("fz_peak_n", "peak"))


def trial_text(trial: dict[str, Any]) -> str:
    flags = trial.get("quality_flags") or []
    parts = [trial.get("subject_id", ""), trial.get("activity", ""), f"#{trial.get('trial_number', '')}"]
    return " · ".join(str(p) for p in parts if p) + (f"  ⚑ {len(flags)}" if flags else "")


class SignalsView(QWidget):
    """Trial list · channel selection · zoomable waveform plot.

    ``run_task(fn, on_done)`` (optional) runs service calls off the GUI thread, e.g.
    ``MainWindow.run_task``; without it calls are synchronous.
    """

    trial_selected = Signal(str)

    def __init__(self, service: Any, run_task: Callable[[Callable[[], Any], Callable[[Any], None]], Any] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.run_task = run_task or (lambda fn, done: done(fn()))
        self.snapshot_id: str | None = None
        self.trials: list[dict[str, Any]] = []
        self.trial: dict[str, Any] | None = None
        self.waveform: dict[str, Any] | None = None
        self.curves: dict[str, pg.PlotDataItem] = {}
        self._theme = theme.current_theme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self.subject_filter = QComboBox()
        self.subject_filter.setAccessibleName("Filter trials by athlete")
        self.activity_filter = QComboBox()
        self.activity_filter.setAccessibleName("Filter trials by activity")
        for combo in (self.subject_filter, self.activity_filter):
            combo.currentIndexChanged.connect(self._fill_list)
            filters.addWidget(combo, 1)
        left_layout.addLayout(filters)
        self.trial_list = QListWidget()
        self.trial_list.setAccessibleName("Signal trials")
        self.trial_list.currentItemChanged.connect(self._trial_clicked)
        left_layout.addWidget(self.trial_list, 1)
        self.count_label = QLabel()
        self.count_label.setObjectName("PaneContext")
        left_layout.addWidget(self.count_label)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self.title = QLabel("Choose a trial")
        self.title.setObjectName("BlockHeading")
        header.addWidget(self.title, 1)
        header.addWidget(theme.chip("Observed", "obs"))
        right_layout.addLayout(header)
        self.channel_row = QHBoxLayout()
        self.channel_row.addWidget(QLabel("Channels"))
        self.channel_boxes: list[QCheckBox] = []
        self.channel_row.addStretch(1)
        self.reference_box = QCheckBox("Recorded baseline / peak")
        self.reference_box.setChecked(True)
        self.reference_box.toggled.connect(self._render)
        self.channel_row.addWidget(self.reference_box)
        reset = QPushButton("Reset zoom")
        reset.clicked.connect(self.reset_zoom)
        self.channel_row.addWidget(reset)
        right_layout.addLayout(self.channel_row)
        self.plot = pg.PlotWidget()
        self.plot.setAccessibleName("Signal waveform")
        self.plot.setMenuEnabled(False)
        right_layout.addWidget(self.plot, 1)
        self.detail = QLabel()
        self.detail.setObjectName("BlockNote")
        self.detail.setWordWrap(True)
        right_layout.addWidget(self.detail)
        splitter.addWidget(right)
        splitter.setSizes([280, 720])

    # -- API ----------------------------------------------------------------
    def set_snapshot(self, snapshot_id: str, subject_id: str | None = None, activity: str | None = None) -> None:
        """Load the trial list of ``snapshot_id`` (optionally pre-filtered)."""
        self.snapshot_id = snapshot_id

        def done(trials: list[dict[str, Any]]) -> None:
            self.trials = trials
            for combo, key, chosen in ((self.subject_filter, "subject_id", subject_id),
                                       (self.activity_filter, "activity", activity)):
                combo.blockSignals(True)
                combo.clear()
                combo.addItem(ALL)
                combo.addItems(sorted({str(t[key]) for t in trials if t.get(key) is not None}))
                combo.setCurrentIndex(max(0, combo.findText(chosen or ALL)))
                combo.blockSignals(False)
            self._fill_list()

        self.run_task(lambda: self.service.list_signal_trials(snapshot_id), done)

    def visible_trials(self) -> list[dict[str, Any]]:
        subject, activity = self.subject_filter.currentText(), self.activity_filter.currentText()
        return [t for t in self.trials
                if subject in (ALL, "", str(t.get("subject_id"))) and activity in (ALL, "", str(t.get("activity")))]

    def show_trial(self, trial_id: str, max_points: int = 2500) -> None:
        self.trial = next((t for t in self.trials if t.get("trial_id") == trial_id), {"trial_id": trial_id})
        snapshot_id = self.snapshot_id
        for row in range(self.trial_list.count()):
            if self.trial_list.item(row).data(Qt.ItemDataRole.UserRole) == trial_id:
                self.trial_list.blockSignals(True)
                self.trial_list.setCurrentRow(row)
                self.trial_list.blockSignals(False)

        def done(waveform: dict[str, Any]) -> None:
            self.waveform = waveform
            self._channels()
            self._render()
            self.reset_zoom()
            self.trial_selected.emit(trial_id)

        self.run_task(lambda: self.service.get_signal_waveform(snapshot_id, trial_id, max_points), done)

    def channels(self) -> list[str]:
        return [box.text() for box in self.channel_boxes]

    def set_channel_visible(self, label: str, visible: bool) -> None:
        next(box for box in self.channel_boxes if box.text() == label).setChecked(visible)

    def reset_zoom(self) -> None:
        self.plot.getPlotItem().enableAutoRange()

    # -- internals ----------------------------------------------------------
    def _fill_list(self) -> None:
        self.trial_list.blockSignals(True)
        self.trial_list.clear()
        visible = self.visible_trials()
        for trial in visible:
            item = QListWidgetItem(trial_text(trial))
            item.setData(Qt.ItemDataRole.UserRole, trial["trial_id"])
            item.setToolTip(", ".join(trial.get("quality_flags") or []) or "No quality flags")
            self.trial_list.addItem(item)
        self.trial_list.blockSignals(False)
        self.count_label.setText(f"{len(visible)} of {len(self.trials)} trials")

    def _trial_clicked(self, item: QListWidgetItem | None) -> None:
        if item is not None:
            self.show_trial(item.data(Qt.ItemDataRole.UserRole))

    def _channels(self) -> None:
        for box in self.channel_boxes:
            self.channel_row.removeWidget(box)
            box.deleteLater()
        self.channel_boxes = []
        for index, series in enumerate(self.waveform["series"]):
            box = QCheckBox(series["label"] if len(self.waveform["series"]) == 1 else f"Plate {series['label']}")
            box.setChecked(True)
            box.toggled.connect(self._render)
            self.channel_row.insertWidget(1 + index, box)
            self.channel_boxes.append(box)

    def _render(self) -> None:
        if not self.waveform:
            return
        t = theme.tokens()
        self._theme = theme.current_theme()
        item = self.plot.getPlotItem()
        item.clear()
        self.plot.setBackground(t["base"])
        for name in ("left", "bottom"):
            axis = item.getAxis(name)
            axis.setPen(pg.mkPen(t["line2"]))
            axis.setTextPen(pg.mkPen(t["muted"]))
        item.showGrid(x=True, y=True, alpha=0.2)
        legend = item.legend or item.addLegend(offset=(10, 6), labelTextSize="8pt")
        legend.clear()
        legend.setLabelTextColor(t["muted"])
        self.curves = {}
        series_list = self.waveform["series"]
        for index, (series, box) in enumerate(zip(series_list, self.channel_boxes)):
            if not box.isChecked():
                continue
            rows = series["rows"]
            x, y = series["time_column"], series["value_column"]
            # None samples stay gaps (connect="finite"); they are never interpolated
            xs = [row[x] for row in rows]
            ys = [float("nan") if row[y] is None else row[y] for row in rows]
            pen = pg.mkPen(t["obs"], width=1.3, style=DASHES[index % len(DASHES)])
            self.curves[box.text()] = item.plot(xs, ys, pen=pen, name=box.text(), connect="finite")
        first = series_list[0] if series_list else {"time_column": "time", "value_column": "value"}
        item.setLabel("bottom", first["time_column"].replace("_", " "), color=t["muted"])
        item.setLabel("left", first["value_column"].replace("_", " "), color=t["muted"])
        trial = self.trial or {}
        if self.reference_box.isChecked():
            for key, label in REFERENCES:
                if trial.get(key) is not None:
                    line = pg.InfiniteLine(trial[key], angle=0, pen=pg.mkPen(t["dim"], style=Qt.PenStyle.DashLine),
                                           label=f"{label} {trial[key]:,.1f}", labelOpts={"color": t["dim_text"],
                                                                                         "position": 0.97})
                    item.addItem(line)
        for event in self.waveform.get("events") or []:
            item.addItem(pg.InfiniteLine(event["time"], angle=90, pen=pg.mkPen(t["accent"]),
                                         label=str(event.get("label", "")), labelOpts={"color": t["accent_text"]}))
        flags = trial.get("quality_flags") or []
        self.title.setText(f"{trial.get('trial_id', '')} · {trial.get('activity', '')}".strip(" ·"))
        self.detail.setText(
            f"{self.waveform['sample_count']:,} plotted samples (min/max per bucket) from "
            f"{self.waveform['source_rows']:,} source rows"
            + (f" · {trial['sampling_hz']:g} Hz" if trial.get("sampling_hz") else "")
            + (f" · {trial['nan_count']} missing samples shown as gaps" if trial.get("nan_count") else "")
            + (f" · flags: {', '.join(flags)}" if flags else "")
            + ("" if self.waveform.get("events") else " · no events recorded for this trial"))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.PaletteChange and theme.current_theme() != self._theme:
            self._render()


__all__ = ["SignalsView", "trial_text"]
