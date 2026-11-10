"""Descriptive result blocks: Descriptives, Frequencies and Athlete change (observed claims).

Values are summarised with pandas from the rows ``DynamisAppService.read_table_page``
returns. The registered methods do not cover these tables: METH-REAL-DESC gives only
mean / SD / t-interval per occasion (no median, IQR, min, max or missing counts) and
METH-U-CHANGE is not applicable to the real-data studies, so nothing here duplicates an
existing qualified computation and no model is fitted. Every block is an observed,
descriptive claim and is never promotable (spec E rules 1-3). Missing values are counted
and shown in red; nothing is imputed (rule 5).
"""

from __future__ import annotations

import html
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from matplotlib.figure import Figure

from .. import theme
from .spec import DEFAULTS, descriptives_syntax
from .figures import _style
from .results import ResultBlock, _table

MAX_ROWS = 50_000
NOT_PROMOTABLE = "Descriptive summaries are observed claims and are never promoted to evidence"
DESCRIPTIVE_STATE = {"label": "Descriptive", "kind": "descriptive", "reason": NOT_PROMOTABLE}


# --------------------------------------------------------------------------- #
# Data (no Qt)
# --------------------------------------------------------------------------- #


def load_table(service: Any, snapshot_id: str, table: str, max_rows: int = MAX_ROWS) -> pd.DataFrame:
    """All rows of a snapshot table via ``read_table_page`` (500 per page)."""
    page = service.read_table_page(snapshot_id, table, 0, 500)
    if page["total_rows"] > max_rows:
        raise ValueError(f"{table} has {page['total_rows']:,} rows; descriptives are limited to {max_rows:,}")
    rows = list(page["rows"])
    while len(rows) < page["total_rows"]:
        rows += service.read_table_page(snapshot_id, table, len(rows), 500)["rows"]
    return pd.DataFrame(rows, columns=page["columns"])


def describe(frame: pd.DataFrame, variables: list[str], by: str | None = None,
             subject: str | None = None) -> pd.DataFrame:
    """n, missing, mean, SD, median, IQR, min, max, 95 % t-interval of the mean per variable (and per ``by`` level).

    With ``by`` and ``subject``, missing counts athletes absent at that level as well as null
    values, so an athlete-occasion row that was never recorded is still counted.
    """
    groups = [(None, frame)] if by is None else list(frame.groupby(by, sort=True, dropna=False))
    expected = frame[subject].nunique() if by is not None and subject else None
    out = []
    for variable in variables:
        for level, part in groups:
            values = pd.to_numeric(part[variable], errors="coerce")
            valid = values.dropna()
            if expected is not None:
                missing = expected - part.loc[values.notna(), subject].nunique()
            else:
                missing = int(values.isna().sum())
            half = stats.t.ppf(0.975, len(valid) - 1) * valid.std(ddof=1) / math.sqrt(len(valid)) if len(valid) > 1 else math.nan
            q1, q3 = (valid.quantile(0.25), valid.quantile(0.75)) if len(valid) else (math.nan, math.nan)
            out.append({
                "variable": variable, "group": level, "n": len(valid), "missing": int(missing),
                "mean": valid.mean() if len(valid) else math.nan,
                "sd": valid.std(ddof=1) if len(valid) > 1 else math.nan,
                "median": valid.median() if len(valid) else math.nan, "iqr": q3 - q1,
                "min": valid.min() if len(valid) else math.nan, "max": valid.max() if len(valid) else math.nan,
                "ci_low": valid.mean() - half if len(valid) > 1 else math.nan,
                "ci_high": valid.mean() + half if len(valid) > 1 else math.nan,
            })
    return pd.DataFrame(out)


def frequencies(frame: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    """Count and percent of rows per level; a Missing level is always listed (count may be 0)."""
    out = []
    for variable in variables:
        column = frame[variable]
        counts = column.dropna().astype(str).value_counts().sort_index()
        total = len(column)
        for level, count in counts.items():
            out.append({"variable": variable, "level": level, "count": int(count), "percent": 100 * count / total})
        missing = int(column.isna().sum())
        out.append({"variable": variable, "level": "Missing", "count": missing,
                    "percent": 100 * missing / total if total else math.nan})
    return pd.DataFrame(out)


def athlete_change(frame: pd.DataFrame, outcome: str, subject: str, occasion: str, from_level: Any,
                   to_level: Any, swc: float | None = None) -> pd.DataFrame:
    """Per-athlete change ``end - start`` (columns subject, start, end, change, percent, status); athletes missing either occasion keep a NaN change.

    Repeated rows at one occasion are averaged within the athlete. ``swc`` (a user-entered
    smallest worthwhile change, not a qualified threshold) only labels the status column.
    """
    values = frame.assign(_v=pd.to_numeric(frame[outcome], errors="coerce"))
    wide = values.pivot_table(index=subject, columns=occasion, values="_v", aggfunc="mean")
    wide = wide.reindex(index=sorted(frame[subject].dropna().unique()))
    start = wide[from_level] if from_level in wide.columns else pd.Series(math.nan, index=wide.index)
    end = wide[to_level] if to_level in wide.columns else pd.Series(math.nan, index=wide.index)
    out = pd.DataFrame({"subject": wide.index, "start": start.to_numpy(), "end": end.to_numpy()})
    out["change"] = out["end"] - out["start"]
    out["percent"] = out["change"] / out["start"] * 100

    def status(row) -> str:
        gaps = [str(level) for level, value in ((from_level, row["start"]), (to_level, row["end"])) if pd.isna(value)]
        if gaps:
            return f"missing at {' and '.join(gaps)}"
        if swc is None:
            return "no threshold"
        return "above SWC" if row["change"] > swc else "below −SWC" if row["change"] < -swc else "within SWC"

    out["status"] = out.apply(status, axis=1)
    return out


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #


def _num(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)) or pd.isna(value):
        return _missing()
    return f"{value:,.{digits}f}".replace("-", "−")


def _missing(text: str = "—") -> str:
    return f'<span style="color: {theme.tokens()["bad_text"]};">{text}</span>'


def _count(value: int) -> str:
    return _missing(str(value)) if value else "0"


def _lit(value: Any) -> str:
    """Python literal for a level (numpy scalars print as plain numbers, not ``np.int64(4)``)."""
    return repr(value.item() if hasattr(value, "item") else value)


def _level(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return html.escape(str(value))


class DescriptiveBlock(ResultBlock):
    """A ResultBlock with the observed claim chip, provenance and a non-promotable footer.

    ``provenance``: {"source": "real" | "synthetic", "snapshot_id": str, "table": str}.
    """

    promotable = False

    def __init__(self, title: str, provenance: dict[str, Any], frame: pd.DataFrame, syntax: str,
                 limits: str, subtitle: str = "") -> None:
        super().__init__(title, [("Observed", "obs")], provenance.get("source") or "real", subtitle)
        self.provenance = provenance
        self.syntax = syntax
        self.set_note(limits)
        self.set_footer(DESCRIPTIVE_STATE, "Not a recorded run · computed live with pandas · " + syntax,
                        f"Source {provenance.get('snapshot_id', '—')} · table {provenance.get('table', '—')} · "
                        f"{len(frame):,} rows", False)

    def promote(self) -> None:
        return None


class DescriptivesBlock(DescriptiveBlock):
    """Descriptive statistics per variable, optionally split by a categorical/ordinal column."""

    def __init__(self, frame: pd.DataFrame, variables: list[str], by: str | None = None,
                 subject: str | None = None, provenance: dict[str, Any] | None = None,
                 units: dict[str, str] | None = None, options: dict[str, Any] | None = None) -> None:
        self.table = describe(frame, variables, by, subject)
        units = units or {}
        o = {**DEFAULTS["descriptives"], **(options or {})}
        syntax = descriptives_syntax(variables, by, o)
        super().__init__("Descriptives", provenance or {}, frame, syntax,
                         "Descriptive only. No inference. Missing athlete-occasions are counted, never imputed.")
        self.heading("Descriptive statistics")
        # columns follow the Statistics options; every value stays in self.table
        spec = [("stat_n_missing", ["N", "Missing"], ("n", "missing")), ("stat_mean_sd", ["Mean", "SD"], ("mean", "sd")),
                ("stat_median_iqr", ["Median", "IQR"], ("median", "iqr")), ("stat_min_max", ["Min", "Max"], ("min", "max")),
                ("stat_ci", ["95% CI low", "95% CI high"], ("ci_low", "ci_high"))]
        chosen = [(heads, keys) for flag, heads, keys in spec if o[flag]]
        headers = ["Variable"] + ([by.capitalize()] if by else []) + [h for heads, _ in chosen for h in heads]
        rows = []
        for row in self.table.itertuples():
            first = row.variable if row.Index == 0 or self.table.variable[row.Index - 1] != row.variable else ""
            name = f"<b>{html.escape(first)}</b>" + (f" ({html.escape(units[first])})" if first in units else "")
            cells = []
            for _, keys in chosen:
                for key in keys:
                    value = getattr(row, key)
                    cells.append(str(value) if key == "n" else _count(value) if key == "missing" else _num(value))
            rows.append([name] + ([_level(row.group)] if by else []) + cells)
        self.rich(_table(headers, rows, numeric_from=2 if by else 1))
        unit = units.get(variables[0], "")
        if o["plot_box"]:
            self.figure(box_figure(frame, variables[0], by, unit), 260)
            self.rich(f"{html.escape(variables[0])}{f' by {html.escape(by)}' if by else ''}. Box: median and IQR; "
                      "whiskers 1.5 × IQR; dots: observations.")
        if o["plot_hist"]:
            self.figure(hist_figure(frame, variables[0], by, unit), 260)
            self.rich(f"{html.escape(variables[0])}{f' by {html.escape(by)}' if by else ''}. Histogram of observed values.")


class FrequenciesBlock(DescriptiveBlock):
    """Counts and percent of rows per level for categorical / ordinal variables."""

    def __init__(self, frame: pd.DataFrame, variables: list[str], provenance: dict[str, Any] | None = None) -> None:
        self.table = frequencies(frame, variables)
        columns = ", ".join(f'"{v}"' for v in variables)
        super().__init__("Frequencies", provenance or {}, frame,
                         f"data[[{columns}]].apply(lambda c: c.value_counts(dropna=False))",
                         "Counts of rows, not athletes. Missing is always listed, even when zero.")
        for variable in variables:
            part = self.table[self.table.variable == variable]
            self.heading(variable)
            rows = [[_missing("Missing") if r.level == "Missing" and r.count else html.escape(r.level),
                     _count(r.count) if r.level == "Missing" else str(r.count), _num(r.percent, 1)]
                    for r in part.itertuples()]
            self.rich(_table(["Level", "Count", "Percent"], rows))


class AthleteChangeBlock(DescriptiveBlock):
    """Per-athlete observed change between two occasions, sorted by change."""

    def __init__(self, frame: pd.DataFrame, outcome: str, subject: str, occasion: str, from_level: Any,
                 to_level: Any, provenance: dict[str, Any] | None = None, swc: float | None = None,
                 unit: str = "", labels: dict[str, str] | None = None, sort: bool = True) -> None:
        self.table = athlete_change(frame, outcome, subject, occasion, from_level, to_level, swc)
        labels = labels or {}
        if swc is None:
            limits = (f"Observed change only. No qualified noise threshold exists for {outcome}, so no athlete is "
                      "classified as changed. Enter a smallest worthwhile change in the options to classify.")
        else:
            limits = (f"Classified against a user-entered smallest worthwhile change of {swc:g} {unit}; this is not a "
                      "qualified threshold. Repeated rows per occasion are averaged within athlete.")
        super().__init__(f"Change in {outcome}: {_level(from_level)} → {_level(to_level)}", provenance or {}, frame,
                         f'wide[{_lit(to_level)}] - wide[{_lit(from_level)}]  # wide = data.pivot_table("{outcome}", '
                         f'"{subject}", "{occasion}")', limits)
        valid = self.table.dropna(subset=["change"])
        if sort:
            self.table = pd.concat([valid.sort_values("change", ascending=False),
                                    self.table[self.table.change.isna()]])
        missing = self.table[self.table.change.isna()]
        mean = valid.change.mean() if len(valid) else math.nan
        self.rich(f"{len(valid)} athletes with both occasions · mean change {_num(mean)} {html.escape(unit)} · "
                  f"SD {_num(valid.change.std(ddof=1) if len(valid) > 1 else math.nan)} · "
                  f"missing {_count(len(missing))}")
        self.figure(change_figure(self.table, labels, unit), max(180, 16 * len(self.table) + 60))
        self.heading("Per athlete")
        rows = [[html.escape(labels.get(r.subject, str(r.subject))), _num(r.start, 1), _num(r.end, 1),
                 f"<b>{_num(r.change, 1)}</b>", _num(r.percent, 1),
                 _missing(r.status) if r.status.startswith("missing") else html.escape(r.status)]
                for r in self.table.itertuples()]
        self.rich(_table(["Athlete", _level(from_level), _level(to_level), "Change", "%", "Status"], rows))


# --------------------------------------------------------------------------- #
# Figures (Matplotlib, exportable like figures.py)
# --------------------------------------------------------------------------- #


def box_figure(frame: pd.DataFrame, variable: str, by: str | None, unit: str = "", theme_name: str | None = None) -> Figure:
    t = theme.tokens(theme_name)
    figure = Figure(figsize=(7.2, 2.6), dpi=100, constrained_layout=True)
    axis = figure.subplots()
    values = frame.assign(_v=pd.to_numeric(frame[variable], errors="coerce"))
    if by is None:
        values, by = values.assign(_all="All"), "_all"
    levels = sorted(values[by].dropna().unique())
    data = [values.loc[values[by] == level, "_v"].dropna().to_numpy() for level in levels]
    positions = list(range(len(levels)))
    axis.boxplot(data, positions=positions, widths=0.32, whis=1.5, showfliers=False, patch_artist=True,
                 boxprops={"facecolor": t["base"], "edgecolor": t["obs"]}, medianprops={"color": t["obs"]},
                 whiskerprops={"color": t["obs"]}, capprops={"color": t["obs"]})
    for x, sample in zip(positions, data):
        jitter = [0.26 + ((i * 7) % 11) * 0.012 for i in range(len(sample))]  # deterministic offset to the right
        axis.scatter([x + j for j in jitter], sample, s=7, color=t["obs"], alpha=0.75, linewidths=0)
    axis.set_xticks(positions, [_level(level) for level in levels])
    axis.set_xlabel("" if by == "_all" else by)
    axis.set_ylabel(f"{variable} ({unit})" if unit else variable)
    _style(figure, t)
    return figure


def hist_figure(frame: pd.DataFrame, variable: str, by: str | None, unit: str = "", theme_name: str | None = None) -> Figure:
    t = theme.tokens(theme_name)
    figure = Figure(figsize=(7.2, 2.6), dpi=100, constrained_layout=True)
    axis = figure.subplots()
    values = pd.to_numeric(frame[variable], errors="coerce")
    bins = np.histogram_bin_edges(values.dropna(), bins="auto") if values.notna().any() else 10
    parts = [(None, values)] if by is None else [(lvl, values[frame[by] == lvl]) for lvl in sorted(frame[by].dropna().unique())]
    for level, part in parts:
        axis.hist(part.dropna(), bins=bins, alpha=0.9 if by is None else 0.45, color=t["obs"],
                  label=None if level is None else _level(level))
    if by is not None:
        axis.legend(frameon=False, fontsize=7, title=by, title_fontsize=7)
    axis.set_xlabel(f"{variable} ({unit})" if unit else variable)
    axis.set_ylabel("Count")
    _style(figure, t)
    return figure


def change_figure(table: pd.DataFrame, labels: dict[str, str], unit: str = "", theme_name: str | None = None) -> Figure:
    t = theme.tokens(theme_name)
    height = max(1.8, 0.16 * len(table) + 0.6)
    figure = Figure(figsize=(7.2, height), dpi=100, constrained_layout=True)
    axis = figure.subplots()
    names = [labels.get(s, str(s)) for s in table.subject]
    ys = list(range(len(table)))[::-1]
    changes = table.change.to_numpy()
    for y, change, name in zip(ys, changes, names):
        if pd.isna(change):
            axis.text(0, y, "— missing", color=t["bad_text"], fontsize=7, va="center", ha="left")
            continue
        axis.barh(y, change, height=0.62, color=t["obs"])
        axis.text(change, y, f" {change:+.1f}".replace("-", "−"), color=t["muted"], fontsize=7, va="center",
                  ha="left" if change >= 0 else "right")
    axis.set_yticks(ys, names)
    axis.axvline(0, color=t["line2"], linewidth=0.8)
    axis.set_xlabel(f"Change ({unit})" if unit else "Change")
    _style(figure, t)
    axis.tick_params(axis="y", labelsize=7)
    axis.grid(False, axis="y")
    return figure


__all__ = [
    "AthleteChangeBlock",
    "DescriptiveBlock",
    "DescriptivesBlock",
    "FrequenciesBlock",
    "athlete_change",
    "box_figure",
    "change_figure",
    "describe",
    "frequencies",
    "hist_figure",
    "load_table",
]
