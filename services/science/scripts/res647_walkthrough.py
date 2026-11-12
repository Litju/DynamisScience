"""RES-647 real Windows Qt journey: cohort and individual longitudinal research in one workspace.

Disposable synthetic data only; never touches the installed app or the operational research store.
uv run python scripts/res647_walkthrough.py <output-directory> [light|dark]
uv run python scripts/res647_walkthrough.py --reopen <data-root> <workspace-id> <output-directory>
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

reopen = sys.argv[1] == "--reopen"
if reopen:
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = sys.argv[2]
    out = Path(sys.argv[4]).resolve()
else:
    out = Path(sys.argv[1]).resolve()
    work = Path(tempfile.mkdtemp(prefix="res647-native-"))
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(work / "private")
out.mkdir(parents=True, exist_ok=True)
if getattr(sys, "frozen", False):
    sys.stdout = sys.stderr = (out / ("reopen-console.log" if reopen else "packaged-console.log")).open("w", encoding="utf-8")
    import faulthandler
    faulthandler.enable(sys.stderr)
os.environ.pop("DYNAMISSCIENCE_TEST_SESSION", None)


from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox, QTableWidgetItem
from dynamis_science import researchstore
from dynamis_science.desktop import theme
from dynamis_science.desktop.import_review import ImportReviewDialog
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService

app = QApplication([])
assert app.platformName() == "windows"
mode = "dark" if "dark" in sys.argv else "light"
geometry = app.primaryScreen().availableGeometry()
scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
failures: list[str] = []
QMessageBox.warning = lambda parent, title, text, *args: failures.append(f"{title}: {text}") or QMessageBox.StandardButton.Ok


def open_window() -> MainWindow:
    window = MainWindow(DynamisAppService())
    theme.apply_theme(app, mode)
    window.show()
    app.processEvents()
    # Size the whole frame (title bar included) to the 1366×768 target clamped to the work area.
    chrome = window.frameGeometry().height() - window.height()
    window.resize(min(round(1366 / scale), geometry.width()), min(round(768 / scale), geometry.height()) - chrome)
    window.move(geometry.topLeft())
    app.processEvents()
    return window


window = open_window()


def settle() -> None:
    deadline = time.monotonic() + 90
    while window.runner.active and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert not window.runner.active, "Background task did not finish"
    assert not failures, failures


def shot(name: str, widget=None) -> None:
    app.processEvents()
    (widget or window).grab().save(str(out / f"{name}.png"))


def fits(widget) -> None:
    frame = widget.frameGeometry()
    assert frame.width() <= geometry.width() and frame.height() <= geometry.height(), (frame, geometry)


answers: list[str] = []


def answer_dialogs() -> None:
    modal = app.activeModalWidget()
    if isinstance(modal, QInputDialog) and answers:
        modal.setTextValue(answers.pop(0))
        modal.accept()


responder = QTimer()
responder.timeout.connect(answer_dialogs)
responder.start(50)

if reopen:
    identity = sys.argv[3]
    settle()
    window._show_study(identity, window.service.get_study_detail(identity))
    settle()
    panel = window.research.individual
    assert window.research_context["scope"] == "INDIVIDUAL" and "Participant P01" in panel.header.text()
    assert panel.run_picker.count() == 2
    shot("20-new-process-restored")
    (out / "reopen-receipt.json").write_text(json.dumps({
        "pid": os.getpid(), "workspace_id": identity, "research_context": researchstore.get_entity(identity)["research_context"],
        "investigations": [item["id"] for item in window.service.individual_investigations(identity)],
        "runs": [run["id"] for run in researchstore.list_runs(identity)], "reports": researchstore.report_versions(identity),
    }, indent=2), encoding="utf-8")
    window.close()
    sys.exit(0)

def study_file(directory, weeks, name):
    lines = ["Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N),week"]
    missing = {("P03", 3), ("P03", 5), ("P07", 6), ("P11", 2), ("P11", 3), ("P11", 4), ("P11", 5), ("P11", 6)}
    for index in range(1, 13):
        subject = f"P{index:02d}"
        for week in weeks:
            if (subject, week) in missing:
                continue
            for trial in range(1, 3 + index % 2):
                value = round(30 + index + .4*week + ((trial*7+index*3+week)%5-2)*.3, 2)
                lines.append(f"{subject},{subject}-W{week}-T{trial},{value},{70+index},{1600+10*index},{week}")
    path = directory / name
    path.write_text("\n".join(lines)+"\n")
    return path

settle()
answers.append("Squad CMJ longitudinal research")
window._new_workspace()
settle()
identity = window.current_study_id
assert identity and not window.current_snapshot_id
fields = {"source_name": "Native RES-647 fixture", "publisher": "DynamisScience qualification",
          "dataset_identity": "RES-647", "privacy_status": "TEST_FIXTURE",
          "license_or_agreement": "Internal fixture only", "redistribution_restrictions": "Synthetic fixture only",
          "manufacturer": "Simulated", "model": "Fixture", "serial_number": "SYNTH-647",
          "protocol_name": "Fixture CMJ", "protocol_version": "1.0", "sampling_hz": "1000", "session_id": "S1"}


def import_batch(weeks: range, name: str, append: bool) -> None:
    file = study_file(work, weeks, name)
    dialog = ImportReviewDialog(window.service, window.run_task, lambda record: window._admission_saved(record, identity), window)
    dialog.show()
    if append:
        answers.append("Append compatible measurements (same participant identifiers)")
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
    dialog.open_button.click()
    settle()
    assert window.current_study_id == identity


# 1–2. One persistent workspace; cohort-level analysis.
import_batch(range(1, 4), "weeks1-3.csv", append=False)
rev1 = window.current_study["active_data_revision_id"]
window._analyze_workspace()
window.research.analysis_metric_picker.setCurrentIndex(window.research.analysis_metric_picker.findData("MET-CMJ-HEIGHT"))
window.research.execute_button.click()
settle()
cohort_first = window.research.latest_run
assert cohort_first["scope"]["kind"] == "COHORT" and cohort_first["result"]["n_subjects"] == 12
shot("01-cohort-analysis")
fits(window)
from PySide6.QtWidgets import QToolBar
bar = window.findChild(QToolBar, "PersistentWorkspaceActions")
assert all(bar.widgetForAction(a).isVisibleTo(window) for a in bar.actions()), "Primary action hidden in overflow"

# 3–5. Individuals explorer; Participant A and Participant B investigations.
panel = window.research.individual


def open_participant(row: int, title: str, question: str, name: str) -> None:
    window._show_squad_mode()
    window.squad.setCurrentWidget(window.squad.board)
    settle()
    tiles = sorted(window.squad.board.tiles(), key=lambda t: t.athlete["subject_id"])
    assert len(tiles) == 12
    shot(name)
    tiles[row].click()
    settle()
    answers.append(title)
    window.squad.athlete_page.new_branch()
    settle()
    assert window.squad.athlete_page.research_tabs.currentIndex() == 1



open_participant(0, "Jump height trajectory", "How did P01's CMJ height change across the season?", "02-individuals-explorer")
assert "Participant P01" in panel.header.text() and window.research_context["scope"] == "INDIVIDUAL"
panel.tabs.setCurrentIndex(1)
shot("03-individual-analysis-options")
panel.execute()
settle()
a_first = panel.run_picker.currentData()
a_first_document = researchstore.get_run(a_first["id"])
shot("04-individual-results")
open_participant(1, "Off-season tracking", "", "05-explorer-participant-b")
assert "Participant P02" in panel.header.text() and panel.run_picker.count() == 0
panel.execute()
settle()

# 6–8. Further measurements; back to Participant A on the updated revision.
import_batch(range(4, 7), "weeks4-6.csv", append=True)
rev2 = window.current_study["active_data_revision_id"]
assert rev2 != rev1 and window.current_study_id == identity
investigations = window.service.individual_investigations(identity)
a_id = next(item["id"] for item in investigations if item["scope"]["subject_id"] == "P01")
window._select_scope("INDIVIDUAL", a_id)
settle()
assert "Participant P01" in panel.header.text() and "Data revision 2" in panel.header.text()
panel.execute()
settle()
a_second = panel.run_picker.currentData()
assert a_second["data_revision_id"] == rev2 and a_second["result"]["last"] == 6
assert researchstore.get_run(a_first["id"]) == a_first_document
shot("06-individual-updated-revision")

# 9. Experimental protocol (observational tracking).
panel.tabs.setCurrentIndex(3)
panel._add_period({"kind": "BASELINE", "label": "Pre-season", "start": 1, "end": 2})
panel._add_period({"kind": "INTERVENTION", "label": "Plyometric block", "start": 3, "end": 6}, {"adherence_percent": 85, "deviations": "One missed session"})
panel.changes.setPlainText("4: Added depth jumps")
panel.save_protocol()
settle()
shot("07-protocol")

# 10–11. Worst-case scenario stays NOT QUALIFIED.
panel.tabs.setCurrentIndex(4)
panel.scenario_kind.setCurrentIndex(panel.scenario_kind.findData("WORST_CASE"))
panel.scenario_title.setText("Four-week detraining stress test")
panel.adverse.setText("CMJ height below the pre-season mean")
panel.assumptions.setPlainText("No jump training\nSame test protocol and instrument")
for column, text in enumerate(("weekly change", "-2", "0", "cm/week")):
    panel.bounds.setItem(0, column, QTableWidgetItem(text))
panel.save_scenario()
settle()
assert "NOT QUALIFIED — Numerical forecast unavailable." in panel.scenario_view.toPlainText()
shot("08-scenario-not-qualified")

# Events distinguish original recorded evaluations from current-rule retrospective history.
window.service.save_flag_rules(identity, [{"name": "Observed decrease", "category": "Research follow-up", "tone": "neutral",
    "conditions": [{"metric_id": "MET-CMJ-HEIGHT", "measure": "change_from_previous_pct", "operator": "<", "value": 0}]}])
window._show_events_mode()
settle()
assert any(e["kind"] == "rule_evaluation" for e in window.events_view.feed["events"])
assert all(e.get("evaluation_kind") == "RETROSPECTIVE" for e in window.events_view.feed["events"] if e["kind"] == "flag")
shot("08b-events-and-history")
window._open_athlete("P01")
settle()
# 12. Compare with cohort.
panel.tabs.setCurrentIndex(5)
panel.compare()
settle()
assert panel.compare_table.rowCount() == 6
shot("09-compare-with-cohort")

# 13. Individual, cohort and combined exports through the ordinary actions.
picker = QFileDialog.getSaveFileName
exports = {}
for name in ("individual", "cohort", "combined"):
    exports[name] = out / f"{name}-report.html"
    QFileDialog.getSaveFileName = lambda *args, target=exports[name], **kwargs: (str(target), "HTML")
    if name == "individual":
        window.research.export_report()
    elif name == "cohort":
        window._select_scope("COHORT")
        window._analyze_workspace()
        window.research.analysis_metric_picker.setCurrentIndex(window.research.analysis_metric_picker.findData("MET-CMJ-HEIGHT"))
        window.research.execute_button.click()
        settle()
        window.research.export_report()
    else:
        window._select_scope("INDIVIDUAL", a_id)
        settle()
        window._export_combined_report()
    settle()
QFileDialog.getSaveFileName = picker
assert "Individual investigation · participant P01" in exports["individual"].read_text(encoding="utf-8")
assert "<h3>Cohort research</h3>" in exports["cohort"].read_text(encoding="utf-8")
combined = exports["combined"].read_text(encoding="utf-8")
assert "<h3>Cohort research</h3>" in combined and "Individual investigation · participant P01" in combined
reports_before = {item["version"]: item["content_hash"] for item in researchstore.report_versions(identity)}


def inspect_history():
    modal = app.activeModalWidget()
    assert modal.windowTitle() == "Workspace history"
    fits(modal)
    shot("10-history", modal)
    modal.accept()


QTimer.singleShot(300, inspect_history)
window._workspace_history()
settle()

# 14. Restart in-process, then in a new process.
window.close()
settle()
window = open_window()
settle()
window._show_study(identity, window.service.get_study_detail(identity))
settle()
panel = window.research.individual
assert window.research_context["scope"] == "INDIVIDUAL" and "Participant P01" in panel.header.text()
assert {item["version"]: item["content_hash"] for item in researchstore.report_versions(identity)} == reports_before
shot("11-reopened")
fits(window)
window.close()
subprocess.run([sys.executable, *( ["--qualification-walkthrough"] if getattr(sys, "frozen", False) else [__file__] ), "--reopen", os.environ["DYNAMISSCIENCE_DATA_ROOT"], identity, str(out), mode], check=True)
receipt = {"source_commit": os.environ.get("DYNAMISSCIENCE_QUALIFICATION_COMMIT") or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "dirty_files": [] if getattr(sys, "frozen", False) else subprocess.check_output(["git", "status", "--porcelain"], text=True).splitlines(),
           "packaged": bool(getattr(sys, "frozen", False)),
           "executable_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
           "platform": app.platformName(), "scale": scale, "theme": mode, "available_geometry": [geometry.width(), geometry.height()],
           "data_root": os.environ["DYNAMISSCIENCE_DATA_ROOT"], "workspace_id": identity, "revisions": [rev1, rev2],
           "investigations": [{"id": item["id"], "subject_id": item["scope"]["subject_id"], "version": item["version"]}
                              for item in window.service.individual_investigations(identity)],
           "runs": [{k: r.get(k) for k in ("id", "scope", "data_revision_id", "method_id", "result_digest")} for r in researchstore.list_runs(identity)],
           "participant_a_first_run_unchanged": researchstore.get_run(a_first["id"]) == a_first_document,
           "reports": researchstore.report_versions(identity), "failures": failures,
           "exports": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in exports.items()},
           "screenshots": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.png"))}}
(out / "receipt.json").write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
print(json.dumps({"workspace": identity, "runs": len(receipt["runs"]), "reports": len(receipt["reports"])}))
