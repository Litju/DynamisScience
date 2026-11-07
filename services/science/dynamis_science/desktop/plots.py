"""Matplotlib views and provenance-bearing scientific figure exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QWidget, QVBoxLayout


def longitudinal_figure(exploration: dict[str, Any], provenance: dict[str, Any]) -> Figure:
    metric = exploration.get("metric", {})
    unit = exploration.get("unit") or metric.get("unit") or ""
    figure = Figure(figsize=(7, 4), constrained_layout=True)
    axis = figure.subplots()
    summary = exploration.get("summary", [])
    x = [row.get("week", row.get("occasion", index + 1)) for index, row in enumerate(summary)]
    y = [row.get("mean") for row in summary]
    axis.plot(x, y, marker="o", color="#176b87", label="Cohort mean")
    lower = [row.get("ci_low") for row in summary]
    upper = [row.get("ci_high") for row in summary]
    if summary and all(value is not None for value in [*lower, *upper]):
        axis.fill_between(x, lower, upper, color="#176b87", alpha=0.18, label="95% interval")
    axis.set_title(metric.get("label", "Longitudinal results"))
    axis.set_xlabel(exploration.get("method", {}).get("axis_label", "Testing occasion"))
    axis.set_ylabel(f"{metric.get('label', 'Estimate')} ({unit})" if unit else metric.get("label", "Estimate"))
    axis.grid(True, alpha=0.25)
    if summary:
        axis.legend(frameon=False)
    figure._dynamis_metadata = {"DynamisScience provenance": json.dumps(provenance, sort_keys=True, default=str)}
    return figure


def run_figure(run: dict[str, Any]) -> Figure:
    result = run.get("result", {})
    data = run.get("figure_data") or {}
    figure = Figure(figsize=(7, 4), constrained_layout=True)
    diagnostics = run.get("diagnostics", {})
    qq = diagnostics.get("residual_qq") or []
    cv = result.get("cv_percent_by_subject") or []
    agreement = result.get("body_weight", {}).get("rows") or []
    has_secondary = bool(qq or cv or agreement)
    axes = figure.subplots(1, 2) if qq or (not data and has_secondary) else [figure.subplots()]
    axis = axes[0]
    diagnostic_axis = axes[1] if len(axes) > 1 else None
    kind = data.get("kind")
    if kind == "LINE" and data.get("series"):
        series = data["series"]
        x = [point.get("week", index + 1) for index, point in enumerate(series)]
        y = [point.get("mean") for point in series]
        axis.plot(x, y, marker="o", color="#176b87", label="Mean")
        low = [point.get("ci_low") for point in series]
        high = [point.get("ci_high") for point in series]
        if all(value is not None for value in [*low, *high]):
            axis.fill_between(x, low, high, alpha=0.18, color="#176b87", label="95% interval")
        axis.set_xlabel("Testing occasion / activity")
        axis.set_ylabel(data.get("unit", "Estimate"))
        axis.legend(frameon=False)
    elif kind == "SCATTER" and data.get("points"):
        points = data["points"]
        axis.scatter([item["baseline"] for item in points], [item["change"] for item in points], color="#176b87")
        axis.axhline(0, color="#777", linewidth=0.8)
        axis.set_xlabel("Baseline")
        axis.set_ylabel(f"Change ({data.get('unit', '')})")
    elif kind == "DISTRIBUTION" and data.get("values"):
        axis.boxplot(data["values"], vert=True, labels=[data.get("unit", "Values")])
        axis.set_ylabel(data.get("unit", "Values"))
    else:
        series = result.get("activities") or result.get("occasions") or []
        rows = [row for row in series if row.get("mean", row.get("peak_fz_mean_n")) is not None]
        if rows:
            x = [row.get("occasion", row.get("activity", index + 1)) for index, row in enumerate(rows)]
            y = [row.get("mean", row.get("peak_fz_mean_n")) for row in rows]
            errors = [row.get("sd", row.get("peak_fz_sd_n")) for row in rows]
            if all(value is not None for value in errors):
                axis.errorbar(x, y, yerr=errors, marker="o", color="#176b87", capsize=3)
                axis.set_ylabel(f"{run.get('outcome_metric_id', 'Estimate')} (mean ± SD)")
            else:
                axis.plot(x, y, marker="o", color="#176b87")
                axis.set_ylabel(run.get("outcome_metric_id", "Estimate"))
            axis.set_xlabel("Testing occasion / activity")
        else:
            contrasts = result.get("contrasts", {})
            contrast = contrasts.get(result.get("primary_contrast_id"), {})
            if not contrast and contrasts:
                contrast = next(iter(contrasts.values()))
            estimate = contrast.get("estimate")
            lower = contrast.get("ci_low")
            upper = contrast.get("ci_high")
            if estimate is not None and lower is not None and upper is not None:
                axis.errorbar(
                    [0],
                    [estimate],
                    yerr=[[estimate - lower], [upper - estimate]],
                    fmt="o",
                    color="#176b87",
                    capsize=4,
                )
                axis.axhline(0, color="#777", linewidth=0.8)
                axis.set_xticks([0], [contrast.get("contrast", "Primary contrast")])
                axis.set_ylabel(contrast.get("unit", run.get("outcome_metric_id", "Estimate")))
            elif result.get("icc_3_1") is not None:
                axis.errorbar(
                    [0],
                    [result["icc_3_1"]],
                    yerr=[[
                        result["icc_3_1"] - result["icc_3_1_ci_low"]
                    ], [result["icc_3_1_ci_high"] - result["icc_3_1"]]],
                    fmt="o",
                    color="#176b87",
                    capsize=4,
                )
                axis.axhline(0, color="#777", linewidth=0.8)
                axis.set_xticks([0], ["ICC(3,1)"])
                axis.set_ylabel("Intraclass correlation")
                axis.set_ylim(-1, 1)
            elif result.get("cv_percent_by_subject"):
                cv = result["cv_percent_by_subject"]
                axis.plot([item["subject_id"] for item in cv], [item["cv_percent"] for item in cv], marker="o", color="#176b87")
                axis.tick_params(axis="x", labelrotation=45)
                axis.set_ylabel("Within-subject CV (%)")
            else:
                axis.text(0.5, 0.5, "No plot data supplied by this analysis", ha="center", va="center", transform=axis.transAxes)
                axis.set_axis_off()
    axis.set_title(
        "Model-implied estimate" if result.get("contrasts") else result.get("method", run.get("method_id", "Scientific result"))
    )
    axis.grid(True, alpha=0.25)
    if diagnostic_axis is not None:
        if qq:
            diagnostic_axis.scatter(
                [item["theoretical"] for item in qq],
                [item["observed"] for item in qq],
                s=18,
                color="#176b87",
            )
            bounds = [
                min(min(item["theoretical"], item["observed"]) for item in qq),
                max(max(item["theoretical"], item["observed"]) for item in qq),
            ]
            diagnostic_axis.plot(bounds, bounds, color="#777", linewidth=0.8)
            diagnostic_axis.set_title("Residual Q–Q diagnostic")
            diagnostic_axis.set_xlabel("Theoretical normal quantile")
            diagnostic_axis.set_ylabel("Standardized residual")
        elif cv:
            diagnostic_axis.plot(
                [item["subject_id"] for item in cv],
                [item["cv_percent"] for item in cv],
                marker="o",
                color="#c07139",
            )
            diagnostic_axis.tick_params(axis="x", labelrotation=45)
            diagnostic_axis.set_title("Within-subject variation")
            diagnostic_axis.set_xlabel("Participant")
            diagnostic_axis.set_ylabel("CV (%)")
        else:
            pairs = agreement
            means = [
                (item["support_window_mean_n"] + item["metadata_weight_n"]) / 2
                for item in pairs
            ]
            differences = [item["difference_n"] for item in pairs]
            diagnostic_axis.scatter(means, differences, s=18, color="#c07139")
            body = result["body_weight"]
            for value, style, label in (
                (body.get("bias_n"), "-", "Bias"),
                (body.get("loa_low_n"), "--", "95% limits"),
                (body.get("loa_high_n"), "--", None),
            ):
                if value is not None:
                    diagnostic_axis.axhline(value, linestyle=style, linewidth=0.9, label=label)
            diagnostic_axis.set_title("Metadata comparison · not a validated measure")
            diagnostic_axis.set_xlabel("Mean support force and metadata weight (N)")
            diagnostic_axis.set_ylabel("Difference (N)")
            diagnostic_axis.legend(frameon=False)
        diagnostic_axis.grid(True, alpha=0.25)
    provenance = {
        "run_id": run.get("id"),
        "study_id": run.get("study_id"),
        "snapshot_id": run.get("snapshot_id"),
        "cohort_id": run.get("cohort_id"),
        "result_digest": run.get("result_digest"),
    }
    figure._dynamis_metadata = {"DynamisScience provenance": json.dumps(provenance, sort_keys=True, default=str)}
    return figure


def export_figure(figure: Figure, path: str | Path, dpi: int = 300) -> Path:
    target = Path(path).expanduser().resolve()
    if target.suffix.lower() not in {".png", ".pdf", ".svg"}:
        raise ValueError("Scientific figures can be exported as PNG, PDF or SVG")
    if not 72 <= int(dpi) <= 1200:
        raise ValueError("dpi must be between 72 and 1200")
    provenance = getattr(figure, "_dynamis_metadata", {}).get("DynamisScience provenance", "{}")
    metadata: dict[str, str]
    if target.suffix.lower() == ".png":
        metadata = {"Software": "DynamisScience", "Description": provenance}
    elif target.suffix.lower() == ".pdf":
        metadata = {"Creator": "DynamisScience", "Subject": provenance}
    else:
        metadata = {"Creator": "DynamisScience", "Description": provenance}
    target.parent.mkdir(parents=True, exist_ok=True)
    previous_canvas = figure.canvas
    FigureCanvasAgg(figure)
    try:
        figure.savefig(target, dpi=dpi, metadata=metadata, bbox_inches="tight")
    finally:
        figure.set_canvas(previous_canvas)
    return target


class ScientificFigureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(7, 4), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def show_figure(self, source: Figure) -> None:
        layout = self.layout()
        layout.removeWidget(self.canvas)
        self.canvas.setParent(None)
        self.figure = source
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas)
        self.canvas.draw_idle()
