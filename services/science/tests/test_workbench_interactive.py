"""RES-620 Gate 4A: interactive trajectories, descriptive blocks and signal inspection widgets."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6.QtWidgets import QApplication, QLabel

from dynamis_science.desktop import theme
from dynamis_science.desktop.workbench import descriptive, interactive
from dynamis_science.desktop.workbench.signals_view import SignalsView

PRIVATE = Path(r"D:\datasets\DynamisScience")


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    theme.apply_theme(application, "light")
    return application


EXPLORE = {
    "metric": {"column": "cmj_height_cm", "label": "CMJ height", "unit": "cm"},
    "unit": "cm", "reference": "RAW", "reference_label": "observed values",
    "summary": [{"occasion": 1}, {"occasion": 2}, {"occasion": 3}],
    "athletes": [
        {"subject_id": "S1", "display_id": "A01", "values": [30.0, 31.0, 32.0]},
        {"subject_id": "S2", "display_id": "A02", "values": [40.0, None, 43.0]},
        {"subject_id": "S3", "display_id": "A03", "values": [None, 35.0, 36.0]},
    ],
}
RUN = {"id": "RUN-X", "method_id": "METH-REAL-TREND", "result": {
    "outcome": "cmj_height_cm", "reference_occasion": 1,
    "coefficients": {"intercept": {"estimate": 35.0, "std_error": 1.0, "ci_low": 33.0, "ci_high": 37.0},
                     "occasion_slope": {"estimate": 1.0, "std_error": 0.25, "ci_low": 0.5, "ci_high": 1.5}}}}


def _texts(widget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


# --------------------------------------------------------------------------- #
# interactive.py
# --------------------------------------------------------------------------- #


def test_model_band_uses_recorded_estimates_only():
    band = interactive.model_band(RUN, [1.0, 2.0, 3.0], "cmj_height_cm")
    assert band["mean"] == [35.0, 36.0, 37.0]
    # conservative half-width = recorded intercept half-width + |elapsed| * slope half-width
    assert band["low"] == [33.0, 33.5, 34.0] and band["high"] == [37.0, 38.5, 40.0]
    assert interactive.model_band(RUN, [1.0], "other_outcome") is None
    assert interactive.model_band({**RUN, "method_id": "METH-REAL-RELIABILITY"}, [1.0]) is None
    assert interactive.model_band(None, [1.0]) is None


def test_observed_and_depth_axes_never_use_identifier_as_continuous():
    data = interactive.observed(EXPLORE)
    assert data["missing"] == [["A03"], ["A02"], []]
    options = interactive.depth_options(data, {"Body mass (kg)": {}})
    assert "categorical" in options[interactive.LANES] and "continuous" in options[interactive.BASELINE]
    assert interactive.depth_values(data, interactive.BASELINE) == {"S1": 30.0, "S2": 40.0, "S3": None}
    lanes = interactive.depth_values(data, interactive.LANES)
    assert lanes == {"S1": 0.0, "S2": 1.0, "S3": 2.0}  # ordered by baseline, missing baseline last
    assert interactive.depth_values(data, "Body mass (kg)", {"Body mass (kg)": {"S1": 80.0}})["S2"] is None


def test_trajectory_plot_hover_select_and_missing(app):
    plot = interactive.TrajectoryPlot()
    plot.resize(700, 420)
    plot.set_data(EXPLORE, RUN)
    plot.show()
    app.processEvents()
    assert plot.mod_chip.isVisibleTo(plot) and "RUN-X" in plot.model_note.text()
    assert "Occasion 1: 1 missing (A03)" in plot.missing_note.text()
    box = plot.plot.getPlotItem().vb
    hit = plot.nearest(box.mapViewToScene(interactive.pg.Point(2, 31.0)))
    assert hit == ("S1", 1)
    assert plot.describe_point("S1", 1) == "A01 · Occasion 2 · 31.0 cm (observed)"
    assert plot.describe_point("S2", 1).endswith("missing · not imputed")
    chosen = []
    plot.athlete_selected.connect(chosen.append)
    plot.select_athlete("S2")
    assert plot.selected == "S2" and chosen == []  # programmatic selection does not echo
    plot.set_data({**EXPLORE, "reference": "CHANGE"}, RUN)  # the model is on the raw scale only
    assert plot.model is None and not plot.mod_chip.isVisibleTo(plot)


def test_trajectory_3d_controls_or_fallback(app, monkeypatch):
    view = interactive.Trajectory3D()
    view.set_data(EXPLORE, RUN, {"Body mass (kg)": {"S1": 80.0, "S2": 90.0, "S3": 70.0}})
    assert view.depth_combo.count() == 3
    view.set_depth(interactive.LANES)
    assert view.depth_key == interactive.LANES
    with pytest.raises(ValueError):
        view.set_depth("subject_id")
    assert "Occasion 2: A02" in view.missing_note.text()
    if view.available:
        view.set_view("Front", animate=False)
        assert view.camera()[:2] == interactive.PRESETS["Front"]
    monkeypatch.setattr(interactive, "_gl", lambda: None)
    fallback = interactive.Trajectory3D()
    fallback.set_data(EXPLORE, RUN)
    assert not fallback.available and "3D view unavailable" in _texts(fallback)
    assert not fallback.depth_combo.isEnabled() and fallback.camera() is None


# --------------------------------------------------------------------------- #
# descriptive.py
# --------------------------------------------------------------------------- #


def _frame():
    import pandas as pd

    return pd.DataFrame({
        "subject_id": ["S1", "S1", "S2", "S2", "S3"],
        "occasion": [1, 2, 1, 2, 1],
        "height": [30.0, 32.0, 40.0, None, 35.0],
        "position": ["F", "F", "B", "B", None],
    })


def test_describe_counts_absent_and_null_as_missing():
    table = descriptive.describe(_frame(), ["height"], by="occasion", subject="subject_id")
    first, second = table.iloc[0], table.iloc[1]
    assert (first.n, first.missing, first["mean"], first["median"], first["min"], first["max"]) == (3, 0, 35.0, 35.0, 30.0, 40.0)
    assert first.iqr == pytest.approx(5.0) and first.sd == pytest.approx(5.0)
    assert (second.n, second.missing) == (1, 2)  # S2 null, S3 absent
    plain = descriptive.describe(_frame(), ["height"])
    assert (plain.iloc[0].n, plain.iloc[0].missing) == (4, 1)


def test_descriptives_block_follows_statistic_and_plot_options(app):
    only = {"stat_n_missing": False, "stat_mean_sd": False, "stat_median_iqr": False, "stat_min_max": True,
            "stat_ci": True, "plot_box": False, "plot_hist": True}
    block = descriptive.DescriptivesBlock(_frame(), ["height"], by="occasion", subject="subject_id", options=only)
    text = _texts(block)
    assert "Min" in text and "Max" in text and "95% CI low" in text and "Median" not in text and "Mean" not in text
    assert "Histogram of observed values" in text and "Box: median" not in text
    assert ".agg([" in block.syntax and '"sem"' in block.syntax and ".hist(" in block.syntax
    row = block.table.iloc[0]  # occasion 1: 30, 40, 35 -> mean 35, SD 5, t(0.975, 2) = 4.303
    assert row.ci_low == pytest.approx(35 - 4.302653 * 5 / math.sqrt(3), rel=1e-5)
    default = descriptive.DescriptivesBlock(_frame(), ["height"], provenance={})  # no split: box plot of all rows
    assert "Box: median" in _texts(default) and "Min" not in _texts(default) and "95% CI" not in _texts(default)


def test_frequencies_always_list_missing():
    table = descriptive.frequencies(_frame(), ["position"])
    assert table.level.tolist() == ["B", "F", "Missing"] and table["count"].tolist() == [2, 2, 1]
    assert table.percent.sum() == pytest.approx(100)


def test_athlete_change_keeps_missing_athletes():
    table = descriptive.athlete_change(_frame(), "height", "subject_id", "occasion", 1, 2).set_index("subject")
    assert table.loc["S1", "change"] == 2.0 and table.loc["S1", "status"] == "no threshold"
    assert math.isnan(table.loc["S2", "change"]) and table.loc["S2", "status"] == "missing at 2"
    assert table.loc["S3", "status"] == "missing at 2"
    swc = descriptive.athlete_change(_frame(), "height", "subject_id", "occasion", 1, 2, swc=1.0)
    assert swc.set_index("subject").loc["S1", "status"] == "above SWC"


def test_descriptive_blocks_are_observed_and_never_promotable(app):
    prov = {"source": "real", "snapshot_id": "DS-X", "table": "t"}
    blocks = [descriptive.DescriptivesBlock(_frame(), ["height"], by="occasion", subject="subject_id", provenance=prov),
              descriptive.FrequenciesBlock(_frame(), ["position"], provenance=prov),
              descriptive.AthleteChangeBlock(_frame(), "height", "subject_id", "occasion", 1, 2, provenance=prov)]
    for block in blocks:
        assert block.promote() is None and not block.promotable
        assert not block.promote_button.isEnabled()
        assert [c.property("chip") for c in block.chips] == ["obs", "real"]
        assert block.method_chip.property("chip") == "descriptive"
        text = _texts(block)
        assert "DS-X" in text and block.note.text()
    assert "no qualified noise threshold" in blocks[2].note.text().lower()


class _PagedService:
    def __init__(self, rows):
        self.rows, self.calls = rows, 0

    def read_table_page(self, snapshot_id, table, offset=0, limit=500):
        self.calls += 1
        return {"total_rows": len(self.rows), "columns": ["a"], "rows": self.rows[offset:offset + limit]}


def test_load_table_pages_and_caps():
    service = _PagedService([{"a": i} for i in range(1200)])
    assert len(descriptive.load_table(service, "S", "t")) == 1200 and service.calls == 3
    with pytest.raises(ValueError):
        descriptive.load_table(service, "S", "t", max_rows=1000)


# --------------------------------------------------------------------------- #
# signals_view.py
# --------------------------------------------------------------------------- #


class _SignalService:
    trials = ({"trial_id": "T1", "subject_id": "MS-01", "activity": "Walking", "trial_number": 1,
               "fz_baseline_n": 0.5, "fz_peak_n": 900.0, "quality_flags": ["SINGLE_PLATE"], "nan_count": 3},
              {"trial_id": "T2", "subject_id": "MS-02", "activity": "Running", "trial_number": 1})

    def list_signal_trials(self, snapshot_id, subject_id=None, activity=None):
        return list(self.trials)

    def get_signal_waveform(self, snapshot_id, trial_id, max_points=2500):
        rows = [{"time_s": i / 10, "fz_n": None if i == 3 else float(i)} for i in range(10)]
        series = [{"label": p, "time_column": "time_s", "value_column": "fz_n", "rows": rows} for p in ("6", "7")]
        return {"trial_id": trial_id, "series": series, "sample_count": 20, "source_rows": 20,
                "events": [{"time": 0.5, "label": "contact"}]}


def test_signals_view_with_fake_service(app):
    view = SignalsView(_SignalService())
    view.set_snapshot("DS-X", activity="Walking")
    assert [t["trial_id"] for t in view.visible_trials()] == ["T1"] and view.trial_list.count() == 1
    shown = []
    view.trial_selected.connect(shown.append)
    view.show_trial("T1")
    assert shown == ["T1"] and view.channels() == ["Plate 6", "Plate 7"]
    assert set(view.curves) == {"Plate 6", "Plate 7"}
    view.set_channel_visible("Plate 7", False)
    assert set(view.curves) == {"Plate 6"}
    assert "missing samples shown as gaps" in view.detail.text() and "SINGLE_PLATE" in view.detail.text()


# --------------------------------------------------------------------------- #
# Real snapshots on an isolated copy (skipped without the private data)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    snapshots = sorted((PRIVATE / "snapshots").glob("DS-REAL-*")) if (PRIVATE / "snapshots").is_dir() else []
    if len(snapshots) < 2 or not (PRIVATE / "research" / "research.db").is_file():
        pytest.skip("Verified private Mendeley and MoveSmart snapshots are not available")
    root = tmp_path_factory.mktemp("interactive-real")
    (root / "manifests").mkdir()
    (root / "research").mkdir()
    shutil.copy2(PRIVATE / "manifests" / "admissions.json", root / "manifests")
    for source in snapshots:
        copied = root / "snapshots" / source.name
        shutil.copytree(source, copied)
        for name, expected in json.loads((copied / "snapshot.json").read_text(encoding="utf-8"))["checksums"].items():
            with (copied / name).open("rb") as handle:
                assert hashlib.file_digest(handle, "sha256").hexdigest() == expected
    source = sqlite3.connect(f"file:{(PRIVATE / 'research' / 'research.db').as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(root / "research" / "research.db")
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    patch = pytest.MonkeyPatch()
    patch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    from dynamis_science.desktop.services import DynamisAppService

    service = DynamisAppService()
    service.ensure_initialized()
    snapshot = {s.name.split("-")[2]: s.name for s in snapshots}
    yield service, snapshot
    patch.undo()


def test_real_trajectory_and_descriptives(app, real):
    service, snapshot = real
    explore = service.explore_longitudinal("STUDY-REAL-001", "MET-REAL-CMJ-HEIGHT")
    plot = interactive.TrajectoryPlot()
    plot.set_data(explore)
    assert len(plot.data["athletes"]) == 21 and "missing" in plot.missing_note.text()
    frame = descriptive.load_table(service, snapshot["MENDELEY"], "cmj_occasions")
    table = descriptive.describe(frame, ["cmj_height_cm"], by="occasion", subject="subject_id")
    assert table.n.tolist() == [21, 21, 21, 19] and table.missing.tolist() == [0, 0, 0, 2]
    # agrees with the registered descriptive summary (METH-REAL-DESC means per occasion)
    assert table["mean"].tolist() == pytest.approx([row["mean"] for row in explore["summary"]], rel=1e-9)
    change = descriptive.athlete_change(frame, "cmj_height_cm", "subject_id", "occasion", 1, 4)
    assert change.change.notna().sum() == 19 and (change.status == "missing at 4").sum() == 2


def test_real_signals(app, real):
    service, snapshot = real
    view = SignalsView(service)
    view.set_snapshot(snapshot["MOVESMART"], activity="Walking")
    assert view.visible_trials() and all(t["activity"] == "Walking" for t in view.visible_trials())
    view.show_trial(view.visible_trials()[0]["trial_id"])
    assert view.channels() and view.curves
