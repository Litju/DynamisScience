"""Prospective plans and append-only visit records in existing individual investigations."""
from __future__ import annotations

import math
import secrets
import copy
from datetime import datetime
from statistics import mean, median, stdev

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


def timeline(investigation_id: str, protocol_version: int | None = None, *, investigation: dict | None = None) -> dict:
    inv = investigation if investigation is not None else long.get_individual_investigation(investigation_id)
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


def analysis_context(entity: dict, scope: dict, parameters: dict) -> dict:
    """Read the captured investigation version, never a newer correction during execution."""
    identity = scope.get('investigation_id')
    if scope.get('kind') != 'INDIVIDUAL' or not identity:
        return {'issues': ['Select an individual experiment investigation.']}
    inv = store.get_investigation(identity)
    version = scope.get('investigation_version')
    if version is not None:
        inv = next((v for v in store.investigation_versions(identity) if v['version'] == version), None)
    if not inv or inv['study_id'] != entity['id'] or inv.get('scope', {}).get('subject_id') != scope.get('subject_id'):
        return {'issues': ['The investigation, participant or workspace binding is incompatible.']}
    version = parameters.get('protocol_version')
    if version is not None and (type(version) is not int or version < 1):
        return {'issues': ['protocol_version must be a positive integer.']}
    data = timeline(identity, version, investigation=inv)
    p = data['protocol']
    if not p:
        return {'issues': ['No saved prospective experimental protocol at the selected version.']}
    revision = store.get_data_revision(entity.get('active_data_revision_id') or '')
    issues = []
    if not revision or revision['workspace_id'] != entity['id']:
        issues.append('Pin an admitted data revision in this workspace.')
    source_ids = {r['visit']['data_revision_id'] for r in data['rows'] if r['visit']}
    sources = [store.get_data_revision(r) for r in sorted(source_ids)]
    if revision:
        for source in sources:
            if (not source or source['workspace_id'] != entity['id'] or source['number'] > revision['number']
                    or not set(source['input_snapshot_ids']) <= set(revision['input_snapshot_ids'])):
                issues.append('Visit revisions are incompatible with the pinned data revision; select a revision containing their source data.')
                break
    for row in data['rows']:
        v = row['visit']
        if not v:
            continue
        if v['subject_id'] != p['subject_id'] or v['outcome_metric_id'] != p['outcome_metric_id'] or v['unit'] != p['unit']:
            issues.append('Visit participant, outcome or units differ from the saved protocol.')
        if v.get('measurement') and (not math.isfinite(v['measurement']['mean']) or v['measurement']['n_trials'] < 1):
            issues.append('A measured visit has no finite QC-eligible session mean.')
    return dict(issues=issues, investigation=inv, timeline=data, revision=revision,
                sources=sources, subject_id=p['subject_id'])


def analysis_eligibility(method: dict, metric: dict, subjects: list[str], scope: dict,
                         parameters: dict, context: dict | None) -> dict:
    context = context or {'issues': ['Experimental protocol and recorded-visit context is required.']}
    issues = list(context.get('issues', []))
    data = context.get('timeline') or {}
    p = data.get('protocol') or {}
    if scope.get('kind') != 'INDIVIDUAL' or subjects != [p.get('subject_id')]:
        issues.append('This method describes exactly one pinned athlete; cross-subject comparisons are unsupported.')
    if p.get('design') not in method['supported_designs'] or not p.get('prespecified'):
        issues.append('Incompatible experimental design: a saved prospective N-of-1 protocol is required.')
    if metric['table'] not in method['required_tables'] or metric['id'] != p.get('outcome_metric_id') or metric.get('unit') != p.get('unit'):
        issues.append('Outcome and units must match the experimental protocol.')
    if set(parameters) - {'protocol_version'}:
        issues.append('Unsupported comparison or parameter; this method provides phase descriptions only.')
    observed = sum(r['mean'] is not None for r in data.get('rows', []))
    if not observed:
        issues.append('At least one recorded QC-eligible measurement is required; planned or missing visits are not observations.')
    return {**copy.deepcopy(method), 'method_id': method['id'], 'status': 'INELIGIBLE' if issues else 'ELIGIBLE',
            'issues': issues, 'population': {'subjects': len(subjects), 'observed_sessions': observed},
            'protocol_version': p.get('version'), 'limitations': [*method['limitations'], *DESCRIPTION_LIMITS]}


DESCRIPTION_LIMITS = [
    'Descriptive observed changes only. Causal experimental inference is NOT_QUALIFIED; no effect estimate, confidence interval or p-value is supplied.',
    'Phase differences may reflect time trends, order, carryover, testing changes or other exposures; they cannot be attributed to treatment.',
    'Serial dependence between visits is not modeled. Slopes and sample SD describe the recorded data, not independent-sample uncertainty.',
    'Unequal phase durations and informative missingness can distort phase summaries; missing or unrecorded visits are never imputed.',
    'Phase membership uses the actual ordinal occasion; date-based trends use actual elapsed days. Documented exposure is not inferred from the planned phase.',
    'Phase SD is variation between session means, not measurement error or a response threshold. Each visit has equal weight regardless of trial count.',
]


def describe(context: dict) -> dict:
    """Pure phase arithmetic on a frozen, eligibility-checked visit ledger."""
    data, inv = context['timeline'], context['investigation']
    p = data['protocol']
    rows = copy.deepcopy(data['rows'])
    phases = []
    baseline = [r['mean'] for r in rows if r['mean'] is not None and r['observed_period']
                and r['observed_period']['kind'] == 'BASELINE']
    baseline_mean = mean(baseline) if baseline else None
    for phase in p['periods']:
        scheduled = [r for r in rows if r['period']['id'] == phase['id']]
        observed = [r for r in rows if r['observed_period'] and r['observed_period']['id'] == phase['id'] and r['mean'] is not None]
        observed.sort(key=lambda r: datetime.fromisoformat(r['visit']['occurred_at']))
        values = [r['mean'] for r in observed]
        dates = [datetime.fromisoformat(r['visit']['occurred_at']) for r in observed]
        n = len(values)
        days = [(d-dates[0]).total_seconds()/86400 for d in dates] if dates else []
        distinct = len(set(days))
        slope = None
        if n >= 3 and distinct >= 3:
            center = mean(days)
            slope = sum((x-center)*(y-mean(values)) for x, y in zip(days, values))/sum((x-center)**2 for x in days)
        limitations = []
        if n < 2:
            limitations.append('Insufficient observations: within-phase SD and first-to-last change need at least two sessions on distinct dates.')
        if n < 3 or distinct < 3:
            limitations.append('Insufficient distinct visit dates: descriptive trend needs at least three sessions on three dates.')
        if n > distinct:
            limitations.append('Repeated timestamps: within-day order is unknown; tied endpoints do not support a first-to-last change.')
        if baseline_mean is None:
            limitations.append('No observed baseline; change from baseline is unavailable.')
        endpoint_unique = n >= 2 and days.count(days[0]) == 1 and days.count(days[-1]) == 1
        phases.append(dict(period=phase, n_sessions=n, n_trials=sum(r['visit']['measurement']['n_trials'] for r in observed),
            scheduled_n=len(scheduled), scheduled_measured_n=sum(r['status']=='MEASURED' for r in scheduled),
            missing_n=sum(r['status']=='MISSING' for r in scheduled), unrecorded_n=sum(r['status']=='PLANNED' for r in scheduled),
            mean=mean(values) if values else None, median=median(values) if values else None,
            sd=stdev(values) if n >= 2 else None, minimum=min(values) if values else None, maximum=max(values) if values else None,
            first_date=dates[0].isoformat() if dates else None, last_date=dates[-1].isoformat() if dates else None,
            observed_change=values[-1]-values[0] if endpoint_unique else None,
            change_from_baseline=mean(values)-baseline_mean if values and baseline_mean is not None else None,
            slope_per_day=slope, limitations=limitations))
    return dict(method='Individual experimental phase descriptions', status='COMPUTED', subject_id=p['subject_id'],
        protocol_version=p['version'], protocol=copy.deepcopy(p), investigation_version=inv['version'],
        data_revision_id=context['revision']['id'], source_data_revision_ids=[s['id'] for s in context['sources']],
        source_revisions=copy.deepcopy(context['sources']), unit=p['unit'], outcome=p['outcome_metric_id'],
        n_subjects=1, n_observations=sum(f['n_sessions'] for f in phases), baseline_mean=baseline_mean,
        phases=phases, observations=rows, outside_phase_n=sum(r['mean'] is not None and not r['observed_period'] for r in rows),
        limitations=list(DESCRIPTION_LIMITS), inference_status='NOT_QUALIFIED')
