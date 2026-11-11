from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QDropEvent

from dynamis_science import admission, importer
from dynamis_science.desktop.import_review import ImportReviewDialog
from dynamis_science.desktop.services import DynamisAppService
from dynamis_science.desktop.tasks import TaskRunner

from test_importer import FIXTURE, HEADER, ROWS, _file


@pytest.fixture
def dialog(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    service.ensure_initialized()
    admitted = []
    dlg = ImportReviewDialog(service, lambda op, done, label: done(op()), admitted.append)
    qtbot.addWidget(dlg)
    dlg.admitted = admitted
    return dlg


def _preset(tmp_path, name="seed.csv", fields=None):
    path = _file(tmp_path, name, HEADER + ROWS)
    plan = importer.edit_mapping(importer.probe_file(path), {}, {"sampling_hz": "1000"})
    plan = importer.edit_mapping(plan, {}, {"sampling_hz": "1000", "session_id": "seed"})
    importer.save_preset("Lab export", plan, importer.build_context(fields or FIXTURE))
    return path


def _fill(dlg):
    dlg._fill_form(FIXTURE)
    dlg.edits["sampling_hz"].setText("1000")


def test_initial_surface_is_simple_accessible_and_compact(dialog):
    assert dialog.state == "select" and dialog.heading.text() == "Import your data"
    assert dialog.details.isHidden() and dialog.question_box.isHidden() and dialog.progress.isHidden()
    assert not dialog.drop.isHidden() and dialog.file_button.isDefault()
    assert dialog.minimumSizeHint().width() <= 910 and dialog.minimumSizeHint().height() <= 512
    assert dialog.file_button.text() and dialog.drop.accessibleName()


def test_saved_profile_runs_all_stages_then_opens_actual_dataset(dialog, tmp_path):
    path = _preset(tmp_path)
    labels = []
    def run(op, done, label):
        labels.append(label)
        assert dialog.state == "processing" and dialog.busy and dialog.open_button.isHidden()
        assert dialog.progress.minimum() == dialog.progress.maximum() == 0
        done(op())
    dialog.run_task = run
    dialog.load(str(path))
    assert dialog.state == "ready" and dialog.heading.text() == "Your data is ready."
    assert "2 records imported" in dialog.summary.text() and "Synthetic" in dialog.summary.text()
    assert [label.split(" ·")[0] for label in labels] == ["Extracting", "Validating", "Validating", "Saving", "Integrating"]
    assert dialog.details.isHidden() and len(dialog.admitted) == 1
    snapshot = dialog.snapshot_id
    assert snapshot in {d["id"] for d in dialog.service.list_workspace()}
    result = dialog.service.query_table(snapshot, "cmj_trials")
    assert result["total_rows"] == 2
    opened = []
    dialog.open_dataset.connect(opened.append)
    dialog.open_button.click()
    assert opened == [snapshot]


def test_first_file_asks_one_question_and_keeps_original(dialog, tmp_path):
    path = _file(tmp_path, "first.csv", HEADER + ROWS)
    dialog.load(str(path))
    assert dialog.state == "attention" and dialog.question_key == "privacy_status"
    assert dialog.details.isHidden() and not admission.list_admitted_snapshots()
    staged = Path(dialog.items[0]["plan"]["path"])
    assert staged.read_bytes() == path.read_bytes()
    path.unlink()
    answers = dict(FIXTURE, sampling_hz="1000")
    for _ in range(20):
        if dialog.state != "attention":
            break
        key = dialog.question_key
        if key == "privacy_status":
            dialog.answer_choice.setCurrentIndex(dialog.answer_choice.findData(answers[key]))
        else:
            dialog.answer.setText(answers[key])
        dialog.continue_button.click()
    assert dialog.state == "ready" and staged.exists()
    assert len(dialog.admitted) == 1


def test_partial_import_retains_bad_rows_and_optional_issues(dialog, tmp_path):
    _preset(tmp_path)
    dialog.load(str(_file(tmp_path, "mixed.csv", HEADER + "A1,T1,40,80,1800\nA2,T2,400,75,1700\n")))
    assert dialog.state == "partial" and "1 record imported" in dialog.summary.text()
    assert "1 record quarantined" in dialog.summary.text() and dialog.details.isHidden()
    quarantine = dialog.items[0]["staged"]["receipt"]["row_quarantine"]
    assert Path(quarantine["file"]).exists() and quarantine["count"] == 1
    dialog.details_button.click()
    assert not dialog.details.isHidden() and "implausible" in dialog.verdict.toPlainText()


def test_invalid_file_quarantines_without_success(dialog, tmp_path):
    _preset(tmp_path)
    dialog.load(str(_file(tmp_path, "invalid.csv", HEADER + "A1,T1,400,80,1800\nA2,T1,38,75,1700\n")))
    assert dialog.state == "failure" and dialog.items[0]["decision"] == "QUARANTINED"
    assert dialog.open_button.isHidden() and not admission.list_admitted_snapshots()
    assert importer.list_receipts()[0]["decision"] == "QUARANTINED"


def test_unsupported_and_empty_folder_offer_reselection(dialog, tmp_path):
    dialog.load(str(_file(tmp_path, "invalid.bin", "unsupported")))
    assert dialog.state == "failure" and not dialog.another_button.isHidden()
    folder = tmp_path / "empty"
    folder.mkdir()
    dialog.load(str(folder))
    assert dialog.state == "failure" and "No supported files" in dialog.summary.text()


@pytest.mark.parametrize("operation", ["prepare_import", "stage", "admit"])
def test_worker_failure_preserves_diagnostics_and_retry(dialog, tmp_path, monkeypatch, operation):
    path = _preset(tmp_path)
    original = getattr(importer, operation)
    def fail(*args, **kwargs):
        raise OSError("disposable storage failure")
    monkeypatch.setattr(importer, operation, fail)
    dialog.load(str(path))
    assert dialog.state == "failure" and not dialog.busy
    assert "disposable storage failure" in dialog.verdict.toPlainText()
    assert dialog.open_button.isHidden() and not admission.list_admitted_snapshots()
    monkeypatch.setattr(importer, operation, original)
    dialog.retry_button.click()
    assert dialog.state == "ready"


def test_catalogue_failure_never_shows_ready_and_retry_is_idempotent(dialog, tmp_path, monkeypatch):
    path = _preset(tmp_path)
    original = dialog.service.list_workspace
    monkeypatch.setattr(dialog.service, "list_workspace", lambda: [])
    dialog.load(str(path))
    assert dialog.state == "failure" and dialog.open_button.isHidden()
    assert len(admission.list_admitted_snapshots()) == 1
    monkeypatch.setattr(dialog.service, "list_workspace", original)
    dialog.retry_button.click()
    assert dialog.state == "ready" and len(admission.list_admitted_snapshots()) == 1


def test_drop_and_picker_start_import_without_extra_click(dialog, tmp_path, monkeypatch):
    path = _preset(tmp_path)
    monkeypatch.setattr("dynamis_science.desktop.import_review.QFileDialog.getOpenFileName", lambda *a: (str(path), ""))
    dialog.file_button.click()
    assert dialog.state == "ready"
    dialog.another_button.click()
    assert dialog.state == "select" and not dialog.items
    path = _file(tmp_path, "second.csv", HEADER + "B1,T7,41,70,1500\n")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = QDropEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    dialog.dropEvent(event)
    assert dialog.state == "ready" and event.isAccepted()
    assert dialog.service.logical_datasets()[0]["row_counts"] == {"cmj_trials": 3}


def test_missing_rate_recovery_and_no_unrelated_last_profile(dialog, tmp_path):
    _preset(tmp_path)
    path = _file(tmp_path, "different.csv", HEADER.replace("Jump Height (cm)", "Jump Height (m)") + "C1,T1,0.4,80,1800\n")
    dialog.load(str(path))
    assert dialog.state == "attention" and dialog.question_key == "privacy_status"
    _fill(dialog)
    dialog.edits["sampling_hz"].clear()
    dialog._continue_import()
    assert dialog.question_key == "mapping"
    dialog.items[0]["mapping_confirmed"] = True
    dialog._continue_import()
    assert dialog.question_key == "sampling_hz" and not admission.list_admitted_snapshots()
    dialog.answer.setText("1000")
    dialog.continue_button.click()
    assert dialog.state == "ready"


def test_actual_worker_keeps_event_loop_responsive_and_blocks_reentry(dialog, tmp_path, qtbot):
    path = _preset(tmp_path)
    runner = TaskRunner(dialog)
    dialog.run_task = lambda op, done, label: runner.submit(op, done, lambda error: pytest.fail(str(error)))
    ticks = []
    timer = QTimer(dialog)
    timer.setInterval(1)
    timer.timeout.connect(lambda: ticks.append(dialog.state))
    timer.start()
    dialog.load(str(path))
    assert dialog.busy
    dialog.reject()
    assert dialog.result() != dialog.DialogCode.Rejected or dialog.busy
    first_path = dialog.input_path
    dialog.load("ignored.csv")
    assert dialog.input_path == first_path
    qtbot.waitUntil(lambda: dialog.state == "ready", timeout=20000)
    qtbot.waitUntil(lambda: not runner.active, timeout=10000)
    timer.stop()
    assert "processing" in ticks and not dialog.busy


def test_real_rights_require_specific_confirmation(dialog, tmp_path):
    path = _preset(tmp_path, fields={**FIXTURE, "privacy_status": "DEIDENTIFIED", "calibration_status": "CALIBRATED"})
    dialog.load(str(path))
    assert dialog.state == "attention" and dialog.question_key == "rights"
    assert dialog.details.isHidden() and not admission.list_admitted_snapshots()
    dialog.continue_button.click()
    assert dialog.state == "ready" and dialog.items[0]["staged"]["rights_status"] == "VERIFIED"
    assert "Synthetic" not in dialog.summary.text()


def test_folder_uses_each_files_authorized_source_context(dialog, tmp_path):
    folder = tmp_path / "inputs"
    folder.mkdir()
    _preset(folder)
    second = _file(folder, "other.csv", HEADER.replace("Jump Height (cm)", "Jump Height (m)") + "B1,T1,0.4,80,1800\n")
    plan = importer.edit_mapping(importer.probe_file(second), {}, {"sampling_hz": "1000", "session_id": "S2"})
    importer.save_preset("Other lab", plan, importer.build_context({**FIXTURE, "source_name": "Other lab", "serial_number": "2"}))
    dialog.load(str(folder))
    assert dialog.state == "ready" and len(dialog.admitted) == 2
    assert len(dialog.service.logical_datasets()) == 2
    sources = {r["source_id"] for r in importer.list_receipts()}
    assert len(sources) == 2


def test_new_service_reopens_durable_import(dialog, tmp_path):
    path = _preset(tmp_path)
    dialog.load(str(path))
    reopened = DynamisAppService()
    reopened.ensure_initialized()
    assert reopened.query_table(dialog.snapshot_id, "cmj_trials")["total_rows"] == 2


def test_main_window_open_dataset_navigates_to_selected_workspace(dialog, tmp_path, qtbot, monkeypatch):
    from dynamis_science.desktop.data_workspace import DataWorkspaceDialog
    from dynamis_science.desktop.main_window import MainWindow
    path = _preset(tmp_path)
    main = MainWindow(dialog.service)
    qtbot.addWidget(main)
    qtbot.waitUntil(lambda: not main.runner.active, timeout=20000)
    selected = []

    def workspace_exec(workspace):
        qtbot.waitUntil(lambda: workspace.rows_model.rowCount() == 2, timeout=20000)
        selected.append(workspace.snapshot_id)
        workspace.close()
        return 0

    def import_exec(import_dialog):
        import_dialog.load(str(path))
        qtbot.waitUntil(lambda: import_dialog.state == "ready", timeout=20000)
        import_dialog.open_button.click()
        return 0

    monkeypatch.setattr(DataWorkspaceDialog, "exec", workspace_exec)
    monkeypatch.setattr(ImportReviewDialog, "exec", import_exec)
    main._open_import()
    qtbot.waitUntil(lambda: not main.runner.active, timeout=20000)
    assert len(selected) == 1 and selected[0].startswith("DS-ADMITTED-")


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_theme_and_small_logical_desktop(dialog, qapp, mode):
    from dynamis_science.desktop import theme
    theme.apply_theme(qapp, mode)
    dialog.resize(680, 400)
    dialog.show()
    assert dialog.minimumSizeHint().width() <= 910 and dialog.minimumSizeHint().height() <= 512
    assert dialog.file_button.isVisible() and not dialog.detail_tabs.isVisible()
    dialog.move(100, 300)
    dialog.details_button.click()
    qapp.processEvents()
    assert dialog.screen().availableGeometry().contains(dialog.frameGeometry())
    theme.apply_theme(qapp, "light")

