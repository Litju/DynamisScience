"""RES-644 real Windows Qt journey on disposable synthetic data. Never uses the installed app.

uv run python scripts/res644_walkthrough.py <output-directory> [light|dark]
Set QT_SCALE_FACTOR=1/1.25/1.5 for scaling qualification.
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
work = Path(tempfile.mkdtemp(prefix="res644-native-"))
os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(work / "private")
os.environ.pop("DYNAMISSCIENCE_TEST_SESSION", None)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QFileDialog, QMessageBox
from dynamis_science import researchstore
from dynamis_science.desktop import theme
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.import_review import ImportReviewDialog
from dynamis_science.desktop.services import DynamisAppService

app = QApplication([])
assert app.platformName() == "windows"
theme.apply_theme(app, sys.argv[2] if len(sys.argv) > 2 else "light")
window = MainWindow(DynamisAppService())
geometry = app.primaryScreen().availableGeometry()
scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
window.resize(min(round(1366 / scale), geometry.width()), min(round(768 / scale), geometry.height()))
window.show()
failures = []
original_warning = QMessageBox.warning
# Fail the receipt on any application error, while retaining the native dialog for a screenshot.
def warning(parent, title, text, *args):
    failures.append(f"{title}: {text}")
    return QMessageBox.StandardButton.Ok
QMessageBox.warning = warning


def settle():
    deadline = time.monotonic() + 60
    while window.runner.active and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert not window.runner.active, "Background task did not finish"
    assert not failures, failures


def shot(name, widget=None):
    app.processEvents()
    (widget or window).grab().save(str(out / f"{name}.png"))


settle()
def title():
    modal = app.activeModalWidget()
    assert isinstance(modal, QInputDialog)
    modal.setTextValue("Continuing CMJ investigation")
    modal.accept()
QTimer.singleShot(100, title)
window._new_workspace()
settle()
identity = window.current_study_id
assert identity and not window.current_snapshot_id
shot("01-empty-workspace")

fields = {"source_name": "Native RES-644 fixture", "publisher": "DynamisScience qualification",
          "dataset_identity": "RES-644", "privacy_status": "TEST_FIXTURE",
          "license_or_agreement": "Internal fixture only", "redistribution_restrictions": "Synthetic fixture only",
          "manufacturer": "Simulated", "model": "Fixture", "serial_number": "SYNTH-644",
          "protocol_name": "Fixture CMJ", "protocol_version": "1.0", "sampling_hz": "1000"}

for number in (1, 2):
    file = work / f"batch{number}.csv"
    file.write_text("Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N),week\n" +
                    f"A1,T{number}a,{39+number},80,1800,{number}\nA2,T{number}b,{37+number},75,1700,{number}\n")
    dialog = ImportReviewDialog(window.service, window.run_task, lambda record: window._admission_saved(record, identity), window)
    dialog.show()
    # Real native modal choice: explicit compatible append on the second import.
    def choose_append():
        modal = app.activeModalWidget()
        if isinstance(modal, QInputDialog) and modal.windowTitle() == "Attach data":
            modal.setTextValue("Append compatible measurements (same participant identifiers)")
            modal.accept()
    timer = QTimer()
    timer.timeout.connect(choose_append)
    timer.start(50)
    dialog.load(str(file))
    settle()
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
    assert dialog.state == "ready", (dialog.state, dialog.summary.text())
    shot(f"0{number*2}-import-ready", dialog)
    dialog.open_button.click()
    settle()
    timer.stop()
    assert window.current_study_id == identity
    revision = window.current_study["active_data_revision_id"]
    assert len(researchstore.data_revisions(identity)) == number
    window._analyze_workspace()
    window.research.analysis_metric_picker.setCurrentIndex(window.research.analysis_metric_picker.findData("MET-CMJ-HEIGHT"))
    assert window.research.method_picker.currentData() == "METH-U-DESC"
    window.research.execute_button.click()
    settle()
    assert window.research.latest_run and window.research.latest_run["data_revision_id"] == revision
    shot(f"0{number*2+1}-analysis")
    if number == 1:
        first_run = window.research.latest_run
        first_revision = revision

assert researchstore.get_run(first_run["id"])["data_revision_id"] == first_revision
output = out / "workspace-report.html"
original_picker = QFileDialog.getSaveFileName
QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(output), "HTML")
window.research.export_report()
settle()
QFileDialog.getSaveFileName = original_picker
assert output.is_file() and window.research.latest_run["id"] in output.read_text(encoding="utf-8")
assert len(researchstore.report_versions(identity)) == 1
shot("06-exported")
window.close()
settle()
window = MainWindow(DynamisAppService())
window.resize(min(round(1366 / scale), geometry.width()), min(round(768 / scale), geometry.height()))
window.show()
settle()
window._show_study(identity, window.service.get_study_detail(identity))
settle()
assert window.research.latest_run["data_revision_id"] == revision
shot("07-reopened")
# Inspect the real history dialog and then return to the exact earlier data revision.
def inspect_history():
    modal = app.activeModalWidget()
    assert modal.windowTitle() == "Workspace history"
    shot("08-history", modal)
    modal.accept()
QTimer.singleShot(200, inspect_history)
window._workspace_history()
settle()
window._show_study(identity, researchstore.select_data_revision(identity, first_revision))
settle()
assert window.research.latest_run["id"] == first_run["id"]
shot("09-earlier-analysis")
receipt = {"source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "platform": app.platformName(), "scale": scale, "window_logical": [window.width(), window.height()],
           "data_root": str(work / "private"), "workspace_id": identity,
           "revisions": [r["id"] for r in researchstore.data_revisions(identity)],
           "runs": [{k: r.get(k) for k in ("id", "data_revision_id", "snapshot_id", "result_digest")} for r in researchstore.list_runs(identity)],
           "reports": researchstore.report_versions(identity), "failures": failures,
           "screenshots": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob("*.png")}}
(out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
window.close()
print(json.dumps(receipt))
