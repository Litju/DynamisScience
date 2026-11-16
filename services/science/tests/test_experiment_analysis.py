"""Independent numerical checks of descriptive experimental results (no inference qualification)."""
import copy
from datetime import datetime, timedelta, timezone
from statistics import mean

import numpy as np
import pytest

from dynamis_science import experiments, importer, longitudinal, researchstore
from dynamis_science.desktop.services import DynamisAppService
from test_longitudinal_research import service, study_file, admit, value
from test_importer import FIXTURE


def protocol():
    kinds = ['BASELINE', 'INTERVENTION', 'COMPARISON', 'INTERVENTION', 'COMPARISON']
    return dict(prospective=True, question='How do measured phase trajectories differ?', outcome_metric_id='MET-CMJ-HEIGHT',
        unit='cm', assignment='Documented coach-specified sequence; not randomized', prespecified=True,
        testing_occasions=list(range(4, 21)), periods=[dict(kind=k, label=f'{k}-{i}', start=4+3*i,
        end=6+3*i if i < 4 else 20) for i, k in enumerate(kinds)])


def visit(revision, at, **changes):
    return {**dict(protocol_version=1, scheduled_occasion=at, occasion=at, data_revision_id=revision,
        occurred_at=(datetime(2026, 1, 1, tzinfo=timezone.utc)+timedelta(days=(at-4)**2)).isoformat(),
        measurement_status='MEASURED', exposure='Athlete-reported training', adherence_percent=90), **changes}


@pytest.fixture
def experiment_study(service, tmp_path):
    context = importer.build_context(FIXTURE)
    identity = service.create_workspace('Two-athlete synthetic experiments')['study']['id']
    baseline = admit(study_file(tmp_path, range(1,4), 'before.csv'), context)
    rev1 = service.attach_workspace_data(identity, baseline)['active_data_revision_id']
    athletes = [service.create_individual_investigation(identity, s, f'Experiment {s}') for s in ('P01','P02')]
    athletes = [service.save_protocol(i['id'], protocol(), i['version']) for i in athletes]
    later = admit(study_file(tmp_path, range(4,19), 'later.csv'), context)
    rev2 = service.attach_workspace_data(identity, later, append=True, confirm_participant_ids=True,
        base_revision=rev1)['active_data_revision_id']
    for i in athletes:
        for at in range(4,19):
            if at == 8:
                continue  # Unrecorded, not an explicit missing measurement.
            i = service.record_experimental_visit(i['id'], visit(rev2, at), i['version'])
        service.record_experimental_visit(i['id'], visit(rev2, 19, measurement_status='MISSING',
            missing_reason='Athlete unavailable', exposure='Unknown', adherence_percent=None), i['version'])
    return dict(id=identity, rev1=rev1, rev2=rev2, athletes=athletes)


def execute(service, study, inv, **parameters):
    return service.execute_analysis_run(study['id'], dict(method_id='METH-EXPERIMENT-DESC',
        outcome_metric_id='MET-CMJ-HEIGHT', parameters={'protocol_version':1, **parameters},
        data_revision_id=study['rev2'], scope={'kind':'INDIVIDUAL', 'investigation_id':inv['id']}))


def test_phase_statistics_against_independent_numpy(service, experiment_study):
    study = experiment_study
    runs = []
    for index, inv in enumerate(study['athletes'], 1):
        saved = execute(service, study, inv)
        runs.append(saved)
        result = saved['result']
        baseline = [mean(value(index, at, t) for t in range(1,3+index%2)) for at in (4,5,6)]
        for phase in result['phases']:
            start, end = phase['period']['start'], min(18, phase['period']['end'])
            occasions = [at for at in range(start, end+1) if at != 8]
            expected = [mean(value(index, at, t) for t in range(1,3+index%2)) for at in occasions]
            assert phase['mean'] == pytest.approx(np.mean(expected))
            assert phase['median'] == pytest.approx(np.median(expected))
            assert phase['sd'] == pytest.approx(np.std(expected, ddof=1))
            assert phase['observed_change'] == pytest.approx(expected[-1]-expected[0])
            assert phase['change_from_baseline'] == pytest.approx(np.mean(expected)-np.mean(baseline))
            assert phase['n_sessions'] == len(expected)
            assert phase['n_trials'] == len(expected)*(2+index%2)
            if len(expected) >= 3:
                x = np.array([(at-4)**2 for at in occasions], dtype=float)
                assert phase['slope_per_day'] == pytest.approx(np.polyfit(x, expected, 1)[0])
            else:
                assert phase['slope_per_day'] is None and phase['limitations']
        assert result['phases'][1]['unrecorded_n'] == 1
        assert result['phases'][-1]['missing_n'] == 1 and result['phases'][-1]['unrecorded_n'] == 1
        binding = saved['execution']['method_binding']['experiment']
        assert binding['subject_id'] == f'P0{index}' and binding['protocol_version'] == 1
        assert binding['source_data_revision_ids'] == [study['rev2']]
        assert saved['data_revision_id'] == study['rev2']
        assert all(r['visit']['subject_id']==f'P0{index}' for r in result['observations'] if r['visit'])
        assert result['inference_status'] == 'NOT_QUALIFIED'
        assert any('Serial dependence' in l for l in result['limitations'])
        assert any('time trends' in l for l in result['limitations'])
    assert runs[0]['result']['phases'][0]['mean'] != runs[1]['result']['phases'][0]['mean']


def test_corrections_pinned_history_and_protocol_versions(service, experiment_study):
    s = experiment_study
    a,b = s['athletes']
    first = execute(service,s,a)
    before = copy.deepcopy(researchstore.get_run(first['id']))
    current = researchstore.get_investigation(a['id'])
    original = next(v for v in current['experiment_visits'] if v['scheduled_occasion']==7)
    current = service.record_experimental_visit(a['id'], visit(s['rev2'], 7, occasion=8,
        occurred_at=visit(s['rev2'],8)['occurred_at'], supersedes=original['id'],
        deviations='Correction: actual visit was occasion 8'), current['version'])
    corrected = execute(service,s,a)
    assert corrected['result']['phases'][1]['mean'] != first['result']['phases'][1]['mean']
    assert corrected['reproducibility_key'] != first['reproducibility_key']
    amendment = protocol()
    amendment['periods'].append(dict(kind='FOLLOW_UP', label='Future follow-up', start=21, end=21))
    amendment['testing_occasions'].append(21)
    amendment['amendment_reason'] = 'Extend still-future comparison schedule'
    service.save_protocol(a['id'], amendment, current['version'])
    newer = execute(service,s,a,protocol_version=2)
    assert newer['result']['protocol_version'] == 2
    reopened = DynamisAppService().individual_research(a['id'])
    assert len(reopened['runs']) == 3
    assert researchstore.get_run(first['id']) == before
    assert not longitudinal.investigation_runs(b['id'])


def test_eligibility_rejects_unsupported_comparisons_and_designs(service, experiment_study):
    s = experiment_study
    inv = s['athletes'][0]
    for params in ({'comparison':'causal'}, {'protocol_version':99}, {'protocol_version':True}):
        with pytest.raises(researchstore.ResearchValidation):
            execute(service,s,inv,**params)
    with pytest.raises(researchstore.ResearchConflict):
        execute(service,{**s,'rev2':s['rev1']},inv)
    assert not longitudinal.investigation_runs(inv['id'])
    current = researchstore.get_investigation(inv['id'])
    plans = copy.deepcopy(current['experiment_protocols'])
    plans[0]['design'] = 'OBSERVATIONAL_TRACKING'
    researchstore.update_investigation_fields(inv['id'], {'experiment_protocols':plans}, current['version'], 'test.invalid_design')
    with pytest.raises(researchstore.ResearchValidation, match='Incompatible experimental design'):
        execute(service,s,inv)
