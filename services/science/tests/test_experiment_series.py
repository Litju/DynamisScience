"""RES-717 series checks use persisted synthetic experiments and independent expectations."""
import copy

import pytest

from dynamis_science import experiment_series as series, researchstore as store
from test_randomized_onset import service, prospective, conduct, run


def test_capture_isolation_exact_results_and_immutable_history(service, prospective, tmp_path):
    s = prospective
    rev = conduct(service, s)
    results = [run(service, s, inv, rev) for inv in s['athletes']]
    service.export_workspace_report(s['id'], results[0]['id'], str(tmp_path/'original.html'))
    before = store.export_html(s['id'], store.report_versions(s['id'])[0]['version'])
    roster = series.roster(s['id'])
    members = roster['members']
    assert {m['subject_id'] for m in members} == {'P01', 'P02'}
    for m in members:
        assert m['observed'] == m['scheduled'] == 31
        assert m['result_current']
        assert all(r['visit']['subject_id'] == m['subject_id'] for r in m['timeline']['rows'])
        expected = [31 + (8 if at >= 15 else 0) if m['subject_id'] == 'P01' else 32 for at in range(4,35)]
        assert [r['mean'] for r in m['timeline']['rows']] == expected
        assert m['eligibility']['p_value'] == (1/26 if m['subject_id'] == 'P01' else 1)
    bindings = {m['investigation_id']: m['investigation_version'] for m in members}
    saved = series.capture(s['id'], bindings, rev)
    assert all(c['status'] in {'MATCH', 'COMPLETE', 'CURRENT'} for c in saved['comparison']['checks'])
    frozen = copy.deepcopy(saved)
    a = store.get_investigation(s['athletes'][0]['id'])
    amended = {**a['protocol'], **a['protocol']['allocation']['configuration'],
               'amendment_reason':'Clarify question', 'question':'Amended question'}
    amended.pop('allocation')
    service.save_protocol(a['id'], amended, a['version'])
    with pytest.raises(store.ResearchConflict, match='experiment changed'):
        series.capture(s['id'], bindings, rev)
    with pytest.raises(store.ResearchConflict, match='Data revision changed'):
        series.capture(s['id'], bindings, s['rev1'])
    fresh = series.roster(s['id'])
    assert not next(m for m in fresh['members'] if m['investigation_id'] == a['id'])['result_current']
    assert series.history(s['id']) == [frozen]
    assert store.export_html(s['id'], store.report_versions(s['id'])[0]['version']) == before
    # Historical getter returns detached values, including original protocol and measurements.
    series.history(s['id'])[0]['comparison']['members'].clear()
    assert series.history(s['id']) == [frozen]
    assert any(m['reports'] for m in members)


def test_missing_data_and_each_incompatibility(service, prospective):
    roster = series.roster(prospective['id'])
    members = roster['members']
    assert all(m['observed'] == 0 and m['eligibility']['status'] == 'NOT_ESTIMABLE' for m in members)
    assert next(c for c in series.comparability(members) if c['check'] == 'Data sufficiency')['status'] == 'INSUFFICIENT'
    changes = [
        ('Outcome definitions', lambda m: m['protocol'].update(outcome_label='Different measurement definition')),
        ('Units', lambda m: m['protocol'].update(unit='m')),
        ('Period structure', lambda m: m['protocol']['testing_occasions'].append(35)),
        ('Period structure', lambda m: m['protocol']['allocation']['configuration']['testing_dates'].__setitem__(0, '2090-01-01T00:00:00+00:00')),
        ('Allocation mechanisms', lambda m: m['protocol']['allocation'].update(mechanism='NON_RANDOM')),
        ('Intervention conditions', lambda m: m['protocol']['allocation']['configuration'].update(intervention_condition='Other dose')),
        ('Method versions', lambda m: m['method_contracts'][0].update(version='other')),
    ]
    for label, change in changes:
        altered = copy.deepcopy(members)
        change(altered[0])
        check = next(c for c in series.comparability(altered) if c['check'] == label)
        assert check['status'] == 'REVIEW_REQUIRED', label
    duplicate = copy.deepcopy(members[0])
    duplicate['investigation_id'] = 'foreign'
    with pytest.raises(store.ResearchValidation):
        series.capture(prospective['id'], {members[0]['investigation_id']:members[0]['investigation_version'], 'foreign':1}, roster['data_revision_id'])
    other = service.create_individual_investigation(prospective['id'], members[0]['subject_id'], 'Same athlete')
    with pytest.raises(store.ResearchValidation, match='distinct athletes'):
        series.capture(prospective['id'], {members[0]['investigation_id']:members[0]['investigation_version'], other['id']:other['version']}, roster['data_revision_id'])


def test_persisted_mixed_designs_missing_visits_and_new_revision(service, prospective):
    from test_experiments import plan as crossover_plan

    s = prospective
    a = s['athletes'][0]
    b = service.create_individual_investigation(s['id'], 'P02', 'Replicated nonrandom crossover')
    b = service.save_protocol(b['id'], crossover_plan(), b['version'])
    b = service.record_experimental_visit(b['id'], dict(protocol_version=1, scheduled_occasion=4,
        occasion=4, data_revision_id=s['rev1'], occurred_at='2026-11-17T10:00:00-03:00',
        measurement_status='MISSING', missing_reason='Athlete unavailable', exposure='Unknown'), b['version'])
    bindings = {a['id']:a['version'], b['id']:b['version']}
    saved = series.capture(s['id'], bindings, s['rev1'])
    checks = {c['check']:c['status'] for c in saved['comparison']['checks']}
    assert checks['Period structure'] == checks['Allocation mechanisms'] == 'REVIEW_REQUIRED'
    assert checks['Data sufficiency'] == 'INSUFFICIENT'
    missing = next(m for m in saved['comparison']['members'] if m['investigation_id'] == b['id'])
    assert missing['timeline']['rows'][0]['visit']['missing_reason'] == 'Athlete unavailable'
    assert missing['timeline']['rows'][0]['mean'] is None
    # New admitted observations and conduct cannot change an earlier captured comparison.
    conduct(service, s)
    with pytest.raises(store.ResearchConflict, match='Data revision changed'):
        series.capture(s['id'], bindings, s['rev1'])
    assert series.history(s['id']) == [saved]
    assert all(m['observed'] == 0 for m in saved['comparison']['members'])
