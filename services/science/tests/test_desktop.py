from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import polars as pl
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QTextBrowser,
)

from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.dialogs import (
    CohortDialog,
    DatasetAdmissionDialog,
    PlanDialog,
    ProjectDialog,
    StudyDialog,
)
from dynamis_science.desktop.plots import export_figure, run_figure
from dynamis_science.desktop.performance_workbench import (
    PlanDialog as PerformancePlanDialog,
    ReportDialog,
    SessionDialog,
)
from dynamis_science.desktop.performance_navigation import (
    PERFORMANCE_PAGE_KEYS,
    PERFORMANCE_PAGE_NAMES,
)
from dynamis_science.desktop.services import DynamisAppService
from dynamis_science.desktop.tasks import TaskRunner
from dynamis_science.desktop.library_dialog import ScientificLibraryDialog
from dynamis_science.desktop.lineage_dialog import LineageDialog
from dynamis_science import qualification_real, realstore, researchstore


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


def test_fixture_generator_build_override_preserves_repository_manifest(tmp_path):
    repository_manifest = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "generator_manifest.json"

    def checksum(path: Path) -> str:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()

    before = checksum(repository_manifest)
    fixture_root = tmp_path / "packaged-synthetic-fixture"
    environment = os.environ.copy()
    environment["DYNAMISSCIENCE_FIXTURE_DIR"] = str(fixture_root)
    process = subprocess.run(
        [sys.executable, "-m", "dynamis_science.generate"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert process.returncode == 0, process.stderr
    assert (fixture_root / "parquet" / "force_traces.parquet").is_file()
    assert (fixture_root / "artifacts" / "dataset_snapshot.json").is_file()
    after = checksum(repository_manifest)
    assert after == before


def test_native_entry_point_smokes_and_reopens_its_private_store(tmp_path):
    root = tmp_path / "private"
    ready_file = tmp_path / "startup-ready.txt"
    settings_file = tmp_path / "settings.json"
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="offscreen",
        DYNAMISSCIENCE_DATA_ROOT=str(root),
        DYNAMISSCIENCE_SETTINGS_FILE=str(settings_file),
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "dynamis_science.desktop",
            "--data-root",
            str(root),
            "--benchmark-ready-file",
            str(ready_file),
            "--benchmark-exit-after-ready",
            "--benchmark-performance-page",
            "today",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    assert ready_file.is_file()
    assert json.loads(settings_file.read_text(encoding="utf-8"))["data_root"] == str(root)
    with sqlite3.connect(root / "research" / "research.db") as database:
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_native_window_loads_five_workspaces_and_catalogue(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    window = MainWindow(DynamisAppService())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)

    available = window.screen().availableGeometry()
    assert window.frameGeometry().width() <= available.width()
    assert window.frameGeometry().height() <= available.height()

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
    background_mendeley = service.execute_analysis_isolated(
        realstore.STUDY_MENDELEY,
        {
            "method_id": "METH-REAL-TREND",
            "outcome_metric_id": "MET-REAL-CMJ-HEIGHT",
            "parameters": {"reference_occasion": 1, "contrast_occasion": 4},
        },
    )
    assert background_mendeley["result_digest"] == mendeley["result_digest"]
    assert background_mendeley["result"] == mendeley["result"]
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
    isolated_movesmart = service.execute_analysis_isolated(
        realstore.STUDY_MOVESMART,
        {
            "method_id": "METH-REAL-RELIABILITY",
            "outcome_metric_id": "MET-REAL-FZ-PEAK",
            "parameters": {"activity": "Walking", "max_trials": 8},
        },
    )
    assert isolated_movesmart["result_digest"] == movesmart["result_digest"]
    assert isolated_movesmart["result"] == movesmart["result"]

    rscript = os.environ.get("DYNAMISSCIENCE_RSCRIPT", "")
    if not (rscript and Path(rscript).is_file()) and shutil.which("Rscript") is None:
        pytest.skip("Independent R/lme4 MixedLM qualification is unavailable")
    raw_source = Path(r"D:\datasets\DynamisScience\extracted\zenodo-17376717\Dataset")
    if not raw_source.is_dir():
        pytest.skip("Verified MoveSmart raw signal copies are unavailable")
    raw_target = root / "extracted" / "zenodo-17376717" / "Dataset"
    signal_rows = realstore.read_table(movesmart["snapshot_id"], "signal_trials")
    prefixes = {"Walking": "walk", "Running": "run", "Heel drop": "heel", "Step drop": "drop"}
    for activity, prefix in prefixes.items():
        row = (
            signal_rows.filter(pl.col("activity") == activity)
            .sort(["subject_id", "trial_number"])
            .row(0, named=True)
        )
        files = sorted(
            raw_source.glob(
                f"{row['participant_folder']}/{prefix}{int(row['trial_number']):04d}_f_*.csv"
            )
        )
        if not files:
            pytest.skip(f"MoveSmart raw force files for {activity} are unavailable")
        destination = raw_target / row["participant_folder"]
        destination.mkdir(parents=True, exist_ok=True)
        for source_file in files:
            shutil.copy2(source_file, destination / source_file.name)

    signal_qa = service.execute_analysis_run(
        realstore.STUDY_MOVESMART,
        {
            "method_id": "METH-REAL-SIGNAL-QA",
            "outcome_metric_id": "MET-REAL-FZ-PEAK",
            "parameters": {},
        },
    )
    assert signal_qa["status"] == "COMPLETED"
    isolated_signal_qa = service.execute_analysis_isolated(
        realstore.STUDY_MOVESMART,
        {
            "method_id": "METH-REAL-SIGNAL-QA",
            "outcome_metric_id": "MET-REAL-FZ-PEAK",
            "parameters": {},
        },
    )
    assert isolated_signal_qa["result_digest"] == signal_qa["result_digest"]
    qualifications = {
        item["id"]: item for item in qualification_real.run()
    }
    for qualification_id in (
        "QUAL-REAL-MIXEDLM",
        "QUAL-REAL-RELIABILITY",
        "QUAL-REAL-SIGNAL",
    ):
        qualification = qualifications[qualification_id]
        assert qualification["status"] == "QUALIFIED", qualification
        comparisons = qualification.get("comparisons", {})
        checks = comparisons.values() if isinstance(comparisons, dict) else comparisons
        assert all(
            comparison["pass"]
            for comparison in checks
        )
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
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)
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
    citation_version = window.research.report_document_version or 0
    window.research._cite_latest()
    qtbot.waitUntil(
        lambda: (
            window.research.report_document_version is not None
            and window.research.report_document_version > citation_version
        ) or bool(errors)
    )
    qtbot.waitUntil(lambda: not window.runner.active)
    assert not errors, errors
    assert any(
        citation["artifact_id"] == window.research.latest_evidence_id
        for citation in service.get_report(study_id).get("citations", [])
    )
    window.research.report_title.setText("Native authored results")
    window.research.report_summary.setPlainText("The observed within-subject estimate is reported with its stored interval.")
    window.research.report_conclusion.setPlainText("Interpret the estimate within the single-arm observational design.")
    document_version = window.research.report_document_version
    window.research._save_report_draft()
    qtbot.waitUntil(
        lambda: (
            window.research.report_document_version is not None
            and window.research.report_document_version > document_version
        ) or bool(errors)
    )
    qtbot.waitUntil(lambda: not window.runner.active)
    assert not errors, errors
    assert service.get_report(study_id).get("summary") == "The observed within-subject estimate is reported with its stored interval."
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
    assert "Native authored results" in html
    assert "single-arm observational design" in html
    assert "doi" in html.lower()
    qtbot.waitUntil(lambda: not window.runner.active)
    window.close()

    reopened = DynamisAppService().get_study_detail(study_id)
    assert any(run["id"] == window.research.latest_run["id"] for run in reopened["runs"])
    assert any(item["id"] == window.research.latest_evidence_id for item in reopened["evidence"])
    with sqlite3.connect(root / "research" / "research.db") as database:
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert service.get_report(study_id)["status"] == "FROZEN"


def test_native_investigation_editor_and_report_version_comparison(
    qtbot, tmp_path, monkeypatch
):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    library = service.scientific_library()
    assert any(item["id"] == "MET-CMJ-IMPULSE" for item in library["metrics"])
    assert any(item["id"] == "METH-LONG" for item in library["methods"])
    assert any(item["status"] in {"PROTOTYPE", "UNAVAILABLE"} for item in library["models"])
    library_dialog = ScientificLibraryDialog(library)
    qtbot.addWidget(library_dialog)
    assert library_dialog.tabs.count() == 4
    model_records = library_dialog.sections["models"]["records"]
    model_dialog = library_dialog.sections["models"]["detail"]
    assert any(item["status"] == "UNAVAILABLE" for item in model_records)
    assert "known_limitations" in model_dialog.toPlainText()

    project = service.create_project(
        {"title": "Scratchpad UI test", "dataset_snapshot_ids": ["DS-SYNTH-001"]}
    )
    study = service.create_study(
        project["id"],
        {
            "title": "Investigation UI study",
            "research_question": "How does the measured outcome vary?",
            "dataset_snapshot_id": "DS-SYNTH-001",
            "primary_metric_id": "MET-CMJ-IMPULSE",
        },
    )["study"]
    lineage_graph = service.get_lineage_graph(study["id"])
    lineage_dialog = LineageDialog(lineage_graph)
    qtbot.addWidget(lineage_dialog)
    assert len(lineage_dialog.node_items) == len(lineage_graph["nodes"])
    assert lineage_graph["edges"]
    selected_node = lineage_graph["nodes"][-1]
    lineage_dialog.scene.clearSelection()
    lineage_dialog.node_items[selected_node["id"]].setSelected(True)
    assert selected_node["id"] in lineage_dialog.detail.toPlainText()

    report = service.update_report(study["id"], {"summary": "Initial draft"}, 1)
    first_version = service.freeze_report(study["id"])["version"]
    service.update_report(
        study["id"], {"summary": "Revised draft"}, base_version=report["version"]
    )
    second_version = service.freeze_report(study["id"])["version"]

    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    window.research.set_study(study["id"], service.get_study_detail(study["id"]))
    qtbot.waitUntil(
        lambda: window.research.investigation_editor.current is not None
        and not window.runner.active
    )
    editor = window.research.investigation_editor
    assert editor.investigations.count() == 1
    editor.block_type.setCurrentText("interpretation")
    editor._add_block()
    editor.state.setPlainText('{"note":"Review with the observed cohort only."}')
    editor._save()
    qtbot.waitUntil(
        lambda: editor.current is not None
        and editor.current["version"] == 2
        and not window.runner.active
    )
    assert editor.blocks[-1]["type"] == "interpretation"

    editor._fork_investigation()
    qtbot.waitUntil(
        lambda: editor.current is not None
        and editor.current.get("parent_id") is not None
        and not window.runner.active
    )
    assert len(service.list_investigations(study["id"])) == 2

    opened = []
    monkeypatch.setattr(QDialog, "exec", lambda dialog: opened.append(dialog) or 0)
    window._show_report_version_comparison(
        [
            service.get_report_version(study["id"], first_version),
            service.get_report_version(study["id"], second_version),
        ]
    )
    comparison = opened[0].findChild(QTextBrowser)
    assert comparison is not None
    assert "Initial draft" in comparison.toPlainText()
    assert "Revised draft" in comparison.toPlainText()
    window.close()


def test_native_project_and_study_creation_forms(qtbot, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: errors.append(_args[-1]))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)

    def create_project_form():
        dialog = next(item for item in QApplication.topLevelWidgets() if isinstance(item, ProjectDialog))
        dialog.title.setText("Native-created project")
        dialog.description.setPlainText("Created through Qt Widgets")
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(0, create_project_form)
    window._new_project()
    qtbot.waitUntil(lambda: not window.runner.active)
    assert not errors, errors
    assert window.current_target and window.current_target["type"] == "project"
    project_id = window.current_target["id"]

    def edit_project_form():
        dialog = next(item for item in QApplication.topLevelWidgets() if isinstance(item, ProjectDialog))
        dialog.title.setText("Edited native project")
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(0, edit_project_form)
    window._edit_current()
    qtbot.waitUntil(lambda: not window.runner.active)
    assert service.get_project(project_id)["title"] == "Edited native project"

    def create_study_form():
        dialog = next(item for item in QApplication.topLevelWidgets() if isinstance(item, StudyDialog))
        dialog.title.setText("Native-created study")
        dialog.question.setPlainText("Does the admitted metric change over the observed weeks?")
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(0, create_study_form)
    window._new_research_object(False)
    qtbot.waitUntil(lambda: not window.runner.active)
    assert not errors, errors
    qtbot.waitUntil(lambda: bool(window.current_study_id and window.current_study_id.startswith("STUDY-U-")))
    detail = service.get_study_detail(window.current_study_id)
    assert detail["study"]["project_id"] == project_id
    assert detail["question"]["statement"] == "Does the admitted metric change over the observed weeks?"

    def edit_study_form():
        dialog = next(item for item in QApplication.topLevelWidgets() if isinstance(item, StudyDialog))
        dialog.title.setText("Edited native study")
        dialog.question.setPlainText("How does the metric change across the observed weeks?")
        dialog.population.setText("Participants in the local admitted snapshot")
        dialog.estimand.setText("Descriptive change across observed weeks")
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(0, edit_study_form)
    window._edit_current()
    qtbot.waitUntil(lambda: not window.runner.active)
    detail = service.get_study_detail(window.current_study_id)
    assert detail["study"]["title"] == "Edited native study"
    assert detail["question"]["statement"] == "How does the metric change across the observed weeks?"
    assert detail["question"]["estimand"] == "Descriptive change across observed weeks"
    assert detail["question"]["population"] == "Participants in the local admitted snapshot"

    def create_monitoring_form():
        dialog = next(item for item in QApplication.topLevelWidgets() if isinstance(item, StudyDialog))
        dialog.title.setText("Native monitoring program")
        dialog.question.setPlainText("How does the monitoring metric vary during the period?")
        dialog.start_week.setValue(8)
        dialog.weeks.setValue(4)
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(0, create_monitoring_form)
    window._new_research_object(True)
    qtbot.waitUntil(lambda: not window.runner.active)
    assert window.current_study_id and window.current_study_id.startswith("PROG-U-")
    monitoring_id = window.current_study_id
    monitoring = service.get_study_detail(monitoring_id)
    assert monitoring["kind"] == "MONITORING"
    assert monitoring["program"]["schedule"]["start_week"] == 8
    assert monitoring["program"]["schedule"]["weeks"] == 4

    def edit_monitoring_form():
        dialog = next(item for item in QApplication.topLevelWidgets() if isinstance(item, StudyDialog))
        dialog.title.setText("Edited monitoring program")
        dialog.start_week.setValue(10)
        dialog.weeks.setValue(3)
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(0, edit_monitoring_form)
    window._edit_current()
    qtbot.waitUntil(lambda: not window.runner.active)
    updated = service.get_study_detail(monitoring_id)
    assert updated["study"]["title"] == "Edited monitoring program"
    assert updated["program"]["schedule"]["start_week"] == 10
    assert updated["program"]["schedule"]["weeks"] == 3
    assert not errors, errors
    window.close()


def test_native_admission_form_verifies_rights_runs_qc_and_admits(
    qtbot, tmp_path, monkeypatch
):
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: errors.append(_args[-1]))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    root = tmp_path / "private"
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    service = DynamisAppService()
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)
    source_file = tmp_path / "local-cmj.csv"
    dialog = DatasetAdmissionDialog(service, window.run_task, window._admission_saved, window)
    qtbot.addWidget(dialog)
    source_file.write_text(
        "subject_id,session_id,trial_id,instrument_id,protocol_id,sampling_hz,week,body_mass_kg,jump_height_cm,concentric_impulse_n_s_kg\n"
        f"P01,S01,T01,{dialog.instrument_id},{dialog.protocol_id},1000,1,80,38,1.7\n"
        f"P01,S02,T02,{dialog.instrument_id},{dialog.protocol_id},1000,2,80,39,1.8\n"
        f"P02,S01,T03,{dialog.instrument_id},{dialog.protocol_id},1000,1,75,35,1.6\n"
        f"P02,S02,T04,{dialog.instrument_id},{dialog.protocol_id},1000,2,75,36,1.7\n",
        encoding="utf-8",
    )
    dialog.source_name.setText("Native admission test")
    dialog.publisher.setText("Local test manifest")
    dialog.dataset_identity.setText("local-cmj-test-v1")
    dialog.license.setText("Test-only license terms")
    dialog.permitted_uses.setText("research testing")
    dialog.restrictions.setPlainText("Local test data; do not redistribute")
    dialog.rights_reviewed.setChecked(True)
    dialog.manufacturer.setText("Test")
    dialog.instrument_model.setText("Force plate")
    dialog.serial.setText("LOCAL-1")
    dialog.calibration.setText("CALIBRATED")
    dialog.protocol_name.setText("CMJ protocol")
    dialog.file_path.setText(str(source_file))
    dialog.show()
    dialog.review_button.click()
    qtbot.waitUntil(lambda: dialog.quality is not None or bool(errors), timeout=30000)
    assert not errors, errors
    assert dialog.quality["status"] in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
    dialog.admit_button.click()
    qtbot.waitUntil(
        lambda: any(item.get("dataset_snapshot_id") for item in service.list_admission_records()),
        timeout=30000,
    )
    qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    record = service.list_admission_records()[-1]
    assert record["dataset_snapshot_id"]
    admitted = service.get_dataset_detail(record["dataset_snapshot_id"])
    assert admitted["source"]["rights_status"] == "VERIFIED"
    assert any(item["id"] == record["dataset_snapshot_id"] for item in service.list_datasets())
    dialog.close()
    window.close()


def test_native_cohort_and_plan_forms_support_freeze_fork_and_history(
    qtbot, tmp_path, monkeypatch
):
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: errors.append(_args[-1]))
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: errors.append(_args[-1]))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    service.ensure_initialized()
    project = service.create_project({"title": "Cohort and plan UI test"})
    detail = service.create_study(
        project["id"],
        {
            "title": "Authored cohort study",
            "research_question": "How does impulse vary across observed weeks?",
            "dataset_snapshot_id": "DS-SYNTH-001",
            "primary_metric_id": "MET-CMJ-IMPULSE",
        },
    )
    study_id = detail["study"]["id"]
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)
    item = next(
        window.navigator.topLevelItem(1).child(index)
        for index in range(window.navigator.topLevelItem(1).childCount())
        if window.navigator.topLevelItem(1).child(index).data(0, Qt.ItemDataRole.UserRole)["id"] == study_id
    )
    window._navigation_activated(item, 0)
    qtbot.waitUntil(lambda: window.current_study_id == study_id)

    def save_cohort_dialog():
        dialog = next(item for item in QApplication.topLevelWidgets() if isinstance(item, CohortDialog))
        dialog.name.setText("Saved native cohort")
        dialog.description.setText("Cohort authored in Qt")
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(0, save_cohort_dialog)
    window._new_cohort()
    qtbot.waitUntil(lambda: not window.runner.active)
    cohorts = service.list_cohorts(study_id)
    created_cohort = cohorts[-1]
    assert created_cohort["name"] == "Saved native cohort"

    window._freeze_cohort()
    qtbot.waitUntil(lambda: service.get_cohort(created_cohort["id"])["status"] == "FROZEN")
    qtbot.waitUntil(lambda: not window.runner.active)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs: ("Forked cohort", True))
    window._fork_cohort()
    qtbot.waitUntil(lambda: len(service.list_cohorts(study_id)) == len(cohorts) + 1)
    qtbot.waitUntil(lambda: not window.runner.active)
    forked_cohort = service.list_cohorts(study_id)[-1]
    assert forked_cohort["parent_id"] == created_cohort["id"]

    def save_plan_dialog():
        dialog = next(
            (item for item in QApplication.topLevelWidgets() if isinstance(item, PlanDialog)),
            None,
        )
        if dialog is None:
            QTimer.singleShot(25, save_plan_dialog)
            return
        dialog.name.setText("Native frozen plan")
        dialog.cohort.setCurrentIndex(dialog.cohort.findData(created_cohort["id"]))
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(0, save_plan_dialog)
    window._new_plan()
    qtbot.waitUntil(lambda: not window.runner.active)
    plan = service.list_plans(study_id)[-1]
    assert plan["name"] == "Native frozen plan"
    window._freeze_plan()
    qtbot.waitUntil(lambda: service.get_plan(plan["id"])["status"] == "FROZEN")
    qtbot.waitUntil(lambda: not window.runner.active)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs: ("Forked plan", True))
    window._fork_plan()
    qtbot.waitUntil(lambda: len(service.list_plans(study_id)) >= 3)
    qtbot.waitUntil(lambda: not window.runner.active)
    forked_plan = service.list_plans(study_id)[-1]
    assert forked_plan["parent_id"] == plan["id"]
    assert service.cohort_history(created_cohort["id"])
    assert service.plan_history(plan["id"])
    assert not errors, errors
    qtbot.waitUntil(lambda: not window.runner.active)
    window.close()


def test_performance_direct_service_preserves_records_and_science(tmp_path, monkeypatch):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    overview = service.performance_page_data("today")
    assert overview["today"]["pulse"]["readiness"] == pytest.approx(7.091, abs=0.001)
    assert overview["today"]["data_quality"]["valid_trials"] == 883
    assert len(overview["athletes"]) == 28

    athlete = service.performance_athlete("ATH-003")
    assert len(athlete["weeks"]) == 16
    assert athlete["availability"]["status"] == "ROSTER_ONLY"
    assert athlete["force_trial_id"] == "CMJ-003-16-1"

    plan = service.performance_page_data("plan")["plan"]
    next_week = plan["current_week"] + 1
    next_microcycle = next(row for row in plan["microcycles"] if row["week"] == next_week)
    updated = service.performance_update_plan(
        {
            "week": next_week,
            "focus": "Native editor persistence check",
            "testing_window": next_microcycle.get("testing_window", ""),
            "sessions": next_microcycle["sessions"],
        }
    )
    assert updated["microcycles"][1]["focus"] == "Native editor persistence check"
    assert service.performance_log_session(
        {
            "date": "2026-11-07",
            "session_type": "Field",
            "duration_min": 60,
            "session_rpe": 5,
            "attendance": 27,
        }
    )["srpe_load_au"] == 300

    assessment = service.performance_run_reliability()
    assert assessment["status"] == "COMPUTED"
    assert assessment["provenance"]["snapshot_id"] == "DS-SYNTH-001"
    report = service.performance_create_report({"audience": "coach", "role": "Test coach"})
    frozen = service.performance_freeze_report(report["id"])
    assert frozen["status"] == "FROZEN"
    exported = service.performance_export_report(report["id"], tmp_path / "coach-report.html")
    assert "DS-SYNTH-001" in exported.read_text(encoding="utf-8")

    match = service.performance_page_data("match")
    assert match["movement"]["scope"] == "SEGMENT_ONLY"
    frame = service.performance_match_frame(900, "PLAYER-14")
    assert len(frame["tracking"]) >= 20
    assert len(frame["pose"]) > 0
    assert len(service.performance_tracking("PLAYER-14")["rows"]) == 1800
    assert len(service.performance_page_data("research")["metrics"]) >= 1
    with pytest.raises(ValueError, match="Unknown Performance OS workspace"):
        service.performance_page_data("unknown")


def test_performance_domain_imports_without_http_or_webengine():
    service_root = Path(__file__).resolve().parents[1]
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from dynamis_science import performance; "
            "assert 'fastapi' not in sys.modules; "
            "assert 'uvicorn' not in sys.modules; "
            "assert not any(name.startswith('PySide6.QtWebEngine') for name in sys.modules)",
        ],
        cwd=service_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr


def test_native_performance_os_workspaces_load_without_errors(qtbot, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: errors.append(_args[-1]))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    window = MainWindow(DynamisAppService())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)
    performance_root = window.navigator.topLevelItem(3)
    assert performance_root.childCount() == len(PERFORMANCE_PAGE_NAMES)
    for index, page in enumerate(PERFORMANCE_PAGE_KEYS):
        item = performance_root.child(index)
        window._navigation_activated(item, 0)
        qtbot.waitUntil(lambda page=page: page in window.performance.loaded_pages)
        qtbot.waitUntil(lambda: not window.runner.active)
        assert window.performance.current_page == page
    qtbot.waitUntil(lambda: window.performance.test_model.rowCount() > 0)
    qtbot.waitUntil(lambda: window.performance.event_model.rowCount() > 0)
    qtbot.waitUntil(lambda: not window.runner.active)
    assert window.performance.tabs.count() == 8
    assert window.performance.athlete_trend.plotItem.listDataItems()
    assert window.performance.match_field.plotItem.listDataItems()
    assert window.performance.pose_plot.plotItem.listDataItems()
    window.show_performance_page("today")
    qtbot.waitUntil(lambda: not window.runner.active)
    assert {key: button.accessibleName() for key, button in window.performance_rail.buttons.items()} == {
        "today": "Today", "plan": "Plan", "monitor": "Monitor", "test": "Test",
        "research": "Research", "report": "Reports",
    }
    assert window.performance.context_panel.injury.wordWrap()
    assert window.performance.context_panel.movement.wordWrap()
    window.performance._open_selected_athlete()
    qtbot.waitUntil(
        lambda: window.performance.context_panel.views.currentWidget()
        is window.performance.context_panel.athlete_view
    )
    assert window.performance.current_page == "today"
    assert window.inspector_dock.windowTitle() == "ATHLETE 360"
    qtbot.waitUntil(lambda: not window.runner.active)
    window._show_daily_context()
    assert window.inspector_dock.windowTitle() == "DAILY CONTEXT"
    assert not errors, errors
    window.close()


def test_native_performance_operations_edit_monitor_and_reports(qtbot, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: errors.append(_args[-1]))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)
    performance_root = window.navigator.topLevelItem(3)

    window._navigation_activated(performance_root.child(3), 0)
    qtbot.waitUntil(lambda: "monitor" in window.performance.loaded_pages)
    qtbot.waitUntil(lambda: not window.runner.active)
    def save_session(dialog):
        dialog.notes.setText("Native session entry")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SessionDialog, "exec", save_session)
    window.performance._log_session()
    qtbot.waitUntil(lambda: not window.runner.active)
    monitor = service.performance_page_data("monitor")["load"]
    assert monitor["session_logs"][-1]["notes"] == "Native session entry"

    window._navigation_activated(performance_root.child(1), 0)
    qtbot.waitUntil(lambda: bool(window.performance.athlete_trend.plotItem.listDataItems()))
    qtbot.waitUntil(lambda: not window.runner.active)
    athlete_index = window.performance.athlete_picker.findText("ATH-003")
    window.performance.athlete_picker.setCurrentIndex(athlete_index)
    qtbot.waitUntil(lambda: not window.runner.active)
    monkeypatch.setattr(
        QInputDialog,
        "getMultiLineText",
        lambda *_args: ("Native practitioner note", True),
    )
    window.performance._add_athlete_note()
    qtbot.waitUntil(lambda: not window.runner.active)
    assert service.performance_athlete("ATH-003")["notes"][-1]["text"] == "Native practitioner note"

    window._navigation_activated(performance_root.child(2), 0)
    qtbot.waitUntil(lambda: bool(window.performance.plan_chart.plotItem.listDataItems()))
    qtbot.waitUntil(lambda: not window.runner.active)
    def save_plan(dialog):
        dialog.focus.setText("Native microcycle editor")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PerformancePlanDialog, "exec", save_plan)
    window.performance._edit_plan()
    qtbot.waitUntil(lambda: not window.runner.active)
    window.performance._publish_plan()
    qtbot.waitUntil(lambda: not window.runner.active)
    plan = service.performance_page_data("plan")["plan"]
    assert plan["status"] == "PUBLISHED"
    assert plan["microcycles"][1]["focus"] == "Native microcycle editor"

    window._navigation_activated(performance_root.child(7), 0)
    qtbot.waitUntil(lambda: "report" in window.performance.loaded_pages)
    qtbot.waitUntil(lambda: not window.runner.active)
    monkeypatch.setattr(
        ReportDialog,
        "exec",
        lambda dialog: (dialog.role.setText("Native report author"), QDialog.DialogCode.Accepted)[1],
    )
    window.performance._create_report()
    qtbot.waitUntil(lambda: not window.runner.active)
    reports = service.performance_page_data("report")["reports"]
    assert reports
    preview = window.performance.report_preview.toPlainText()
    assert reports[-1]["title"] in preview
    assert reports[-1]["sections"][0]["body"][0] in preview
    assert reports[-1]["limitations"][0] in preview
    report_id = window.performance.selected_report_id
    window.performance._freeze_report()
    qtbot.waitUntil(lambda: not window.runner.active)
    assert next(item for item in service.performance_page_data("report")["reports"] if item["id"] == report_id)["status"] == "FROZEN"
    output = tmp_path / "practitioner-report.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(output), "HTML report (*.html)"))
    window.performance._export_report()
    qtbot.waitUntil(output.is_file)
    qtbot.waitUntil(lambda: not window.runner.active)
    assert "DS-SYNTH-001" in output.read_text(encoding="utf-8")
    assert not errors, errors
    window.close()


def test_native_database_tools_verify_backup_and_restore_safely(qtbot, tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append(_args[-1]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: pytest.fail(str(_args[-1])))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    root = tmp_path / "private"
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(root))
    service = DynamisAppService()
    project = service.create_project({"title": "Backup rehearsal test"})
    detail = service.create_study(
        project["id"],
        {
            "title": "Restore verification study",
            "research_question": "Does the temporary restore preserve the audit trail?",
            "dataset_snapshot_id": "DS-SYNTH-001",
            "primary_metric_id": "MET-CMJ-IMPULSE",
        },
    )
    study_id = detail["study"]["id"]
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)
    qtbot.waitUntil(lambda: not window.runner.active)
    original = service.verify_research_database()
    window._backup_research_database()
    qtbot.waitUntil(lambda: not window.runner.active)
    backups = list((root / "backups").glob("research-*.sqlite3"))
    assert len(backups) == 1
    assert any("Verified online backup created" in message for message in messages)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(backups[0]), "SQLite backups"))
    window._rehearse_research_restore()
    qtbot.waitUntil(lambda: not window.runner.active)
    assert any("restored into an isolated private copy" in message for message in messages)
    assert service.verify_research_database()["logical_sha256"] == original["logical_sha256"]
    restored = next((root / "tmp").glob("restore-*/research/research.db"))
    assert restored.is_file()
    assert service.get_study_detail(study_id)["study"]["id"] == study_id
    window.close()


def test_native_qualification_action_reports_an_honest_empty_state(qtbot, tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append(_args[-1]))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    window = MainWindow(DynamisAppService())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.navigator.topLevelItemCount() == 4)
    window.action_run_qualification.trigger()
    qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    assert any("No admitted real-data snapshots" in message for message in messages)
    window.close()
