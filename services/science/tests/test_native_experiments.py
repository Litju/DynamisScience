"""Exercise the native protocol → revision → visit → history flow for two athletes."""
import os
from statistics import mean

import pytest

from dynamis_science import researchstore
from dynamis_science.desktop.individual_research import IndividualResearchPanel, _cell
from dynamis_science.desktop.services import DynamisAppService
from test_experiments import plan
from test_longitudinal_research import service, study, value


def test_native_two_athlete_protocol_visit_workflow(qtbot, service, study):
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    # Offscreen Qt needs an explicitly registered font on this Windows test host.
    font_path = 'C:/Windows/Fonts/segoeui.ttf'
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)
        QApplication.instance().setFont(QFont('Segoe UI', 10))
    panel = IndividualResearchPanel(service, lambda op, done, label: done(op()))
    qtbot.addWidget(panel)
    panel.resize(1300, 950)
    panel.show()
    investigations = []
    for subject in ('P01', 'P02'):
        inv = service.create_individual_investigation(study['id'], subject, f'{subject} prospective experiment')
        investigations.append(inv)
        panel.set_investigation(study['id'], inv['id'])
        panel.design_picker.setCurrentIndex(panel.design_picker.findData('N_OF_1_EXPERIMENT'))
        panel.protocol_question.setText(f'How does {subject} change during the documented training block?')
        panel.assignment.setText(plan()['assignment'])
        panel.prespecified.setChecked(True)
        panel.testing_occasions.setText('4, 5, 6, 7, 8')
        for period in plan()['periods']:
            panel._add_period(period)
        panel.save_protocol_button.click()
        assert panel.protocol_history.count() == 1
        assert panel.timeline_table.rowCount() == 5
        assert _cell(panel.timeline_table, 0, 3) == 'PLANNED'
        assert 'NOT_QUALIFIED' in panel.experiment_summary.toPlainText()
        assert panel.period_table.isColumnHidden(4) and panel.period_table.isColumnHidden(5)
    rev2 = service.attach_workspace_data(study['id'], study['follow_up'], append=True,
        confirm_participant_ids=True, base_revision=study['rev1'])['active_data_revision_id']
    for index, inv in enumerate(investigations, 1):
        panel.set_investigation(study['id'], inv['id'])
        assert panel.visit_history.rowCount() == 0
        assert panel.visit_exposure.text() == ''
        for at in (4, 5):
            panel.visit_schedule.setCurrentIndex(panel.visit_schedule.findData(at))
            panel.visit_time.setText('2026-11-16T11:00:00-03:00')
            panel.visit_exposure.setText(f'Actual training reported for P0{index}, occasion {at}')
            panel.visit_adherence.setText('85')
            panel.save_visit_button.click()
        expected = mean(value(index, 5, t) for t in range(1, 3+index%2))
        assert float(_cell(panel.timeline_table, 1, 7)) == pytest.approx(expected, abs=.005)
        assert _cell(panel.timeline_table, 1, 9) == rev2
        assert panel.visit_history.rowCount() == 2
        panel.visit_schedule.setCurrentIndex(panel.visit_schedule.findData(7))
        panel.visit_status.setCurrentText('MISSING')
        panel.visit_missing.setText('Athlete unavailable')
        panel.visit_exposure.setText('Unknown')
        panel.save_visit_button.click()
        assert _cell(panel.timeline_table, 3, 3) == 'MISSING'
        assert panel.visit_history.rowCount() == 3
        panel.visit_status.setCurrentText('MEASURED')
        # Selecting unavailable inference cannot execute a run.
        pos = next(i for i in range(panel.method_picker.count())
                   if panel.method_picker.itemData(i)['method_id'] == 'METH-EXPERIMENT')
        panel.method_picker.setCurrentIndex(pos)
        before = len(researchstore.list_runs(study['id']))
        assert not panel.run_button.isEnabled()
        panel.execute()
        assert len(researchstore.list_runs(study['id'])) == before
    a, b = investigations
    panel.set_investigation(study['id'], a['id'])
    panel.amendment_reason.setText('Longer final comparison period')
    panel.period_table.item(4, 3).setText('9')
    panel.testing_occasions.setText('4, 5, 6, 7, 8, 9')
    panel.save_protocol_button.click()
    assert panel.protocol_history.count() == 2 and panel.timeline_table.rowCount() == 6
    panel.protocol_history.setCurrentIndex(0)
    assert panel.timeline_table.rowCount() == 5
    assert 'P01' in panel.experiment_summary.toPlainText()
    reopened = IndividualResearchPanel(DynamisAppService(), lambda op, done, label: done(op()))
    qtbot.addWidget(reopened)
    reopened.set_investigation(study['id'], b['id'])
    assert reopened.protocol_history.count() == 1 and reopened.visit_history.rowCount() == 3
    assert all('P01' not in _cell(reopened.timeline_table, row, 4) for row in range(5))
    assert 'P02' in reopened.experiment_summary.toPlainText()
    panel.protocol_history.setCurrentIndex(1)
    panel.tabs.setCurrentIndex(next(i for i in range(panel.tabs.count()) if panel.tabs.tabText(i) == 'Visits and timeline'))
    qtbot.wait(50)
    if os.environ.get('RES717_SCREENSHOT'):
        assert panel.grab().save(os.environ['RES717_SCREENSHOT'])


def test_switch_discards_late_experiment_completion(qtbot, service, study):
    from PySide6.QtWidgets import QLabel
    a = service.create_individual_investigation(study['id'], 'P01', 'A')
    b = service.create_individual_investigation(study['id'], 'P02', 'B')
    service.save_protocol(a['id'], plan(), a['version'])
    queued = []
    panel = IndividualResearchPanel(service, lambda op, done, label: queued.append((op, done)))
    qtbot.addWidget(panel)
    panel.set_investigation(study['id'], a['id'])
    panel.figure_holder.layout().addWidget(QLabel('P01 previous trajectory'))
    old = service.individual_research(a['id'])
    panel.set_investigation(study['id'], b['id'])
    assert panel.figure_holder.layout().count() == 0
    queued[0][1](old)
    assert panel.protocol_history.count() == 0 and panel.timeline_table.rowCount() == 0
    queued[1][1](queued[1][0]())
    assert 'P02' in panel.header.text() and panel.protocol_history.count() == 0
