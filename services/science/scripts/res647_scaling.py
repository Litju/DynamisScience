"""RES-647 Squad, athlete, Events and editor screens on the real Windows platform at the current QT_SCALE_FACTOR.

Disposable synthetic data only. uv run python scripts/res647_scaling.py <output-directory> [light|dark]
"""
from __future__ import annotations

import hashlib
import subprocess
import json
import os
import sys
import tempfile
import time
from pathlib import Path

work = Path(tempfile.mkdtemp(prefix="res647-scaling-"))
os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(work / "private")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication, QPushButton

from dynamis_science import importer, squad
from dynamis_science.desktop import theme
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService
from dynamis_science.desktop.squad_view import RulesDialog, SimulationDialog
from test_importer import FIXTURE
from test_longitudinal_research import admit, study_file
from test_monitoring_import import monitoring_context, monitoring_file

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
mode = sys.argv[2] if len(sys.argv) > 2 else "light"
app = QApplication([])
assert app.platformName() == "windows"
service = DynamisAppService()
service.ensure_initialized()
identity = service.create_workspace("Squad season 2026")["study"]["id"]
rev1 = service.attach_workspace_data(identity, admit(study_file(work, range(1, 7), "c.csv"), importer.build_context(FIXTURE)))["active_data_revision_id"]
rev2 = service.attach_workspace_data(identity, admit(monitoring_file(work, range(0, 28), "m1.csv"), monitoring_context()), link=True,
                                     confirm_participant_ids=True, base_revision=rev1)["active_data_revision_id"]
service.attach_workspace_data(identity, admit(monitoring_file(work, range(28, 42), "m2.csv"), monitoring_context()), append=True,
                              confirm_participant_ids=True, base_revision=rev2)
squad.save_rules(identity, [
    {"name": "Load spike with poor wellness", "category": "In danger", "tone": "negative",
     "conditions": [{"metric_id": "MET-MON-LOAD", "measure": "acute_chronic_ratio", "acute": 7, "chronic": 28, "operator": ">", "value": 1.3},
                    {"metric_id": "MET-MON-WELLNESS", "measure": "change_from_baseline_pct", "operator": "<", "value": -20}]},
    {"name": "Short sleep", "category": "Watch", "tone": "neutral",
     "conditions": [{"metric_id": "MET-MON-SLEEP", "measure": "rolling_mean", "window": 7, "operator": "<", "value": 7.6}]},
    {"name": "Jumping higher", "category": "Doing great", "tone": "positive",
     "conditions": [{"metric_id": "MET-CMJ-HEIGHT", "measure": "change_from_baseline_pct", "operator": ">", "value": 6}]}])
investigation = service.create_individual_investigation(identity, "P03", "Load spike follow-up")
service.select_research_scope(identity, "INDIVIDUAL", investigation["id"])

window = MainWindow(service)
theme.apply_theme(app, mode)
window.show()
app.processEvents()
geometry = app.primaryScreen().availableGeometry()
scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
chrome = window.frameGeometry().height() - window.height()
window.resize(min(round(1366 / scale), geometry.width()), min(round(768 / scale), geometry.height()) - chrome)
window.move(geometry.topLeft())
report: dict[str, object] = {"scale": scale, "theme": mode, "available": [geometry.width(), geometry.height()], "checks": {}}


def settle() -> None:
    deadline = time.monotonic() + 60
    while window.runner.active and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def record(name: str, widget) -> None:
    app.processEvents()
    widget.grab().save(str(out / f"{name}.png"))
    frame = widget.frameGeometry()
    assert frame.width() <= geometry.width() and frame.height() <= geometry.height(), (name, frame, geometry)
    if isinstance(widget, RulesDialog):
        assert widget.conditions.horizontalScrollBar().maximum() == 0, "Rule columns overflow"
    if isinstance(widget, SimulationDialog):
        for button in widget.findChildren(QPushButton):
            if button.text() in ("Validate definition", "Save scenario"):
                assert button.isVisibleTo(widget) and widget.rect().contains(button.mapTo(widget, button.rect().center())), button.text()
    report["checks"][name] = {"frame": [frame.width(), frame.height()],
                              "fits": frame.width() <= geometry.width() and frame.height() <= geometry.height()}


settle()
window._show_study(identity, service.get_study_detail(identity))
settle()
record("01-athlete-branch", window)
window.squad.athlete_page.research_tabs.setCurrentIndex(0)
for _ in range(10):
    app.processEvents()
    time.sleep(.01)
assert window.squad.athlete_page.figure.height() >= 160
figure_widget = window.squad.athlete_page.figure
visible = QRect(figure_widget.mapToGlobal(QPoint(0, 0)), figure_widget.size())
ancestor = figure_widget.parentWidget()
while ancestor is not None:
    visible = visible.intersected(QRect(ancestor.mapToGlobal(QPoint(0, 0)), ancestor.size()))
    ancestor = ancestor.parentWidget()
assert visible.height() >= 160, "Trajectory clipped by ancestor viewport"
record("01b-athlete-trajectory", window)
window.squad.athlete_page.research_tabs.setCurrentIndex(2)
window.squad.setCurrentWidget(window.squad.board)
record("02-squad-board", window)
window._show_events_mode()
settle()
record("03-events", window)
board = window.squad.board.board
for name, dialog in (("04-flag-rules", RulesDialog(board["metrics"], board["rules"], window)),
                     ("05-simulation", SimulationDialog(service, window.run_task, identity, board, None, window))):
    if name == "05-simulation":  # show the results tab after a real run
        def run_then_record(d=dialog, n=name):
            d.run(False)
            settle()
            record(n, d)
            d.reject()
        QTimer.singleShot(300, run_then_record)
    else:
        QTimer.singleShot(300, lambda n=name, d=dialog: (record(n, d), d.reject()))
    dialog.exec()
report["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
report["screenshots"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob("*.png")}
(out / "scaling-receipt.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
window.close()
