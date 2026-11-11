"""RES-636 native import walkthrough on a disposable data root: drives the real MainWindow + import dialog,
saves screenshots and a JSON receipt. Usage: python scripts/res636_walkthrough.py <output-dir> [--app-root <install dir>]
Never touches DYNAMISSCIENCE_DATA_ROOT of the operator: it creates and deletes its own root."""

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
out.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="res636-walk-"))
os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(work / "private")
os.environ.pop("DYNAMISSCIENCE_TEST_SESSION", None)

import polars as pl  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

from dynamis_science import admission, importer  # noqa: E402
from dynamis_science.desktop.import_review import ImportReviewDialog  # noqa: E402
from dynamis_science.desktop.main_window import MainWindow  # noqa: E402
from dynamis_science.desktop.services import DynamisAppService  # noqa: E402

app = QApplication.instance() or QApplication([])
HEADER = "Athlete,Trial,Jump Height (m),Body Mass (g),Peak Force (N)\n"
FIELDS = {"source_name": "Walkthrough fixture lab", "publisher": "DynamisScience walkthrough",
          "dataset_identity": "res636-walkthrough", "license_or_agreement": "Internal fixture only",
          "redistribution_restrictions": "Fixture only; not real measurements", "manufacturer": "Fixture", "model": "FP-1",
          "serial_number": "WALK-1", "protocol_name": "Fixture CMJ", "protocol_version": "1.0",
          "session_id": "S1", "sampling_hz": "1000"}
receipt: dict = {"steps": [], "data_root": str(work / "private")}


def write(name: str, text: str) -> Path:
    path = work / "inputs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def settle(window: MainWindow, seconds: float = 20) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if not window.runner.active:
            break
        time.sleep(0.02)
    for _ in range(5):
        app.processEvents()


def shot(widget, name: str, note: str) -> None:
    widget.repaint()
    app.processEvents()
    path = out / f"{name}.png"
    widget.grab().save(str(path))
    receipt["steps"].append({"screenshot": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "note": note})


def fill(dialog: ImportReviewDialog) -> None:
    dialog.privacy.setCurrentIndex(dialog.privacy.findData("TEST_FIXTURE"))
    for key, value in FIELDS.items():
        dialog.edits[key].setText(value)


service = DynamisAppService()
window = MainWindow(service)
window.resize(1366, 768)
window.show()
settle(window)
dialog = ImportReviewDialog(window.service, window.run_task, window._admission_saved, window)
dialog.resize(1100, 700)
dialog.show()


def load(path: Path) -> None:
    dialog.load(str(path))
    settle(window)


valid = write("cmj_a.csv", HEADER + "A1,T1,0.401,80000,1800\nA2,T2,0.385,75000,1700\nA3,T3,0.372,82000,1900\n")
load(valid)
shot(dialog, "01-unknown-file-review", "unknown CSV: detected mapping, session and sampling rate requested, nothing assumed")
fill(dialog)
dialog.qc_button.click()
settle(window)
shot(dialog, "02-qc-verdict-synthetic-only", "QC verdict ADMITTED_WITH_WARNINGS/ADMITTED, SYNTHETIC_ONLY, storage outcome")
dialog.admit_button.click()
settle(window)
shot(dialog, "03-admitted", "snapshot stored")
receipt["admitted_snapshots"] = [s["id"] for s in admission.list_admitted_snapshots()]

QInputDialog.getText = staticmethod(lambda *a, **k: ("Walkthrough CMJ export", True))
load(write("cmj_b.csv", HEADER + "B1,T9,0.41,70000,1500\n"))
fill(dialog)
dialog.qc_button.click()
settle(window)
dialog.preset_button.click()
settle(window)
shot(dialog, "04-preset-saved", "preset saved against the schema fingerprint")
for edit in dialog.edits.values():
    edit.clear()
load(write("cmj_c.csv", HEADER + "C1,T20,0.39,71000,1600\n"))
shot(dialog, "05-preset-repeat-import", "repeat import: preset applied, QC already run, one click left (Admit)")
dialog.admit_button.click()
settle(window)

load(write("cmj_drift.csv", HEADER.replace("Athlete", "Participant ID") + "D1,T30,0.4,70000,1500\n"))
shot(dialog, "06-schema-drift", "schema drift: preset not reused, review required")

load(write("bad.csv", "Athlete,Trial,Jump Height (cm)\nE1,T1,400\nE2,T1,38\n"))
fill(dialog)
dialog.qc_button.click()
settle(window)
shot(dialog, "07-invalid-rejected", "invalid data: REJECTED, Admit disabled")
dialog.quarantine_button.click()
settle(window)
shot(dialog, "08-quarantined", "quarantined without a snapshot")

folder = work / "inputs" / "batch"
folder.mkdir()
for i in range(3):
    (folder / f"f{i}.csv").write_bytes((HEADER + f"F{i},T{50 + i},0.4{i},70000,1500\n").encode())
load(folder)
shot(dialog, "09-folder-import", "bounded folder import: one row per file")

load(write("force_time_trace.csv", "Time (s),Left Force (N),Right Force (N)\n0.000,400,410\n0.001,401,409\n"))
shot(dialog, "10-raw-force-time-held", "raw force-time export recognised but not imported (vendor layout unverified)")

dialog.close()
window.refresh_catalogue(None)
settle(window)
snapshots = [s["id"] for s in admission.list_admitted_snapshots()]
catalogue = [d["id"] for d in service.list_datasets()]
receipt["admitted_snapshots"] = snapshots
receipt["visible_in_workbench_catalogue"] = [s for s in snapshots if s in catalogue]
page = service.read_table_page(snapshots[0], service.get_dataset_detail(snapshots[0])["tables"][0]["name"])
receipt["workbench_read_table_rows"] = page["total_rows"]
receipt["import_receipts"] = [{k: r[k] for k in ("id", "raw_filename", "raw_sha256", "decision", "source_id")} for r in importer.list_receipts()]
shot(window, "11-main-window-after-import", "main window with the admitted snapshots in the catalogue")
(out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
window.close()
shutil.rmtree(work, ignore_errors=True)
print(json.dumps({k: receipt[k] for k in ("admitted_snapshots", "visible_in_workbench_catalogue", "workbench_read_table_rows")}))
