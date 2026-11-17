"""Descriptive series of individual experiments, frozen in existing investigation history."""
from __future__ import annotations

import copy
import json
from datetime import datetime

from . import experiments, longitudinal, randomized_onset, researchstore as store
from .method_catalogue import CATALOGUE_VERSION, method_spec

LIMIT = ('Descriptive cross-athlete inspection only. Comparability is not evidence of a common '
         'treatment effect. No pooled treatment effect or combined p-value is computed. '
         'Each participant retains their own schedule, conditions and scientific assumptions.')
METHODS = ('METH-EXPERIMENT-DESC', 'METH-ONSET-EXACT')


def _member(entity: dict, inv: dict, runs: list, reports: list) -> dict:
    timeline = experiments.timeline(inv['id'], investigation=inv)
    protocol = timeline['protocol']
    scope = {**inv['scope'], 'investigation_id': inv['id'], 'investigation_version': inv['version']}
    context = experiments.analysis_context(entity, scope, {}) if protocol else {'issues': ['No experimental protocol.']}
    if not protocol:
        eligibility = dict(status='NOT_QUALIFIED', issues=context['issues'])
    elif protocol['design'] == randomized_onset.DESIGN:
        eligibility = randomized_onset.evaluate(context)
    else:
        eligibility = dict(status='DESCRIPTIVE_ONLY', issues=context['issues'])
    own_runs = [r for r in runs if r.get('investigation_id') == inv['id'] and r['method_id'] in METHODS]
    latest = own_runs[-1] if own_runs else None
    current = bool(latest and latest.get('data_revision_id') == entity.get('active_data_revision_id')
                   and latest.get('scope', {}).get('investigation_version') == inv['version']
                   and store.method_status(latest)['state'] == 'CURRENT')
    own_reports = []
    for report in reports:
        sections = report['frozen_content'].get('research_sections', [])
        if any(s.get('scope', {}).get('investigation_id') == inv['id'] for s in sections):
            own_reports.append(dict(version=report['version'], content_hash=report['content_hash']))
    return dict(investigation_id=inv['id'], investigation_version=inv['version'], title=inv['title'],
                subject_id=inv['scope']['subject_id'], protocol=protocol, timeline=timeline,
                observed=sum(r['mean'] is not None for r in timeline['rows']), scheduled=len(timeline['rows']),
                eligibility=eligibility, latest_result=latest, result_current=current, reports=own_reports,
                method_contracts=[method_spec(m) for m in METHODS])


def roster(workspace_id: str) -> dict:
    with store._tx():
        entity = longitudinal._workspace(workspace_id)
        runs = store.list_runs(workspace_id)
        reports = [store.get_report_version(workspace_id, r['version']) for r in store.report_versions(workspace_id)]
        members = [_member(entity, inv, runs, reports) for inv in longitudinal.individual_investigations(workspace_id)]
        return dict(workspace_id=workspace_id, data_revision_id=entity.get('active_data_revision_id'),
                    catalogue_version=CATALOGUE_VERSION, members=members, interpretation=LIMIT)


def comparability(members: list[dict]) -> list[dict]:
    """Conservative exact definitions; no unit conversion or inferred exchangeability."""
    def period_structure(p):
        periods = p['periods']
        schedule = p['testing_occasions']
        offsets = [v-schedule[0] for v in schedule]
        if p['design'] == randomized_onset.DESIGN:
            # Realized onset/phase lengths may differ under the same randomized design.
            c = p['allocation']['configuration']
            dates = [datetime.fromisoformat(v) for v in c['testing_dates']]
            elapsed = [(v-dates[0]).total_seconds() for v in dates]
            return p['design'], p['axis'], offsets, elapsed, c['persistence'], c['lag']
        return p['design'], p['axis'], offsets, [(v['kind'], v['label'], v['end']-v['start']+1, v.get('notes')) for v in periods]

    def allocation(p):
        a = p.get('allocation')
        if not a:
            return p['design'], p['assignment']
        c = a['configuration']
        origin = p['testing_occasions'][0]
        return a['mechanism'], [v-origin for v in c['permissible_starts']], c['statistic'], c['alternative']

    def conditions(p):
        c = p.get('allocation', {}).get('configuration', {})
        return (c.get('baseline_condition'), c.get('intervention_condition')) if c else [
            (v['kind'], v['label'], v.get('notes')) for v in p['periods']]

    def method_versions(m):
        r = m['latest_result']
        return dict(contracts=[(c['id'], c['version'], c['catalogue_version']) for c in m['method_contracts']],
                    saved=(r['method_id'], r.get('method_version')) if r else None)

    definitions = {
        'Outcome definitions': lambda m: (m['protocol']['outcome_metric_id'], m['protocol']['outcome_label']),
        'Units': lambda m: m['protocol']['unit'],
        'Period structure': lambda m: period_structure(m['protocol']),
        'Allocation mechanisms': lambda m: allocation(m['protocol']),
        'Intervention conditions': lambda m: conditions(m['protocol']),
        'Method versions': method_versions,
    }
    checks = []
    for label, definition in definitions.items():
        values = [definition(m) if m['protocol'] else None for m in members]
        ok = bool(values) and all(v is not None and v == values[0] for v in values)
        checks.append(dict(check=label, status='MATCH' if ok else 'REVIEW_REQUIRED', values=values))
    complete = all(m['scheduled'] and m['observed'] == m['scheduled'] and not m['eligibility']['issues'] for m in members)
    checks.append(dict(check='Data sufficiency', status='COMPLETE' if complete else 'INSUFFICIENT',
                       values=[dict(subject_id=m['subject_id'], observed=m['observed'], scheduled=m['scheduled'],
                                    issues=m['eligibility']['issues']) for m in members]))
    checks.append(dict(check='Latest result bindings', status='CURRENT' if all(m['result_current'] for m in members)
                       else 'STALE_OR_ABSENT', values=[m['result_current'] for m in members]))
    return checks


def capture(workspace_id: str, bindings: dict[str, int], data_revision_id: str) -> dict:
    with store._tx():
        entity = longitudinal._workspace(workspace_id)
        if entity['state'] == 'ARCHIVED':
            raise store.ResearchConflict('Restore the workspace before saving comparisons')
        payload = roster(workspace_id)
        if payload['data_revision_id'] != data_revision_id:
            raise store.ResearchConflict('Data revision changed; refresh the series')
        selected = [m for m in payload['members'] if m['investigation_id'] in bindings]
        if len(selected) != len(bindings) or len(selected) < 2 or len({m['subject_id'] for m in selected}) != len(selected):
            raise store.ResearchValidation('Select experiments for at least two distinct athletes in this workspace')
        if any(m['investigation_version'] != bindings[m['investigation_id']] for m in selected):
            raise store.ResearchConflict('An experiment changed; refresh the series')
        content = {**payload, 'members': selected, 'checks': comparability(selected), 'schema_version': 1,
                   'captured_at': store._now()}
        content = json.loads(store._canonical(content))
        return store.create_investigation(workspace_id, 'Series comparison', fields={
            'scope': {'kind': 'EXPERIMENT_SERIES'}, 'comparison': content, 'content_hash': store._digest(content)})


def history(workspace_id: str) -> list[dict]:
    # Read the original stored version even if general investigation editing is used later.
    records = []
    for inv in store.list_investigations(workspace_id):
        if inv.get('scope', {}).get('kind') == 'EXPERIMENT_SERIES':
            original = store.investigation_versions(inv['id'])[0]
            if store._digest(original['comparison']) != original['content_hash']:
                raise store.ResearchConflict('Comparison content hash does not match')
            records.append(copy.deepcopy(original))
    return records
