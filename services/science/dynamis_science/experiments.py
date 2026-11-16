"""Prospective plans and append-only visit records in existing individual investigations."""
from __future__ import annotations

import math
import secrets
from datetime import datetime
from statistics import mean

from . import longitudinal as long, researchstore as store
from .method_catalogue import method_spec


def _integer(value, label):
    try:
        if isinstance(value, bool) or float(value) != int(value):
            raise ValueError
        return int(value)
    except (ValueError, TypeError, OverflowError) as error:
        raise store.ResearchValidation(f"{label} must be an integer ordinal occasion") from error


def save_protocol(investigation_id: str, plan: dict, base_version: int) -> dict:
    inv = long.get_individual_investigation(investigation_id)
    entity, snapshot, metric = long._context(inv['study_id'], plan.get('outcome_metric_id'))
    if entity['state'] == 'ARCHIVED':
        raise store.ResearchConflict('Restore this workspace before editing experiments')
    if plan.get('outcome_metric_id') != metric['id'] or plan.get('unit') != metric['unit']:
        raise store.ResearchValidation('Select a registered outcome and its recorded unit')
    if not str(plan.get('question', '')).strip() or not str(plan.get('assignment', '')).strip():
        raise store.ResearchValidation('Research question and actual assignment procedure are required')
    if not plan.get('prespecified'):
        raise store.ResearchValidation('Confirm prospective prespecification; do not reconstruct allocations')
    periods = []
    for index, p in enumerate(plan.get('periods', []), 1):
        start, end = _integer(p.get('start'), 'Start'), _integer(p.get('end'), 'End')
        if p.get('kind') not in long.PERIOD_KINDS or not str(p.get('label', '')).strip() or start > end:
            raise store.ResearchValidation('Each planned period needs a kind, label and increasing bounds')
        periods.append(dict(id=f'P{index}', kind=p['kind'], label=p['label'].strip(), start=start, end=end,
                            notes=str(p.get('notes', '')).strip()))
    periods.sort(key=lambda p: p['start'])
    if any(a['end'] >= b['start'] for a, b in zip(periods, periods[1:])):
        raise store.ResearchValidation('Planned periods overlap')
    kinds = [p['kind'] for p in periods]
    if not {'BASELINE', 'INTERVENTION', 'COMPARISON'} <= set(kinds):
        raise store.ResearchValidation('Include baseline, intervention and comparator periods')
    if kinds.count('INTERVENTION') < 2 or kinds.count('COMPARISON') < 2:
        raise store.ResearchValidation('An N-of-1 plan requires replicated intervention and comparator periods')
    schedule = sorted({_integer(v, 'Measurement schedule') for v in plan.get('testing_occasions', [])})
    if not schedule or any(not any(p['start'] <= v <= p['end'] for p in periods) for v in schedule):
        raise store.ResearchValidation('Schedule every measurement within a planned period')
    if any(not any(p['start'] <= v <= p['end'] for v in schedule) for p in periods):
        raise store.ResearchValidation('Schedule at least one measurement in every period')
    axis, points = long.individual_points(snapshot, metric, inv['scope']['subject_id'])
    last = max((p[axis] for p in points if p['n_trials']), default=-1)
    last = max([last, *(v['scheduled_occasion'] for v in inv.get('experiment_visits', []))])
    previous = inv.get('experiment_protocols', [])
    # Existing plans stay frozen; amendments may change only the still-future portion.
    if previous:
        old = previous[-1]
        frozen_old = [p for p in old['periods'] if p['start'] <= last]
        frozen_new = [p for p in periods if p['start'] <= last]
        if frozen_new != frozen_old or [v for v in schedule if v <= last] != [v for v in old['testing_occasions'] if v <= last]:
            raise store.ResearchValidation('Already observed periods and measurement schedules are frozen')
        if metric['id'] != old['outcome_metric_id'] or metric['unit'] != old['unit']:
            raise store.ResearchValidation('The primary outcome is frozen; create a new investigation')
        if not str(plan.get('amendment_reason', '')).strip():
            raise store.ResearchValidation('Describe the reason for this protocol amendment')
    elif periods[0]['start'] <= last:
        raise store.ResearchValidation('A prospective protocol must start after the latest observed occasion')
    record = dict(schema_version=1, version=len(previous)+1, design='N_OF_1_EXPERIMENT',
                  design_label=long.PROTOCOL_DESIGNS['N_OF_1_EXPERIMENT'], question=plan['question'].strip(),
                  outcome_metric_id=metric['id'], outcome_label=metric['label'], unit=metric['unit'], axis=axis,
                  periods=periods, testing_occasions=schedule, assignment=plan['assignment'].strip(),
                  prespecified=True, blinding=str(plan.get('blinding', '')).strip(),
                  amendment_reason=str(plan.get('amendment_reason', '')).strip(),
                  subject_id=inv['scope']['subject_id'], data_revision_id=entity['active_data_revision_id'],
                  created_at=store._now(), adherence=[], changes=[])
    return store.update_investigation_fields(investigation_id,
        {'protocol': record, 'experiment_protocols': [*previous, record]},
        inv['version'] if base_version is None else base_version, 'experiment.protocol_saved')


def record_visit(investigation_id: str, visit: dict, base_version: int) -> dict:
    inv = long.get_individual_investigation(investigation_id)
    if long._workspace(inv['study_id'])['state'] == 'ARCHIVED':
        raise store.ResearchConflict('Restore this workspace before recording visits')
    plans = inv.get('experiment_protocols', [])
    plan = next((p for p in plans if p['version'] == visit.get('protocol_version')), None)
    if not plan:
        raise store.ResearchValidation('Select a saved experimental protocol version')
    if visit.get('subject_id', plan['subject_id']) != plan['subject_id']:
        raise store.ResearchValidation('Visit participant differs from this investigation')
    revision = store.get_data_revision(visit.get('data_revision_id', ''))
    if not revision or revision['workspace_id'] != inv['study_id']:
        raise store.ResearchValidation('Measurement revision must belong to this workspace')
    _, snapshot, metric = long._context(inv['study_id'], plan['outcome_metric_id'], revision['id'])
    subjects = store.read_snapshot_table(snapshot, 'subjects')['subject_id'].cast(str).to_list()
    if plan['subject_id'] not in subjects:
        raise store.ResearchValidation('This athlete is absent from the referenced revision')
    if metric['id'] != plan['outcome_metric_id'] or metric['unit'] != plan['unit']:
        raise store.ResearchValidation('Revision does not contain the protocol outcome and units')
    at = _integer(visit.get('occasion'), 'Actual occasion')
    scheduled = _integer(visit.get('scheduled_occasion'), 'Scheduled occasion')
    if scheduled not in plan['testing_occasions']:
        raise store.ResearchValidation('Select a measurement from the saved schedule')
    try:
        occurred = datetime.fromisoformat(visit.get('occurred_at', ''))
        if occurred.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError) as error:
        raise store.ResearchValidation('Actual visit time needs an ISO date/time with timezone') from error
    status = visit.get('measurement_status')
    if status not in {'MEASURED', 'MISSING'}:
        raise store.ResearchValidation('Measurement status must be MEASURED or MISSING')
    missing_reason = str(visit.get('missing_reason', '')).strip()
    if status == 'MISSING' and not missing_reason:
        raise store.ResearchValidation('Explain the missing measurement')
    exposure = str(visit.get('exposure', '')).strip()
    if not exposure:
        raise store.ResearchValidation('Record actual exposure, including none or unknown where appropriate')
    percent = visit.get('adherence_percent')
    if percent is not None and (type(percent) not in (float, int) or not math.isfinite(percent) or not 0 <= percent <= 100):
        raise store.ResearchValidation('Adherence must be finite and between 0 and 100, or unknown')
    axis, points = long.individual_points(snapshot, metric, plan['subject_id'])
    point = next((p for p in points if p[axis] == at), None)
    if status == 'MEASURED' and (not point or not point['n_trials']):
        raise store.ResearchValidation('No QC-eligible measurement for this athlete at the actual occasion in this revision')
    if status == 'MISSING' and point and point['n_trials']:
        raise store.ResearchValidation('This revision contains a measurement; choose MEASURED or the correct occasion')
    deviations = str(visit.get('deviations', '')).strip()
    if at != scheduled and not deviations:
        raise store.ResearchValidation('Describe the deviation from the scheduled occasion')
    visits = inv.get('experiment_visits', [])
    supersedes = visit.get('supersedes')
    active = [v for v in visits if v['id'] not in {r.get('supersedes') for r in visits}]
    existing = next((v for v in active if v['scheduled_occasion'] == scheduled), None)
    if status == 'MEASURED' and any(v['measurement_status'] == 'MEASURED' and v['occasion'] == at
                                   and v['scheduled_occasion'] != scheduled for v in active):
        raise store.ResearchValidation('This actual measurement is already linked to another scheduled visit')
    if (existing and supersedes != existing['id']) or (supersedes and (not existing or existing['id'] != supersedes)):
        raise store.ResearchValidation('This scheduled visit already exists; explicitly supersede its latest record')
    if supersedes and not deviations:
        raise store.ResearchValidation('Describe the correction in deviations')
    record = dict(id=f'VIS-{secrets.token_hex(8)}', protocol_version=plan['version'], subject_id=plan['subject_id'],
                  scheduled_occasion=scheduled, occasion=at, occurred_at=occurred.isoformat(),
                  data_revision_id=revision['id'], snapshot_id=snapshot, outcome_metric_id=metric['id'], unit=metric['unit'],
                  measurement_status=status, missing_reason=missing_reason, exposure=exposure, adherence_percent=percent,
                  deviations=deviations, supersedes=supersedes, created_at=store._now(),
                  qc={key: point[key] for key in ('n_trials', 'empty_values', 'quality_flags')} if point else {},
                  measurement=point if status == 'MEASURED' else None)
    return store.update_investigation_fields(investigation_id, {'experiment_visits': [*visits, record]},
                                            inv['version'] if base_version is None else base_version, 'experiment.visit_recorded')


def timeline(investigation_id: str, protocol_version: int | None = None) -> dict:
    inv = long.get_individual_investigation(investigation_id)
    plans = inv.get('experiment_protocols', [])
    plan = next((p for p in plans if p['version'] == protocol_version), None) if protocol_version else (plans[-1] if plans else None)
    method = method_spec('METH-EXPERIMENT')
    result = dict(protocol=plan, rows=[], changes=[], inference={'status': 'NOT_QUALIFIED', 'method': method,
                  'reason': method['reason']}, visits=inv.get('experiment_visits', []))
    if not plan:
        return result
    # History view uses only events recorded against that version; the current plan also shows prior visits.
    visits = [v for v in result['visits'] if v['protocol_version'] <= plan['version']]
    replaced = {v.get('supersedes') for v in visits}
    latest = {v['scheduled_occasion']: v for v in visits if v['id'] not in replaced}
    baseline = []
    for at in plan['testing_occasions']:
        period = next(p for p in plan['periods'] if p['start'] <= at <= p['end'])
        visit = latest.get(at)
        value = visit['measurement']['mean'] if visit and visit['measurement'] else None
        actual_period = next((p for p in plan['periods'] if visit and p['start'] <= visit['occasion'] <= p['end']), None)
        result['rows'].append(dict(scheduled_occasion=at, period=period, observed_period=actual_period, visit=visit, mean=value,
                                   status=visit['measurement_status'] if visit else 'PLANNED'))
        if actual_period and actual_period['kind'] == 'BASELINE' and value is not None:
            baseline.append(value)
    reference = mean(baseline) if baseline else None
    result['baseline_mean'] = reference
    for p in plan['periods']:
        values = [r['mean'] for r in result['rows'] if r['observed_period']
                  and r['observed_period']['id'] == p['id'] and r['mean'] is not None]
        average = mean(values) if values else None
        result['changes'].append(dict(period=p['label'], n=len(values), mean=average,
            change_from_baseline=average-reference if average is not None and reference is not None else None,
            unit=plan['unit'], interpretation='Descriptive observed change only; no causal estimate'))
    return result
