from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.plots import export_figure, run_figure
from dynamis_science.desktop.services import DynamisAppService
from dynamis_science.desktop.tasks import TaskRunner
from dynamis_science import realstore, researchstore


def test_parquet_preview_is_bounded_and_offset_correct(tmp_path, monkeypatch):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    service.ensure_initialized()

    first = service.read_table_page("DS-SYNTH-001", "cmj_trials", offset=0, limit=5)
    later = service.read_table_page("DS-SYNTH-001", "cmj_trials", offset=5, limit=5)
    full = researchstore.read_snapshot_table("DS-SYNTH-001", "cmj_trials")

    assert first["total_rows"] == 884
    assert len(first["rows"]) == len(later["rows"]) == 5
    assert first["rows"][0]["trial_id"] == full.row(0, named=True)["trial_id"]
    assert later["rows"][0]["trial_id"] == full.row(5, named=True)["trial_id"]
    with pytest.raises(ValueError, match="limit"):
        service.read_table_page("DS-SYNTH-001", "cmj_trials", limit=501)
    with pytest.raises(researchstore.ResearchNotFound):
        service.read_table_page("DS-SYNTH-001", "..\\study.json")


def test_task_results_are_delivered_on_gui_thread(qtbot):
    runner = TaskRunner()
    main_thread = threading.get_ident()
    received = []
    runner.submit(
        lambda: 17,
        lambda value: received.append((value, threading.get_ident())),
        lambda error: pytest.fail(str(error)),
    )
    qtbot.waitUntil(lambda: bool(received))
    assert received == [(17, main_thread)]


def test_native_window_loads_five_workspaces_and_catalogue(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    window = MainWindow(DynamisAppService())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 3)

    assert window.research.tabs.count() == 5
    study_parent = window.navigator.topLevelItem(1)
    synthetic = next(
        study_parent.child(index)
        for index in range(study_parent.childCount())
        if study_parent.child(index).data(0, Qt.ItemDataRole.UserRole)["id"] == "STUDY-001"
    )
    window._navigation_activated(synthetic, 0)
    qtbot.waitUntil(lambda: window.current_study_id == "STUDY-001")
    qtbot.waitUntil(lambda: window.research.table_model.rowCount() == 500)
    qtbot.waitUntil(lambda: not window.runner.active)
    screenshot = tmp_path / "g1-native-research.png"
    assert window.grab().save(str(screenshot))
    assert screenshot.stat().st_size > 0
    window.close()


def _isolated_real_root(tmp_path: Path) -> Path:
    source_root = Path(r"D:\datasets\DynamisScience")
    source_snapshots = source_root / "snapshots"
    snapshot_paths = sorted(source_snapshots.glob("DS-REAL-*")) if source_snapshots.is_dir() else []
    admissions = source_root / "manifests" / "admissions.json"
    source_database = source_root / "research" / "research.db"
    if len(snapshot_paths) < 2 or not admissions.is_file() or not source_database.is_file():
        pytest.skip("Verified private Mendeley and MoveSmart snapshots are not available")
    target_root = tmp_path / "isolated-real-data"
    (target_root / "snapshots").mkdir(parents=True)
    (target_root / "manifests").mkdir()
    (target_root / "research").mkdir()
    shutil.copy2(admissions, target_root / "manifests")
    for source in snapshot_paths:
        copied = target_root / "snapshots" / source.name
        shutil.copytree(source, copied)
        manifest = json.loads((copied / "snapshot.json").read_text(encoding="utf-8"))
        for filename, expected in manifest.get("checksums", {}).items():
            with (copied / filename).open("rb") as handle:
                assert hashlib.file_digest(handle, "sha256").hexdigest() == expected
    source_connection = sqlite3.connect(
        f"file:{source_database.as_posix()}?mode=ro", uri=True
    )
    target_connection = sqlite3.connect(target_root / "research" / "research.db")
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    return target_root


def test_real_mendeley_movesmart_runs_evidence_waveforms_and_exports(tmp_path, monkeypatch):
    root = _isolated_real_root(tmp_path)
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    service = DynamisAppService()
    service.ensure_initialized()
    mendeley_dataset = service.get_dataset_detail("DS-REAL-MENDELEY-2C44490E08AD")
    assert mendeley_dataset["source"]["license"]["id"]

    mendeley = service.execute_analysis_run(
        realstore.STUDY_MENDELEY,
        {
            "method_id": "METH-REAL-TREND",
            "outcome_metric_id": "MET-REAL-CMJ-HEIGHT",
            "parameters": {"reference_occasion": 1, "contrast_occasion": 4},
        },
    )
    assert mendeley["status"] == "COMPLETED"
    assert mendeley["method_id"] == "METH-REAL-TREND"
    assert mendeley["result_digest"]
    isolated_mendeley = service.execute_analysis_isolated(
        realstore.STUDY_MENDELEY,
        {
            "method_id": "METH-REAL-TREND",
            "outcome_metric_id": "MET-REAL-CMJ-HEIGHT",
            "parameters": {"reference_occasion": 1, "contrast_occasion": 4},
        },
    )
    assert isolated_mendeley["result_digest"] == mendeley["result_digest"]
    assert isolated_mendeley["result"] == mendeley["result"]
    promoted = service.promote_run_to_evidence(mendeley["id"])
    assert promoted["evidence_artifact"]["analysis_run_id"] == mendeley["id"]
    graph = service.get_lineage_graph(promoted["evidence_artifact"]["id"])
    assert any(node["id"] == mendeley["snapshot_id"] for node in graph["nodes"])
    figure = run_figure(mendeley)
    assert len(figure.axes) == 2
    assert "result_digest" in figure._dynamis_metadata["DynamisScience provenance"]
    for extension in ("png", "pdf", "svg"):
        output = export_figure(figure, tmp_path / f"result.{extension}")
        assert output.is_file() and output.stat().st_size > 0
    assert b"result_digest" in (tmp_path / "result.svg").read_bytes()

    movesmart = service.execute_analysis_run(
        realstore.STUDY_MOVESMART,
        {
            "method_id": "METH-REAL-RELIABILITY",
            "outcome_metric_id": "MET-REAL-FZ-PEAK",
            "parameters": {"activity": "Walking", "max_trials": 8},
        },
    )
    assert movesmart["status"] == "COMPLETED"
    assert movesmart["result_digest"]
    trial = service.list_signal_trials(movesmart["snapshot_id"], activity="Walking")[0]
    waveform = service.get_signal_waveform(movesmart["snapshot_id"], trial["trial_id"])
    assert waveform["source_rows"] > waveform["sample_count"]
    assert waveform["sample_count"] <= 3 * 2500
    assert waveform["series"][0]["value_column"] == "fz_n"

    study_id = next(
        study["id"]
        for study in service.list_all_studies()
        if study["id"].startswith("STUDY-U-")
        and study.get("dataset_snapshot_id") == mendeley["snapshot_id"]
    )
    authored_study = service.get_study_detail(study_id)
    plan = authored_study["plan"]
    authored_run = service.execute_analysis_run(
        study_id,
        {
            "method_id": plan["method_id"],
            "outcome_metric_id": plan["outcome_metric_id"],
            "parameters": plan.get("parameters", {}),
        },
    )
    assert authored_run["plan_alignment"] == "PLANNED"
    authored_evidence = service.promote_run_to_evidence(authored_run["id"])
    assert authored_evidence["evidence_artifact"]["analysis_run_id"] == authored_run["id"]
    service.cite_report_artifact(study_id, authored_evidence["evidence_artifact"]["id"])
    frozen = service.freeze_report(study_id)
    report_path = service.export_report_html(
        study_id, tmp_path / "frozen-report.html", frozen["version"]
    )
    report = report_path.read_text(encoding="utf-8")
    assert "frozen_content" not in report
    assert authored_run["id"] in report


def test_native_research_journey_executes_promotes_freezes_and_exports(
    qtbot, tmp_path, monkeypatch
):
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: errors.append(_args[-1]))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    root = _isolated_real_root(tmp_path)
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    service = DynamisAppService()
    study = next(
        item
        for item in service.list_all_studies()
        if item["id"].startswith("STUDY-U-")
        and item.get("dataset_snapshot_id") == "DS-REAL-MENDELEY-2C44490E08AD"
    )
    study_id = study["id"]
    detail = service.get_study_detail(study_id)
    plan = detail["plan"]
    reference_run = service.execute_analysis_run(
        study_id,
        {
            "method_id": plan["method_id"],
            "outcome_metric_id": plan["outcome_metric_id"],
            "parameters": plan.get("parameters", {}),
        },
    )
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 3)
    study_parent = window.navigator.topLevelItem(1)
    item = next(
        study_parent.child(index)
        for index in range(study_parent.childCount())
        if study_parent.child(index).data(0, Qt.ItemDataRole.UserRole)["id"] == study_id
    )
    window._navigation_activated(item, 0)
    qtbot.waitUntil(lambda: window.current_study_id == study_id)
    qtbot.waitUntil(
        lambda: window.research.method_picker.findData(plan["method_id"]) >= 0
        and window.research.analysis_metric_picker.findData(plan["outcome_metric_id"]) >= 0
    )
    assert not errors, errors

    movesmart = next(
        study
        for study in service.list_all_studies()
        if study["id"] == realstore.STUDY_MOVESMART
    )
    window._navigation_activated(
        next(
            study_parent.child(index)
            for index in range(study_parent.childCount())
            if study_parent.child(index).data(0, Qt.ItemDataRole.UserRole)["id"]
            == movesmart["id"]
        ),
        0,
    )
    qtbot.waitUntil(lambda: window.current_study_id == movesmart["id"])
    qtbot.waitUntil(lambda: window.research.trial_picker.count() > 0)
    walking = next(
        index
        for index in range(window.research.trial_picker.count())
        if "Walking" in window.research.trial_picker.itemText(index)
    )
    window.research.trial_picker.setCurrentIndex(walking)
    window.research._load_signal()
    qtbot.waitUntil(lambda: window.research.table_status.text().startswith("Signal "))
    assert window.research.signal_plot.listDataItems()
    assert not errors, errors

    window._navigation_activated(item, 0)
    qtbot.waitUntil(lambda: window.current_study_id == study_id)
    qtbot.waitUntil(
        lambda: window.research.method_picker.findData(plan["method_id"]) >= 0
        and window.research.analysis_metric_picker.findData(plan["outcome_metric_id"]) >= 0
    )

    window.research.method_picker.setCurrentIndex(
        window.research.method_picker.findData(plan["method_id"])
    )
    window.research.analysis_metric_picker.setCurrentIndex(
        window.research.analysis_metric_picker.findData(plan["outcome_metric_id"])
    )
    window.research.parameters.setPlainText(json.dumps(plan.get("parameters", {})))
    window.research._execute()
    assert window.progress.isVisible()
    qtbot.waitUntil(
        lambda: window.research.latest_run is not None or bool(errors), timeout=30000
    )
    qtbot.waitUntil(lambda: not window.runner.active)
    assert not errors, errors
    window.research._show_run_figure()
    assert window.research.run_plot.figure.axes
    assert window.research.latest_run["result_digest"] == reference_run["result_digest"]
    assert window.current_study_id == study_id

    window.research._promote()
    qtbot.waitUntil(lambda: window.research.latest_evidence_id is not None)
    window.research._cite_latest()
    qtbot.waitUntil(
        lambda: any(
            citation["artifact_id"] == window.research.latest_evidence_id
            for citation in service.get_report(study_id).get("citations", [])
        )
    )
    expected_report_version = service.get_report(study_id)["version"]
    window.research._freeze_report()
    qtbot.waitUntil(
        lambda: window.research.report_version == expected_report_version
    )

    output = tmp_path / "native-report.html"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(output), "HTML report (*.html)"),
    )
    window.research.export_report()
    qtbot.waitUntil(lambda: output.is_file())
    html = output.read_text(encoding="utf-8")
    assert window.research.latest_run["id"] in html
    assert "doi" in html.lower()
    qtbot.waitUntil(lambda: not window.runner.active)
    window.close()

    reopened = DynamisAppService().get_study_detail(study_id)
    assert any(run["id"] == window.research.latest_run["id"] for run in reopened["runs"])
    assert any(item["id"] == window.research.latest_evidence_id for item in reopened["evidence"])
    with sqlite3.connect(root / "research" / "research.db") as database:
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert service.get_report(study_id)["status"] == "FROZEN"
