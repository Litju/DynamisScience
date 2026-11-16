"""Independent scientific references and persisted prospective conduct; synthetic only."""
import copy
from datetime import datetime, timedelta, timezone
from fractions import Fraction

import pytest

from dynamis_science import experiments, importer, randomized_onset as onset, researchstore as store
from dynamis_science.desktop.services import DynamisAppService
from test_longitudinal_research import service, admit
from test_importer import FIXTURE


def plan():
    first = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    return dict(design=onset.DESIGN, prospective=True, prespecified=True,
                question='Does randomized onset change this athlete\'s scheduled jump trajectory?',
                outcome_metric_id='MET-CMJ-HEIGHT', unit='cm', assignment='App uniform onset',
                testing_occasions=list(range(4,35)), permissible_starts=list(range(7,33)),
                testing_dates=[(first+timedelta(days=i)).isoformat() for i in range(31)],
                baseline_condition='Usual training', intervention_condition='Additional training block',
                suitability='Persistent adaptation; withdrawal is inappropriate. Synthetic demonstration.',
                assumptions_confirmed=True)


def reference(values, schedule, support, observed):
    # Weighted finite-population contrast, independently constructed using assignment masks.
    weights = [[Fraction(int(t >= s), sum(x >= s for x in schedule)) -
                Fraction(int(t < s), sum(x < s for x in schedule)) for t in schedule] for s in support]
    scores = [abs(sum(w*Fraction(str(y)) for w,y in zip(row,values))) for row in weights]
    return sum(v >= scores[support.index(observed)] for v in scores), scores


def context(values, support=(4,5,6), assigned=5):
    schedule = list(range(1,len(values)+1))
    dates = [(datetime(2090,1,1,tzinfo=timezone.utc)+timedelta(days=i)).isoformat() for i in schedule]
    p = dict(design=onset.DESIGN, prespecified=True, testing_occasions=schedule,
             allocation=dict(schema_version=1, mechanism='APP_SECRETS_UNIFORM_ONSET', assigned_start=assigned,
                 allocated_at='2080-01-01T00:00:00+00:00', configuration=dict(testing_occasions=schedule,
                     testing_dates=dates, permissible_starts=list(support), assumptions_confirmed=True,
                     statistic='ABS_POST_MINUS_PRE', alternative='TWO_SIDED', lag=0, persistence='THROUGH_FINAL_VISIT')))
    rows = [dict(scheduled_occasion=t, status='MEASURED', mean=y, visit=dict(occasion=t,
                occurred_at=d, actual_condition='BASELINE' if t<assigned else 'INTERVENTION',
                adherence_percent=100, deviations='', qc={})) for t,y,d in zip(schedule,values,dates)]
    return dict(issues=[], timeline=dict(protocol=p, rows=rows))


def test_exact_reference_ties_trend_serial_dependence_and_null_size():
    result = onset.evaluate(context([0]*4+[10]*4))
    assert result['p_value'] == 1/3 and result['tail_count'] == 1
    assert result['descriptive_difference'] == 10 and result['p_resolution'] == 1/3
    assert onset.evaluate(context([5]*8))['p_value'] == 1
    # A deterministic trend with serially dependent oscillation is held fixed under the sharp null.
    values = [i*.2 + (i//4)%3 for i in range(31)]
    schedule, support = list(range(1,32)), list(range(4,30))
    results = []
    for assigned in support:
        got = onset.evaluate(context(values, support, assigned))
        tail, scores = reference(values,schedule,support,assigned)
        assert got['tail_count'] == tail
        assert [d['statistic'] for d in got['distribution']] == pytest.approx(list(map(float,scores)))
        results.append(got['p_value'])
    for alpha in (.01,.05,.1,.5,1):
        assert sum(p <= alpha for p in results)/len(results) <= alpha


def test_irregular_prespecified_dates_and_delayed_response_keep_fixed_statistic():
    c=context([0]*5+[10]*3)
    dates=[(datetime(2090,1,1,tzinfo=timezone.utc)+timedelta(days=i*i)).isoformat() for i in range(8)]
    c['timeline']['protocol']['allocation']['configuration']['testing_dates']=dates
    for row,date in zip(c['timeline']['rows'],dates):
        row['visit']['occurred_at']=date
    receipt=onset.evaluate(c)
    tail,_=reference([0]*5+[10]*3,list(range(1,9)),[4,5,6],5)
    assert receipt['p_value']==tail/3 and receipt['descriptive_difference']==7.5
    assert any('delayed' in s.lower() for s in receipt['limitations'])


@pytest.mark.parametrize('mutation,status', [
    (lambda c: c['timeline']['protocol'].pop('allocation'), 'NOT_QUALIFIED'),
    (lambda c: c['timeline']['rows'][0].update(status='MISSING',mean=None), 'NOT_ESTIMABLE'),
    (lambda c: c['timeline']['rows'][0].update(status='PLANNED',mean=None), 'NOT_ESTIMABLE'),
    (lambda c: c['timeline']['rows'][0].update(mean=float('nan')), 'NOT_ESTIMABLE'),
    (lambda c: c['timeline']['rows'][0]['visit'].update(actual_condition='INTERVENTION'), 'NOT_QUALIFIED'),
    (lambda c: c['timeline']['rows'][-1]['visit'].update(adherence_percent=80), 'NOT_QUALIFIED'),
    (lambda c: c['timeline']['rows'][0]['visit'].update(occurred_at='2090-03-01T00:00:00+00:00'), 'NOT_QUALIFIED'),
    (lambda c: c['timeline']['rows'][0]['visit'].update(deviations='Extra training'), 'NOT_QUALIFIED'),
    (lambda c: c['timeline']['rows'][0]['visit']['qc'].update(empty_values=1), 'NOT_ESTIMABLE'),
])
def test_precise_insufficient_states(mutation,status):
    c = context([0]*4+[10]*4)
    mutation(c)
    result = onset.evaluate(c)
    assert result['status'] == status and result['p_value'] is None and result['issues']


@pytest.fixture
def prospective(service,tmp_path,monkeypatch):
    source = importer.build_context(FIXTURE)
    identity = service.create_workspace('Two synthetic randomized-onset experiments')['study']['id']
    def data(occasions,name):
        lines = ['Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N),week']
        for subject,index,start in [('P01',1,15),('P02',2,24)]:
            for at in occasions:
                y = 30+index+(8 if index==1 and at>=start else 0)
                for trial in (1,2,3):
                    lines.append(f'{subject},{subject}-W{at}-T{trial},{y},75,1700,{at}')
        path=tmp_path/name
        path.write_text('\n'.join(lines)+'\n')
        return admit(path,source)
    rev1 = service.attach_workspace_data(identity,data(range(1,4),'before.csv'))['active_data_revision_id']
    athletes=[]
    for subject,start in [('P01',15),('P02',24)]:
        inv=service.create_individual_investigation(identity,subject,f'{subject} randomized onset')
        with monkeypatch.context() as patch:
            patch.setattr(onset.secrets,'choice',lambda choices,s=start:s)
            inv=service.save_protocol(inv['id'],plan(),inv['version'])
        athletes.append(inv)
    return dict(id=identity, rev1=rev1, athletes=athletes, later=lambda:data(range(4,35),'later.csv'))


def conduct(service,s):
    revision=service.attach_workspace_data(s['id'],s['later'](),append=True,confirm_participant_ids=True,
        base_revision=s['rev1'])['active_data_revision_id']
    for inv in s['athletes']:
        p=inv['protocol']; a=p['allocation']; c=a['configuration']
        for at,date in zip(p['testing_occasions'],c['testing_dates']):
            inv=service.record_experimental_visit(inv['id'],dict(protocol_version=1,scheduled_occasion=at,
                occasion=at,data_revision_id=revision,occurred_at=date,measurement_status='MEASURED',
                exposure='Synthetic recorded training',actual_condition='BASELINE' if at<a['assigned_start'] else 'INTERVENTION',
                adherence_percent=100),inv['version'])
    return revision


def run(service,s,inv,revision,**params):
    return service.execute_analysis_run(s['id'],dict(method_id=onset.METHOD,outcome_metric_id='MET-CMJ-HEIGHT',
        parameters={'protocol_version':1,**params},data_revision_id=revision,
        scope={'kind':'INDIVIDUAL','investigation_id':inv['id']}))


def test_prospective_persistence_references_corrections_and_reports(service,prospective,tmp_path):
    s=prospective
    with pytest.raises(store.ResearchValidation,match='Complete prespecified schedule'):
        run(service,s,s['athletes'][0],s['rev1'])
    revision=conduct(service,s)
    runs=[run(service,s,inv,revision) for inv in s['athletes']]
    assert runs[0]['result']['inference']['p_value'] == 1/26
    assert runs[1]['result']['inference']['p_value'] == 1
    assert runs[0]['result']['inference']['descriptive_difference'] == 8
    for saved in runs:
        r=saved['result']; receipt=r['inference']
        tail,_=reference([row['mean'] for row in r['observations']],r['protocol']['testing_occasions'],
                         r['protocol']['allocation']['configuration']['permissible_starts'],receipt['assigned_start'])
        assert tail==receipt['tail_count'] and r['inference_status']=='QUALIFIED'
        assert saved['execution']['method_binding']['experiment']['protocol']['allocation']==r['protocol']['allocation']
    frozen=copy.deepcopy(store.get_run(runs[0]['id']))
    report=service.export_workspace_report(s['id'],[r['id'] for r in runs],str(tmp_path/'onsets.html'))
    text=report.read_text(encoding='utf-8')
    assert '1/26' in text and 'participant P02' in text and 'sharp null' in text.lower()
    inv=store.get_investigation(s['athletes'][0]['id'])
    original=inv['experiment_visits'][0]
    correction={**original,'supersedes':original['id'],'deviations':'Correction: co-intervention was recorded'}
    inv=service.record_experimental_visit(inv['id'],correction,inv['version'])
    with pytest.raises(store.ResearchValidation,match='deviations violate'):
        run(service,s,inv,revision)
    amended=plan(); amended.update(inv['protocol']['allocation']['configuration'])
    amended.update(question='Corrected research question wording',amendment_reason='Narrative clarification')
    inv=service.save_protocol(inv['id'],amended,inv['version'])
    assert inv['protocol']['allocation']==frozen['result']['protocol']['allocation']
    assert store.get_run(runs[0]['id'])==frozen
    reopened=DynamisAppService().individual_research(inv['id'])
    assert reopened['runs'][0]['result_digest']==frozen['result_digest']
    assert len(DynamisAppService().individual_research(s['athletes'][1]['id'])['runs'])==1
    assert report.read_text(encoding='utf-8')==text


def test_no_backdated_imported_redrawn_or_posthoc_allocation(service,prospective):
    inv=prospective['athletes'][0]
    for changes,pattern in [({'permissible_starts':list(range(8,33))},'frozen allocation'),
                            ({'allocation':inv['protocol']['allocation']},'historical or supplied'),
                            ({'assumptions_confirmed':False},'Acknowledge')]:
        with pytest.raises(store.ResearchValidation,match=pattern):
            service.save_protocol(inv['id'],{**plan(),**changes},inv['version'])
    other=service.create_individual_investigation(prospective['id'],'P01','Invalid historical draw')
    p=plan(); p['testing_dates']=[d.replace(str(datetime.now().year),'2020',1) for d in p['testing_dates']]
    with pytest.raises(store.ResearchValidation,match='future at allocation'):
        service.save_protocol(other['id'],p,other['version'])
