"""Executable 20-athlete researcher journey through the native review and Analysis controls."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QMessageBox, QPushButton

from dynamis_science import reconciliation, researchstore
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.reconciliation_review import ContextEditor, IdentityEditor, ReconciliationReview
from dynamis_science.desktop.services import DynamisAppService
from dynamis_science.qa_cleanup import read_marker
from test_reconciliation import FOLLOWUP_FIELDS, followup_rows, setup, write_export  # noqa: F401


def test_native_reconcile_twenty_athletes(qtbot, setup, tmp_path, monkeypatch, capsys):  # noqa: F811
    service, identity, source, first = setup
    initial_revision = first["active_data_revision_id"]
    baseline_run = service.execute_analysis_run(identity, {"data_revision_id": initial_revision,
        "method_id": "METH-U-DESC", "outcome_metric_id": "MET-CMJ-HEIGHT", "parameters": {}})
    report = service.export_workspace_report(identity, baseline_run["id"], str(tmp_path / "baseline.html"))
    frozen = report.read_bytes()
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: errors.append(text))
    monkeypatch.setattr(QMessageBox, "exec", lambda box: errors.append(box.text()))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.resize(1366, 768)
    window.show()

    def capture(widget, filename):
        run_root = os.environ.get("DYNAMISSCIENCE_QA_RUN_ROOT")
        if run_root and read_marker(run_root)["issue_id"] == "RES-722":
            assert widget.grab().save(str(Path(run_root) / filename))

    def idle():
        qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)

    def click(button):
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    idle()
    window._show_study(identity, service.get_study_detail(identity))
    idle()
    rows = followup_rows()
    rows.append(["A01", "Baseline renamed", "B01", 1, 1000, 310, 73, 1601, "v2"])
    followup = write_export(tmp_path / "followup.csv", rows, FOLLOWUP_FIELDS)
    duplicate = tmp_path / "copied-baseline.csv"
    duplicate.write_bytes(source.read_bytes())
    unsafe = write_export(tmp_path / "protocol-change.csv",
                          [row + ["OTHER-PROTOCOL"] for row in followup_rows()], FOLLOWUP_FIELDS + ["Protocol"])
    export = {"path": duplicate}
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(export["path"]), ""))

    def get_review():
        return QApplication.activeModalWidget().findChild(ReconciliationReview)

    def loaded(review):
        qtbot.waitUntil(lambda: not review.busy, timeout=30000)

    def choose(review, path):
        export["path"] = path
        click(review.choose)
        loaded(review)

    def decision(review, button, text):
        review.reviewer.setText("Fixture reviewer")
        review.reason.setText(text)
        assert button.isEnabled()
        click(button)
        loaded(review)

    def accept_editor(dialog_type, fill):
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, dialog_type)
        fill(dialog)
        click(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok))

    def confirm_context(dialog):
        button = next(btn for btn in dialog.findChildren(QPushButton) if btn.text() == "Use IDs from reference")
        click(button)

    def map_identities(dialog):
        dialog.controls["athletes", "A07-renamed"].setCurrentText("A07")
        dialog.controls["sessions", "Week 12 export"].setCurrentText("Follow-up")
        dialog.controls["sessions", "Baseline renamed"].setCurrentText("Baseline")

    completed = []
    after = {}

    def review_journey():
        try:
            review = get_review()
            loaded(review)
            assert review.history.count() == 0
            choose(review, duplicate)
            assert "duplicate file" in review.differences.item(0, 0).text().lower()
            decision(review, review.reject, "Identical SHA-256 to the admitted baseline.")
            assert review.entry["state"] == "REJECTED"
            choose(review, unsafe)
            assert any("Protocol drift" in review.differences.item(i, 0).text()
                       for i in range(review.differences.rowCount()))
            assert not review.approve.isEnabled()
            decision(review, review.quarantine, "Testing protocol differs from baseline.")
            assert review.entry["state"] == "QUARANTINED"
            choose(review, followup)
            assert {"source_schema", "unit_change", "athlete_identity", "session_identity"} <= {
                row["kind"] for row in review.entry["discrepancies"]}
            capture(QApplication.activeModalWidget(), "res722-01-review.png")
            QTimer.singleShot(0, lambda: accept_editor(IdentityEditor, map_identities))
            click(review.identity)
            loaded(review)
            QTimer.singleShot(0, lambda: accept_editor(ContextEditor, confirm_context))
            click(review.declare)
            loaded(review)
            assert review.entry["ready"] and review.qc.rowCount() == 2
            assert review.entry["counts"] == {"new": 20, "duplicate": 0, "correction": 1}
            assert any(review.measurements.item(i, 3).text() == "Correction" for i in range(review.measurements.rowCount()))
            decision(review, review.approve, "Checked roster, session log and the source's millimetre header.")
            assert review.entry["state"] == "APPROVED"
            after.update(review.entry)
            review.tables.setCurrentWidget(review.measurements)
            capture(QApplication.activeModalWidget(), "res722-02-approved.png")
            choose(review, followup)
            assert review.status.text().startswith("Duplicate file")
            assert review.entry["decision"] == after["decision"]
            assert review.history.count() == 8  # rejected and quarantined versions, three proposals and approval
            click(review.analyze)
            completed.append(True)
        finally:
            widget = QApplication.activeModalWidget()
            if widget and widget.findChild(ReconciliationReview):
                widget.close()

    QTimer.singleShot(0, review_journey)
    window.workspace_actions["Add data"].trigger()
    assert completed
    idle()
    revision = after["decision"]["revision_id"]
    assert window.current_study_id == identity and window.current_study["active_data_revision_id"] == revision
    assert len(researchstore.data_revisions(identity)) == 2
    assert report.read_bytes() == frozen
    assert Path(after["raw_path"]).read_bytes() == followup.read_bytes()
    assert [item["id"] for item in researchstore.list_entities(kind="STUDY")] == [identity]
    window.close()
    idle()

    reopened = MainWindow(DynamisAppService())
    qtbot.addWidget(reopened)
    reopened.show()
    qtbot.waitUntil(lambda: not reopened.runner.active, timeout=30000)
    reopened._show_study(identity, reopened.service.get_study_detail(identity))
    qtbot.waitUntil(lambda: not reopened.runner.active, timeout=30000)
    reopened.workspace_actions["Analyze"].trigger()
    panel = reopened.research
    panel.method_picker.setCurrentIndex(panel.method_picker.findData("METH-U-DESC"))
    qtbot.waitUntil(lambda: panel.execute_button.isEnabled(), timeout=30000)
    click(panel.execute_button)
    qtbot.waitUntil(lambda: panel.latest_run is not None and panel.latest_run["data_revision_id"] == revision, timeout=30000)
    result = panel.latest_run["result"]
    assert result["n_subjects"] == 20
    assert {int(row["week"]) for row in result["points"]} == {1, 12}
    assert {row["week"]: row["mean"] for row in result["points"]} == pytest.approx({1: 35.275, 12: 37.25})
    assert result["n_observations"] == 40
    assert len(reconciliation.history(identity)) == 8
    qtbot.waitUntil(lambda: not reopened.runner.active, timeout=30000)
    capture(reopened, "res722-03-analysis.png")
    reopened.close()
    assert not errors, errors
    with capsys.disabled():
        print("RES-722 native: reject duplicate → quarantine protocol → map A07 and two session IDs → "
              "confirm source context → approve 20 new trials and one correction → reopen same workspace → "
              f"run descriptives (20 athletes, 40 trials, weekly means 35.275 and 37.25 cm). "
              f"Batch {after['id']} / revision {revision} / run {panel.latest_run['id']}.")
