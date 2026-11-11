"""Results document for the RES-620 workbench (spec E, rules 1-5).

``ResultsDocument`` renders a recorded analysis run as result blocks. Each block has a
claim chip, a provenance chip, a limits note and a footer with method status · run ·
digest. Every number comes from the run record returned by
``DynamisAppService.execute_analysis_isolated``; nothing is recomputed here except
display arithmetic (Wald z / p from the recorded estimate and SE, SD from a variance).

Integration (main window / controller)::

    doc = ResultsDocument(service)
    shell.set_results_widget(doc)
    run_analysis(service, spec.study_id, spec, runner, lambda run: doc.show_run(run, spec))
    doc.check_spec(current_spec)          # dims dependent blocks when the hash differs
    shell.action_promote.triggered.connect(doc.promote)
    shell.action_add_to_report.triggered.connect(doc.add_to_report)
    shell.set_provenance(**doc.provenance_args())
"""

from __future__ import annotations

import html
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ... import researchstore
from .. import theme
from . import figures
from .spec import NOT_QUALIFIED, AnalysisSpec, method_status

ENGINE_KINDS = ("mixed_model", "reliability")
DESCRIPTIVE_KINDS = ("descriptives", "frequencies", "athlete_change")
STALE_OPACITY = 0.42


# --------------------------------------------------------------------------- #
# Status and formatting helpers (pure; unit-tested)
# --------------------------------------------------------------------------- #


def run_method_state(run: dict[str, Any]) -> dict[str, Any]:
    """Method-axis chip for a run: qualification from researchstore.METHODS, supersession from the run.

    Returns {"kind", "label", "promotable", "reason", "record"}.
    """
    meta = researchstore.METHODS.get(str(run.get("method_id")), {})
    qualification = (meta.get("qualification") or {}).get("status")
    status = run.get("method_status") or researchstore.method_status(run)
    record = (meta.get("qualification") or {}).get("record")
    if status.get("state") == "SUPERSEDED":
        return {"kind": "superseded", "label": "superseded", "promotable": False, "record": record,
                "reason": f"Computed with {run.get('method_id')} {status.get('computed_with')}, superseded by "
                          f"{status.get('current_version')}: {status.get('reason', '')}"}
    if status.get("state") != "CURRENT":
        return {"kind": "not_qualified", "label": "unverified method", "promotable": False, "record": record,
                "reason": status.get("reason", "Method version is not verified.")}
    if run.get("status") != "COMPLETED" or (run.get("result") or {}).get("status") == "INSUFFICIENT_DATA":
        return {"kind": "unavailable", "label": "no result", "promotable": False, "record": record,
                "reason": (run.get("result") or {}).get("message") or "The run produced no estimable result."}
    if qualification == "QUALIFIED":
        return {"kind": "qualified", "label": "qualified", "promotable": True, "record": record, "reason": ""}
    if qualification == "QUALIFIED_DESCRIPTIVE":
        return {"kind": "descriptive", "label": "descriptive", "promotable": False, "record": record,
                "reason": "Descriptive method; not promoted as a modeled claim."}
    return {"kind": "not_qualified", "label": "not qualified", "promotable": False, "record": record,
            "reason": "Method is not qualified; exploratory only."}


def estimation_of(formula: str) -> str:
    """Estimation as recorded in the run formula ('..., ML' or '..., REML')."""
    tail = formula.rsplit(",", 1)[-1].strip().upper() if "," in formula else ""
    return tail if tail in ("ML", "REML") else "not recorded"


def wald(estimate: float, se: float) -> tuple[float | None, float | None]:
    if not se or not math.isfinite(se):
        return None, None
    z = estimate / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def _f(value: Any, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    return f"{value:,.{digits}f}".replace("-", "−")


def _p(value: float | None) -> str:
    if value is None:
        return "—"
    return "&lt; .001" if value < 0.001 else f"{value:.3f}".lstrip("0")


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #


def _label(text: str, name: str, rich: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _table(headers: list[str], rows: list[list[str]], numeric_from: int = 1) -> str:
    """A publication table (top / header / bottom rules) as Qt rich text."""
    t = theme.tokens()
    rule = f"border-bottom: 1px solid {t['text']};"

    def cell(tag: str, text: str, index: int, extra: str = "") -> str:
        align = "right" if index >= numeric_from else "left"
        return f'<{tag} align="{align}" style="padding: 3px 6px; {extra}">{text}</{tag}>'

    head = "".join(cell("th", html.escape(h), i, rule) for i, h in enumerate(headers))
    body = []
    for r, row in enumerate(rows):
        extra = rule if r == len(rows) - 1 else ""
        body.append("<tr>" + "".join(cell("td", c, i, extra) for i, c in enumerate(row)) + "</tr>")
    return (f'<table cellspacing="0" style="border-top: 1.5px solid {t["text"]}; color: {t["text"]};">'
            f"<tr>{head}</tr>{''.join(body)}</table>")


class ResultBlock(QFrame):
    """Title + claim/provenance chips, body, limits note and provenance footer."""

    promote_clicked = Signal()

    def __init__(self, title: str, claims: list[tuple[str, str]], provenance: str | None,
                 subtitle: str = "", dependent: bool = True) -> None:
        super().__init__()
        self.setObjectName("ResultBlock")
        self.dependent = dependent  # dimmed when the specification changes
        self.figure_canvases: list[FigureCanvasQTAgg] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(6)
        self.title = _label(title, "BlockTitle")
        self.title.setWordWrap(False)
        header.addWidget(self.title)
        self.chips = [theme.chip(text, kind) for text, kind in claims]
        if provenance:
            self.chips.append(theme.chip(provenance, provenance))
        for widget in self.chips:
            header.addWidget(widget)
        header.addStretch(1)
        layout.addLayout(header)
        if subtitle:
            layout.addWidget(_label(subtitle, "BlockSubtitle"))
        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        layout.addLayout(self.body)
        self.note = _label("", "BlockNote")
        self.note.hide()
        layout.addWidget(self.note)
        self.footer = QFrame()
        self.footer.setObjectName("BlockFooter")
        self.footer.hide()
        layout.addWidget(self.footer)

    def heading(self, text: str) -> None:
        self.body.addWidget(_label(text, "BlockHeading"))

    def rich(self, text: str) -> QLabel:
        label = _label(text, "BlockText", rich=True)
        self.body.addWidget(label)
        return label

    def figure(self, figure, height: int) -> FigureCanvasQTAgg:
        canvas = FigureCanvasQTAgg(figure)
        canvas.setMinimumHeight(height)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body.addWidget(canvas)
        self.figure_canvases.append(canvas)
        return canvas

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def set_footer(self, state: dict[str, Any], run_text: str, source_text: str, promotable: bool) -> None:
        layout = QVBoxLayout(self.footer)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.method_chip = theme.chip(state["label"], state["kind"])
        row.addWidget(self.method_chip)
        self.run_text = _label(run_text, "FooterText")
        row.addWidget(self.run_text, 1)
        self.promote_button = QPushButton("Promote to evidence")
        self.promote_button.setObjectName("PromoteButton")
        self.promote_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.promote_button.setEnabled(promotable)
        self.promote_button.setToolTip("Promote this run to evidence" if promotable else
                                       (state.get("reason") or "Only qualified methods can be promoted to evidence"))
        self.promote_button.clicked.connect(self.promote_clicked)
        row.addWidget(self.promote_button)
        layout.addLayout(row)
        if source_text:
            layout.addWidget(_label(source_text, "FooterText"))
        self.footer.show()


class ResultsDocument(QScrollArea):
    """Vertical stack of result blocks for one run."""

    evidence_promoted = Signal(dict)
    report_cited = Signal(dict)
    action_failed = Signal(str)
    athlete_selected = Signal(str)  # from the trajectory views; "" when cleared

    def __init__(self, service: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.run: dict[str, Any] | None = None
        self.spec: AnalysisSpec | None = None
        self.observed: list[dict[str, Any]] | None = None
        self.explore: dict[str, Any] | None = None  # explore_longitudinal result for the trajectory views
        self.trajectory_mode = "2D"
        self.selected_athlete = ""
        self.trajectory_plot = self.trajectory_3d = None
        self._build: Callable[[], list[ResultBlock]] | None = None  # descriptive blocks, rebuilt on theme change
        self.run_spec_hash: str | None = None
        self.stale = False
        self.blocks: list[ResultBlock] = []
        self.state: dict[str, Any] = {"kind": "unavailable", "label": "", "promotable": False, "reason": ""}
        self._theme = theme.current_theme()
        self.setObjectName("ResultsDocument")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # a wide table scrolls, never clips
        self.setAccessibleName("Results document")
        canvas = QWidget()
        canvas.setObjectName("ResultsCanvas")
        self.column = QVBoxLayout(canvas)
        self.column.setContentsMargins(10, 12, 10, 12)  # at the 551 px design width tables must not clip
        self.column.setSpacing(14)
        self.superseded_bar = QFrame()
        self.superseded_bar.setObjectName("SupersededBar")
        bar = QHBoxLayout(self.superseded_bar)
        bar.setContentsMargins(14, 10, 14, 10)
        self.superseded_label = _label("", "SupersededText", rich=True)
        bar.addWidget(self.superseded_label)
        self.empty = _label("Run an analysis to see results here.", "PaneEmpty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for widget in (self.superseded_bar, self.empty):
            self.column.addWidget(widget)
        self.column.addStretch(1)
        self.superseded_bar.hide()
        self.setWidget(canvas)

    # -- public API ---------------------------------------------------------
    def clear(self) -> None:
        for block in self.blocks:
            for canvas in block.figure_canvases:
                canvas.figure.clear()
            block.setParent(None)
            block.deleteLater()
        self.blocks = []
        self.run = self.spec = self.observed = self.explore = None
        self.trajectory_plot = self.trajectory_3d = None
        self._build = None
        self.run_spec_hash = None
        self.state = {"kind": "unavailable", "label": "", "promotable": False, "reason": ""}
        self.superseded_bar.hide()
        self.mark_stale(False)
        self.empty.show()

    def show_run(self, run: dict[str, Any] | None, spec: AnalysisSpec | None = None,
                 observed: list[dict[str, Any]] | None = None, explore: dict[str, Any] | None = None) -> None:
        """Render ``run`` (a run record). ``spec`` sets the stale-detection hash; ``observed``
        (snapshot rows) adds the observed layer to the trajectory figure; ``explore``
        (``explore_longitudinal``) adds the interactive 2D / 3D trajectories to a mixed model."""
        if spec is not None and spec.kind not in ENGINE_KINDS:
            self.show_unavailable(spec)
            return
        self.clear()
        if run is None:
            return
        self.run, self.spec, self.observed, self.explore = run, spec, observed, explore
        self.run_spec_hash = spec.spec_hash() if spec is not None else None
        self.state = run_method_state(run)
        self.empty.hide()
        if self.state["kind"] == "superseded":
            evidence = ", ".join(run.get("evidence_ids") or [])
            self.superseded_label.setText(
                f"<b>Historical result · superseded method version.</b> {html.escape(self.state['reason'])} "
                f"{'Evidence ' + html.escape(evidence) + ' is superseded. ' if evidence else ''}"
                "Kept for audit; it cannot be promoted or newly cited. Re-run to obtain current evidence.")
            self.superseded_bar.show()
        method = run.get("method_id")
        if method == "METH-REAL-TREND" and "coefficients" in (run.get("result") or {}):
            self._mixed_model(run)
        elif method == "METH-REAL-RELIABILITY" and (run.get("result") or {}).get("icc_3_1") is not None:
            self._reliability(run)
        else:
            self._generic(run)

    def show_unavailable(self, spec: AnalysisSpec) -> None:
        """Not-qualified analyses (t-test, ANOVA, regression): stated, never promotable."""
        self.clear()
        self.spec = spec
        self.run_spec_hash = spec.spec_hash()
        status = method_status(spec.kind)
        self.state = {"kind": "not_qualified" if status["status"] == NOT_QUALIFIED else "unavailable",
                      "label": status["status"], "promotable": False,
                      "reason": "Not qualified: no engine run; cannot be promoted to evidence."}
        self.empty.hide()
        title = spec.kind.replace("_", " ").title().replace("Ttest", "T-Test").replace("Anova", "ANOVA")
        block = ResultBlock(title, [], None, dependent=False)
        if status["status"] == NOT_QUALIFIED:
            block.rich(f'<span style="color:{theme.tokens()["warn_text"]}"><b>Unavailable in the qualified engine.</b>'
                       "</span> This analysis has no independently qualified implementation, so DynamisScience does "
                       "not compute or report it as a result. The syntax bar shows an exploratory equivalent.")
            block.set_note("Limits: not qualified (RES-619 method matrix). Exploratory only; cannot be promoted to evidence.")
        else:
            block.rich("Descriptive analysis: it has no engine run in the results document.")
            block.set_note("Limits: descriptive only; not promoted as a modeled claim.")
        block.set_footer(self.state, "no run · no digest", "", False)
        self._add(block)

    def show_blocks(self, build: Callable[[], list[ResultBlock]], spec: AnalysisSpec | None,
                    state: dict[str, Any]) -> None:
        """Descriptive results: blocks made by ``build()`` (re-run on theme change). No run, never promotable."""
        self.clear()
        self.spec, self.state = spec, {**state, "promotable": False}
        self.run_spec_hash = spec.spec_hash() if spec is not None else None
        self.empty.hide()
        for block in build():
            self._add(block)
        self._build = build

    def select_athlete(self, subject_id: str) -> None:
        """Highlight ``subject_id`` in the trajectory views ("" clears)."""
        self.selected_athlete = subject_id or ""
        for view in (self.trajectory_plot, self.trajectory_3d):
            if view is not None and view.selected != (subject_id or None):
                view.select_athlete(subject_id or None)

    def set_trajectory_mode(self, mode: str) -> None:
        """``2D`` (pyqtgraph) or ``3D`` (pyqtgraph.opengl, created on first use)."""
        self.trajectory_mode = mode
        block = next((b for b in self.blocks if getattr(b, "trajectory_stack", None)), None)
        if block is None:
            return
        if mode == "3D" and self.trajectory_3d is None:
            from .interactive import Trajectory3D

            self.trajectory_3d = Trajectory3D()
            self.trajectory_3d.set_data(self.explore, self.run)
            self.trajectory_3d.select_athlete(self.selected_athlete or None)
            block.trajectory_stack.addWidget(self.trajectory_3d)
        block.trajectory_stack.setCurrentWidget(self.trajectory_3d if mode == "3D" else self.trajectory_plot)
        for button in block.trajectory_buttons.buttons():
            button.setChecked(button.text() == mode)

    def mark_stale(self, stale: bool) -> None:
        self.stale = bool(stale) and bool(self.blocks)
        for block in self.blocks:
            if block.dependent and self.stale:
                effect = QGraphicsOpacityEffect(block)
                effect.setOpacity(STALE_OPACITY)
                block.setGraphicsEffect(effect)
            else:
                block.setGraphicsEffect(None)
            if hasattr(block, "promote_button"):
                block.promote_button.setEnabled(self.promotable)

    def check_spec(self, spec: AnalysisSpec | None) -> bool:
        """Mark stale when ``spec`` no longer hashes to the spec the shown run was made with."""
        self.mark_stale(spec is not None and self.run_spec_hash is not None and spec.spec_hash() != self.run_spec_hash)
        return self.stale

    @property
    def promotable(self) -> bool:
        return bool(self.run) and self.state["promotable"] and not self.stale

    def provenance_args(self) -> dict[str, str]:
        """Keyword arguments for WorkbenchShell.set_provenance."""
        if not self.run:
            return {"method_status": self.state["kind"] if self.blocks else ""}
        return {"source": str(self.run.get("snapshot_id") or ""), "run": str(self.run.get("id") or ""),
                "digest": str(self.run.get("result_digest") or "")[:8], "method_status": self.state["kind"],
                "provenance": "real" if str(self.run.get("snapshot_id", "")).startswith("DS-REAL") else "synthetic"}

    def promote(self) -> dict[str, Any] | None:
        if not self.promotable:
            self.action_failed.emit(self.state.get("reason") or
                                    ("Rerun first: the specification changed" if self.stale else "Nothing to promote"))
            return None
        try:
            outcome = self.service.promote_run_to_evidence(self.run["id"])
        except Exception as error:  # service errors are reported, not raised into Qt
            self.action_failed.emit(str(error))
            return None
        self.run = {**self.run, "evidence_ids": [outcome["evidence_artifact"]["id"]]}
        self.evidence_promoted.emit(outcome)
        return outcome

    def add_to_report(self, section: str | None = None) -> list[dict[str, Any]] | None:
        """Promote (if needed) and cite the evidence and its figure in the study report."""
        outcome = self.promote()
        if outcome is None:
            return None
        cited = []
        try:
            for artifact in (outcome.get("evidence_artifact"), outcome.get("figure_artifact")):
                if artifact:
                    cited.append(self.service.cite_report_artifact(self.run["study_id"], artifact["id"], section))
        except Exception as error:
            self.action_failed.emit(str(error))
            return None
        for item in cited:
            self.report_cited.emit(item)
        return cited

    def export(self, path: str | Path, fmt: str | None = None, dpi: int = 300) -> list[Path]:
        """Export the run's figures as ``<stem>-<figure>.<fmt>`` (PNG, PDF or SVG; light theme)."""
        if not self.run:
            raise ValueError("No result to export")
        pairs = figures.figures_for_run(self.run, self.observed, "light")
        if not pairs:
            raise ValueError("This result has no exportable figure")
        path = Path(path)
        fmt = (fmt or path.suffix.lstrip(".") or "png").lower()
        return [figures.export(figure, path.with_name(f"{path.stem}-{key}"), fmt, dpi) for key, figure in pairs]

    # -- block builders -----------------------------------------------------
    def _add(self, block: ResultBlock) -> None:
        block.promote_clicked.connect(self.promote)
        self.column.insertWidget(self.column.count() - 1, block)
        self.blocks.append(block)

    def _footer(self, block: ResultBlock, run: dict[str, Any]) -> None:
        reproduced = run.get("reproduces") or []
        run_text = " · ".join(part for part in (
            f"{run.get('id')}",
            f"{run.get('method_id')} " + (run.get("method_version") or
                f"{(run.get('method_status') or {}).get('computed_with', '?')} (version not recorded on run)"),
            f"digest {str(run.get('result_digest') or '')[:8]}",
            f"reproduces {reproduced[-1]}" if reproduced else "",
        ) if part)
        cohort = ((run.get("execution") or {}).get("cohort") or {}).get("id") or run.get("cohort_id")
        source = " · ".join(part for part in (
            f"Source {run.get('snapshot_id')}", f"cohort {cohort}", f"spec {run.get('analysis_spec_id')}",
            f"{self.state.get('record')}" if self.state.get("record") else "",
            f"evidence {', '.join(run['evidence_ids'])}" if run.get("evidence_ids") else "",
        ) if part)
        block.set_footer(self.state, run_text, source, self.promotable)

    def _provenance(self, run: dict[str, Any]) -> str:
        return "real" if str(run.get("snapshot_id", "")).startswith("DS-REAL") else "synthetic"

    def _mixed_model(self, run: dict[str, Any]) -> None:
        t = theme.tokens()
        result, diagnostics = run["result"], run.get("diagnostics") or run["result"].get("diagnostics") or {}
        context = diagnostics.get("sample_context") or {}
        unit = result.get("unit", "")
        prov = self._provenance(run)
        block = ResultBlock("Linear Mixed Model", [("mod", "mod")], prov, result.get("formula", ""))
        block.heading("Model information")
        random = ("intercept + occasion slope | subject" if result.get("estimator") == "MIXEDLM_RANDOM_SLOPE"
                  else "intercept only | subject (documented fallback)")
        block.rich(_table(
            ["Estimation", "Random effects", "Observations", "Athletes", "Log-likelihood", "Optimizer"],
            [[estimation_of(result.get("formula", "")), random, str(result["n_observations"]),
              str(result["n_subjects"]), _f(result.get("log_likelihood"), 2),
              f"{result.get('optimizer') or '—'} · {'converged' if result.get('converged') else 'NOT converged'}"]],
            numeric_from=2))
        occasions = context.get("weeks_observed") or []
        slots = result["n_subjects"] * len(occasions)
        missing = slots - result["n_observations"]
        if occasions:
            colour = t["bad_text"] if missing else t["dim_text"]
            block.rich(f'<span style="color:{colour}">{"— " if missing else ""}{missing} of {slots} athlete-occasions '
                       f"missing · {html.escape(diagnostics.get('quality_note', 'complete case'))}</span>")
        block.heading("Fixed effects")
        rows = []
        for term, coefficient in result["coefficients"].items():
            z, p = wald(coefficient["estimate"], coefficient["std_error"])
            rows.append([term, f'<span style="color:{t["mod_text"]}">{_f(coefficient["estimate"])}</span>',
                         _f(coefficient["std_error"]), f"{_f(coefficient['ci_low'])} – {_f(coefficient['ci_high'])}",
                         _f(z, 2), _p(p)])
        block.rich(_table(["Term", "Estimate", "SE", "95% CI (Wald)", "z", "p"], rows))
        contrast_key = f"occasion_{result['reference_occasion']}_to_{result['contrast_occasion']}"
        contrast = result.get("contrasts", {}).get(contrast_key)
        if contrast:
            block.rich(_table(["Contrast", "Estimate", "SE", "95% CI (Wald)", "Effect size"],
                              [[html.escape(contrast["contrast"]),
                                f'<span style="color:{t["mod_text"]}">{_f(contrast["estimate"])} {unit}</span>',
                                _f(contrast["std_error"]), f"{_f(contrast['ci_low'])} – {_f(contrast['ci_high'])}",
                                _f(result.get("effect_size"), 2)]]))
        effects = result.get("random_effects") or {}
        if effects:
            block.heading("Variance components")
            iv, sv = effects.get("subject_intercept_variance"), effects.get("subject_slope_variance")
            cov, rv = effects.get("subject_intercept_slope_covariance"), effects.get("residual_variance")
            corr = cov / math.sqrt(iv * sv) if iv and sv else None
            block.rich(_table(["Component", "Variance", "SD"], [
                ["Athlete intercept", _f(iv), _f(math.sqrt(iv) if iv is not None else None)],
                ["Athlete occasion slope", _f(sv), _f(math.sqrt(sv) if sv is not None else None)],
                ["Intercept–slope correlation", "—", _f(corr)],
                ["Residual (σ̂²)", _f(rv), _f(math.sqrt(rv) if rv is not None else None)],
            ]))
        block.set_note(
            f"Note. Wald z 95% intervals from the {estimation_of(result.get('formula', ''))} fit; with "
            f"{result['n_subjects']} athletes they may be too narrow (no small-sample correction, RES-619). "
            f"Effect size: {result.get('effect_size_basis', 'not recorded')}. "
            + " ".join(diagnostics.get("limitations") or []))
        self._footer(block, run)
        self._add(block)

        figure_block = ResultBlock(
            "Estimated change by occasion",
            ([("obs", "obs")] if self.observed else []) + [("mod", "mod")], prov)
        figure_block.figure(figures.trajectory_figure(run, self.observed), 290)
        figure_block.set_note("Cobalt: model-implied change with the slope's Wald 95% CI. "
                              + ("Graphite: observed change per athlete from the snapshot rows; missing occasions are "
                                 "not imputed." if self.observed else "Observed layer not loaded."))
        self._footer(figure_block, run)
        self._add(figure_block)
        if self.explore:
            self._trajectories(run, prov)

        checks = ResultBlock("Assumption checks", [("mod", "mod")], prov)
        definitions = diagnostics.get("residual_definitions") or {}
        summary = diagnostics.get("residual_summary") or {}
        conditional = diagnostics.get("conditional_residual_summary") or {}
        qq_type = diagnostics.get("residual_qq_type")
        exploratory = theme.tokens()["warn_text"]
        tag = f'<span style="color:{exploratory}; font-size:10px; font-weight:700">EXPLORATORY</span>'
        rows = [
            ["marginal residual y − Xβ̂", "RMSE / mean / max |r|",
             f"{_f(summary.get('rmse'), 2)} / {_f(summary.get('mean_residual'), 2)} / {_f(summary.get('max_abs_residual'), 2)} {unit}", ""],
            ["marginal residual, mean by occasion", "occasions " + ", ".join(
                str(item["week"]) for item in diagnostics.get("residual_by_week") or []),
             " / ".join(_f(item["mean_residual"], 2) for item in diagnostics.get("residual_by_week") or []) + f" {unit}", ""],
        ]
        if qq_type == "CONDITIONAL_PEARSON":
            rows.append(["conditional Pearson residual (y − Xβ̂ − Zb̂) / σ̂", "SD / σ̂ · max |r|",
                         f"{_f(conditional.get('sd_over_sigma'))} · {_f(conditional.get('max_abs_pearson'), 2)}", tag])
        else:
            rows.append(["marginal residual / conditional SD", "Q–Q", "residual type not recorded (legacy run)", tag])
        checks.rich(_table(["Diagnostic (RES-619 name)", "Statistic", "Value", ""], rows, numeric_from=2))
        checks.figure(figures.residual_figure(run), 260)
        attempts = ", ".join(diagnostics.get("estimator_attempts") or [])
        checks.set_note(
            "Exploratory diagnostics; no formal normality test. "
            + (f"Q–Q definition (recorded): {definitions['residual_qq']}. " if definitions.get("residual_qq") else "")
            + (f"Optimizer attempts: {attempts}." if attempts else ""))
        self._footer(checks, run)
        self._add(checks)

    def _trajectories(self, run: dict[str, Any], prov: str) -> None:
        """E5: interactive observed trajectories with the recorded fitted mean; 2D / 3D toggle."""
        from .interactive import BAND_LABEL, TrajectoryPlot

        block = ResultBlock("Trajectories", [("obs", "obs"), ("mod", "mod")], prov,
                            "Athlete × occasion. Points are observed values; the cobalt line or surface is the "
                            "fixed-effect mean of this run. Click an athlete to link it with the Data pane.")
        switch = QFrame()
        switch.setObjectName("Segmented")
        row = QHBoxLayout(switch)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(0)
        block.trajectory_buttons = QButtonGroup(block)
        for mode in ("2D", "3D"):
            button = QPushButton(mode)
            button.setCheckable(True)
            button.setAccessibleName(f"{mode} trajectories")
            button.clicked.connect(lambda _checked=False, mode=mode: self.set_trajectory_mode(mode))
            block.trajectory_buttons.addButton(button)
            row.addWidget(button)
        bar = QHBoxLayout()
        bar.addWidget(switch)
        bar.addStretch(1)
        block.body.addLayout(bar)
        block.trajectory_stack = QStackedWidget()
        block.trajectory_stack.setMinimumHeight(440)
        self.trajectory_plot = TrajectoryPlot()
        self.trajectory_plot.set_data(self.explore, run)
        self.trajectory_plot.select_athlete(self.selected_athlete or None)
        self.trajectory_plot.athlete_selected.connect(self._trajectory_selected)
        block.trajectory_stack.addWidget(self.trajectory_plot)
        block.body.addWidget(block.trajectory_stack)
        block.set_note(f"Band: {BAND_LABEL}. Runs record the intercept and slope limits but not their covariance, "
                       "so the band bounds it; it is not the model interval. Missing athlete-occasions are listed, "
                       "never interpolated.")
        self._footer(block, run)
        self._add(block)
        self.set_trajectory_mode(self.trajectory_mode)

    def _trajectory_selected(self, subject_id: str) -> None:
        self.select_athlete(subject_id)
        self.athlete_selected.emit(subject_id)

    def _reliability(self, run: dict[str, Any]) -> None:
        t = theme.tokens()
        result = run["result"]
        cohort = (run.get("execution") or {}).get("cohort") or {}
        catalogue = cohort.get("subject_ids") or []
        analysed = result.get("subject_ids") or []
        excluded = sorted(set(catalogue) - set(analysed))
        k = result.get("trials_per_subject")
        prov = self._provenance(run)
        block = ResultBlock(
            "Reliability", [("mod", "mod")], prov,
            f"{result.get('outcome')} ({result.get('unit')}) · {result.get('activity')} · ICC(3,1) consistency")
        block.heading("Cohort")
        bad = t["bad_text"]
        block.rich(_table(["", "Participants", "Trials"], [
            [f"Study cohort {html.escape(cohort.get('id', ''))} (catalogue)", str(len(catalogue)) if catalogue else "—",
             f"{result.get('n_trials_available')} eligible {html.escape(str(result.get('activity', '')).lower())}"],
            ["Analysed ICC cohort", str(result.get("n_subjects")),
             f"{result.get('n_trials_used')} = {result.get('n_subjects')} × {k}"],
            [f'<span style="color:{bad}">Excluded</span>',
             f'<span style="color:{bad}">{len(excluded)}{" (" + ", ".join(excluded) + ")" if excluded else ""}</span>',
             f'<span style="color:{bad}">{result.get("excluded_trials")}</span>'],
        ]))
        if cohort.get("description"):
            block.rich(f'<span style="color:{t["dim_text"]}">{html.escape(cohort["description"])}</span>')
        block.heading("Trial selection")
        max_trials = (run.get("parameters") or {}).get("max_trials")
        rules = [
            f"First k = {k} trials per participant in acquisition order (max_trials = {max_trials}); "
            "trials are never sorted by value.",
            "Participants need at least two trials; later trials are excluded to keep the design balanced.",
            "Only force trials matched to an IMU recording are eligible (admitted snapshot).",
        ]
        if self.state["kind"] == "superseded":  # never restate current rules for a superseded selection
            rules = ["Selected by a superseded implementation; see the recorded limitations and the banner above."]
        block.rich("<br>".join(f"· {html.escape(rule)}" for rule in rules))
        block.heading("Intraclass correlation")
        mod = t["mod_text"]
        block.rich(_table(
            ["Form", "ICC", "95% CI (Shrout–Fleiss)", "Typical error √MSE", "95% MDC"],
            [["ICC(3,1) consistency", f'<span style="color:{mod}">{_f(result["icc_3_1"])}</span>',
              f"{_f(result.get('icc_3_1_ci_low'))} – {_f(result.get('icc_3_1_ci_high'))}",
              f"{_f(result.get('typical_error'), 2)} {result.get('unit')}",
              f"{_f(result.get('minimal_detectable_change_95'), 2)} {result.get('unit')}"
              if result.get("minimal_detectable_change_95") is not None else "not recorded"],
             ["ICC(2,1) sensitivity", _f(result.get("icc_2_1_sensitivity")), "—", "", ""],
             ["ICC(1,1) sensitivity", _f(result.get("icc_1_1_sensitivity")), "—", "", ""]]))
        block.rich(_table(["Within-participant CV", "Mean", "Median", "TE % of mean"], [[
            "trial-to-trial", f"{_f(result.get('mean_cv_percent'), 1)}%", f"{_f(result.get('median_cv_percent'), 1)}%",
            f"{_f(result.get('typical_error_percent'), 1)}%"]]))
        block.set_note(
            ("Note. 95% MDC = 1.96 · √2 · typical error: the 95% minimal detectable change; changes smaller than "
             f"{_f(result.get('minimal_detectable_change_95'), 1)} {result.get('unit')} are within measurement error. "
             if result.get("minimal_detectable_change_95") is not None else "Note. 95% MDC not recorded by this run. ")
            + " ".join(result.get("limitations") or []))
        self._footer(block, run)
        self._add(block)
        figure_block = ResultBlock("ICC and trial-to-trial variation", [("obs", "obs"), ("mod", "mod")], prov)
        figure_block.figure(figures.reliability_figure(run), 270)
        figure_block.set_note("Cobalt: ICC(3,1) with its Shrout–Fleiss 95% CI; sensitivities are point estimates "
                              "only. Graphite: observed within-participant CV per analysed participant.")
        self._footer(figure_block, run)
        self._add(figure_block)

    def _generic(self, run: dict[str, Any]) -> None:
        result = run.get("result") or {}
        block = ResultBlock(str(result.get("method") or run.get("method_id")), [], self._provenance(run))
        message = result.get("message") or "No workbench renderer for this method; see the run record."
        block.rich(html.escape(message))
        block.set_note(" ".join(result.get("limitations") or []) or "Limits: see the run record.")
        self._footer(block, run)
        self._add(block)

    # -- theme --------------------------------------------------------------
    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and theme.current_theme() != self._theme:
            self._theme = theme.current_theme()
            if self.run is not None:
                stale = self.stale
                self.show_run(self.run, self.spec, self.observed, self.explore)
                self.mark_stale(stale)
            elif self._build is not None:
                stale = self.stale
                self.show_blocks(self._build, self.spec, self.state)
                self.mark_stale(stale)
            elif self.spec is not None:
                self.show_unavailable(self.spec)


def run_analysis(service: Any, study_id: str | None, spec: AnalysisSpec, runner: Any,
                 on_done: Callable[[dict[str, Any] | None], None],
                 on_error: Callable[[Exception], None] | None = None) -> bool:
    """Run ``spec`` through the isolated worker on ``runner`` (a TaskRunner).

    Returns False (and calls ``on_done(None)``) for kinds without a qualified engine;
    invalid specifications are reported through ``on_error``.
    """
    if spec.kind not in ENGINE_KINDS:
        on_done(None)
        return False
    report = on_error or (lambda error: None)
    try:
        payload = spec.to_run_payload()
    except ValueError as error:
        report(error)
        return False
    study = study_id or spec.study_id
    runner.submit(lambda: service.execute_analysis_isolated(study, payload), on_done, report)
    return True
