from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QUrl

from dynamis_science import admission, importer
from dynamis_science.desktop.import_review import ImportReviewDialog
from dynamis_science.desktop.services import DynamisAppService

from test_importer import FIXTURE, HEADER, ROWS, _file  # noqa: E402


@pytest.fixture
def dialog(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path / "private"))
    service = DynamisAppService()
    service.ensure_initialized()
    admitted: list[dict] = []

    def run_task(operation, on_result, label="Working"):  # synchronous stand-in for the thread pool
        on_result(operation())

    dlg = ImportReviewDialog(service, run_task, admitted.append)
    qtbot.addWidget(dlg)
    dlg.admitted = admitted
    return dlg


def _fill(dlg, with_session=True):
    dlg.privacy.setCurrentIndex(dlg.privacy.findData("TEST_FIXTURE"))
    values = {"source_name": FIXTURE["source_name"], "publisher": FIXTURE["publisher"],
              "dataset_identity": FIXTURE["dataset_identity"], "license_or_agreement": FIXTURE["license_or_agreement"],
              "redistribution_restrictions": FIXTURE["redistribution_restrictions"], "manufacturer": "Fixture",
              "model": "FP", "serial_number": "1", "protocol_name": "Fixture CMJ"}
    if with_session:
        values.update(session_id="S1", sampling_hz="1000")
    for key, text in values.items():
        dlg.edits[key].setText(text)


def test_unknown_file_review_then_admit(dialog, tmp_path):
    dialog.load(str(_file(tmp_path, "a.csv", HEADER + ROWS)))
    assert dialog.files.rowCount() == 1 and dialog.preview.rowCount() == 2
    assert "Missing" in dialog.verdict.toPlainText()  # session and sampling rate are asked for, not assumed
    assert not dialog.admit_button.isEnabled()
    _fill(dialog)
    dialog.qc_button.click()
    text = dialog.verdict.toPlainText()
    assert "QC verdict: QC passed" in text and "SYNTHETIC_ONLY" in text and "DS-ADMITTED-" in text
    assert dialog.admit_button.isEnabled()
    dialog.admit_button.click()
    assert dialog.items[0]["decision"].startswith("ADMITTED") and len(dialog.admitted) == 1
    assert not dialog.admit_button.isEnabled()
    assert dialog.admitted[0]["dataset_snapshot_id"] in {s["id"] for s in admission.list_admitted_snapshots()}


def test_invalid_file_cannot_be_admitted_and_quarantines(dialog, tmp_path):
    dialog.load(str(_file(tmp_path, "bad.csv", "Athlete,Trial,Jump Height (cm)\nA1,T1,400\nA2,T1,38\n")))
    _fill(dialog)
    dialog.qc_button.click()
    assert "REJECTED" in dialog.verdict.toPlainText() and "Not eligible" in dialog.verdict.toPlainText()
    assert not dialog.admit_button.isEnabled() and dialog.quarantine_button.isEnabled()
    dialog.quarantine_button.click()
    assert dialog.items[0]["decision"] == "QUARANTINED" and not admission.list_admitted_snapshots()


def test_saved_preset_runs_qc_automatically_and_drift_requires_review(dialog, tmp_path, monkeypatch):
    dialog.load(str(_file(tmp_path, "p1.csv", HEADER + ROWS)))
    _fill(dialog)
    dialog.qc_button.click()
    monkeypatch.setattr("dynamis_science.desktop.import_review.QInputDialog.getText", lambda *a, **k: ("Lab export", True))
    dialog.preset_button.click()
    assert "Preset saved" in dialog.verdict.toPlainText()
    for edit in dialog.edits.values():
        edit.clear()
    dialog.load(str(_file(tmp_path, "p2.csv", HEADER + "B1,T7,41,70,1500\n")))
    assert "Saved preset" in dialog.verdict.toPlainText() and "QC verdict" in dialog.verdict.toPlainText()
    assert dialog.edits["manufacturer"].text() == "Fixture" and dialog.admit_button.isEnabled()  # one click left: Admit
    dialog.load(str(_file(tmp_path, "p3.csv", HEADER.replace("Athlete", "Participant ID") + ROWS)))
    text = dialog.verdict.toPlainText()
    assert "Schema drift" in text and "QC verdict" not in text and not dialog.admit_button.isEnabled()


def test_edit_mapping_resolves_ambiguity(dialog, tmp_path, monkeypatch):
    dialog.load(str(_file(tmp_path, "m.csv", "Athlete,Trial,Jump Height,Body Mass (kg)\nA1,T1,40,80\n")))
    assert "unit is not stated" in dialog.verdict.toPlainText()
    item = dialog.items[0]
    dialog.edit_button.click.__self__  # button exists
    item["plan"] = importer.edit_mapping(item["plan"], {"jump_height_cm": {"source": "Jump Height", "unit": "cm"}})
    dialog._show(0)
    assert item["plan"]["mapping"]["columns"]["jump_height_cm"]["origin"] == "user"
    assert "unit is not stated" not in dialog.verdict.toPlainText()


def test_drop_event_loads_and_fits_small_screen(dialog, tmp_path):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QDropEvent
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(_file(tmp_path, "d.csv", HEADER + ROWS)))])
    dialog.dropEvent(QDropEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert dialog.files.rowCount() == 1
    # 1366x768 at 150% scale is a 910x512 logical desktop
    assert dialog.minimumSizeHint().width() <= 910 and dialog.minimumSizeHint().height() <= 512
    assert all(b.accessibleName() or b.text() for b in (dialog.admit_button, dialog.qc_button))
