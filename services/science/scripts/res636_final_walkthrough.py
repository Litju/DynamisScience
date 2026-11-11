"""RES-636 final native walkthrough (source application, real Windows Qt platform, disposable data root).

Drives the real MainWindow, Import review and Data workspace through Qt calls, saves screenshots and a JSON
receipt, then reopens a new window on the same root to prove persistence.
Usage: python scripts/res636_final_walkthrough.py <output-dir> [prefix]    (set QT_SCALE_FACTOR for other DPI)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

out = Path(sys.argv[1]).resolve()
prefix = sys.argv[2] if len(sys.argv) > 2 else "w"
out.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="res636-final-"))
os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(work / "private")
os.environ.pop("DYNAMISSCIENCE_TEST_SESSION", None)

import polars as pl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

from dynamis_science import admission, importer  # noqa: E402
from dynamis_science.desktop.data_workspace import DataWorkspaceDialog  # noqa: E402
from dynamis_science.desktop.import_review import ImportReviewDialog  # noqa: E402
from dynamis_science.desktop.main_window import MainWindow  # noqa: E402
from dynamis_science.desktop.services import DynamisAppService  # noqa: E402

app = QApplication.instance() or QApplication([])
HEADER = "Athlete,Trial,Jump Height (m),Body Mass (g),Peak Force (N)\n"
FIELDS = {"source_name": "Walkthrough fixture lab", "publisher": "DynamisScience walkthrough", "dataset_identity": "res636-final",
          "license_or_agreement": "Internal fixture only", "redistribution_restrictions": "Fixture only; not real measurements",
          "manufacturer": "Fixture", "model": "FP-1", "serial_number": "WALK-1", "protocol_name": "Fixture protocol",
          "protocol_version": "1.0", "session_id": "S1", "sampling_hz": "1000"}
receipt: dict = {"steps": [], "scale": os.environ.get("QT_SCALE_FACTOR", "1")}
step = [0]


def write(name: str, text: str) -> Path:
    path = work / "inputs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def settle(window: MainWindow, seconds: float = 30) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if not window.runner.active:
            break
        time.sleep(0.02)
    for _ in range(8):
        app.processEvents()


def pause(window: MainWindow, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    settle(window)


def shot(widget, name: str, note: str) -> None:
    step[0] += 1
    widget.repaint()
    app.processEvents()
    path = out / f"{prefix}{step[0]:02d}-{name}.png"
    widget.grab().save(str(path))
    receipt["steps"].append({"screenshot": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "note": note})


def fill(dialog: ImportReviewDialog, **extra) -> None:
    dialog.privacy.setCurrentIndex(dialog.privacy.findData("TEST_FIXTURE"))
    for key, value in {**FIELDS, **extra}.items():
        dialog.edits[key].setText(value)


def fit(w) -> None:
    geometry = QGuiApplication.primaryScreen().availableGeometry()
    receipt["logical_screen"] = f"{geometry.width()}x{geometry.height()}"
    w.resize(min(1366, geometry.width()), min(768, geometry.height()))


window = MainWindow(DynamisAppService())
fit(window)
window.show()
settle(window)
dialog = ImportReviewDialog(window.service, window.run_task, window._admission_saved, window)
dialog.show()


def load(path: Path) -> None:
    dialog.load(str(path))
    settle(window)


def clear_form() -> None:
    for edit in dialog.edits.values():
        edit.clear()
    dialog.edits["protocol_version"].setText("1.0")


# 1 generic CSV, 2 invalid, 3 parquet, 4 preset reuse + drift, 5 folder, 6 trace with repeated trial ids
load(write("cmj_a.csv", HEADER + "A1,T1,0.401,80000,1800\nA2,T2,0.385,75000,1700\nA3,T3,0.372,82000,1900\n"))
fill(dialog)
dialog.qc_button.click()
settle(window)
shot(dialog, "csv-qc", "generic CSV: units converted, QC passed, SYNTHETIC_ONLY, storage outcome")
dialog.admit_button.click()
settle(window)

QInputDialog.getText = staticmethod(lambda *a, **k: ("Walkthrough CMJ", True))
dialog.preset_button.click()
settle(window)
clear_form()
load(write("cmj_b.csv", HEADER + "B1,T9,0.41,70000,1500\n"))
shot(dialog, "preset-repeat", "saved preset reused: form filled, QC already run")
dialog.admit_button.click()
settle(window)
load(write("cmj_drift.csv", HEADER.replace("Athlete", "Participant ID") + "D1,T30,0.4,70000,1500\n"))
shot(dialog, "schema-drift", "schema drift: preset not reused")

clear_form()
load(write("bad.csv", "Athlete,Trial,Jump Height (cm)\nE1,T1,400\nE2,T1,38\n"))
fill(dialog)
dialog.qc_button.click()
settle(window)
dialog.quarantine_button.click()
settle(window)
shot(dialog, "quarantine", "invalid file rejected and quarantined, no snapshot")

pq_path = work / "inputs" / "cmj_parquet.parquet"
pl.DataFrame({"subject_id": ["P1", "P2"], "session_id": ["S1", "S1"], "trial_id": ["a", "b"], "sampling_hz": [1000.0, 1000.0],
              "jump_height_cm": [30.0, 31.5], "body_mass_kg": [70.0, 82.0]}).write_parquet(pq_path)
clear_form()
load(pq_path)
fill(dialog, source_name="Parquet lab", session_id="", sampling_hz="")
dialog.qc_button.click()
settle(window)
dialog.admit_button.click()
settle(window)
shot(dialog, "parquet", "Parquet import admitted")

folder = work / "inputs" / "batch"
folder.mkdir()
for i in range(3):
    (folder / f"f{i}.csv").write_bytes((HEADER + f"F{i},T{50 + i},0.4{i},70000,1500\n").encode())
clear_form()
load(folder)
fill(dialog, source_name="Folder lab")
dialog.qc_button.click()
settle(window)
dialog.admit_button.click()
settle(window)
shot(dialog, "folder", "bounded folder import: three files admitted")

trace_rows = "\n".join(f"{s},{t},{i / 1000:.3f},{700 + (i * 7) % 90 + (400 if 300 < i < 500 else 0)}"
                       for s, t in (("A1", "TR-1"), ("A2", "TR-2")) for i in range(1000))
clear_form()
load(write("traces.csv", "Athlete,Trial,Time (s),Force (N)\n" + trace_rows + "\n"))
fill(dialog, source_name="Trace lab", sampling_hz="1000")
dialog.qc_button.click()
settle(window)
shot(dialog, "trace-qc", "sample-level recording: 2000 samples, 2 traces, repeated trial ids valid, orientation warning")
dialog.admit_button.click()
settle(window)
dialog.close()

snapshots = admission.list_admitted_snapshots()
receipt["admitted"] = {s["id"]: s["measurement_family"] for s in snapshots}
trace_id = next(s["id"] for s in snapshots if s["measurement_family"] == "RAW_FORCE_TIME")
cmj_id = next(s["id"] for s in snapshots if s["measurement_family"] == "CMJ_FORCE_PLATFORM")

# Data workspace: browse, filter, columns, traces, query, inspector, analyze
workspace = DataWorkspaceDialog(window.service, window.run_task, window._analyze_dataset, window)
workspace.open(cmj_id)
workspace.show()
settle(window)
shot(workspace, "workspace-table", "dataset catalogue and paged table with units")
workspace.filter_column.setCurrentText("peak_force_n")
workspace.filter_op.setCurrentText(">=")
workspace.filter_value.setText("1700")
workspace._add_filter()
settle(window)
shot(workspace, "workspace-filter", "filter peak_force_n >= 1700 applied (rows and total updated)")
receipt["filtered_rows"] = workspace.rows_model.rowCount()
workspace.tabs.setCurrentIndex(1)
settle(window)
shot(workspace, "workspace-columns", "column types, units, missingness")
workspace.tabs.setCurrentIndex(3)
workspace.query_text.setPlainText("SELECT subject_id, jump_height_cm, peak_force_n FROM cmj_trials ORDER BY peak_force_n DESC")
workspace._run_query()
settle(window)
shot(workspace, "workspace-query", "read-only SELECT result")
workspace.query_text.setPlainText("DROP TABLE cmj_trials")
workspace._run_query()
settle(window)
receipt["drop_rejected"] = workspace.query_status.text()
workspace.tabs.setCurrentIndex(4)
settle(window)
shot(workspace, "workspace-inspector", "rights, QC, exclusions, instrument, provenance, import receipt")
workspace.catalogue.setCurrentRow([workspace.catalogue.item(i).data(0x0100) for i in range(workspace.catalogue.count())].index(trace_id))
settle(window)
workspace.tabs.setCurrentIndex(2)
settle(window, 40)
pause(window, 1.5)
shot(workspace, "workspace-traces", "raw force-time recording plotted")
workspace.tabs.setCurrentIndex(0)
workspace.table_picker.setCurrentText("force_signals")
settle(window)
shot(workspace, "workspace-samples", "sample-level table: repeated trial ids across samples")
receipt["sample_rows_total"] = workspace.total
workspace.catalogue.setCurrentRow([workspace.catalogue.item(i).data(0x0100) for i in range(workspace.catalogue.count())].index(cmj_id))
settle(window)
workspace._analyze()
settle(window, 40)
shot(window, "analysis-selected", "dataset selected into the research workbench")
receipt["analysis_snapshot"] = window.current_snapshot_id
catalogue_before = sorted(d["id"] for d in window.service.list_datasets())

# restart: a brand-new service and window on the same root
window.close()
app.processEvents()
service2 = DynamisAppService()
window2 = MainWindow(service2)
fit(window2)
window2.show()
settle(window2)
ws2 = DataWorkspaceDialog(service2, window2.run_task, window2._analyze_dataset, window2)
ws2.open(trace_id)
ws2.show()
settle(window2)
shot(ws2, "after-restart", "after restart: catalogue and datasets persisted")
receipt["persisted_after_restart"] = sorted(d["id"] for d in service2.list_datasets()) == catalogue_before
receipt["presets_after_restart"] = [p["name"] for p in importer.list_presets()]
receipt["import_receipts"] = [{k: r[k] for k in ("id", "raw_filename", "raw_sha256", "decision", "family")} for r in importer.list_receipts()]
ws2.close()
window2.close()
(out / f"{prefix}-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
shutil.rmtree(work, ignore_errors=True)
print(json.dumps({k: receipt[k] for k in ("admitted", "filtered_rows", "sample_rows_total", "analysis_snapshot", "persisted_after_restart")}))
