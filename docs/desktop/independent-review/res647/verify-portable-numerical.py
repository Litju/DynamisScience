"""Independent standard-library checks against numerical results written by the portable executable."""
import hashlib, json, math, sqlite3
from pathlib import Path
from statistics import mean, stdev
out=Path('C:/Users/Usuario/AppData/Local/Temp/dynamis-independent-20261112')
missing={("P03",3),("P03",5),("P07",6),("P11",2),("P11",3),("P11",4),("P11",5),("P11",6)}
def trials(index,week):
 return [round(30+index+.4*week+((trial*7+index*3+week)%5-2)*.3,2) for trial in range(1,3+index%2)]
def same(actual,expected):
 assert math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12),(actual,expected)
receipts=[]
for scale in ('100','125','150'):
 receipt=json.loads((out/f'portable-{scale}/receipt.json').read_text())
 database=Path(receipt['data_root'])/'research/research.db'
 with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as c:
  documents=[json.loads(row[0]) for row in c.execute('SELECT document FROM runs')]
 checked=[]
 for run in documents:
  result=run['result']; individual=run['scope']['kind']=='INDIVIDUAL'
  expected_points=[]
  for point in result['points']:
   week=point['week']
   if individual:
    index=int(run['scope']['subject_id'][1:]); values=trials(index,week)
    same(point['mean'],mean(values)); same(point['within_session_sd'],stdev(values))
    assert point['n_trials']==len(values)
   else:
    values=[mean(trials(index,week)) for index in range(1,13) if (f'P{index:02d}',week) not in missing]
    same(point['mean'],mean(values)); same(point['sd'],stdev(values)); assert point['n']==len(values)
   expected_points.append({'week':week,'mean':mean(values),'sd':stdev(values),'n':len(values)})
  expected_change=expected_points[-1]['mean']-expected_points[0]['mean']
  same(result['change_first_to_last'],expected_change)
  record={'run_id':run['id'],'scope':run['scope'],'expected_points':expected_points,'expected_change':expected_change,'matched':True}
  if individual:
   sessions=[trials(index,p['week']) for p in result['points']]
   df=sum(len(v)-1 for v in sessions)
   sse=sum(sum((a-b)**2 for i,a in enumerate(v) for b in v[i+1:])/len(v) for v in sessions)
   se=math.sqrt(sse/df*(1/len(sessions[0])+1/len(sessions[-1])))
   same(result['within_session_sd'],math.sqrt(sse/df)); same(result['change_trial_noise_se'],se)
   record.update(independent_sse=sse,df=df,independent_trial_noise_se=se)
  checked.append(record)
 receipts.append({'scale':scale,'executable_sha256':receipt['executable_sha256'],'source_commit':receipt['source_commit'],'workspace_id':receipt['workspace_id'],'runs':checked})
(out/'portable-independent-numerical.json').write_text(json.dumps({'basis':'Standard-library means/SD and independent pairwise-difference SSE; deterministic fixture expectations, not fitted forecasts','checks':receipts},indent=2))
print('Portable numerical checks passed: 15 runs, 63 session/cohort points, 9 trial-noise estimates.')
