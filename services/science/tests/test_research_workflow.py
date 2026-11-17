"""Researcher task paths through the real MainWindow and persisted revisions."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from dynamis_science import researchstore
from dynamis_science.desktop.main_window import MainWindow
from dynamis_science.desktop.services import DynamisAppService
from test_longitudinal_research import service, study
from test_experiments import plan


def idle(qtbot, window):
    qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)


def choose(picker, value):
    index = picker.findData(value)
    assert index >= 0
    picker.setCurrentIndex(index)
    picker.activated.emit(index)


def stage(window, name):
    index = window.stage_picker.findText(name)
    window.stage_picker.setCurrentIndex(index)
    window.stage_picker.activated.emit(index)


def test_research_tasks_keep_athlete_across_data_series_append_and_restart(qtbot, service, study, monkeypatch):
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, text, *args: errors.append(str(text)))
    monkeypatch.setattr(QMessageBox, 'exec', lambda box: errors.append(box.text()))
    identity = study['id']
    invs = []
    for subject in ('P01', 'P02'):
        inv = service.create_individual_investigation(identity, subject, subject+' training')
        invs.append(service.save_protocol(inv['id'], plan(), inv['version']))
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    idle(qtbot, window)
    window._show_study(identity, service.get_study_detail(identity))
    idle(qtbot, window)
    choose(window.scope_picker, invs[0]['id'])
    idle(qtbot, window)
    panel = window.research.individual
    for name in ('Protocol', 'Observations', 'Analysis', 'Results', 'Data / QC', 'Series comparison'):
        stage(window, name)
        idle(qtbot, window)
        assert window.research_context['subject_id'] == 'P01'
        assert panel.investigation_id == invs[0]['id']
        assert window.scope_picker.currentData() == invs[0]['id']
        assert 'Protocol v1' in window.context_binding.text()
        assert researchstore.get_entity(identity)['active_data_revision_id'] == study['rev1']
    assert window.research.tabs.currentWidget() is window.research.series
    # One import entry action; the admitted-dataset alternative remains in Research.
    opened = []
    monkeypatch.setattr(window, '_open_import', lambda: opened.append(identity))
    window._add_workspace_data()
    assert opened == [identity]
    revision = service.attach_workspace_data(identity, study['follow_up'], append=True,
        confirm_participant_ids=True, base_revision=study['rev1'])['active_data_revision_id']
    window._show_study(identity, service.get_study_detail(identity))
    idle(qtbot, window)
    assert not errors, errors
    assert window.research.tabs.currentWidget() is window.research.series
    assert panel.payload['data_revision_id'] == revision
    choose(window.scope_picker, invs[1]['id'])
    idle(qtbot, window)
    stage(window, 'Analysis')
    assert panel.payload['investigation']['scope']['subject_id'] == 'P02'
    assert not panel.payload['experiment']['protocol'].get('allocation')
    # Randomized inference stays blocked after navigation and append.
    pos = next(i for i in range(panel.method_picker.count())
               if panel.method_picker.itemData(i)['method_id'] == 'METH-ONSET-EXACT')
    panel.method_picker.setCurrentIndex(pos)
    assert not panel.run_button.isEnabled()
    window.close()
    reopened = MainWindow(DynamisAppService())
    qtbot.addWidget(reopened)
    idle(qtbot, reopened)
    reopened._show_study(identity, service.get_study_detail(identity))
    idle(qtbot, reopened)
    assert reopened.scope_picker.currentData() == invs[1]['id']
    assert reopened.stage_picker.currentText() == 'Analysis'
    assert reopened.research.individual.tabs.tabText(reopened.research.individual.tabs.currentIndex()) == 'Analysis'
    reopened.close()
