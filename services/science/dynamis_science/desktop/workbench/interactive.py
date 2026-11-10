"""Interactive trajectory figures (pyqtgraph) for the RES-620 workbench.

Observed values come from ``DynamisAppService.explore_longitudinal`` and are drawn in
graphite. The modeled fitted mean and its interval come only from a recorded
METH-REAL-TREND run (cobalt); nothing is refitted here. Missing athlete-occasions are
listed in red and never interpolated or imputed (spec E rules 1 and 5).

The 3D view never uses the athlete identifier as a continuous axis: depth is either a
continuous athlete-level measure (baseline outcome, or one the caller supplies) or
explicitly labelled categorical lanes.
"""

from __future__ import annotations

import math
from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme

TREND_METHOD = "METH-REAL-TREND"
BAND_LABEL = "Approximate band from recorded limits, conservative; not the model's Wald band"
LANES = "lanes"
BASELINE = "baseline"


# --------------------------------------------------------------------------- #
# Data (no Qt)
# --------------------------------------------------------------------------- #


def observed(explore: dict[str, Any]) -> dict[str, Any]:
    """Occasion positions/labels and per-athlete values (None = missing) from an explore result."""
    summary = explore["summary"]
    xs = [float(item.get("occasion", item.get("week"))) for item in summary]
    labels = [str(item.get("activity") or f"Occasion {item.get('occasion', item.get('week'))}") for item in summary]
    athletes = [
        {"id": a["subject_id"], "label": a.get("display_id") or a["subject_id"], "values": list(a["values"])}
        for a in explore["athletes"]
    ]
    missing = [[a["label"] for a in athletes if a["values"][i] is None] for i in range(len(xs))]
    metric = explore.get("metric") or {}
    unit = explore.get("unit") or metric.get("unit") or ""
    return {"xs": xs, "labels": labels, "athletes": athletes, "missing": missing, "unit": unit,
            "outcome": metric.get("column"), "title": metric.get("label") or metric.get("column") or "Outcome",
            "scale": explore.get("reference_label", "observed values"), "raw": explore.get("reference", "RAW") == "RAW"}


def model_band(run: dict[str, Any] | None, xs: list[float], outcome: str | None = None) -> dict[str, Any] | None:
    """Fitted fixed-effect mean and a 95% band at ``xs`` from a recorded MixedLM run, else None.

    Uses only recorded estimates and their recorded Wald limits.
    """
    if not run or run.get("method_id") != TREND_METHOD:
        return None
    result = run.get("result") or {}
    coefficients = result.get("coefficients") or {}
    b0, b1 = coefficients.get("intercept"), coefficients.get("occasion_slope")
    if not b0 or not b1 or (outcome and result.get("outcome") not in (None, outcome)):
        return None
    reference = float(result.get("reference_occasion", 1))
    h0, h1 = b0["estimate"] - b0["ci_low"], b1["estimate"] - b1["ci_low"]
    mean = [b0["estimate"] + b1["estimate"] * (x - reference) for x in xs]
    # shortcut: the intercept-slope covariance is not recorded, so |cov| <= SE0*SE1 bounds the band
    # (wider than the exact Wald band); use the exact covariance once runs record it.
    half = [h0 + abs(x - reference) * h1 for x in xs]
    return {"mean": mean, "low": [m - h for m, h in zip(mean, half)], "high": [m + h for m, h in zip(mean, half)],
            "run_id": run.get("id"), "reference": reference, "slope": b1,
            "label": BAND_LABEL}


def depth_options(data: dict[str, Any], measures: dict[str, dict[str, float]] | None = None) -> dict[str, str]:
    """key -> label for the 3D depth axis; categorical lanes are labelled as such."""
    first = data["labels"][0] if data["labels"] else "first occasion"
    options = {BASELINE: f"Baseline at {first} ({data['unit']}) · continuous"}
    options.update({name: f"{name} · continuous" for name in (measures or {})})
    options[LANES] = "Athlete lanes · categorical, ordered by baseline"
    return options


def depth_values(data: dict[str, Any], key: str,
                 measures: dict[str, dict[str, float]] | None = None) -> dict[str, float | None]:
    """athlete id -> depth value (None = missing); lanes are rank positions 0..n-1."""
    baseline = {a["id"]: a["values"][0] if a["values"] else None for a in data["athletes"]}
    if key == BASELINE:
        return baseline
    if key == LANES:
        order = sorted(data["athletes"], key=lambda a: (baseline[a["id"]] is None, baseline[a["id"]] or 0, a["label"]))
        return {a["id"]: float(i) for i, a in enumerate(order)}
    values = (measures or {}).get(key, {})
    return {a["id"]: values.get(a["id"]) for a in data["athletes"]}


def _finite(values: list[float | None]) -> list[float]:
    return [v for v in values if v is not None and math.isfinite(v)]


def _nice_ticks(low: float, high: float, count: int = 4) -> list[float]:
    if high <= low:
        return [low]
    step = 10 ** math.floor(math.log10((high - low) / count))
    step *= next(m for m in (1, 2, 2.5, 5, 10) if (high - low) / (step * m) <= count)
    first = math.ceil(low / step) * step
    return [round(first + i * step, 10) for i in range(int((high - first) / step) + 1)]


def _qcolor(hex_value: str, alpha: float = 1.0) -> QColor:
    colour = QColor(hex_value)
    colour.setAlphaF(alpha)
    return colour


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


# --------------------------------------------------------------------------- #
# 2D trajectories
# --------------------------------------------------------------------------- #


class TrajectoryPlot(QWidget):
    """Athlete × occasion values; hover shows a point, click selects an athlete.

    ``set_data(explore, run=None)`` takes a ``DynamisAppService.explore_longitudinal`` result and
    optionally a recorded METH-REAL-TREND run (fitted mean + band in cobalt).
    """

    athlete_selected = Signal(str)  # subject id, "" when cleared

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data: dict[str, Any] | None = None
        self.model: dict[str, Any] | None = None
        self.selected: str | None = None
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._theme = theme.current_theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QHBoxLayout()
        self.title = _label("", "BlockHeading")
        header.addWidget(self.title, 1)
        self.obs_chip = theme.chip("Observed", "obs")
        self.mod_chip = theme.chip("Modeled", "mod")
        header.addWidget(self.obs_chip)
        header.addWidget(self.mod_chip)
        layout.addLayout(header)
        self.plot = pg.PlotWidget()
        self.plot.setAccessibleName("Trajectory plot")
        self.plot.setMinimumHeight(260)
        self.plot.setMenuEnabled(False)
        layout.addWidget(self.plot, 1)
        self.hover = pg.TextItem(anchor=(0, 1))
        self.model_note = _label("", "BlockNote")
        self.missing_note = _label("", "MissingNote")
        layout.addWidget(self.model_note)
        layout.addWidget(self.missing_note)
        self.plot.scene().sigMouseMoved.connect(self._hover)
        self.plot.scene().sigMouseClicked.connect(self._click)

    # -- API ----------------------------------------------------------------
    def set_data(self, explore: dict[str, Any], run: dict[str, Any] | None = None) -> None:
        self.data = observed(explore)
        self.run = run
        self.model = model_band(run, self.data["xs"], self.data["outcome"]) if self.data["raw"] else None
        self._render()

    def select_athlete(self, subject_id: str | None) -> None:
        self.selected = subject_id or None
        self._restyle()

    def nearest(self, scene_pos, radius: float = 10.0) -> tuple[str, int] | None:
        """(athlete id, occasion index) of the observed point within ``radius`` px of ``scene_pos``."""
        if not self.data:
            return None
        box = self.plot.getPlotItem().vb
        best, best_d = None, radius
        for athlete in self.data["athletes"]:
            for i, (x, y) in enumerate(zip(self.data["xs"], athlete["values"])):
                if y is None:
                    continue
                point = box.mapViewToScene(pg.Point(x, y))
                d = math.hypot(point.x() - scene_pos.x(), point.y() - scene_pos.y())
                if d <= best_d:
                    best, best_d = (athlete["id"], i), d
        return best

    def describe_point(self, athlete_id: str, index: int) -> str:
        athlete = next(a for a in self.data["athletes"] if a["id"] == athlete_id)
        value = athlete["values"][index]
        shown = "missing · not imputed" if value is None else f"{value:.1f} {self.data['unit']} (observed)"
        return f"{athlete['label']} · {self.data['labels'][index]} · {shown}"

    # -- drawing ------------------------------------------------------------
    def _render(self) -> None:
        t = theme.tokens()
        self._theme = theme.current_theme()
        data = self.data
        item = self.plot.getPlotItem()
        item.clear()
        self.plot.setBackground(t["base"])
        for name in ("left", "bottom"):
            axis = item.getAxis(name)
            axis.setPen(pg.mkPen(t["line2"]))
            axis.setTextPen(pg.mkPen(t["muted"]))
        item.showGrid(x=False, y=True, alpha=0.25)
        item.getAxis("bottom").setTicks([list(zip(data["xs"], data["labels"]))])
        item.setXRange(min(data["xs"]) - 0.25, max(data["xs"]) + 0.25, padding=0)
        item.setLabel("left", f"{data['title']} ({data['unit']})" if data["raw"] else data["scale"], color=t["muted"])
        legend = item.legend or item.addLegend(offset=(10, 6), labelTextSize="8pt")
        legend.clear()
        legend.setLabelTextColor(t["muted"])
        self.title.setText(f"{data['title']} by athlete and occasion · {data['scale']}")
        self._curves = {}
        nan = float("nan")
        for athlete in data["athletes"]:
            ys = [nan if v is None else v for v in athlete["values"]]
            curve = item.plot(data["xs"], ys, connect="finite", symbol="o", symbolSize=5)
            self._curves[athlete["id"]] = curve
        if data["athletes"]:
            legend.addItem(self._curves[data["athletes"][0]["id"]], "Observed · one line per athlete")
        self.mod_chip.setVisible(self.model is not None)
        if self.model:
            edge = pg.mkPen(_qcolor(t["mod"], 0.5), width=1)
            # the edge curves must live in the plot: a FillBetweenItem over unowned curves crashes on paint
            low = item.plot(data["xs"], self.model["low"], pen=edge)
            high = item.plot(data["xs"], self.model["high"], pen=edge)
            band = pg.FillBetweenItem(low, high, brush=pg.mkBrush(_qcolor(t["mod"], 0.18)))
            item.addItem(band)
            mean = item.plot(data["xs"], self.model["mean"], pen=pg.mkPen(t["mod"], width=2.5))
            mean.setZValue(10)
            legend.addItem(mean, f"Fitted mean · {self.model['run_id']}")
            legend.addItem(low, self.model["label"])
            slope = self.model["slope"]
            self.model_note.setText(
                f"Modeled: fixed-effect mean from recorded run {self.model['run_id']} (slope "
                f"{slope['estimate']:+.3f} {data['unit']}/occasion, 95% CI {slope['ci_low']:.3f} to {slope['ci_high']:.3f}). "
                f"{BAND_LABEL}: runs do not record the intercept-slope covariance, so the band bounds it and is "
                "wider than the model interval.")
        elif self.run is not None:
            self.model_note.setText("The supplied run is not a recorded mixed-model run for this outcome on the observed "
                                    "scale; no modeled values are shown.")
        else:
            self.model_note.setText("")
        self.model_note.setVisible(bool(self.model_note.text()))
        gaps = [f"{label}: {len(names)} missing ({', '.join(names)})"
                for label, names in zip(data["labels"], data["missing"]) if names]
        self.missing_note.setText(("Missing · not imputed — " + "; ".join(gaps)) if gaps else "No missing athlete-occasions.")
        self.missing_note.setStyleSheet(f"color: {t['bad_text' if gaps else 'dim_text']};")
        for x, names in zip(data["xs"], data["missing"]):
            if names:  # red dash on the axis floor marks the occasion with missing values
                floor = min(_finite([v for a in data["athletes"] for v in a["values"]]) or [0])
                mark = pg.TextItem(f"— {len(names)} missing", color=t["bad_text"], anchor=(0.5, 0))
                mark.setPos(x, floor)
                item.addItem(mark)
        item.addItem(self.hover, ignoreBounds=True)
        self.hover.setColor(t["text"])
        self.hover.hide()
        self._restyle()

    def _restyle(self) -> None:
        if not self.data:
            return
        t = theme.tokens()
        for athlete_id, curve in self._curves.items():
            chosen = athlete_id == self.selected
            alpha = 1.0 if chosen or self.selected is None else 0.18
            alpha = 0.55 if self.selected is None else alpha
            colour = _qcolor(t["obs"], alpha)
            curve.setPen(pg.mkPen(colour, width=2.6 if chosen else 1.1))
            curve.setSymbolPen(pg.mkPen(colour))
            curve.setSymbolBrush(pg.mkBrush(colour))
            curve.setSymbolSize(7 if chosen else 5)
            curve.setZValue(20 if chosen else 1)

    def _hover(self, pos) -> None:
        hit = self.nearest(pos)
        if hit is None:
            self.hover.hide()
            return
        athlete_id, index = hit
        self.hover.setText(self.describe_point(athlete_id, index))
        athlete = next(a for a in self.data["athletes"] if a["id"] == athlete_id)
        self.hover.setPos(self.data["xs"][index], athlete["values"][index])
        self.hover.show()

    def _click(self, event) -> None:
        hit = self.nearest(event.scenePos())
        self.select_athlete(hit[0] if hit else None)
        self.athlete_selected.emit(self.selected or "")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.PaletteChange and self.data and theme.current_theme() != self._theme:
            self._render()


# --------------------------------------------------------------------------- #
# 3D trajectories
# --------------------------------------------------------------------------- #

SPAN = {"x": 10.0, "depth": 8.0, "y": 6.0}  # scene units for occasion, depth and outcome
PRESETS = {"Front": (0.0, -90.0), "Side": (0.0, 0.0), "3D": (20.0, -68.0)}  # (elevation, azimuth) degrees
ELEVATION = (math.degrees(-0.1), math.degrees(1.35))  # 06-interactions: pitch clamped -0.1 .. 1.35 rad
ZOOM = (0.6, 2.2)
DISTANCE = 14.0  # fills the pane (E5-3d-dark); 21 left the scene at 40 % of the view


def _gl():
    """pyqtgraph.opengl, or None when PyOpenGL / OpenGL is unavailable."""
    try:
        import pyqtgraph.opengl as gl
    except Exception:  # noqa: BLE001 - ImportError without PyOpenGL; RuntimeError on broken drivers
        return None
    return gl


def _view_class(gl):
    class ClampedView(gl.GLViewWidget):
        """GLViewWidget with the 06-interactions pitch and zoom limits."""

        def orbit(self, azim, elev):
            super().orbit(azim, elev)
            self.opts["elevation"] = min(max(self.opts["elevation"], ELEVATION[0]), ELEVATION[1])

        def wheelEvent(self, event):
            super().wheelEvent(event)
            self.opts["distance"] = min(max(self.opts["distance"], DISTANCE / ZOOM[1]), DISTANCE / ZOOM[0])
            self.update()

    return ClampedView


class Trajectory3D(QWidget):
    """Occasion × outcome × a continuous athlete measure (or labelled categorical lanes).

    ``set_data(explore, run=None, measures=None)``: ``measures`` maps a label to
    {subject id: value} for extra continuous depth axes (e.g. body mass from the subjects table).
    Controls: layer toggles, Front / Side / 3D presets (eased 250 ms), reset, depth-axis choice.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data: dict[str, Any] | None = None
        self.model: dict[str, Any] | None = None
        self.measures: dict[str, dict[str, float]] = {}
        self.selected: str | None = None
        self.depth_key = BASELINE
        self._theme = theme.current_theme()
        self._items: list[Any] = []
        self._layers: dict[str, list[Any]] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        header = QHBoxLayout()
        self.title = _label("3D trajectories", "BlockHeading")
        header.addWidget(self.title, 1)
        self.obs_chip = theme.chip("Observed", "obs")
        self.mod_chip = theme.chip("Modeled", "mod")
        header.addWidget(self.obs_chip)
        header.addWidget(self.mod_chip)
        layout.addLayout(header)
        controls = QHBoxLayout()
        controls.setSpacing(4)
        self.layer_buttons: dict[str, QPushButton] = {}
        for key, text in (("observed", "Observed"), ("model", "Model surface"), ("lines", "Athlete lines")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(True)
            button.toggled.connect(self._apply_layers)
            self.layer_buttons[key] = button
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        controls = QHBoxLayout()  # second row: the controls do not fit one row of the 551 px Results pane
        controls.setSpacing(4)
        controls.addWidget(QLabel("Depth"))
        self.depth_combo = QComboBox()
        self.depth_combo.setAccessibleName("Depth axis")
        self.depth_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.depth_combo.setMinimumContentsLength(14)
        self.depth_combo.currentIndexChanged.connect(self._depth_changed)
        controls.addWidget(self.depth_combo, 1)
        self.preset_group = QButtonGroup(self)
        for name in PRESETS:
            button = QPushButton(name)
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, n=name: self.set_view(n))
            self.preset_group.addButton(button)
            controls.addWidget(button)
        reset = QPushButton("Reset")
        reset.setToolTip("Reset rotation and zoom to the 3D preset")
        reset.clicked.connect(lambda: self.set_view("3D"))
        controls.addWidget(reset)
        layout.addLayout(controls)
        gl = _gl()
        self.gl = gl
        self.view = None
        if gl is not None:
            try:
                self.view = _view_class(gl)()
            except Exception:  # noqa: BLE001 - no usable OpenGL context
                self.view = None
        if self.view is None:
            self.view_fallback = _label(
                "3D view unavailable: OpenGL (PyOpenGL) could not be initialised on this machine. "
                "The 2D trajectory plot shows the same observed values.", "PaneEmpty")
            self.view_fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.view_fallback.setMinimumHeight(320)
            layout.addWidget(self.view_fallback, 1)
            for widget in (*self.layer_buttons.values(), self.depth_combo, *self.preset_group.buttons(), reset):
                widget.setEnabled(False)
        else:
            self.view.setMinimumHeight(360)
            self.view.setAccessibleName("3D trajectories view")
            layout.addWidget(self.view, 1)
            self.set_view("3D", animate=False)
        self.hint = _label("Drag to rotate · scroll to zoom · Front / Side / 3D presets", "BlockNote")
        self.missing_note = _label("", "MissingNote")
        layout.addWidget(self.hint)
        layout.addWidget(self.missing_note)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(250)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._step)

    @property
    def available(self) -> bool:
        return self.view is not None

    # -- API ----------------------------------------------------------------
    def set_data(self, explore: dict[str, Any], run: dict[str, Any] | None = None,
                 measures: dict[str, dict[str, float]] | None = None) -> None:
        self.data = observed(explore)
        self.model = model_band(run, self.data["xs"], self.data["outcome"]) if self.data["raw"] else None
        self.measures = dict(measures or {})
        options = depth_options(self.data, self.measures)
        self.depth_combo.blockSignals(True)
        self.depth_combo.clear()
        for key, text in options.items():
            self.depth_combo.addItem(text, key)
        self.depth_combo.setCurrentIndex(max(0, self.depth_combo.findData(self.depth_key)))
        self.depth_key = self.depth_combo.currentData()
        self.depth_combo.blockSignals(False)
        self.layer_buttons["model"].setEnabled(self.available and self.model is not None)
        self.hint.setText("Drag to rotate · scroll to zoom · Front / Side / 3D presets" + (
            f"\nModel surface: fitted mean from {self.model['run_id']}; faint surfaces: {BAND_LABEL.lower()}."
            if self.model else ""))
        self._render()

    def set_depth(self, key: str) -> None:
        index = self.depth_combo.findData(key)
        if index < 0:
            raise ValueError(f"Unknown depth axis {key!r}")
        self.depth_combo.setCurrentIndex(index)

    def select_athlete(self, subject_id: str | None) -> None:
        self.selected = subject_id or None
        self._render()

    def set_view(self, name: str, animate: bool = True) -> None:
        elevation, azimuth = PRESETS[name]
        for button in self.preset_group.buttons():
            button.setChecked(button.text() == name)
        if self.view is None:
            return
        target = (elevation, azimuth, DISTANCE)
        if not animate:
            self._set_camera(*target)
            return
        start = (self.view.opts["elevation"], self.view.opts["azimuth"], self.view.opts["distance"])
        self._animation.stop()
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._tween = (start, target)
        self._animation.start()

    def camera(self) -> tuple[float, float, float] | None:
        return None if self.view is None else (self.view.opts["elevation"], self.view.opts["azimuth"],
                                               self.view.opts["distance"])

    # -- internals ----------------------------------------------------------
    def _step(self, value) -> None:
        (e0, a0, d0), (e1, a1, d1) = self._tween
        da = (a1 - a0 + 180) % 360 - 180  # shortest way round
        self._set_camera(e0 + (e1 - e0) * value, a0 + da * value, d0 + (d1 - d0) * value)

    def _set_camera(self, elevation: float, azimuth: float, distance: float) -> None:
        center = pg.Vector(SPAN["x"] / 2, SPAN["depth"] / 2, SPAN["y"] * 0.3)
        self.view.setCameraPosition(pos=center, distance=distance, elevation=elevation, azimuth=azimuth)

    def _depth_changed(self) -> None:
        self.depth_key = self.depth_combo.currentData() or BASELINE
        if self.data:
            self._render()

    def _apply_layers(self) -> None:
        for key, items in self._layers.items():
            visible = self.layer_buttons[key].isChecked()
            for item in items:
                item.setVisible(visible)

    def _render(self) -> None:
        if self.data is None:
            return
        t = theme.tokens()
        self._theme = theme.current_theme()
        data = self.data
        depth = depth_values(data, self.depth_key, self.measures)
        lanes = self.depth_key == LANES
        self.mod_chip.setVisible(self.model is not None)
        label = self.depth_combo.currentText() or ""
        self.title.setText(f"3D trajectories · occasion × {data['title']} × {label.split(' · ')[0]}")
        skipped = sorted(a["label"] for a in data["athletes"] if depth.get(a["id"]) is None)
        gaps = [f"{lab}: {', '.join(names)}" for lab, names in zip(data["labels"], data["missing"]) if names]
        parts = []
        if gaps:
            parts.append("Missing athlete-occasions (not imputed) — " + "; ".join(gaps))
        if skipped:
            parts.append(f"No depth value, not placed: {', '.join(skipped)}")
        self.missing_note.setText(" · ".join(parts) or "No missing athlete-occasions.")
        self.missing_note.setStyleSheet(f"color: {t['bad_text' if parts else 'dim_text']};")
        if self.view is None:
            return
        gl = self.gl
        for item in self._items:
            self.view.removeItem(item)
        self._items, self._layers = [], {"observed": [], "model": [], "lines": []}
        self.view.setBackgroundColor(t["base"])

        values = _finite([v for a in data["athletes"] for v in a["values"]]
                         + (self.model["low"] + self.model["high"] if self.model else []))
        y_ticks = _nice_ticks(min(values), max(values)) if values else [0.0]
        y_lo, y_hi = min(values + y_ticks), max(values + y_ticks)
        d_values = _finite(list(depth.values()))
        d_lo, d_hi = (min(d_values), max(d_values)) if d_values else (0.0, 1.0)
        x_lo, x_hi = min(data["xs"]), max(data["xs"])

        def sx(v): return (v - x_lo) / (x_hi - x_lo) * SPAN["x"] if x_hi > x_lo else SPAN["x"] / 2
        def sd(v): return (v - d_lo) / (d_hi - d_lo) * SPAN["depth"] if d_hi > d_lo else SPAN["depth"] / 2
        def sy(v): return (v - y_lo) / (y_hi - y_lo) * SPAN["y"] if y_hi > y_lo else SPAN["y"] / 2

        def add(item, layer: str | None = None):
            self.view.addItem(item)
            self._items.append(item)
            if layer:
                self._layers[layer].append(item)
            return item

        def rgba(key, alpha=1.0):
            return pg.mkColor(t[key]).getRgbF()[:3] + (alpha,)

        font = QFont(theme.SANS, 8)

        def text(pos, value, colour="muted"):
            add(gl.GLTextItem(pos=pos, text=value, color=QColor(t[colour]), font=font))

        # floor grid and axes
        grid = []
        for x in data["xs"]:
            grid += [(sx(x), 0, 0), (sx(x), SPAN["depth"], 0)]
        for v in y_ticks:
            grid += [(0, SPAN["depth"], sy(v)), (SPAN["x"], SPAN["depth"], sy(v))]
        add(gl.GLLinePlotItem(pos=grid, mode="lines", color=rgba("line2", 0.7), width=1, antialias=True))
        axes = [(0, 0, 0), (SPAN["x"], 0, 0), (0, 0, 0), (0, SPAN["depth"], 0), (0, 0, 0), (0, 0, SPAN["y"])]
        add(gl.GLLinePlotItem(pos=axes, mode="lines", color=rgba("dim"), width=1.5, antialias=True))
        for x, lab in zip(data["xs"], data["labels"]):
            text((sx(x), -0.6, 0), lab)
        text((SPAN["x"] / 2, -1.6, 0), "Occasion", "text")
        for v in y_ticks:
            text((-0.4, 0, sy(v)), f"{v:g}")
        text((-0.4, 0, SPAN["y"] + 0.6), f"{data['title']} ({data['unit']})", "text")
        if lanes:
            every = max(1, math.ceil(len(data["athletes"]) / 10))  # thin labels so lanes stay legible
            for athlete in data["athletes"]:
                if depth.get(athlete["id"]) is not None and (int(depth[athlete["id"]]) % every == 0
                                                             or athlete["id"] == self.selected):
                    text((SPAN["x"] + 0.3, sd(depth[athlete["id"]]), 0), athlete["label"], "dim_text")
            text((SPAN["x"] + 0.3, SPAN["depth"] + 0.8, 0), "Athlete lanes (categorical · spacing has no meaning)", "text")
        else:
            for v in _nice_ticks(d_lo, d_hi, 3):
                text((SPAN["x"] + 0.3, sd(v), 0), f"{v:g}")
            text((SPAN["x"] + 0.3, SPAN["depth"] + 0.8, 0), label.split(" · ")[0], "text")

        # observed points and athlete lines (graphite)
        points, selected_points = [], []
        for athlete in data["athletes"]:
            d = depth.get(athlete["id"])
            if d is None:
                continue
            chosen = athlete["id"] == self.selected
            segment: list[tuple[float, float, float]] = []
            for x, v in zip(data["xs"] + [None], athlete["values"] + [None]):
                if v is None:  # break the line at a missing occasion
                    if len(segment) > 1:
                        alpha = 1.0 if chosen else (0.25 if self.selected else 0.45)
                        add(gl.GLLinePlotItem(pos=segment, color=rgba("obs", alpha), width=3 if chosen else 1,
                                              antialias=True), "lines")
                    segment = []
                    continue
                p = (sx(x), sd(d), sy(v))
                segment.append(p)
                (selected_points if chosen else points).append(p)
        if points:
            alpha = 0.35 if self.selected else 0.9
            add(gl.GLScatterPlotItem(pos=points, color=rgba("obs", alpha), size=7, pxMode=True, glOptions="translucent"), "observed")
        if selected_points:
            add(gl.GLScatterPlotItem(pos=selected_points, color=rgba("obs"), size=11, pxMode=True, glOptions="translucent"), "observed")

        # modeled fixed-effect mean (cobalt) and its band, flat across depth (no depth term in the model)
        if self.model:
            for key, alpha in (("mean", 0.28), ("low", 0.1), ("high", 0.1)):
                verts, faces = [], []
                for i, (x, v) in enumerate(zip(data["xs"], self.model[key])):
                    verts += [(sx(x), 0, sy(v)), (sx(x), SPAN["depth"], sy(v))]
                    if i:
                        a = 2 * i
                        faces += [(a - 2, a - 1, a), (a - 1, a + 1, a)]
                mesh = gl.MeshData(vertexes=_array(verts), faces=_array(faces, int))
                add(gl.GLMeshItem(meshdata=mesh, color=rgba("mod", alpha), smooth=False, drawEdges=False,
                                  glOptions="translucent"), "model")
            edge = [(sx(x), 0, sy(v)) for x, v in zip(data["xs"], self.model["mean"])]
            add(gl.GLLinePlotItem(pos=edge, color=rgba("mod"), width=2.5, antialias=True), "model")
        self._apply_layers()
        if self.model is None:
            self.layer_buttons["model"].setChecked(False)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.PaletteChange and self.data and theme.current_theme() != self._theme:
            self._render()


def _array(values, dtype=float):
    import numpy as np

    return np.asarray(values, dtype=dtype)


__all__ = ["Trajectory3D", "TrajectoryPlot", "depth_options", "depth_values", "model_band", "observed"]
