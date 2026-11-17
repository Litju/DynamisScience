"""Historical reports stay readable without selecting their data revision or rerunning."""
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QPushButton, QTextBrowser

from dynamis_science import researchstore as store
from dynamis_science.desktop.main_window import MainWindow
from test_randomized_onset import service, prospective, conduct, run


def test_preview_and_export_frozen_report_without_changing_active_revision(qtbot, service, prospective, tmp_path, monkeypatch):
    s = prospective
    revision = conduct(service, s)
    saved = run(service, s, s['athletes'][0], revision)
    original = service.export_workspace_report(s['id'], saved['id'], str(tmp_path/'original.html')).read_bytes()
    reports = store.report_versions(s['id'])
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    idle = lambda: qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    idle()
    window._show_study(s['id'], service.get_study_detail(s['id']))
    idle()
    # Keep the real dialog visible while the test drives its asynchronous callbacks.
    monkeypatch.setattr(QDialog, 'exec', lambda dialog: dialog.show())
    window._workspace_history()
    idle()
    dialog = next(d for d in window.findChildren(QDialog) if d.windowTitle() == 'Workspace history')
    picker = next(w for w in dialog.findChildren(QComboBox) if w.accessibleName() == 'Workspace history selection')
    picker.setCurrentIndex(next(i for i in range(picker.count()) if picker.itemData(i)[0] == 'report'))
    idle()
    detail = next(w for w in dialog.findChildren(QTextBrowser) if w.accessibleName() == 'Workspace history detail or frozen report')
    assert 'Exact randomized onset' in detail.toPlainText()
    assert '1/26' in detail.toPlainText() and 'participant P01' in detail.toPlainText()
    button = next(w for w in dialog.findChildren(QPushButton) if w.text() == 'Export selected frozen report…')
    assert button.isEnabled()
    target = tmp_path/'historical.html'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kw: (str(target), 'HTML'))
    button.click()
    idle()
    assert target.read_bytes() == original
    assert store.report_versions(s['id']) == reports
    assert service.get_study_detail(s['id'])['active_data_revision_id'] == revision
    dialog.close()
    window.close()
