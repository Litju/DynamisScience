"""Publication figures for workbench result blocks (Matplotlib, no Qt).

Every value plotted comes from a recorded analysis run (``run["result"]`` /
``run["diagnostics"]``) or from observed snapshot rows the caller passes in.
Colour semantics follow spec E rule 1: observed = graphite (``obs``), modeled =
cobalt (``mod``) and always drawn with its interval. Export goes through
``plots.export_figure`` so PNG/PDF/SVG carry the run provenance metadata.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from matplotlib import rc_context
from matplotlib.figure import Figure

from .. import theme
from ..plots import export_figure

FORMATS = ("png", "pdf", "svg")


def _style(figure: Figure, t: dict[str, str]) -> None:
    figure.set_facecolor(t["base"])
    for axis in figure.axes:
        axis.set_facecolor(t["base"])
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            axis.spines[side].set_color(t["line2"])
        axis.tick_params(colors=t["muted"], labelsize=8)
        axis.xaxis.label.set_color(t["muted"])
        axis.yaxis.label.set_color(t["muted"])
        axis.xaxis.label.set_size(8)
        axis.yaxis.label.set_size(8)
        for title in (axis.title, axis._left_title):  # set_title(loc="left") draws _left_title
            title.set_color(t["text"])
            title.set_size(9)
        axis.grid(True, color=t["line"], linewidth=0.6)
        axis.set_axisbelow(True)


def _new(t: dict[str, str], ncols: int = 1, width: float = 7.2, height: float = 3.0) -> tuple[Figure, list]:
    figure = Figure(figsize=(width, height), dpi=100, constrained_layout=True)
    axes = figure.subplots(1, ncols)
    return figure, list(axes) if ncols > 1 else [axes]


def provenance(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "study_id": run.get("study_id"),
        "snapshot_id": run.get("snapshot_id"),
        "cohort_id": run.get("cohort_id"),
        "method_id": run.get("method_id"),
        "method_version": run.get("method_version"),
        "method_status": run.get("method_status"),
        "result_digest": run.get("result_digest"),
    }


def provenance_footer(run: dict[str, Any]) -> str:
    """One line printed on exported figures: run id, method, method-version state (CURRENT or SUPERSEDED) and result digest."""
    status = (run.get("method_status") or {}).get("state", "UNKNOWN")
    version = run.get("method_version") or (run.get("method_status") or {}).get("computed_with") or "version not recorded"
    return (f"Run {run.get('id')} · {run.get('method_id')} {version} · method version {status} · "
            f"result digest {str(run.get('result_digest') or '')[:8]}")


def _finish(figure: Figure, run: dict[str, Any], t: dict[str, str]) -> Figure:
    _style(figure, t)
    status = run.get("method_status") or {}
    if status.get("state") == "SUPERSEDED":
        figure.suptitle(
            f"SUPERSEDED · {run.get('method_id')} {status.get('computed_with')} → {status.get('current_version')}"
            " · audit only, not current evidence",
            color=t["bad"], fontsize=8, fontweight="bold",
        )
    figure._dynamis_metadata = {"DynamisScience provenance": json.dumps(provenance(run), sort_keys=True, default=str)}
    figure._dynamis_footer = provenance_footer(run)
    return figure


# --------------------------------------------------------------------------- #
# Mixed model
# --------------------------------------------------------------------------- #


def trajectory_figure(run: dict[str, Any], observed: list[dict[str, Any]] | None = None,
                      theme_name: str | None = None) -> Figure:
    """Model-implied within-athlete change from the reference occasion (cobalt, Wald 95% band)
    with observed per-athlete change (graphite) when snapshot rows are supplied."""
    t = theme.tokens(theme_name)
    result = run["result"]
    slope = result["coefficients"]["occasion_slope"]
    reference = int(result["reference_occasion"])
    occasions = result["diagnostics"]["sample_context"]["weeks_observed"]
    unit = result.get("unit", "")
    figure, (axis,) = _new(t)
    missing = 0
    if observed:
        outcome = result["outcome"]
        by_subject: dict[str, dict[int, float]] = {}
        for row in observed:
            if row.get(outcome) is not None:
                by_subject.setdefault(str(row["subject_id"]), {})[int(row["occasion"])] = float(row[outcome])
        for values in by_subject.values():
            missing += sum(1 for occasion in occasions if occasion not in values)
            if reference not in values:
                continue
            xs = [o for o in occasions if o in values]
            axis.plot(xs, [values[o] - values[reference] for o in xs], color=t["obs"], alpha=0.28,
                      linewidth=0.8, marker="o", markersize=2.5)
        axis.plot([], [], color=t["obs"], alpha=0.5, marker="o", markersize=3, linewidth=0.8,
                  label="Observed change per athlete")
    elapsed = [o - reference for o in occasions]
    axis.fill_between(occasions, [slope["ci_low"] * e for e in elapsed], [slope["ci_high"] * e for e in elapsed],
                      color=t["mod"], alpha=0.16, linewidth=0, label="Wald 95% CI (slope)")
    axis.plot(occasions, [slope["estimate"] * e for e in elapsed], color=t["mod"], linewidth=2,
              label=f"Model-implied change ({slope['estimate']:+.3f} {unit}/occasion)")
    axis.axhline(0, color=t["line2"], linewidth=0.8)
    axis.set_xticks(occasions)
    axis.set_xlabel("Testing occasion")
    axis.set_ylabel(f"Change from occasion {reference} ({unit})")
    axis.set_title("Within-athlete change · fixed occasion slope", loc="left")
    if missing:
        axis.text(0.99, 0.02, f"{missing} athlete-occasions missing · not imputed", transform=axis.transAxes,
                  ha="right", va="bottom", fontsize=7, color=t["bad_text"])
    axis.legend(frameon=False, fontsize=7, loc="upper left", labelcolor=t["muted"])
    return _finish(figure, run, t)


def residual_figure(run: dict[str, Any], theme_name: str | None = None) -> Figure:
    """Conditional Pearson residuals by occasion and their normal Q-Q (both exploratory)."""
    t = theme.tokens(theme_name)
    diagnostics = run.get("diagnostics") or {}
    figure, (left, right) = _new(t, 2)
    qq_type = diagnostics.get("residual_qq_type")
    residuals = diagnostics.get("conditional_residuals") or []
    sigma = math.sqrt((run["result"].get("random_effects") or {}).get("residual_variance") or float("nan"))
    if residuals and qq_type == "CONDITIONAL_PEARSON" and math.isfinite(sigma):
        xs = [item["occasion"] for item in residuals]
        subjects = sorted({item["subject_id"] for item in residuals})  # deterministic jitter per athlete
        jitter = [((subjects.index(item["subject_id"]) % 11) - 5) * 0.025 for item in residuals]
        left.scatter([x + j for x, j in zip(xs, jitter)], [item["residual"] / sigma for item in residuals],
                     s=10, color=t["obs"], alpha=0.75, linewidths=0)
        left.axhline(0, color=t["line2"], linewidth=0.8)
        left.set_xticks(sorted(set(xs)))
        left.set_xlabel("Testing occasion")
        left.set_ylabel("(y − Xβ̂ − Zb̂) / σ̂")
        left.set_title("Conditional Pearson residual · EXPLORATORY", loc="left")
    else:
        left.text(0.5, 0.5, "Conditional residuals not recorded for this run", ha="center", va="center",
                  transform=left.transAxes, fontsize=8, color=t["dim_text"])
        left.set_axis_off()
    qq = diagnostics.get("residual_qq") or []
    if qq:
        theoretical = [item["theoretical"] for item in qq]
        right.scatter(theoretical, [item["observed"] for item in qq], s=10, color=t["obs"], alpha=0.75, linewidths=0)
        if qq_type == "CONDITIONAL_PEARSON":
            bounds = [min(theoretical), max(theoretical)]
            right.plot(bounds, bounds, color=t["muted"], linewidth=0.8, label="N(0, 1) reference")
            right.legend(frameon=False, fontsize=7, loc="upper left", labelcolor=t["muted"])
            right.set_title("Normal Q–Q · EXPLORATORY", loc="left")
            right.set_ylabel("Observed quantile")
        else:  # legacy runs: never relabel a residual whose definition was not recorded
            right.set_title("Residual Q–Q · residual type not recorded (legacy run)", loc="left")
            right.set_ylabel("Residual (definition not recorded)")
        right.set_xlabel("Theoretical normal quantile")
    else:
        right.set_axis_off()
    return _finish(figure, run, t)


# --------------------------------------------------------------------------- #
# Reliability
# --------------------------------------------------------------------------- #


def reliability_figure(run: dict[str, Any], theme_name: str | None = None) -> Figure:
    """ICC(3,1) with its Shrout-Fleiss CI (modeled) beside within-participant CV% (observed)."""
    t = theme.tokens(theme_name)
    result = run["result"]
    figure, (left, right) = _new(t, 2)
    rows = [("ICC(3,1)", result.get("icc_3_1"), result.get("icc_3_1_ci_low"), result.get("icc_3_1_ci_high"))]
    rows += [(label, result.get(key), None, None) for label, key in
             (("ICC(2,1) sensitivity", "icc_2_1_sensitivity"), ("ICC(1,1) sensitivity", "icc_1_1_sensitivity"))]
    rows = [row for row in rows if row[1] is not None]
    for index, (label, value, low, high) in enumerate(rows):
        y = len(rows) - 1 - index
        if low is not None and high is not None and math.isfinite(high):
            left.errorbar([value], [y], xerr=[[value - low], [high - value]], fmt="o", color=t["mod"],
                          capsize=3, markersize=5, linewidth=1.6)
            left.annotate(f"{value:.3f} [{low:.3f}, {high:.3f}]", (value, y), xytext=(0, 7),
                          textcoords="offset points", ha="center", fontsize=7, color=t["mod_text"])
        else:  # sensitivities are point estimates only; never imply an interval
            left.plot([value], [y], marker="o", markerfacecolor="none", color=t["mod"], markersize=5)
            left.annotate(f"{value:.3f}", (value, y), xytext=(0, 7), textcoords="offset points", ha="center",
                          fontsize=7, color=t["mod_text"])
    left.set_yticks(range(len(rows)), [row[0] for row in reversed(rows)])
    left.set_xlim(max(0.0, min((row[2] if row[2] is not None else row[1]) for row in rows) - 0.1), 1.0)
    left.set_ylim(-0.6, len(rows) - 0.4)
    left.set_xlabel("Intraclass correlation")
    left.set_title("ICC · Shrout–Fleiss 95% CI", loc="left")
    cv = result.get("cv_percent_by_subject") or []
    right.plot([item["subject_id"] for item in cv], [item["cv_percent"] for item in cv], marker="o",
               linestyle="none", color=t["obs"], markersize=4)
    if result.get("mean_cv_percent") is not None:
        right.axhline(result["mean_cv_percent"], color=t["muted"], linewidth=0.8, linestyle="--",
                      label=f"Mean CV {result['mean_cv_percent']:.1f}%")
        right.legend(frameon=False, fontsize=7, labelcolor=t["muted"])
    right.tick_params(axis="x", labelrotation=45)
    right.set_xlabel("Participant (analysed cohort)")
    right.set_ylabel("Within-participant CV (%)")
    right.set_title("Observed trial-to-trial CV", loc="left")
    return _finish(figure, run, t)


# --------------------------------------------------------------------------- #


def figures_for_run(run: dict[str, Any], observed: list[dict[str, Any]] | None = None,
                    theme_name: str | None = None) -> list[tuple[str, Figure]]:
    """(key, figure) pairs for a run; empty for methods without a figure here."""
    method = run.get("method_id")
    if method == "METH-REAL-TREND" and "coefficients" in (run.get("result") or {}):
        return [("trajectory", trajectory_figure(run, observed, theme_name)),
                ("residuals", residual_figure(run, theme_name))]
    if method == "METH-REAL-RELIABILITY" and (run.get("result") or {}).get("icc_3_1") is not None:
        return [("reliability", reliability_figure(run, theme_name))]
    return []


def export(figure: Figure, path: str | Path, fmt: str | None = None, dpi: int = 300) -> Path:
    target = Path(path)
    fmt = (fmt or target.suffix.lstrip(".")).lower()
    if fmt not in FORMATS:
        raise ValueError("Figures export as PNG, PDF or SVG")
    footer = getattr(figure, "_dynamis_footer", "")
    engine = figure.get_layout_engine()
    layout = dict(engine.get()) if footer and engine is not None else None
    artist = None
    if footer:  # printed on the figure face (not only metadata); the layout leaves a strip for it
        strip = 0.28 / figure.get_figheight()
        if engine is not None:
            engine.set(rect=(0, strip, 1, 1 - strip))
        artist = figure.text(0.01, 0.1 / figure.get_figheight(), footer, fontsize=6.5, ha="left", va="bottom",
                             color=theme.tokens("light")["muted"])
    try:
        # Keep text as text so SVG/PDF figures stay searchable and editable in journals' tools.
        with rc_context({"svg.fonttype": "none", "pdf.fonttype": 42}):
            return export_figure(figure, target.with_suffix(f".{fmt}"), dpi=dpi)
    finally:
        if artist is not None:
            artist.remove()
            if layout is not None:
                engine.set(**layout)
