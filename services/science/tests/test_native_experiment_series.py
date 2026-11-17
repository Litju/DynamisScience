"""Native series selection, persistence, report/drill-down and stale callback isolation."""
import copy

from PySide6.QtCore import QItemSelectionModel, QUrl
from PySide6.QtWidgets import QDialog, QPushButton, QTextBrowser

from dynamis_science import experiment_series, researchstore as store
from dynamis_science.desktop.experiment_series import ExperimentSeriesPanel, series_figure
from dynamis_science.desktop.main_window import MainWindow
from test_randomized_onset import service, prospective, conduct, run


def test_native_series_complete_journey(qtbot, service, prospective, tmp_path, monkeypatch):
    s = prospective
    revision = conduct(service, s)
    runs = [run(service, s, inv, revision) for inv in s['athletes']]
    service.export_workspace_report(s['id'], runs[0]['id'], str(tmp_path/'report.html'))
    reports = store.report_versions(s['id'])
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    idle = lambda: qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    idle()
    window._show_study(s['id'], service.get_study_detail(s['id']))
    idle()
    panel = window.research.series
    window.research.tabs.setCurrentWidget(panel)
    assert panel.roster.rowCount() == 2
    selection = panel.roster.selectionModel()
    for i in range(2):
        selection.select(panel.roster.model().index(i, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    assert panel.save.isEnabled()
    assert 'MATCH' in panel.checks.toPlainText()
    panel.save.click()
    idle()
    saved = copy.deepcopy(panel.history.currentData())
    assert saved and 'Frozen' in panel.binding.text()
    timeline_tables = panel.detail.widget().findChildren(type(panel.roster))
    assert len(timeline_tables) == 2 and all(t.rowCount() == 31 for t in timeline_tables)
    monkeypatch.setattr(QDialog, 'exec', lambda dialog: dialog.show())
    panel.checks.anchorClicked.emit(QUrl('details'))
    check_dialog = next(d for d in panel.findChildren(QDialog) if d.windowTitle() == 'Captured design comparability definitions')
    assert 'Method versions' in check_dialog.findChild(QTextBrowser).toPlainText()
    buttons = panel.detail.widget().findChildren(QPushButton)
    next(b for b in buttons if b.text() == 'Inspect captured result and diagnostics').click()
    diagnostics = next(d for d in panel.findChildren(QDialog) if 'diagnostics' in d.windowTitle())
    assert 'result_digest' in diagnostics.findChild(QTextBrowser).toPlainText()
    next(b for b in buttons if b.text().startswith('Open historical report')).click()
    idle()
    report = next(d for d in panel.findChildren(QDialog) if d.windowTitle().startswith('Frozen report'))
    assert '1/26' in report.findChild(QTextBrowser).toPlainText()
    next(b for b in buttons if b.property('investigation_id') == saved['comparison']['members'][0]['investigation_id']).click()
    idle()
    assert window.research.individual.investigation_id == saved['comparison']['members'][0]['investigation_id']
    # Reopen through a fresh panel and service call; stored content, reports and active revision do not change.
    other = ExperimentSeriesPanel(service, lambda work, done, label: done(work()))
    qtbot.addWidget(other)
    other.set_workspace(s['id'])
    other.history.setCurrentIndex(1)
    assert other.history.currentData() == saved
    assert store.report_versions(s['id']) == reports
    assert store.get_entity(s['id'])['active_data_revision_id'] == revision
    window.close()


def test_switch_clears_data_and_rejects_late_callback(qtbot, service, prospective):
    queued = []
    panel = ExperimentSeriesPanel(service, lambda work, done, label: queued.append((work, done)))
    qtbot.addWidget(panel)
    panel.set_workspace(prospective['id'])
    work, done = queued.pop()
    payload = work()
    panel.set_workspace(None)
    done(payload)
    assert not panel.payload and panel.roster.rowCount() == panel.history.count() == 0
    assert panel.detail.widget() is None


def test_figure_keeps_individual_units_actual_time_and_missing_gaps(service, prospective):
    member = experiment_series.roster(prospective['id'])['members'][0]
    figure = series_figure(member)
    axis = figure.axes[0]
    assert 'cm' in axis.get_ylabel() and 'week' in axis.get_xlabel()
    import numpy as np
    assert np.isnan(axis.lines[0].get_ydata()).all()
    assert not any('pooled' in line.get_label().lower() for line in axis.lines)
