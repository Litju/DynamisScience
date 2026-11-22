"""Exercise the source-run Windows workspace inside a bounded RES-760 QA allocation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter, sleep

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))

from dynamis_science.qa_cleanup import read_marker


def walk(scale: str, appearance: str | None = None) -> None:
    scratch = Path(os.environ["DYNAMISSCIENCE_QA_RUN_ROOT"]).resolve(strict=True)
    marker = read_marker(scratch)
    if marker["issue_id"] != "RES-760":
        raise ValueError("Run the walkthrough inside a marked RES-760 QA allocation.")
    private = scratch / "private"
    private.mkdir()
    evidence = scratch / "captures"
    evidence.mkdir()
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ["QT_SCALE_FACTOR"] = scale
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(private)

    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDialog, QInputDialog

    from dynamis_science.desktop import theme
    from dynamis_science.desktop.data_workspace import DataWorkspaceDialog
    from dynamis_science.desktop.main_window import MainWindow
    from dynamis_science.desktop.performance_navigation import PERFORMANCE_PAGE_KEYS
    from dynamis_science.desktop.services import DynamisAppService
    from res621_study import follow_up, prepare

    app = QApplication([])
    assert app.platformName() == "windows"
    service = DynamisAppService()
    case = follow_up(service, prepare(service, private), private)
    window = MainWindow(service)
    if appearance:
        window.workbench.set_theme(appearance)
    initial_appearance = theme.current_theme()
    screen = window.screen()
    work_area = screen.availableGeometry()
    window.resize(min(1366, work_area.width() - 16), min(720, work_area.height() - 36))
    window.show()
    window.activateWindow()
    steps = []

    def wait_for(predicate) -> None:
        deadline = perf_counter() + 30
        while not predicate():
            if perf_counter() >= deadline:
                last = steps[-1]["step"] if steps else "launch"
                raise TimeoutError(f"Native view timed out after {last}: {window.status_text.text()}")
            app.processEvents()
            sleep(0.015)
        QTest.qWait(45)

    def click(button) -> None:
        assert button.isVisible() and button.isEnabled(), button.text()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    def capture(name, started, target=window) -> None:
        assert target.isVisible()
        if target is window:
            assert window.frameGeometry().height() <= work_area.height() + 2, (
                name, window.frameGeometry().height(), work_area.height())
            assert window.frameGeometry().width() <= work_area.width() + 2, (
                name, window.frameGeometry().width(), work_area.width())
        pixmap = target.grab()
        filename = f"{len(steps) + 1:02d}-{name}.png"
        assert not pixmap.isNull() and pixmap.save(str(evidence / filename))
        steps.append({
            "step": name,
            "ms_including_settle_and_capture": round(1000 * (perf_counter() - started)),
            "pixels": [pixmap.width(), pixmap.height()],
            "frame_fits_work_area": (target.frameGeometry().width() <= work_area.width() + 2
                                     and target.frameGeometry().height() <= work_area.height() + 2),
            "file": filename,
        })

    def visit(name, button, ready=lambda: True) -> None:
        started = perf_counter()
        click(button)
        wait_for(lambda: ready() and not window.runner.active)
        capture(name, started)

    def dialog_step(name, action, inspect=None) -> None:
        started = perf_counter()
        first_step = len(steps)
        timer = QTimer()
        errors = []

        def on_dialog() -> None:
            modal = app.activeModalWidget()
            if modal is None or window.runner.active:
                return
            timer.stop()
            try:
                capture(name, started, modal)
                if inspect:
                    inspect(modal)
            except Exception as error:
                errors.append(error)
                modal.reject()
            else:
                if not inspect:
                    modal.reject()

        timer.timeout.connect(on_dialog)
        timer.start(30)
        action()
        timer.stop()
        if errors:
            raise errors[0]
        assert len(steps) > first_step and steps[first_step]["step"] == name

    started = perf_counter()
    wait_for(lambda: not window.runner.active and hasattr(window, "studies"))
    capture("library", started)
    def choose_study(dialog) -> None:
        assert isinstance(dialog, QInputDialog)
        label = next(item for item in dialog.comboBoxItems() if item.endswith(case["id"]))
        dialog.setTextValue(label)
        dialog.accept()

    dialog_step("open-study", lambda: click(window.study_home.open_button), choose_study)
    wait_for(lambda: window._investigation_visible() and not window.runner.active)
    panel = window.research.training_context
    athlete, revision = panel.scope.currentData(), panel.revision
    assert revision == case["revisions"][-1]
    capture("investigate", perf_counter())
    actions = {action.text(): action for action in panel.research_actions.menu().actions()}
    for command, name in (
        ("Plan", "individual-protocol"), ("Record visits", "individual-visits"),
        ("Run analysis", "individual-analysis"), ("Saved analyses", "individual-results"),
        ("Compare with cohort", "individual-comparison"), ("Scenarios", "individual-scenarios"),
        ("Assessment data", "individual-data"),
    ):
        dialog_step(name, actions[command].trigger)
    started = perf_counter()
    panel.athlete_record_action.trigger()
    wait_for(lambda: window.perspectives.currentWidget() is window.squad
             and window.squad.currentWidget() is window.squad.athlete_page and not window.runner.active)
    assert window.squad.athlete_page.athlete["subject_id"] == athlete
    capture("athlete-record", started)
    page = window.squad.athlete_page
    page.view_values.setFocus()
    QTest.keyClick(page.view_values, Qt.Key.Key_Space)
    assert page.measurement_view.currentWidget() is page.measurement_values
    capture("athlete-values", perf_counter())
    QTest.keyClick(page.view_values, Qt.Key.Key_Space)
    assert page.measurement_view.currentWidget() is page.figure
    visit("library-with-study", window.study_button)
    visit("design", window.destinations["design"])
    visit("evidence", window.destinations["evidence"])
    visit("analyze", window.destinations["analyze"])
    def inspect_data_workspace(dialog) -> None:
        assert isinstance(dialog, DataWorkspaceDialog)
        for index in range(1, dialog.tabs.count()):
            started = perf_counter()
            dialog.tabs.setCurrentIndex(index)
            wait_for(lambda: not window.runner.active)
            name = dialog.tabs.tabText(index).replace("&", "").lower().replace(" ", "-")
            capture(f"data-workspace-{name}", started, dialog)
        dialog.reject()

    dialog_step("data-workspace", window.action_workspace.trigger, inspect_data_workspace)
    dialog_step("measurement-import", window.action_import.trigger)
    visit("operations-today", window.destinations["operations"])
    for page in PERFORMANCE_PAGE_KEYS[1:]:
        picker = window.performance_header.page_picker
        if picker.isVisible():
            started = perf_counter()
            picker.setFocus()
            QTest.keyClick(picker, Qt.Key.Key_Down)
            wait_for(lambda: page in window.performance.loaded_pages and not window.runner.active)
            capture(f"operations-{page}", started)
        else:
            button = window.performance_rail.buttons[page]
            window.performance_navigation.ensureWidgetVisible(button)
            visit(f"operations-{page}", button,
                  lambda page=page: page in window.performance.loaded_pages)
        assert window.performance.current_page == page
    visit("return-to-investigate", window.investigate_button)
    assert (panel.scope.currentData(), panel.revision) == (athlete, revision)

    def change_preferences(dialog) -> None:
        assert isinstance(dialog, QDialog)
        dialog.findChild(QComboBox).setCurrentText("Light")
        dialog.findChild(QCheckBox).setChecked(True)
        dialog.accept()

    dialog_step("preferences", window._open_preferences, change_preferences)
    wait_for(lambda: theme.current_theme() == "light" and theme.reduced_motion())
    capture("light-reduced-motion", perf_counter())
    window.investigate_button.setFocus()
    QTest.keyClick(window.investigate_button, Qt.Key.Key_Tab)
    assert window.destinations["design"].hasFocus()
    compact_width = max(720, window.width() - 150)
    window.resize(compact_width, min(max(350, window.height() - 80), work_area.height() - 36))
    wait_for(lambda: window.width() <= max(work_area.width(), compact_width))
    assert all(button.isVisible() for button in window.destinations.values())
    capture("compact", perf_counter())

    receipt = {
        "platform": app.platformName(),
        "initial_appearance": initial_appearance,
        "requested_scale": scale,
        "device_pixel_ratio": window.devicePixelRatioF(),
        "logical_work_area": [work_area.width(), work_area.height()],
        "logical_compact_window": [window.width(), window.height()],
        "fixture": "Disposable SUB-001 to SUB-020 study from res621_study.py",
        "frozen_report_unchanged_while_seeding_followup": True,
        "steps": steps,
    }
    (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    window.close()
    print(json.dumps(receipt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=("1", "1.25", "1.5"), default="1")
    parser.add_argument("--appearance", choices=("light", "dark"))
    args = parser.parse_args()
    walk(args.scale, args.appearance)
