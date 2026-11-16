"""Create an intentionally retained, synthetic-only native workspace in a NEW external root.

Usage: python scripts/demo_randomized_onset.py --data-root ABSOLUTE_NEW_DIRECTORY
No private inputs, fixed draws, installer steps or owner settings are used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def write_launcher(root: Path) -> None:
    service = Path(__file__).resolve().parents[1]
    quote = lambda path: str(path).replace("'", "''")
    script = (f"$previousSettings = $env:DYNAMISSCIENCE_SETTINGS_FILE\n"
              f"$env:DYNAMISSCIENCE_SETTINGS_FILE = '{quote(root/'demo-settings.json')}'\n"
              f"Push-Location -LiteralPath '{quote(service)}'\n"
              f"try {{ & '{quote(service/'.venv'/'Scripts'/'python.exe')}' -m dynamis_science.desktop --data-root '{quote(root)}' }}\n"
              "finally { Pop-Location; $env:DYNAMISSCIENCE_SETTINGS_FILE = $previousSettings }\n")
    (root/'Open-Demo.ps1').write_text(script,encoding='utf-8')


def build(root: Path) -> dict:
    root = root.resolve()
    protected = Path('D:/datasets/DynamisScience').resolve()
    repo = Path(__file__).resolve().parents[3]
    if (root == protected or root.is_relative_to(protected) or protected.is_relative_to(root)
            or root == repo or root.is_relative_to(repo) or root.exists()):
        raise ValueError('Demo requires a new external directory outside the repository and protected dataset')
    os.environ['DYNAMISSCIENCE_DATA_ROOT'] = str(root)
    from dynamis_science import importer, researchstore as store
    from dynamis_science.desktop.services import DynamisAppService
    app = DynamisAppService()
    app.ensure_initialized()
    context = importer.build_context(dict(source_name='SYNTHETIC randomized-onset demonstration',
        publisher='DynamisScience synthetic generator', dataset_identity='res716-onset-demo',
        license_or_agreement='Synthetic demonstration only', redistribution_restrictions='No real athlete data',
        privacy_status='TEST_FIXTURE', manufacturer='Simulated', model='Simulated CMJ', serial_number='SYNTHETIC',
        protocol_name='SYNTHETIC fixed CMJ sessions', protocol_version='1.0'))
    identity = app.create_workspace('SYNTHETIC · Randomized onset · two athletes')['study']['id']
    starts = {}
    with tempfile.TemporaryDirectory(prefix='res716-demo-inputs-') as scratch:
        def admit(occasions, name):
            lines = ['Athlete,Trial,Jump Height (cm),Body Mass (kg),Peak Force (N),week']
            for subject,index in [('SYN-A',1),('SYN-B',2)]:
                for at in occasions:
                    y = 30+index+(8 if subject=='SYN-A' and at>=starts.get(subject,99999) else 0)
                    for trial in range(1,3+index):
                        lines.append(f'{subject},{subject}-W{at}-T{trial},{y},75,1700,{at}')
            path = Path(scratch)/name
            path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            mapping = importer.edit_mapping(importer.probe_file(path),{},dict(session_id='SYNTHETIC',sampling_hz=1000))
            staged = importer.stage(mapping,context)
            if not staged['eligible']:
                raise RuntimeError(str(staged))
            return importer.admit(staged)['dataset_snapshot_id']
        rev1 = app.attach_workspace_data(identity,admit(range(1,4),'synthetic-before.csv'))['active_data_revision_id']
        first = datetime.now(timezone.utc).replace(microsecond=0)+timedelta(days=30)
        schedule = list(range(4,35))
        dates = [(first+timedelta(days=i)).isoformat() for i in range(31)]
        plan = dict(design='RANDOMIZED_ONSET',prospective=True,prespecified=True,
            question='SYNTHETIC: is the scheduled trajectory incompatible with the onset sharp null?',
            outcome_metric_id='MET-CMJ-HEIGHT',unit='cm',testing_occasions=schedule,testing_dates=dates,
            permissible_starts=list(range(7,33)),baseline_condition='Simulated usual training',
            intervention_condition='Simulated additional training; persistent through final visit',
            suitability='Synthetic persistent adaptation example; no real intervention or efficacy evidence.',
            assumptions_confirmed=True)
        athletes = []
        for subject in ('SYN-A','SYN-B'):
            inv = app.create_individual_investigation(identity,subject,f'SYNTHETIC {subject} randomized onset')
            inv = app.save_protocol(inv['id'],plan,inv['version'])
            starts[subject] = inv['protocol']['allocation']['assigned_start']  # Real app draw, never chosen by demo.
            athletes.append(inv)
        rev2 = app.attach_workspace_data(identity,admit(range(4,35),'synthetic-after-allocation.csv'),
            append=True,confirm_participant_ids=True,base_revision=rev1)['active_data_revision_id']
        runs = []
        for inv in athletes:
            subject = inv['scope']['subject_id']
            for at,date in zip(schedule,dates):
                condition = 'BASELINE' if at<starts[subject] else 'INTERVENTION'
                inv = app.record_experimental_visit(inv['id'],dict(protocol_version=1,scheduled_occasion=at,
                    occasion=at,data_revision_id=rev2,occurred_at=date,measurement_status='MEASURED',
                    actual_condition=condition,exposure=f'SYNTHETIC recorded {condition.lower()} training',
                    adherence_percent=100),inv['version'])
            runs.append(app.execute_analysis_run(identity,dict(method_id='METH-ONSET-EXACT',
                outcome_metric_id='MET-CMJ-HEIGHT',parameters={'protocol_version':1},data_revision_id=rev2,
                scope={'kind':'INDIVIDUAL','investigation_id':inv['id']})))
        original = store.get_run(runs[0]['id'])
        report = app.export_workspace_report(identity,[r['id'] for r in runs],str(root/'reports'/'original-two-athletes.html'))
        frozen_html = report.read_text(encoding='utf-8')
        version = store.report_versions(identity)[0]['version']
        rev3 = app.attach_workspace_data(identity,admit(range(35,36),'synthetic-extra-session.csv'),
            append=True,confirm_participant_ids=True,base_revision=rev2)['active_data_revision_id']
        inv = store.get_investigation(athletes[0]['id'])
        inv = app.save_protocol(inv['id'],{**plan, 'question':'SYNTHETIC: clarified finite-schedule onset question',
            'amendment_reason':'Narrative correction; allocation and original measurement schedule stay frozen'},inv['version'])
        current = app.execute_analysis_run(identity,dict(method_id='METH-ONSET-EXACT',outcome_metric_id='MET-CMJ-HEIGHT',
            parameters={'protocol_version':2},data_revision_id=rev3,scope={'kind':'INDIVIDUAL','investigation_id':inv['id']}))
        app.export_workspace_report(identity,current['id'],str(root/'reports'/'amended-protocol.html'))
        reopened = DynamisAppService().individual_research(inv['id'])
        assert reopened['runs'][0]['result_digest']==original['result_digest']
        assert store.get_run(original['id'])==original
        old_again=app.export_report_html(identity,str(root/'reports'/'original-reopened.html'),version)
        assert old_again.read_text(encoding='utf-8')==frozen_html
    receipt = dict(synthetic_only=True,data_root=str(root),workspace_id=identity,
        revisions=[rev1,rev2,rev3],investigations=[i['id'] for i in athletes],
        actual_uniform_draws=starts,original_report_version=version,
        results=[dict(subject=r['result']['subject_id'],run_id=r['id'],
            difference_cm=r['result']['inference']['descriptive_difference'],p=r['result']['inference']['p_value'],
            tail_count=r['result']['inference']['tail_count'],assignments=26) for r in runs],
        amended_run_id=current['id'],historical_result_unchanged=True,historical_report_identical=True)
    (root/'demo-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    write_launcher(root)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',required=True,type=Path)
    args=parser.parse_args()
    if not args.data_root.is_absolute():
        parser.error('--data-root must be absolute')
    print(json.dumps(build(args.data_root),indent=2))
