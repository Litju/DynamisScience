"""RES-717: independent arithmetic, immutable histories and athlete isolation."""
import copy
from statistics import mean

import pytest

from dynamis_science import experiments, researchstore
from dynamis_science.desktop.services import DynamisAppService
from test_longitudinal_research import service, study, value, run


def plan():
    return dict(prospective=True, question='Does the documented training block change measured jump height?',
        outcome_metric_id='MET-CMJ-HEIGHT', unit='cm', assignment='Coach-specified alternating order; not randomized',
        prespecified=True, testing_occasions=[4, 5, 6, 7, 8],
        periods=[dict(kind=kind, label=f'{kind} {at}', start=at, end=at) for at, kind in
                 enumerate(['BASELINE', 'INTERVENTION', 'COMPARISON', 'INTERVENTION', 'COMPARISON'], 4)])


def visit(revision, at=4, **fields):
    return dict(protocol_version=1, scheduled_occasion=at, occasion=at, data_revision_id=revision,
                occurred_at='2026-11-16T10:00:00-03:00', measurement_status='MEASURED',
                exposure='Actual standard training reported by athlete', adherence_percent=90, **fields)


def test_two_prospective_experiments_updates_history_and_isolation(service, study):
    a = service.create_individual_investigation(study['id'], 'P01', 'Experiment A')
    b = service.create_individual_investigation(study['id'], 'P02', 'Experiment B')
    a = service.save_protocol(a['id'], plan(), a['version'])
    b = service.save_protocol(b['id'], plan(), b['version'])
    frozen_plan = copy.deepcopy(a['protocol'])
    rev2 = service.attach_workspace_data(study['id'], study['follow_up'], append=True,
        confirm_participant_ids=True, base_revision=study['rev1'])['active_data_revision_id']
    for inv, subject_index in ((a, 1), (b, 2)):
        for at in (4, 5, 6):
            inv = service.record_experimental_visit(inv['id'], visit(rev2, at), inv['version'])
        result = experiments.timeline(inv['id'])
        expected = [mean(value(subject_index, at, trial) for trial in range(1, 3 + subject_index % 2)) for at in (4, 5, 6)]
        assert [r['mean'] for r in result['rows'][:3]] == pytest.approx(expected)
        assert result['changes'][1]['change_from_baseline'] == pytest.approx(expected[1]-expected[0])
        assert all(v['subject_id'] == f'P0{subject_index}' for v in result['visits'])
        assert [r['status'] for r in result['rows']] == ['MEASURED']*3 + ['PLANNED']*2
        assert result['inference']['status'] == 'NOT_QUALIFIED'
    a = researchstore.get_investigation(a['id'])
    before = copy.deepcopy(a['experiment_visits'])
    a = service.record_experimental_visit(a['id'], {**visit(rev2, 7), 'measurement_status': 'MISSING',
        'missing_reason': 'Athlete unavailable', 'exposure': 'Unknown', 'adherence_percent': None}, a['version'])
    assert a['protocol'] == frozen_plan
    a = service.record_experimental_visit(a['id'], {**visit(rev2, 7), 'measurement_status': 'MISSING',
        'missing_reason': 'Visit cancelled by athlete', 'deviations': 'Corrected reason',
        'supersedes': a['experiment_visits'][-1]['id']}, a['version'])
    assert a['experiment_visits'][:3] == before
    amendment = {**plan(), 'amendment_reason': 'Extend final comparator', 'testing_occasions': [4,5,6,7,8,9]}
    amendment['periods'][-1]['end'] = 9
    a = service.save_protocol(a['id'], amendment, a['version'])
    reopened = DynamisAppService().individual_research(a['id'])
    assert reopened['experiment']['rows'][3]['visit']['missing_reason'] == 'Visit cancelled by athlete'
    assert reopened['experiment']['protocol']['version'] == 2
    assert experiments.timeline(a['id'], 1)['protocol'] == frozen_plan
    assert researchstore.investigation_versions(a['id'])[1]['protocol'] == frozen_plan
    assert len(experiments.timeline(b['id'])['visits']) == 3
    assert all(v['data_revision_id'] == rev2 for v in reopened['experiment']['visits'])
    assert frozen_plan['data_revision_id'] == study['rev1']
    with pytest.raises(researchstore.ResearchValidation):
        run(service, study['id'], rev2, 'METH-EXPERIMENT', {'kind':'INDIVIDUAL', 'investigation_id':a['id']})


def test_experiment_validation_and_concurrency(service, study):
    a = service.create_individual_investigation(study['id'], 'P01', 'Experiment')
    for update in ({'unit':'m'}, {'question':''}, {'assignment':''}, {'prespecified':False}, {'testing_occasions':[99]}):
        with pytest.raises(researchstore.ResearchValidation):
            service.save_protocol(a['id'], {**plan(), **update}, a['version'])
    retrospective = plan()
    retrospective['periods'][0]['start'] = 1
    with pytest.raises(researchstore.ResearchValidation, match='prospective'):
        service.save_protocol(a['id'], retrospective, a['version'])
    saved = service.save_protocol(a['id'], plan(), a['version'])
    with pytest.raises(researchstore.ResearchConflict):
        service.save_protocol(a['id'], {**plan(), 'amendment_reason':'test'}, a['version'])
    for update in ({'subject_id':'P02'}, {'data_revision_id':'foreign'}, {'adherence_percent':float('nan')},
                   {'occurred_at':'2026-11-16'}, {'measurement_status':'MISSING'}, {'scheduled_occasion':99}):
        with pytest.raises(researchstore.ResearchValidation):
            service.record_experimental_visit(a['id'], {**visit(study['rev1']), **update}, saved['version'])
    with pytest.raises(researchstore.ResearchValidation, match='No QC-eligible'):
        service.record_experimental_visit(a['id'], visit(study['rev1']), saved['version'])
