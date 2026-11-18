"""Native 20-athlete RES-723 assessment and frozen-history journey."""

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from dynamis_science import admission, importer, measurement_trust as trust, reconciliation, researchstore as store
from dynamis_science.desktop.data_workspace import DataWorkspaceDialog
from dynamis_science.desktop.individual_research import RetestReviewDialog
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService
from test_measurement_trust import (
    DATED_FIELDS, FIXTURE, RETEST, SESSIONS, assessment, attach, declaration, decide, revise, visit, write_export,
)


def select_session(picker, name, revision=None):
    index = next(i for i in range(1, picker.count())
                 if picker.itemData(i)["session_id"] == name and
                 (revision is None or picker.itemData(i)["revision_id"] == revision))
    picker.setCurrentIndex(index)


def test_twenty_athletes_retest_correction_and_refusals_in_native_results(qtbot, assessment, tmp_path, monkeypatch):
    service, workspace, base, original, investigation, _ = assessment
    errors = []
    monkeypatch.setattr(QMessageBox, "exec", lambda box: errors.append(box.text()))
    trace = tmp_path / "trace.csv"
    trace.write_text("Athlete,Session,Trial,Time (s),Force (N)\n" + "\n".join(
        f"A01,Assessment,{trial},{i / 1000:.3f},{700 + i % 11}"
        for trial in ("V3-01-1", "V3-01-2") for i in range(200)), encoding="utf-8")
    staged = importer.stage(importer.edit_mapping(importer.probe_file(trace), {}, {"sampling_hz": 1000}),
                            importer.build_context(FIXTURE))
    trace_id = importer.admit(staged)["dataset_snapshot_id"]
    linked = service.attach_workspace_data(workspace, trace_id, link=True, confirm_participant_ids=True,
                                            base_revision=original)["active_data_revision_id"]
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.resize(1366, 768)
    window.show()

    def idle():
        qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)

    def show(active_window):
        active_window._show_study(workspace, active_window.service.get_study_detail(workspace))
        qtbot.waitUntil(lambda: not active_window.runner.active or bool(errors), timeout=30000)
        assert not errors
        panel = active_window.research.individual
        panel.set_investigation(workspace, investigation["id"])
        qtbot.waitUntil(lambda: (not active_window.runner.active and bool(panel.payload.get("investigation"))) or bool(errors),
                        timeout=30000)
        assert not errors
        return panel

    def prepare(panel, reference, target=SESSIONS[3]):
        panel.tabs.setCurrentIndex(1)
        index = next(i for i in range(panel.method_picker.count()) if panel.method_picker.itemData(i)["method_id"] == trust.METHOD)
        panel.method_picker.setCurrentIndex(index)
        select_session(panel.trust_reference, SESSIONS[2], reference)
        select_session(panel.trust_comparison, target)
        assert panel.run_button.isEnabled()

    def execute(panel):
        count = panel.run_picker.count()
        panel.run_button.click()
        qtbot.waitUntil(lambda: panel.run_picker.count() == count + 1 or bool(errors), timeout=30000)
        assert not errors
        result = panel.run_picker.currentData()
        assert result["method_id"] == trust.METHOD
        return result

    idle()
    panel = show(window)
    prepare(panel, base)
    failures = []

    def confirm():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, RetestReviewDialog)
            select_session(dialog.first, RETEST["first_session"])
            select_session(dialog.second, RETEST["second_session"])
            dialog.reviewer.setText(RETEST["reviewer"])
            dialog.population.setText(RETEST["population"])
            dialog.evidence.setPlainText(RETEST["design_evidence"])
            ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
            assert not ok.isEnabled()
            dialog.confirm.setChecked(True)
            assert ok.isEnabled()
            qtbot.mouseClick(ok, Qt.MouseButton.LeftButton)
        except Exception as error:
            failures.append(error)
            if dialog:
                dialog.reject()

    QTimer.singleShot(0, confirm)
    panel.trust_review.click()
    assert not failures
    qualified = execute(panel)
    assert qualified["result"]["status"] == "INTERPRETABLE"
    assert qualified["result"]["retest_evidence"]["n_pairs"] == 19
    assert qualified["result"]["observed_change"] == pytest.approx(3)
    assert qualified["data_revision_id"] == linked
    report = service.export_workspace_report(workspace, qualified["id"], str(tmp_path / "review.html"))
    frozen = report.read_bytes()
    for label in ("Observed", "Can conclude", "Cannot conclude", "Verify next"):
        assert label in panel.result_view.toPlainText()
    assert "above the matched 95% retest prediction range" in panel.result_view.toPlainText()
    panel.result_tabs.setCurrentWidget(panel.trust_sources)
    assert panel.trust_trials.rowCount() == 4
    panel.trust_trials.setCurrentCell(3, 1)
    assert panel.trust_trace.isEnabled()
    rendered = []
    timer = QTimer()
    timer.setInterval(25)

    def observe_trace():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, DataWorkspaceDialog) and dialog.signals and dialog.signals.waveform:
            rendered.append((dialog.snapshot_id, dialog.signals.trial["trial_id"], dialog.signals.waveform["source_rows"]))
            dialog.close()
            timer.stop()

    timer.timeout.connect(observe_trace)
    timer.start()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(lambda: QApplication.activeModalWidget() and QApplication.activeModalWidget().close())
    deadline.start(15000)
    try:
        panel.trust_trace.click()
        qtbot.waitUntil(lambda: bool(rendered), timeout=18000)
    finally:
        timer.stop()
        deadline.stop()
    assert rendered == [(trace_id, "V3-01-2", 200)]
    idle()

    prepare(panel, linked, SESSIONS[4])
    assert panel.trust_retest is None
    sparse = execute(panel)["result"]
    assert sparse["status"] == "NOT_ESTIMABLE" and sparse["comparison"]["n_trials"] == 1
    assert "Between-session error is unknown" in panel.result_view.toPlainText()

    row = visit(3, subjects=[1])[0]
    row[5] += 2
    proposal = reconciliation.propose(workspace, write_export(tmp_path / "correction.csv", [row], DATED_FIELDS))
    mapped = revise(proposal, declared=declaration(proposal))
    correction = decide(mapped, "APPROVED")
    amended = correction["decision"]["revision_id"]
    assert store.get_data_revision(amended)["parent_revision_id"] == linked
    reopened = MainWindow(DynamisAppService())
    qtbot.addWidget(reopened)
    reopened.resize(1366, 768)
    reopened.show()
    panel = show(reopened)
    earlier = next(i for i in range(panel.run_picker.count()) if panel.run_picker.itemData(i)["id"] == qualified["id"])
    panel.run_picker.setCurrentIndex(earlier)
    assert "earlier revision" in panel.run_picker.currentText()
    assert "+3.00 cm" in panel.result_view.toPlainText()
    prepare(panel, base)
    current = execute(panel)
    assert current["result"]["observed_change"] == pytest.approx(4)
    assert current["data_revision_id"] == amended
    assert store.get_run(qualified["id"]) == qualified and report.read_bytes() == frozen

    protocol = attach(service, workspace, write_export(tmp_path / "protocol.csv", visit(3), DATED_FIELDS),
                      {**FIXTURE, "protocol_version": "2.0"}, base_revision=amended)["active_data_revision_id"]
    panel = show(reopened)
    prepare(panel, base)
    blocked = execute(panel)["result"]
    assert blocked["status"] == "INCOMPARABLE"
    assert "athlete identity lineage" in panel.result_view.toPlainText()
    assert "protocol or sampling rate changed" in panel.result_view.toPlainText()

    rows = visit(2) + visit(3)
    rows[0][5] += 0.2
    no_units = write_export(tmp_path / "legacy.csv", rows, DATED_FIELDS)
    staged = importer.stage(importer.probe_file(no_units), importer.build_context(FIXTURE))
    metadata = {**staged["receipt"]["admission_metadata"]}
    metadata.pop("units")
    legacy = admission.admit_artifact(staged["artifact"]["id"], trust.FAMILY, metadata)["dataset_snapshot_id"]
    legacy_revision = service.attach_workspace_data(workspace, legacy, base_revision=protocol)["active_data_revision_id"]
    panel = show(reopened)
    prepare(panel, legacy_revision)
    blocked = execute(panel)["result"]
    assert blocked["status"] == "INCOMPARABLE"
    assert "canonical jump height in cm" in panel.result_view.toPlainText()

    rows = visit(2) + visit(3)
    duplicate = rows[40].copy()
    duplicate[5] += 0.1
    duplicate_revision = attach(service, workspace, write_export(tmp_path / "duplicates.csv", rows + [duplicate], DATED_FIELDS),
                                base_revision=legacy_revision)["active_data_revision_id"]
    panel = show(reopened)
    prepare(panel, duplicate_revision)
    blocked = execute(panel)["result"]
    assert blocked["status"] == "INCOMPARABLE"
    assert "quarantined trial rows" in panel.result_view.toPlainText()
    assert store.get_run(qualified["id"]) == qualified and report.read_bytes() == frozen
    reopened.close()
    window.close()
    assert not errors
