"""RES-636 simplified native journey: real Windows Qt, disposable root, assertions and screenshots.

Usage: python scripts/res636_final_walkthrough.py <output-dir> [light|dark]
QT_SCALE_FACTOR=1.5 exercises a 910x512 logical desktop. No system keystrokes are sent.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="res636-simple-"))
os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(work / "private")
os.environ.pop("DYNAMISSCIENCE_TEST_SESSION", None)

from openpyxl import Workbook
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication
from dynamis_science import admission, importer
from dynamis_science.desktop import theme
from dynamis_science.desktop.data_workspace import DataWorkspaceDialog
from dynamis_science.desktop.import_review import ImportReviewDialog
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService

assert os.environ.get("QT_QPA_PLATFORM", "windows") != "offscreen"
app = QApplication([])
mode = sys.argv[2] if len(sys.argv) > 2 else "light"
theme.apply_theme(app, mode)
service = DynamisAppService()
window = MainWindow(service)
theme.apply_theme(app, mode)
geometry = app.primaryScreen().availableGeometry()
window.resize(min(1366, geometry.width()), min(768, geometry.height()))
window.show()
receipt = {"source": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "data_root": str(work / "private"), "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
           "theme": mode, "platform": app.platformName(), "steps": [], "stages": []}


def settle():
    deadline = time.monotonic() + 60
    while window.runner.active and time.monotonic() < deadline:
        app.processEvents()
    app.processEvents()
    assert not window.runner.active, "Worker did not finish"


def shot(widget, name):
    app.processEvents()
    widget.grab().save(str(out / (name + ".png")))
    receipt["steps"].append({"name": name, "state": getattr(widget, "state", None),
                             "size": [widget.width(), widget.height()]})


settle()
dialog = ImportReviewDialog(service, window.run_task, window._admission_saved, window)
dialog.show()
original_run = dialog.run_task


def observe(operation, done, label):
    receipt["stages"].append(label)
    assert dialog.state == "processing" and dialog.busy
    if label in ("Extracting", "Saving · writing validated records", "Integrating · checking dataset availability"):
        shot(dialog, label.split(" ·")[0].lower())
    original_run(operation, done, label)


dialog.run_task = observe
shot(dialog, "01-select")
inputs = work / "inputs"
inputs.mkdir()
headers = ["Athlete", "Trial", "Jump Height (cm)", "Body Mass (kg)", "Peak Force (N)"]
book = Workbook()
book.active.append(headers)
book.active.append(["A1", "T1", 40, 80, 1800])
book.active.append(["A2", "T2", 38, 75, 1700])
spreadsheet = inputs / "first.xlsx"
book.save(spreadsheet)
dialog.load(str(spreadsheet))
settle()
assert dialog.state == "attention" and dialog.details.isHidden()
shot(dialog, "02-specific-question")
fields = {"source_name": "Native walkthrough fixture", "publisher": "DynamisScience qualification",
          "dataset_identity": "RES-636-simple", "privacy_status": "TEST_FIXTURE",
          "license_or_agreement": "Internal fixture only", "redistribution_restrictions": "Synthetic fixture only",
          "manufacturer": "Simulated", "model": "Fixture", "serial_number": "SYNTH-636",
          "protocol_name": "Fixture CMJ", "protocol_version": "1.0", "sampling_hz": "1000"}
for _ in range(20):
    if dialog.state != "attention":
        break
    key = dialog.question_key
    if key == "privacy_status":
        dialog.answer_choice.setCurrentIndex(dialog.answer_choice.findData(fields[key]))
    else:
        dialog.answer.setText(fields[key])
    dialog.continue_button.click()
    settle()
assert dialog.state == "ready"
shot(dialog, "03-ready")
snapshot = dialog.snapshot_id
assert service.query_table(snapshot, "cmj_trials")["total_rows"] == 2
opened = []
dialog.open_dataset.connect(opened.append)
dialog.open_button.click()
assert opened == [snapshot]
workspace = DataWorkspaceDialog(service, window.run_task, window._analyze_dataset, window)
workspace.open(opened[0])
workspace.resize(min(1180, geometry.width()), min(700, geometry.height()))
workspace.show()
settle()
assert workspace.snapshot_id == snapshot and workspace.rows_model.rowCount() == 2
shot(workspace, "04-opened-records")
workspace.close()
dialog.show()
repeat = inputs / "repeat.xlsx"
book.active.cell(2, 1, "B1")
book.active.cell(3, 1, "B2")
book.save(repeat)
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(str(repeat))])
dialog.dropEvent(QDropEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
settle()
assert dialog.state == "ready" and dialog.details.isHidden()
shot(dialog, "05-drop-saved-profile")
book.active.cell(2, 1, "C1")
book.active.cell(3, 1, "C2")
book.active.cell(3, 3, 400)
book.save(inputs / "partial.xlsx")
dialog.load(str(inputs / "partial.xlsx"))
settle()
assert dialog.state == "partial"
shot(dialog, "06-partial")
dialog.details_button.click()
shot(dialog, "07-issues")
book.active.cell(2, 3, 450)
book.save(inputs / "invalid.xlsx")
dialog.load(str(inputs / "invalid.xlsx"))
settle()
assert dialog.state == "failure" and dialog.items[0]["decision"] == "QUARANTINED"
shot(dialog, "08-invalid-quarantined")
unsupported = inputs / "unsupported.bin"
unsupported.write_bytes(b"not a data table")
dialog.load(str(unsupported))
settle()
assert dialog.state == "failure"
shot(dialog, "09-unsupported")
receipt["snapshots"] = [s["id"] for s in admission.list_admitted_snapshots()]
assert len(receipt["snapshots"]) == 3
receipt["receipts"] = [{k: r[k] for k in ("raw_filename", "raw_sha256", "decision", "row_quarantine")} for r in importer.list_receipts()]
dialog.close()
window.close()
settle()
restarted = MainWindow(DynamisAppService())
restarted.resize(min(1366, geometry.width()), min(768, geometry.height()))
theme.apply_theme(app, mode)
restarted.show()
window = restarted
settle()
assert len(window.service.logical_datasets()[0]["batches"]) == 3
assert window.service.query_table(snapshot, "cmj_trials")["total_rows"] == 2
shot(window, "10-reopened")
window.close()
receipt["screenshot_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob("*.png")}
(out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps({"data_root": receipt["data_root"], "steps": len(receipt["steps"]), "snapshots": receipt["snapshots"]}))

