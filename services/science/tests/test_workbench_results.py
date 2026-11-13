"""RES-620 results document: rendering of recorded runs, stale/superseded gating, exports."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from dynamis_science.desktop import theme  # noqa: E402
from dynamis_science.desktop.workbench import figures  # noqa: E402
from dynamis_science.desktop.workbench.results import (  # noqa: E402
    ResultsDocument,
    estimation_of,
    run_analysis,
    run_method_state,
    wald,
)
from dynamis_science.desktop.workbench.spec import AnalysisSpec  # noqa: E402

PRIVATE = Path(os.environ.get("DYNAMISSCIENCE_TEST_SOURCE_ROOT", r"D:\datasets\DynamisScience"))


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    theme.apply_theme(application, "light")
    return application


def _mixed_spec(**options) -> AnalysisSpec:
    return AnalysisSpec("mixed_model", {"outcome": ["cmj_height_cm"], "subject": ["subject_id"], "occasion": ["occasion"]},
                        options, table="cmj_occasions",
                        variable_types={"cmj_height_cm": "numerical", "subject_id": "identifier", "occasion": "ordinal"})


def _rel_spec() -> AnalysisSpec:
    return AnalysisSpec("reliability", {"outcome": ["fz_peak_n"], "subject": ["subject_id"]}, table="signal_trials",
                        variable_types={"fz_peak_n": "numerical", "subject_id": "identifier"})


def _texts(doc: ResultsDocument) -> str:
    from PySide6.QtWidgets import QLabel

    return "\n".join(label.text() for label in doc.widget().findChildren(QLabel) if label.isVisibleTo(doc.widget()))


def test_helpers():
    assert estimation_of("y ~ x + (1 + x | s), ML") == "ML"
    assert estimation_of("y ~ x, REML") == "REML"
    assert estimation_of("y ~ x") == "not recorded"
    z, p = wald(0.9984512, 0.192008)
    assert z == pytest.approx(5.2, abs=0.01) and p < 1e-6
    assert wald(1.0, 0.0) == (None, None)
    superseded = run_method_state({"method_id": "METH-REAL-RELIABILITY", "method_version": "1.0.0", "status": "COMPLETED"})
    assert superseded["kind"] == "superseded" and not superseded["promotable"]
    current = run_method_state({"method_id": "METH-REAL-TREND", "method_version": "1.1.0", "status": "COMPLETED", "result": {}})
    assert current["kind"] == "qualified" and current["promotable"]
    unknown = run_method_state({"method_id": "METH-REAL-TREND", "method_version": "9.9.9", "status": "COMPLETED", "result": {}})
    assert unknown["kind"] == "not_qualified" and not unknown["promotable"]
    figure, _ = figures._new(theme.tokens())
    figures._finish(figure, {"method_status": {"state": "UNVERIFIED"}}, theme.tokens())
    assert "UNVERIFIED" in figure._suptitle.get_text()
    insufficient = run_method_state({"method_id": "METH-REAL-RELIABILITY", "method_version": "1.1.0", "status": "COMPLETED",
                                     "result": {"status": "INSUFFICIENT_DATA", "message": "too few"}})
    assert insufficient["kind"] == "unavailable" and not insufficient["promotable"]


@pytest.mark.parametrize("kind", ["ttest", "anova", "regression"])
def test_not_qualified_analyses_are_never_promotable(app, kind):
    doc = ResultsDocument()
    calls = []
    assert run_analysis(None, None, AnalysisSpec(kind), None, calls.append) is False and calls == [None]
    doc.show_run(None, AnalysisSpec(kind))
    assert not doc.promotable and doc.state["kind"] == "not_qualified"
    assert "Unavailable in the qualified engine" in _texts(doc)
    assert doc.promote() is None
    with pytest.raises(ValueError):
        doc.export("x.png")


# --------------------------------------------------------------------------- #
# Real recorded runs on an isolated copy (skipped without the private snapshots)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    snapshots = sorted((PRIVATE / "snapshots").glob("DS-REAL-*")) if (PRIVATE / "snapshots").is_dir() else []
    if len(snapshots) < 2 or not (PRIVATE / "research" / "research.db").is_file():
        pytest.skip("Verified private Mendeley and MoveSmart snapshots are not available")
    root = tmp_path_factory.mktemp("results-real")
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
    mixed, rel = _mixed_spec(), _rel_spec()
    runs = {
        "mixed": service.execute_analysis_run(mixed.study_id, mixed.to_run_payload()),
        "rel": service.execute_analysis_run(rel.study_id, rel.to_run_payload()),
    }
    yield service, runs, root
    patch.undo()


def test_mixed_model_block_shows_recorded_specification(app, real):
    service, runs, _ = real
    run = runs["mixed"]
    result = run["result"]
    doc = ResultsDocument(service)
    doc.show_run(run, _mixed_spec())
    text = _texts(doc)
    assert estimation_of(result["formula"]) == "ML" and ">ML<" in text and "REML" not in text
    assert result["estimator"] == "MIXEDLM_RANDOM_SLOPE" and "intercept + occasion slope | subject" in text
    assert f">{result['n_observations']}<" in text and result["n_observations"] == 82
    assert "0.998" in text and "0.622 – 1.375" in text
    assert "conditional Pearson residual (y − Xβ̂ − Zb̂) / σ̂" in text and "EXPLORATORY" in text
    assert "2 of 84 athlete-occasions missing" in text
    assert "QUALIFIED" in text and run["id"] in text and run["result_digest"][:8] in text
    assert doc.promotable
    assert doc.provenance_args()["method_status"] == "qualified"


def test_reliability_block_separates_catalogue_and_analysed_cohort(app, real):
    service, runs, _ = real
    result = runs["rel"]["result"]
    doc = ResultsDocument(service)
    doc.show_run(runs["rel"], _rel_spec())
    text = _texts(doc)
    assert result["icc_3_1"] == pytest.approx(0.888726587, abs=1e-8)
    assert "0.889" in text and "0.745 – 0.969" in text
    assert result["n_subjects"] == 9 and result["trials_per_subject"] == 5
    assert "Study cohort COHORT-REAL-002 (catalogue)" in text and "MS-06" in text
    assert "45 = 9 × 5" in text and "acquisition order" in text
    assert "95% MDC" in text and "minimal detectable change" in text and "210.05" in text
    assert "smallest worthwhile" not in text.lower()


def test_stale_and_superseded_gate_promotion(app, real):
    service, runs, _ = real
    doc = ResultsDocument(service)
    spec = _mixed_spec()
    doc.show_run(runs["mixed"], spec)
    assert doc.check_spec(spec) is False and doc.promotable
    assert doc.check_spec(_mixed_spec(reference_occasion=2)) is True
    assert doc.stale and not doc.promotable
    assert all(block.graphicsEffect() is not None for block in doc.blocks)
    doc.mark_stale(False)
    assert all(block.graphicsEffect() is None for block in doc.blocks)

    legacy = {**runs["rel"], "method_version": "1.0.0", "method_status": None}
    doc.show_run(legacy)
    errors = []
    doc.action_failed.connect(errors.append)
    assert doc.superseded_bar.isVisibleTo(doc) and not doc.promotable
    assert doc.promote() is None and "superseded" in errors[-1]
    assert "acquisition order (max_trials" not in _texts(doc)


def test_exports_print_run_digest_and_method_status_on_the_figure(tmp_path):
    from matplotlib.figure import Figure
    from matplotlib.image import imread

    run = {"id": "RUN-X-0001", "method_id": "METH-A", "method_version": "1.1.0", "result_digest": "abcd1234ef567890",
           "method_status": {"state": "CURRENT"}}
    expected = "Run RUN-X-0001 · METH-A 1.1.0 · method version CURRENT · result digest abcd1234"
    assert figures.provenance_footer(run) == expected

    def make(with_footer: bool) -> Figure:
        figure = Figure(figsize=(7.2, 3.0), dpi=100, constrained_layout=True)
        figure.subplots().plot([0, 1], [0, 1])
        if with_footer:
            figure._dynamis_footer = figures.provenance_footer(run)
        return figure

    with_footer, plain = make(True), make(False)
    layout = dict(with_footer.get_layout_engine().get())
    svg = figures.export(with_footer, tmp_path / "f.svg")
    assert expected in svg.read_text(encoding="utf-8")  # text on the figure, not only metadata
    assert not with_footer.texts and dict(with_footer.get_layout_engine().get()) == layout  # figure restored
    png, bare = figures.export(with_footer, tmp_path / "f.png"), figures.export(plain, tmp_path / "bare.png")
    image, reference = imread(png), imread(bare)
    assert (image[-60:, :, :3] < 0.8).sum() > (reference[-60:, :, :3] < 0.8).sum()  # extra ink: the footer text
    import re
    import zlib

    pdf = figures.export(with_footer, tmp_path / "f.pdf").read_bytes()  # TrueType text: two-byte codes in TJ arrays
    text = ""
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            text += "".join(m.decode("latin-1") for m in re.findall(rb"\(\x00(.)\)", zlib.decompress(stream), re.S))
        except zlib.error:
            continue
    assert expected in text


def test_promote_add_to_report_and_export(app, real, tmp_path):
    service, runs, _ = real
    doc = ResultsDocument(service)
    doc.show_run(runs["rel"], _rel_spec())
    cited = doc.add_to_report()
    assert cited and {item["artifact_id"].split("-")[0] for item in cited} == {"EVID", "FIG"}
    assert cited[0]["artifact_id"] in service.get_report(runs["rel"]["study_id"])["evidence_ids"]
    for fmt in figures.FORMATS:
        paths = doc.export(tmp_path / "rel", fmt)
        assert [path.suffix for path in paths] == [f".{fmt}"]
        assert paths[0].stat().st_size > 1000
    assert "ICC" in (tmp_path / "rel-reliability.svg").read_text(encoding="utf-8")
    assert runs["rel"]["id"].encode() in (tmp_path / "rel-reliability.pdf").read_bytes()
    doc.show_run(runs["mixed"], _mixed_spec())
    assert [path.name for path in doc.export(tmp_path / "mm.svg")] == ["mm-trajectory.svg", "mm-residuals.svg"]
    assert "EXPLORATORY" in (tmp_path / "mm-residuals.svg").read_text(encoding="utf-8")


def test_workspace_reliability_honors_selected_activity(real):
    from dynamis_science import researchstore

    service, previous, _ = real
    detail = service.create_workspace("Activity-specific workspace")
    identity = detail["study"]["id"]
    detail = service.attach_workspace_data(identity, previous["rel"]["snapshot_id"])
    run = service.execute_analysis_run(identity, {
        "method_id": "METH-REAL-RELIABILITY", "outcome_metric_id": "MET-REAL-FZ-PEAK",
        "parameters": {"activity": "Running", "max_trials": 2},
        "data_revision_id": detail["active_data_revision_id"],
    })
    assert researchstore.get_cohort(run["cohort_id"])["activity"] == "Running"
    assert run["parameters"]["activity"] == "Running"
    assert run["result"]["activity"] == "Running"
    assert run["result"]["n_subjects"] == 8
    assert run["plan_alignment"] == "PLANNED"
    assert run["data_revision_id"] == detail["active_data_revision_id"]
