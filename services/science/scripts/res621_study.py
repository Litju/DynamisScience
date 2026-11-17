"""Bounded, deterministic 20-athlete/12-week development case; no empirical claims.

Uses the existing force generator (without dense traces), importer, experiment
engine, catalogue and research store. Call prepare(), then follow_up() in the
same disposable root. No operational store or generator manifest is written.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from dynamis_science import experiments, generate, importer, researchstore as store

SEED = 6212026
MISSING = {('SUB-003', 5), ('SUB-007', 9), ('SUB-011', 4), ('SUB-011', 8)}
CONTEXT = dict(source_name='RES-621 synthetic longitudinal case', publisher='DynamisScience development',
    dataset_identity='RES-621-12W', privacy_status='TEST_FIXTURE',
    license_or_agreement='Internal synthetic demonstration', redistribution_restrictions='No empirical claims',
    manufacturer='Simulated', model='Existing force generator', serial_number='SYNTH-621',
    protocol_name='Synthetic CMJ', protocol_version='1.0')


def files(directory: Path) -> list[Path]:
    rng = np.random.default_rng(SEED)
    subjects = generate._subjects(rng)[:20]
    batches = [[] for _ in range(3)]
    for subject in subjects:
        for week in range(1, 13):
            for trial in range(1, 4):
                _, metrics, _ = generate._force_trace(rng, subject, week, trial, 1., 1., emit_trace=False)
                if (subject['subject_id'], week) in MISSING:
                    continue  # Absent outcomes are never filled or imputed.
                batches[0 if week == 1 else 1 if week <= 6 else 2].append(
                    f"{subject['subject_id']},{subject['subject_id']}-W{week}-T{trial},"
                    f"{metrics['jump_height_cm']},{subject['body_mass_kg']},{metrics['peak_force_n']},{week}")
    paths = []
    for number, rows in enumerate(batches, 1):
        path = directory / f'batch-{number}.csv'
        path.write_text('Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N),week\n'
                        + '\n'.join(rows) + '\n', encoding='utf-8')
        paths.append(path)
    return paths


def admit(service, identity, path, previous=None):
    plan = importer.edit_mapping(importer.probe_file(path), {}, {'session_id': path.stem, 'sampling_hz': 1000})
    staged = importer.stage(plan, importer.build_context(CONTEXT))
    assert staged['eligible'], staged
    record = importer.admit(staged)
    detail = service.attach_workspace_data(identity, record['dataset_snapshot_id'],
        **(dict(append=True, confirm_participant_ids=True, base_revision=previous) if previous else {}))
    return detail['active_data_revision_id']


def protocol(index):
    # Prespecified in the simulation before weeks 2–12 are admitted. Never randomized.
    periods = [dict(kind=k, label=label, start=start, end=end) for k, label, start, end in [
        ('BASELINE', 'Usual training', 2, 3), ('INTERVENTION', 'Training block A', 4, 5),
        ('COMPARISON', 'Usual training comparator', 6, 7), ('INTERVENTION', 'Training block B', 8, 9),
        ('COMPARISON', 'Follow-up comparator', 10, 12)]]
    if index == 20:
        periods[-1]['label'] = 'Reduced-load comparator'  # Explicit noncomparability case.
    return dict(prospective=True, prespecified=True, question=f'Synthetic athlete {index}: observed CMJ response?',
        outcome_metric_id='MET-CMJ-HEIGHT', unit='cm', testing_occasions=list(range(2, 13)), periods=periods,
        assignment='Coach-specified ABAB follow-up; nonrandom assignment',
        blinding=f'Unblinded; individualized supervised dose {2 + index % 3} sessions/week')


def run(service, identity, revision, inv=None):
    return service.execute_analysis_run(identity, dict(method_id='METH-EXPERIMENT-DESC' if inv else 'METH-U-DESC',
        outcome_metric_id='MET-CMJ-HEIGHT', parameters={'protocol_version': inv['protocol']['version']} if inv else {},
        data_revision_id=revision, scope={'kind': 'INDIVIDUAL', 'investigation_id': inv['id']} if inv else None))


def visits(service, inv, revision, weeks):
    for week in weeks:
        missing = (inv['scope']['subject_id'], week) in MISSING
        late = inv['scope']['subject_id'] == 'SUB-002' and week == 6
        date = datetime.fromisoformat('2026-08-17T10:00:00-03:00') + timedelta(weeks=week-1, days=2 if late else 0)
        inv = service.record_experimental_visit(inv['id'], dict(protocol_version=inv['protocol']['version'],
            scheduled_occasion=week, occasion=week, occurred_at=date.isoformat(), data_revision_id=revision,
            measurement_status='MISSING' if missing else 'MEASURED',
            missing_reason='Synthetic athlete unavailable' if missing else '',
            exposure='Unknown' if missing else f'Reported supervised dose {2 + int(inv["scope"]["subject_id"][-3:]) % 3}',
            adherence_percent=None if missing else 75 if late else 100,
            deviations='Measurement delayed two days; one training session missed' if late else ''), inv['version'])
    return inv


def capture(service, identity, revision, invs):
    return service.capture_experiment_series(identity, {i['id']: i['version'] for i in invs}, revision)


def prepare(service, directory):
    paths = files(directory)
    identity = service.create_workspace('SYNTHETIC · 20 athletes · 12-week study')['study']['id']
    rev1 = admit(service, identity, paths[0])
    invs = []
    for index in range(1, 21):
        inv = service.create_individual_investigation(identity, f'SUB-{index:03d}', f'Individual training protocol {index}')
        invs.append(service.save_protocol(inv['id'], protocol(index), inv['version']))
    rev2 = admit(service, identity, paths[1], rev1)
    invs = [visits(service, i, rev2, range(2, 7)) for i in invs]
    cohort = run(service, identity, rev2)
    runs = [run(service, identity, rev2, i) for i in invs[:3]]
    report_path = service.export_workspace_report(identity, [cohort['id'], runs[0]['id']], str(directory/'week6.html'))
    report = store.report_versions(identity)[0]
    series = capture(service, identity, rev2, invs[:2])
    return dict(id=identity, paths=paths, revisions=[rev1, rev2], invs=invs, runs=[cohort, *runs],
                frozen_series=copy.deepcopy(series), report_version=report['version'], report_bytes=report_path.read_bytes())


def follow_up(service, case, directory):
    identity = case['id']
    inv = case['invs'][0]
    amendment = protocol(1)
    amendment['periods'][-1]['notes'] = 'Record reduced-load recovery during future comparator.'
    amendment['amendment_reason'] = 'Prespecified future recovery note after week 6; observed periods unchanged'
    case['invs'][0] = service.save_protocol(inv['id'], amendment, inv['version'])
    revision = admit(service, identity, case['paths'][2], case['revisions'][-1])
    case['revisions'].append(revision)
    case['invs'] = [visits(service, i, revision, range(7, 13)) for i in case['invs']]
    cohort = run(service, identity, revision)
    runs = [run(service, identity, revision, i) for i in case['invs']]
    service.export_workspace_report(identity, [cohort['id'], runs[0]['id']], str(directory/'week12.html'))
    comparison = capture(service, identity, revision, [case['invs'][i] for i in (0, 1, 19)])
    historical = service.export_report_html(identity, str(directory/'week6-reopened.html'), case['report_version'])
    assert historical.read_bytes() == case['report_bytes']
    from dynamis_science import experiment_series
    assert experiment_series.history(identity)[0] == case['frozen_series']
    assert all(store.get_run(r['id']) == r for r in case['runs'])
    case['final_runs'] = [cohort, *runs]
    case['comparison'] = comparison
    return case
