"""Native Qt geometry evidence; synthetic stores only, no physical-display claim."""
import json
import os
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QToolBar, QTextBrowser

from dynamis_science.desktop.main_window import MainWindow
from test_experiments import plan
from test_longitudinal_research import service, study
from test_research_workflow import choose, stage
from test_randomized_onset import prospective


def test_compact_surface_receipt(qtbot, service, study, monkeypatch):
    font = 'C:/Windows/Fonts/segoeui.ttf'
    if Path(font).exists():
        QFontDatabase.addApplicationFont(font)
        QApplication.instance().setFont(QFont('Segoe UI', 10))
    invs = []
    for subject in ('P01', 'P02'):
        inv = service.create_individual_investigation(study['id'], subject, subject+' training experiment')
        invs.append(service.save_protocol(inv['id'], plan(), inv['version']))
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.show()
    idle = lambda: qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    idle()
    window._show_study(study['id'], service.get_study_detail(study['id']))
    idle()
    panel = window.research.individual
    panel.set_investigation(study['id'], invs[0]['id'])
    idle()
    choose(window.scope_picker, invs[0]['id'])
    idle()
    out = Path(os.environ['RES621_COMPACT_EVIDENCE']) if os.environ.get('RES621_COMPACT_EVIDENCE') else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    receipt = {'platform': QApplication.platformName(), 'physical_display': False, 'geometries': []}
    for width, height in ((911, 480), (1024, 640), (1366, 720)):
        window.resize(width, height)
        stage(window, 'Series comparison')
        idle()
        series = window.research.series
        selection = series.roster.selectionModel()
        for row in range(2):
            selection.select(series.roster.model().index(row, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        qtbot.wait(40)
        bars = {bar.objectName(): [a.text() for a in bar.actions() if bar.widgetForAction(a) and bar.widgetForAction(a).isVisible()]
                for bar in window.findChildren(QToolBar) if bar.objectName() in ('PersistentWorkspaceActions', 'ResearchContext')}
        record = {'requested': [width, height], 'actual': [window.width(), window.height()],
                  'roster_viewport': series.roster.viewport().width(),
                  'roster_columns': sum(series.roster.columnWidth(c) for c in range(series.roster.columnCount()) if not series.roster.isColumnHidden(c)),
                  'roster_scroll': series.roster.horizontalScrollBar().maximum(), 'toolbar_visible': bars}
        assert series.roster.horizontalScrollBar().maximum() == 0
        assert {m['subject_id'] for m in series.selected()} == {'P01', 'P02'}
        context_bar = window.findChild(QToolBar, 'ResearchContext')
        for widget in (window.investigate_button, window.study_button):
            assert widget.isVisible() and not widget.visibleRegion().isEmpty()
            assert context_bar.rect().contains(widget.geometry())
        for name in ('Add data', 'Analyze', 'Export report'):
            assert not window.workspace_actions[name].shortcut().isEmpty()
        assert not window.scope_picker.isVisible() and not window.stage_picker.isVisible()
        if out:
            window.grab().save(str(out/f'series-{width}.png'))
        stage(window, 'Protocol')
        qtbot.wait(40)
        scroll = panel.tabs.currentWidget()
        record['protocol_scroll'] = scroll.verticalScrollBar().maximum()
        record['save_visible_in_protocol_viewport'] = scroll.viewport().rect().contains(panel.save_protocol_button.mapTo(scroll.viewport(), panel.save_protocol_button.rect().center()))
        assert record['save_visible_in_protocol_viewport'] and record['protocol_scroll'] == 0
        before = panel.protocol_from_form()
        for section in range(4):
            bar = panel.protocol_sections.tabBar()
            qtbot.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(section).center())
            assert panel.protocol_sections.currentIndex() == section
            assert panel.protocol_from_form() == before
            assert scroll.viewport().rect().contains(panel.save_protocol_button.mapTo(scroll.viewport(), panel.save_protocol_button.rect().center()))
            if out:
                window.grab().save(str(out/f'protocol-section-{section}-{width}.png'))
        panel.protocol_sections.setCurrentIndex(0)
        if out:
            window.grab().save(str(out/f'protocol-{width}.png'))
        stage(window, 'Data / QC')
        idle()
        qtbot.wait(40)
        record['preview_columns'] = window.research.table_model.columns
        assert 'Source QC:' in window.research.data_summary.text()
        record['preview_visible_columns'] = [name for c, name in enumerate(window.research.table_model.columns)
                                              if not window.research.table.isColumnHidden(c)]
        assert record['preview_visible_columns'][:2] == ['subject_id', 'week']
        assert 'instrument_id' not in record['preview_visible_columns']
        assert 'jump_height_cm' in record['preview_visible_columns']
        model = window.research.table_model
        qtbot.waitUntil(lambda: bool(model.rows), timeout=5000)
        c = model.columns.index('jump_height_cm')
        assert '(cm)' in model.headerData(c, Qt.Orientation.Horizontal)
        assert model.data(model.index(0, c), Qt.ItemDataRole.ToolTipRole) == str(model.rows[0]['jump_height_cm'])
        window.research.preview_metadata.setChecked(True)
        assert not window.research.table.isColumnHidden(model.columns.index('instrument_id'))
        window.research.preview_metadata.setChecked(False)
        monkeypatch.setattr(QDialog, 'exec', lambda dialog: dialog.show())
        window.research.table.setCurrentIndex(model.index(0, c))
        window.research._preview_details()
        dialog = next(d for d in window.research.findChildren(QDialog) if d.windowTitle() == 'Measurement row details / provenance')
        text = dialog.findChild(QTextBrowser).toPlainText()
        assert 'instrument_id' in text and study['rev1'] in text
        dialog.close()
        dialog.deleteLater()
        if out:
            window.grab().save(str(out/f'preview-{width}.png'))
        receipt['geometries'].append(record)
    if out:
        (out/'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    window.close()


def test_primary_toolbar_keyboard_actions(qtbot, service, monkeypatch):
    from dynamis_science.desktop.main_window import ResearchWorkbench
    called = []
    monkeypatch.setattr(MainWindow, '_add_workspace_data', lambda self: called.append('import'))
    monkeypatch.setattr(MainWindow, '_analyze_workspace', lambda self: called.append('analyze'))
    monkeypatch.setattr(ResearchWorkbench, 'export_report', lambda self: called.append('report'))
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.resize(911, 480)
    window.show()
    qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    window.activateWindow()
    window.setFocus()
    qtbot.wait(30)
    for key in (Qt.Key.Key_I, Qt.Key.Key_A, Qt.Key.Key_X):
        qtbot.keyClick(window, key, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert called == ['import', 'analyze', 'report']
    window.close()


def test_series_sort_keeps_athlete_identity_and_full_details(qtbot, service, study, monkeypatch):
    from dynamis_science.desktop.experiment_series import ExperimentSeriesPanel
    from dynamis_science import researchstore
    for subject in ('P01', 'P02'):
        inv = service.create_individual_investigation(study['id'], subject, subject+' experiment')
        service.save_protocol(inv['id'], plan(), inv['version'])
    panel = ExperimentSeriesPanel(service, lambda work, done, label: done(work()))
    qtbot.addWidget(panel)
    panel.set_workspace(study['id'])
    panel.roster.sortItems(0, Qt.SortOrder.DescendingOrder)
    panel.roster.selectionModel().select(panel.roster.model().index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
    assert panel.selected()[0]['subject_id'] == 'P02'
    monkeypatch.setattr(QDialog, 'exec', lambda dialog: dialog.show())
    panel.inspect_selected()
    view = panel.findChild(QDialog).findChild(QTextBrowser)
    assert 'P02' in view.toPlainText() and study['rev1'] in view.toPlainText()
    panel.roster.selectAll()
    panel.capture()
    saved = panel.history.currentData()['comparison']
    assert {m['subject_id'] for m in saved['members']} == {'P01', 'P02'}
    assert researchstore.get_entity(study['id'])['active_data_revision_id'] == study['rev1']


def test_visit_counts_sort_numerically(qtbot):
    from PySide6.QtWidgets import QTableWidget
    from dynamis_science.desktop.experiment_series import VisitCountItem
    table = QTableWidget(3, 1)
    qtbot.addWidget(table)
    for row, counts in enumerate(((10, 12), (2, 12), (2, 5))):
        table.setItem(row, 0, VisitCountItem(*counts))
    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    assert [table.item(row, 0).text() for row in range(3)] == ['2 / 5', '2 / 12', '10 / 12']


def test_compact_randomized_schedule_keeps_frozen_constraints(qtbot, service, prospective):
    from dynamis_science.desktop.individual_research import IndividualResearchPanel
    panel = IndividualResearchPanel(service, lambda work, done, label: done(work()))
    qtbot.addWidget(panel)
    panel.set_investigation(prospective['id'], prospective['athletes'][0]['id'])
    panel.resize(911, 480)
    panel.show()
    panel.tabs.setCurrentIndex(next(i for i in range(panel.tabs.count()) if panel.tabs.tabText(i) == 'Protocol'))
    panel.protocol_sections.setCurrentIndex(2)
    qtbot.wait(40)
    assert panel.protocol_sections.currentWidget().horizontalScrollBar().maximum() == 0
    assert panel.onset_starts.isReadOnly() and panel.onset_dates.isReadOnly()
    assert not panel.design_picker.isEnabled() and not panel.onset_acknowledge.isEnabled()
    assert 'assignment-dependent' in panel.onset_acknowledge.toolTip()
    if os.environ.get('RES621_COMPACT_EVIDENCE'):
        panel.grab().save(str(Path(os.environ['RES621_COMPACT_EVIDENCE'])/'randomized-schedule-911.png'))
