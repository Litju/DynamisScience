"""Native Direction E experiment -> exact test -> immutable report, synthetic only."""
import os

from dynamis_science import randomized_onset as onset, researchstore as store
from dynamis_science.desktop.individual_research import IndividualResearchPanel
from test_randomized_onset import service, prospective, plan, conduct


def font():
    from PySide6.QtGui import QFont,QFontDatabase
    from PySide6.QtWidgets import QApplication
    if os.path.exists('C:/Windows/Fonts/segoeui.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        QApplication.instance().setFont(QFont('Segoe UI',10))


def test_native_future_allocation_and_explicit_condition(qtbot,service,prospective,monkeypatch):
    font()
    s=prospective
    inv=service.create_individual_investigation(s['id'],'P01','Native prospective allocation')
    panel=IndividualResearchPanel(service,lambda op,done,label:done(op()))
    qtbot.addWidget(panel)
    panel.set_investigation(s['id'],inv['id'])
    p=plan()
    panel.design_picker.setCurrentIndex(panel.design_picker.findData(onset.DESIGN))
    panel.protocol_question.setText(p['question'])
    panel.prespecified.setChecked(True)
    panel.testing_occasions.setText(','.join(map(str,p['testing_occasions'])))
    panel.onset_starts.setText(','.join(map(str,p['permissible_starts'])))
    panel.onset_dates.setPlainText('\n'.join(p['testing_dates']))
    panel.onset_baseline.setText(p['baseline_condition'])
    panel.onset_intervention.setText(p['intervention_condition'])
    panel.onset_suitability.setText(p['suitability'])
    panel.onset_acknowledge.setChecked(True)
    with monkeypatch.context() as patch:
        patch.setattr(onset.secrets,'choice',lambda values:15)
        panel.save_protocol_button.click()
    assert panel.protocol_history.count()==1 and panel.timeline_table.rowCount()==31
    assert not panel.period_table.isEnabled()
    assert 'NOT_ESTIMABLE' in panel.experiment_summary.toPlainText()
    panel.analyze_experiment_button.click()
    assert panel.method_picker.currentData()['method_id']==onset.METHOD
    assert not panel.run_button.isEnabled()
    revision=service.attach_workspace_data(s['id'],s['later'](),append=True,confirm_participant_ids=True,
        base_revision=s['rev1'])['active_data_revision_id']
    panel.reload()
    panel.visit_schedule.setCurrentIndex(panel.visit_schedule.findData(4))
    panel.visit_time.setText(p['testing_dates'][0])
    panel.visit_exposure.setText('Actual usual training, no additional intervention')
    panel.visit_condition.setCurrentIndex(panel.visit_condition.findData('BASELINE'))
    panel.visit_adherence.setText('100')
    panel.save_visit_button.click()
    saved=store.get_investigation(inv['id'])['experiment_visits'][0]
    assert saved['actual_condition']=='BASELINE' and saved['data_revision_id']==revision
    panel.set_investigation(s['id'],s['athletes'][1]['id'])
    assert panel.visit_condition.currentData() is None
    assert panel.visit_exposure.text()==''


def test_native_two_athletes_exact_results_and_report(qtbot,service,prospective,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from dynamis_science.desktop.main_window import MainWindow
    font()
    s=prospective
    revision=conduct(service,s)
    window=MainWindow(service)
    qtbot.addWidget(window)
    window.resize(1400,950)
    window.show()
    idle=lambda:qtbot.waitUntil(lambda:not window.runner.active,timeout=30000)
    idle()
    window._show_study(s['id'],service.get_study_detail(s['id']))
    idle()
    runs=[]
    for inv,expected in zip(s['athletes'],[1/26,1]):
        window._select_scope('INDIVIDUAL',inv['id'])
        idle()
        panel=window.research.individual
        assert inv['scope']['subject_id'] in panel.header.text()
        assert panel.visit_history.rowCount()==31
        panel.analyze_experiment_button.click()
        assert panel.tabs.tabText(panel.tabs.currentIndex())=='Analysis'
        assert panel.method_picker.currentData()['method_id']==onset.METHOD
        assert panel.analysis_protocol.currentData()['protocol']['version']==1
        assert panel.run_button.isEnabled()
        assert 'QUALIFIED' in panel.method_detail.toPlainText()
        unavailable=next(i for i in range(panel.method_picker.count())
                         if panel.method_picker.itemData(i)['method_id']=='METH-EXPERIMENT')
        panel.method_picker.setCurrentIndex(unavailable)
        assert not panel.run_button.isEnabled()
        assert 'No qualified within-person causal estimator' in panel.method_detail.toPlainText()
        panel.analyze_experiment_button.click()
        panel.method_advanced.setChecked(True)
        assert 'no anticipation' in panel.method_detail.toPlainText().lower()
        panel.method_advanced.setChecked(False)
        panel.run_button.click()
        idle()
        saved=panel.run_picker.currentData()
        runs.append(saved)
        assert saved['result']['inference']['p_value']==expected
        assert saved['data_revision_id']==revision
        assert 'sharp null' in panel.result_view.toPlainText().lower()
        assert 'Null hypothesis:' in panel.result_view.toPlainText()
        assert 'no causal interval' in panel.result_view.toPlainText()
        assert 'distribution' in panel.result_diagnostics.toPlainText()
        assert panel.figure_holder.layout().count()==1
        path=tmp_path/f"{inv['scope']['subject_id']}.html"
        monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**kw:(str(path),'HTML'))
        window.research.export_report()
        idle()
        assert 'Exact randomized onset' in path.read_text(encoding='utf-8')
        if os.environ.get('RES716_ONSET_SCREENSHOT') and expected==1/26:
            panel.grab().save(os.environ['RES716_ONSET_SCREENSHOT'])
            panel.tabs.setCurrentIndex(next(i for i in range(panel.tabs.count()) if panel.tabs.tabText(i)=='Visits and timeline'))
            panel.grab().save(os.environ['RES716_ONSET_SCREENSHOT'].replace('.png','-timeline.png'))
    window._select_scope('INDIVIDUAL',s['athletes'][0]['id'])
    idle()
    assert window.research.individual.run_picker.currentData()['result_digest']==runs[0]['result_digest']
    window.close()
