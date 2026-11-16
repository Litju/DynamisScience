"""Native experiment → saved descriptive result → immutable scientific report."""
import copy

from PySide6.QtCore import Qt

from dynamis_science import experiments, researchstore
from dynamis_science.desktop.services import DynamisAppService
from dynamis_science.desktop.plots import run_figure
from test_experiment_analysis import service, experiment_study, execute, protocol, visit


def test_experiment_reports_freeze_corrected_and_original_results(service, experiment_study, tmp_path):
    s = experiment_study
    a,b = s['athletes']
    first = execute(service,s,a)
    original_html = service.export_workspace_report(s['id'], first['id'], str(tmp_path/'original.html')).read_text(encoding='utf-8')
    first_version = researchstore.report_versions(s['id'])[0]['version']
    original_report = copy.deepcopy(researchstore.get_report_version(s['id'], first_version))
    assert 'Experimental phase descriptions' in original_html and 'NOT_QUALIFIED' in original_html
    assert 'Session-weighted phase descriptions' in original_html
    assert 'Slope / day' in original_html and 'Actual date/time' in original_html
    assert "aria-label='Dated experimental observations (cm)'" in original_html
    assert 'INTERVENTION-1' in original_html and 'Athlete unavailable' in original_html
    assert 'Serial dependence' in original_html
    current = researchstore.get_investigation(a['id'])
    previous = next(v for v in current['experiment_visits'] if v['scheduled_occasion']==7)
    current = service.record_experimental_visit(a['id'], visit(s['rev2'],7, occasion=8,
        occurred_at=visit(s['rev2'],8)['occurred_at'], supersedes=previous['id'],
        deviations='Corrected actual occasion to 8'), current['version'])
    second = execute(service,s,a)
    b_run = execute(service,s,b)
    combined = service.export_workspace_report(s['id'], [second['id'], b_run['id']], str(tmp_path/'combined.html')).read_text(encoding='utf-8')
    assert 'Corrected actual occasion to 8' in combined
    latest = researchstore.get_report_version(s['id'], researchstore.report_versions(s['id'])[0]['version'])
    sections = latest['frozen_content']['research_sections']
    for section, subject in zip(sections, ('P01','P02')):
        result = section['experimental_results'][0]['result']
        assert result['subject_id'] == subject
        assert all(r['visit']['subject_id']==subject for r in result['observations'] if r['visit'])
    assert researchstore.get_report_version(s['id'], first_version) == original_report
    reexported = service.export_report_html(s['id'], str(tmp_path/'old-again.html'), first_version).read_text(encoding='utf-8')
    assert reexported == original_html
    assert 'Corrected actual occasion to 8' not in reexported
    assert DynamisAppService().individual_research(a['id'])['runs'][0]['result'] == first['result']


def test_native_experiment_analysis_chart_and_report(qtbot, service, experiment_study, tmp_path, monkeypatch):
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QFileDialog
    from dynamis_science.desktop.main_window import MainWindow
    import os
    if os.path.exists('C:/Windows/Fonts/segoeui.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        QApplication.instance().setFont(QFont('Segoe UI', 10))
    s = experiment_study
    a,b = s['athletes']
    window = MainWindow(service)
    qtbot.addWidget(window)
    window.resize(1400,950)
    window.show()
    idle = lambda: qtbot.waitUntil(lambda: not window.runner.active, timeout=30000)
    idle()
    window._show_study(s['id'], service.get_study_detail(s['id']))
    idle()
    window._select_scope('INDIVIDUAL',a['id'])
    idle()
    panel = window.research.individual
    index = next(i for i in range(panel.method_picker.count())
                 if panel.method_picker.itemData(i)['method_id']=='METH-EXPERIMENT-DESC')
    panel.method_picker.setCurrentIndex(index)
    panel.tabs.setCurrentIndex(1)
    assert panel.run_button.isEnabled() and panel.analysis_protocol.count()==1
    assert 'Serial dependence' in panel.method_detail.toPlainText()
    qtbot.mouseClick(panel.run_button, Qt.MouseButton.LeftButton)
    idle()
    saved = panel.run_picker.currentData()
    assert saved['method_id']=='METH-EXPERIMENT-DESC'
    assert 'Experimental phase descriptions' in panel.result_view.toPlainText()
    assert 'NOT_QUALIFIED' in panel.result_view.toPlainText()
    figure = run_figure(saved)
    axis = figure.axes[0]
    assert axis.get_ylabel()=='Session mean (cm)' and 'Actual visit date' in axis.get_xlabel()
    assert {'BASELINE','INTERVENTION','COMPARISON'} <= set(axis.get_legend_handles_labels()[1])
    assert any('Missing' in label for label in axis.get_legend_handles_labels()[1])
    path = tmp_path/'native-experiment-report.html'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args,**kwargs:(str(path),'HTML'))
    window.research.export_report()
    idle()
    assert 'Experimental phase descriptions' in path.read_text(encoding='utf-8')
    # A new protocol version gets a separate result; exporting history retains the selected version.
    current = researchstore.get_investigation(a['id'])
    amendment = protocol()
    amendment['periods'].append(dict(kind='FOLLOW_UP',label='Additional follow-up',start=21,end=21))
    amendment['testing_occasions'].append(21)
    amendment['amendment_reason']='Extend future follow-up'
    service.save_protocol(a['id'],amendment,current['version'])
    panel.reload()
    idle()
    panel.method_picker.setCurrentIndex(index)
    assert panel.analysis_protocol.count()==2
    panel.analysis_protocol.setCurrentIndex(1)
    panel.execute()
    idle()
    assert panel.run_picker.currentData()['result']['protocol_version']==2
    panel.run_picker.setCurrentIndex(1)
    assert panel.run_picker.currentData()['id']==saved['id']
    window.research.export_report()
    idle()
    frozen = researchstore.get_report_version(s['id'], researchstore.report_versions(s['id'])[0]['version'])
    exported = frozen['frozen_content']['research_sections'][0]['experimental_results'][0]
    assert exported['run_id']==saved['id'] and exported['result']['protocol_version']==1
    panel.result_tabs.setCurrentIndex(1)
    if os.environ.get('RES717_ANALYSIS_SCREENSHOT'):
        panel.grab().save(os.environ['RES717_ANALYSIS_SCREENSHOT'])
    window._select_scope('INDIVIDUAL',b['id'])
    idle()
    assert panel.run_picker.count()==0 and panel.figure_holder.layout().count()==0
    assert 'P01' not in panel.result_view.toPlainText()
    window.close()


def test_sparse_and_tied_dates_are_explicitly_limited(service, experiment_study):
    s = experiment_study
    inv = researchstore.get_investigation(s['athletes'][0]['id'])
    entity = researchstore.get_entity(s['id'])
    context = experiments.analysis_context(entity, {'kind':'INDIVIDUAL','subject_id':'P01','investigation_id':inv['id']}, {'protocol_version':1})
    # Pure arithmetic edge case, independent of the visit persistence workflow.
    rows = context['timeline']['rows']
    for r in rows:
        if r['visit'] and r['observed_period'] and r['observed_period']['kind']=='BASELINE':
            r['mean']=None
        if r['visit']:
            r['visit']['occurred_at']='2026-01-01T12:00:00+00:00'
    result = experiments.describe(context)
    assert result['baseline_mean'] is None
    for phase in result['phases']:
        assert phase['slope_per_day'] is None and phase['observed_change'] is None
        assert phase['change_from_baseline'] is None and phase['limitations']


def test_qc_and_deviations_remain_visible_and_escaped(service, experiment_study):
    saved = execute(service, experiment_study, experiment_study['athletes'][0])
    displayed = copy.deepcopy(saved)
    first = displayed['result']['observations'][0]['visit']
    first['qc']['quality_flags'] = ['REVIEWED_EXCLUSION']
    first['deviations'] = '<script>documented deviation</script>'
    figure = run_figure(displayed)
    assert any(line.get_marker()=='x' and line.get_color()=='#176b87' for line in figure.axes[0].lines)
    assert any('! visit 4' in text.get_text() for text in figure.axes[0].texts)
    rendered = experiments.result_html(displayed['result'], chart=True)
    assert 'REVIEWED_EXCLUSION' in rendered and '&lt;script&gt;documented deviation&lt;/script&gt;' in rendered
    assert '<script>documented deviation</script>' not in rendered
