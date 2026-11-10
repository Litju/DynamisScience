"""WorkbenchController: owns one AnalysisSpec per analysis kind and keeps the shell in step with it.

Pane edits mutate the spec here; every change refreshes the options pane, the live Python syntax,
the run state (stale detection through the spec hash) and the status-bar provenance.  Switching
dataset, table or study drops all specs and run state, so no outdated result outlives its data.

Run flow: shell.action_run -> `run_requested(spec)` (valid specs only) -> the consumer executes it and
calls `set_last_run_hash(spec.spec_hash(), run=..., digest=...)`, or `mark_run_failed()`.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

from .data_pane import DataPane
from .options_pane import OptionsPane
from .shell import WorkbenchShell
from .spec import ROLE_RULES, AnalysisSpec, method_status

# ribbon key -> spec kind (None: no variable-assignment spec, e.g. the signal viewer)
ANALYSIS_KIND: dict[str, str | None] = {
    "descriptives": "descriptives",
    "t_tests": "ttest",
    "anova": "anova",
    "regression": "regression",
    "mixed_models": "mixed_model",
    "reliability": "reliability",
    "frequencies": "frequencies",
    "athlete_change": "athlete_change",
    "signals": None,
}


class WorkbenchController(QObject):
    spec_changed = Signal(object)  # AnalysisSpec
    run_requested = Signal(object)  # AnalysisSpec, valid only

    def __init__(self, shell: WorkbenchShell, data_pane: DataPane, options_pane: OptionsPane,
                 parent: QObject | None = None) -> None:
        super().__init__(parent or shell)
        self.shell, self.data_pane, self.options_pane = shell, data_pane, options_pane
        self._specs: dict[str, AnalysisSpec] = {}
        self._last_hash: str | None = None
        self._run, self._digest = "", ""
        self._source, self._provenance = "", ""
        self._study_id: str | None = None
        shell.analysis_selected.connect(self._select)
        shell.action_run.triggered.connect(self.request_run)
        data_pane.dataset_changed.connect(self._dataset_changed)
        options_pane.variable_assigned.connect(self._assign)
        options_pane.variable_removed.connect(self._remove)
        options_pane.option_changed.connect(self._option)
        options_pane.message.connect(self._message)
        self._select(shell.current_analysis() or "")

    # ------------------------------------------------------------------ public API
    def current_spec(self) -> AnalysisSpec | None:
        kind = ANALYSIS_KIND.get(self.shell.current_analysis() or "")
        if not kind or not self.data_pane.snapshot_id:
            return None
        return self._spec(kind)

    def set_source(self, source: str, provenance: str = "", study_id: str | None = None) -> None:
        """Dataset provenance for the status bar; `study_id` binds specs to the open study."""
        self._source, self._provenance = source, provenance
        if study_id != self._study_id:
            self._study_id = study_id
            self._specs.clear()  # a spec is bound to its study
            self._refresh()
        else:
            self._update_provenance()

    def set_last_run_hash(self, spec_hash: str | None, run: str = "", digest: str = "") -> None:
        """Record the hash of the spec that produced the visible results (None: no results)."""
        self._last_hash = spec_hash
        self._run, self._digest = (run, digest) if spec_hash else ("", "")
        self._update_run_state()
        self._update_provenance()

    def mark_run_failed(self) -> None:
        self._update_run_state()

    def reset(self) -> None:
        """Drop every spec and any run state."""
        self._specs.clear()
        self._last_hash = None
        self._run = self._digest = ""
        self._refresh()

    def refresh_provenance(self) -> None:
        self._update_provenance()

    def request_run(self) -> None:
        spec = self.current_spec()
        if spec is None:
            self.shell.set_status("Open a dataset and choose an analysis with variable roles first")
            return
        errors = [i["message"] for i in spec.validate() if i["severity"] == "error"]
        if errors:
            self.shell.set_status(f"Cannot run: {errors[0]}")
            self.shell.show_toast(errors[0])
            return
        self.shell.set_run_state("running")
        self.run_requested.emit(spec)

    # ------------------------------------------------------------------ internals
    def _spec(self, kind: str) -> AnalysisSpec:
        spec = self._specs.get(kind)
        if spec is None:
            options = {"study_id": self._study_id} if self._study_id and kind in ("mixed_model", "reliability") else {}
            spec = AnalysisSpec(kind, snapshot_id=self.data_pane.snapshot_id, table=self.data_pane.table,
                                options=options, variable_types=self.data_pane.variable_types())
            self._specs[kind] = spec
        return spec

    def _dataset_changed(self, _snapshot: str, _table: str) -> None:
        self._specs.clear()
        self._last_hash = None
        self._run = self._digest = ""
        self.options_pane.set_variables(self.data_pane.variables())
        self._refresh()

    def _select(self, key: str) -> None:
        self._refresh()

    def _refresh(self) -> None:
        key = self.shell.current_analysis() or ""
        kind = ANALYSIS_KIND.get(key)
        spec = self.current_spec()
        if not self.data_pane.snapshot_id:
            self.options_pane.set_placeholder("Open a dataset or study to assign variables.")
            self.shell.set_syntax("")
        elif kind is None:
            self.options_pane.set_placeholder(
                "Signals has no variable roles: pick a trial and channels in the Results pane." if key == "signals"
                else "Choose an analysis in the ribbon.")
            self.shell.set_syntax("")
        else:
            self.options_pane.set_spec(spec)
            self.shell.set_syntax(spec.to_python_syntax())
        self._update_run_state()
        self._update_provenance()
        if spec is not None:
            self.spec_changed.emit(spec)

    def _update_run_state(self) -> None:
        spec = self.current_spec()
        if self._last_hash is None:
            state = "none"
        else:
            state = "current" if spec is not None and spec.spec_hash() == self._last_hash else "stale"
        self.shell.set_run_state(state)

    def _update_provenance(self) -> None:
        spec = self.current_spec()
        status = method_status(spec.kind)["status"].replace(" ", "_") if spec else ""
        self.shell.set_provenance(self._source, self._run, self._digest, status, self._provenance)

    def _message(self, text: str) -> None:
        self.shell.set_status(text)
        self.shell.show_toast(text)

    def _mutated(self) -> None:
        self._refresh()

    def _assign(self, role: str, name: str) -> None:
        spec = self.current_spec()
        if spec is None:
            return
        rule = ROLE_RULES[spec.kind][role]
        for other, names in spec.roles.items():  # a variable holds one role at a time
            if other != role and name in names:
                spec.roles[other] = [n for n in names if n != name]
        if rule.max == 1:
            spec.roles[role] = [name]
        elif name not in spec.role(role):
            spec.roles[role] = [*spec.role(role), name]
        self._mutated()

    def _remove(self, role: str, name: str) -> None:
        spec = self.current_spec()
        if spec is not None:
            spec.roles[role] = [n for n in spec.role(role) if n != name]
            self._mutated()

    def _option(self, key: str, value: Any) -> None:
        spec = self.current_spec()
        if spec is not None and spec.options.get(key, spec.effective_options().get(key)) != value:
            spec.options[key] = value
            self._mutated()
