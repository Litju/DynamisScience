"""Complete synthetic research lifecycle using native task actions and independent arithmetic."""
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
from statistics import mean
import sys

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from res621_study import prepare, protocol, visits, run, CONTEXT
from dynamis_science import experiments, experiment_series, researchstore as store
from dynamis_science.desktop.import_review import ImportReviewDialog
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService
from test_importer import service
from test_research_workflow import idle, choose, stage


def select_members(panel, indices):
    panel.history.setCurrentIndex(0)
    panel.roster.clearSelection()
    for index in indices:
        panel.roster.selectionModel().select(panel.roster.model().index(index, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)


def test_twelve_week_researcher_journey(qtbot, service, tmp_path, monkeypatch):
    if os.environ.get('RES621_EVIDENCE_DIR'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeuib.ttf')
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, text, *args: errors.append(str(text)))
    monkeypatch.setattr(QMessageBox, 'exec', lambda box: errors.append(box.text()))
    case = prepare(service, tmp_path)
    identity, revision = case['id'], case['revisions'][-1]
    frozen_run = copy.deepcopy(case['runs'][1])
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    window.resize(1366, 720)
    evidence = Path(os.environ['RES621_EVIDENCE_DIR']) if os.environ.get('RES621_EVIDENCE_DIR') else None
    def capture(name):
        if evidence:
            evidence.mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(evidence/f'{name}.png'))
    idle(qtbot, window)
    window._show_study(identity, service.get_study_detail(identity))
    idle(qtbot, window)
    choose(window.scope_picker, case['invs'][0]['id'])
    idle(qtbot, window)
    panel = window.research.individual
    stage(window, 'Protocol')
    # Amend only a future period through the real protocol form and save action.
    panel.period_table.item(4, 6).setText('Future comparator recovery log')
    panel.amendment_reason.setText('Record recovery in the future final comparator')
    panel.save_protocol_button.click()
    idle(qtbot, window)
    assert panel.payload['investigation']['protocol']['version'] == 2
    capture('01-protocol-amendment')
    assert experiments.timeline(panel.investigation_id, 1)['protocol']['periods'] == case['invs'][0]['protocol']['periods']
    # Import follow-up through native questions, QC, admission and same-workspace append.
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kw: ('Append compatible measurements (same participant identifiers)', True))
    dialog = ImportReviewDialog(service, window.run_task, lambda record: window._admission_saved(record, identity), window)
    dialog.show()
    dialog.load(str(case['paths'][2]))
    idle(qtbot, window)
    answers = {**CONTEXT, 'session_id':'batch-3', 'sampling_hz':'1000'}
    for _ in range(25):
        if dialog.state != 'attention':
            break
        key = dialog.question_key
        if key == 'privacy_status':
            dialog.answer_choice.setCurrentIndex(dialog.answer_choice.findData(answers[key]))
        else:
            dialog.answer.setText(str(answers[key]))
        dialog.continue_button.click()
        idle(qtbot, window)
    assert dialog.state == 'ready', dialog.summary.text()
    dialog.open_button.click()
    idle(qtbot, window)
    dialog.close()
    revision = window.current_study['active_data_revision_id']
    assert revision != case['revisions'][-1]
    assert window.current_study_id == identity and len(store.data_revisions(identity)) == 3
    assert len(service.participant_catalogue(identity)['participants']) == 20
    assert window.research_context['subject_id'] == 'SUB-001'
    stage(window, 'Data / QC')
    capture('02-appended-revision')
    # Bulk synthetic conduct uses the same existing visit engine. Last visit is entered in the UI.
    invs = [store.get_investigation(i['id']) for i in case['invs']]
    invs = [visits(service, inv, revision, range(7, 12 if index == 0 else 13)) for index, inv in enumerate(invs)]
    panel.reload()
    idle(qtbot, window)
    stage(window, 'Observations')
    panel._edit_timeline_visit(10, 0)
    assert panel.visit_schedule.currentData() == 12
    panel.visit_time.setText('2026-11-02T10:00:00-03:00')
    panel.visit_exposure.setText('Reported supervised dose 3')
    panel.visit_adherence.setText('100')
    panel.save_visit_button.click()
    idle(qtbot, window)
    assert '11 measured' in panel.conduct_status.text()
    panel._edit_timeline_visit(10, 0)
    assert panel.visit_supersedes.currentData() == panel.payload['experiment']['rows'][10]['visit']['id']
    assert panel.visit_exposure.text() == 'Reported supervised dose 3'
    panel.visit_editor_toggle.setChecked(False)
    capture('03-actual-observations')
    assert not panel.visit_history.isVisible()
    panel.conduct_details.setChecked(True)
    assert panel.visit_history.rowCount() == 11
    panel.conduct_details.setChecked(False)
    # Native analysis executes the existing qualified description, then hands off to Results.
    panel.analyze_experiment_button.click()
    panel.run_button.click()
    idle(qtbot, window)
    latest = panel.run_picker.currentData()
    assert latest['data_revision_id'] == revision
    assert latest['method_id'] == 'METH-EXPERIMENT-DESC'
    assert 'not causal' in panel.result_view.toPlainText().lower()
    capture('04-descriptive-result')
    # Independent CSV arithmetic: equal session weights, three trials per observed occasion.
    values = {}
    for path in case['paths']:
        with path.open() as stream:
            for row in csv.DictReader(stream):
                if row['Athlete'] == 'SUB-001':
                    values.setdefault(int(row['week']), []).append(float(row['Jump Height (cm)']))
    observed = latest['result']['observations']
    for row in observed:
        assert row['mean'] == pytest.approx(mean(values[row['scheduled_occasion']]))
    # A nonrandom assignment stays ineligible, even though every scheduled outcome is present.
    stage(window, 'Analysis')
    exact = next(i for i in range(panel.method_picker.count()) if panel.method_picker.itemData(i)['method_id']=='METH-ONSET-EXACT')
    panel.method_picker.setCurrentIndex(exact)
    assert not panel.run_button.isEnabled()
    capture('05-ineligible-randomized-method')
    # Cohort + individual report sections retain the exact run scopes.
    choose(window.scope_picker, None)
    idle(qtbot, window)
    stage(window, 'Analysis')
    window.research.execute_button.click()
    idle(qtbot, window)
    cohort = window.research.latest_run
    assert cohort['result']['n_subjects'] == 20
    choose(window.scope_picker, invs[0]['id'])
    idle(qtbot, window)
    target = tmp_path/'week12-native.html'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kw: (str(target), 'HTML report (*.html)'))
    window._export_combined_report()
    idle(qtbot, window)
    assert target.is_file() and latest['id'] in target.read_text(encoding='utf-8')
    # Two experiment series exist; the second deliberately exposes mismatched definitions/missingness.
    for inv in invs[1:]:
        run(service, identity, revision, store.get_investigation(inv['id']))
    stage(window, 'Series comparison')
    window.research.series.reload()
    idle(qtbot, window)
    series = window.research.series
    select_members(series, [0, 1, 19])
    series.save.click()
    idle(qtbot, window)
    assert len(experiment_series.history(identity)) == 2
    assert any(c['status']=='REVIEW_REQUIRED' for c in series.history.currentData()['comparison']['checks'])
    capture('06-frozen-series')
    assert experiment_series.history(identity)[0] == case['frozen_series']
    assert store.get_run(frozen_run['id']) == frozen_run
    # Inline history exports the original bytes without switching revision or scope.
    stage(window, 'Reports / history')
    idle(qtbot, window)
    history = window.research.history_panel
    index = next(i for i in range(history.picker.count()) if history.picker.itemData(i)[1]['version']==case['report_version'])
    history.picker.setCurrentIndex(index)
    idle(qtbot, window)
    original = tmp_path/'week6-reopened.html'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kw: (str(original), 'HTML report (*.html)'))
    assert window.rect().contains(history.export.mapTo(window, history.export.rect().center()))
    qtbot.mouseClick(history.export, Qt.MouseButton.LeftButton)
    idle(qtbot, window)
    assert original.read_bytes() == case['report_bytes']
    capture('07-week6-frozen-report')
    history.kind.setCurrentText('Saved analyses')
    assert 'SUB-001' in history.picker.currentText()
    assert store.get_entity(identity)['active_data_revision_id'] == revision
    assert store.get_entity(identity)['research_context']['subject_id'] == 'SUB-001'
    assert not errors, errors
    # The two destinations remain in keyboard order while viewing a historical report.
    window.activateWindow()
    qtbot.wait(10)
    window.investigate_button.setFocus()
    assert window.investigate_button.hasFocus()
    qtbot.keyClick(window.investigate_button, Qt.Key.Key_Tab)
    assert window.destinations["design"].hasFocus()
    window.resize(911, 480)  # 1366×720 physical-area equivalent at 150%; not actual Windows DPI.
    stage(window, 'Observations')
    assert panel.visit_editor_toggle.isVisible()
    assert panel.analyze_experiment_button.isVisible()
    if evidence:
        assert window.grab().save(str(evidence/'09-compact-geometry.png'))
    stage(window, 'Reports / history')
    idle(qtbot, window)
    window.close()
    reopened = MainWindow(DynamisAppService())
    qtbot.addWidget(reopened)
    idle(qtbot, reopened)
    reopened._show_study(identity, service.get_study_detail(identity))
    idle(qtbot, reopened)
    assert reopened.research.tabs.currentWidget() is reopened.research.history_panel
    assert reopened.scope_picker.currentData() == invs[0]['id']
    if evidence:
        assert reopened.grab().save(str(evidence/'08-reopened-history.png'))
    assert hashlib.sha256(service.export_report_html(identity, str(tmp_path/'restarted.html'), case['report_version']).read_bytes()).digest() == hashlib.sha256(case['report_bytes']).digest()
    if evidence:
        (evidence/'week6-frozen.html').write_bytes(case['report_bytes'])
        (evidence/'week12-frozen.html').write_bytes(target.read_bytes())
        receipt = dict(platform='Qt offscreen; not physical Windows display acceptance',
            workspace_id=identity, athletes=20, study_weeks=12, admitted_measurement_rows=708,
            data_revisions=[r['id'] for r in store.data_revisions(identity)],
            individual_protocols=len(service.individual_investigations(identity)),
            actual_scheduled_visits=sum(len(store.get_investigation(i['id'])['experiment_visits']) for i in invs),
            frozen_run_ids=[r['id'] for r in store.list_runs(identity)],
            frozen_series_ids=[s['id'] for s in experiment_series.history(identity)],
            old_report_sha256=hashlib.sha256(case['report_bytes']).hexdigest(),
            reopened_report_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            independent_session_means={str(r['scheduled_occasion']):mean(values[r['scheduled_occasion']]) for r in observed},
            randomized_onset_run=False, interpretation='Descriptive, nonrandom assignments; no causal effect',
            context_restored_after_restart=True, errors=errors)
        (evidence/'journey-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    reopened.close()
