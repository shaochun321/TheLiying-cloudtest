"""Read only the prepared contract and actual first-case records; never launch a solver."""
from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
assert (ROOT/'FIRST_FORMAL_FINISHED.json').exists()
m=read(ROOT/'FORMAL_MANIFEST.json');before=read(ROOT/'COST_GATE_REPORT.json')
e=read(ROOT/'runs/G0_W/execution.json');binding=read(ROOT/'runs/G0_W/verdict-binding.json')
records=[json.loads(x) for x in (ROOT/'formal-ledger.jsonl').read_text().splitlines() if x]
sys.path.insert(0,m['source_software'])
from runtime.coordinator import Coordinator
qualified=before['measured_qualification_rates'];sizes=m['case_sizes']
allrecords=[]
for q in qualified:
 aid='bound-'+q['case_id']
 allrecords.extend([{'rec':'start','analysis_id':aid,'case_id':q['case_id'],'scale':q['scale']},{'rec':'end','analysis_id':aid,'status':'complete','wall_s':q['wall_s']}])
allrecords+=records
ends={x['analysis_id']:x for x in allrecords if x['rec']=='end'}
starts=[x for x in allrecords if x['rec']=='start'];done={x['case_id'] for x in starts}
rates={}
for s in starts:
 end=ends.get(s['analysis_id'])
 if end and end['status']=='complete':rates.setdefault(s['scale'],[]).append(end['wall_s']/max(1,sizes[s['case_id']]))
fallback=max(max(v) for v in rates.values())
registry=read(Path(m['source_software'])/'prereg/cases_q1r.json')
rows=[]
for c in registry['cases']:
 if c['phase']!='formal' or c['case_id'] in done:continue
 rate=max(rates[c['scale']]) if c['scale'] in rates else fallback
 rows.append({'case_id':c['case_id'],'scale':c['scale'],'elements':sizes[c['case_id']],'hard_cap_s':c['timeout_s'],'measured_rate_s_per_element':rate,'forecast_s':min(c['timeout_s'],1.5*rate*sizes[c['case_id']]),'rate_source':'same scale' if c['scale'] in rates else 'largest completed rate fallback'})
spent=sum(x['wall_s'] for x in records if x['rec']=='end')
known=before['known_prior_wall_lower_bound_s']+spent
class BoundView:
 root=m['source_software']
 def records(self):return allrecords
 def status(self):return {'phases':{'formal':{'wall_s':spent}},'total_wall_s':known}
try:
 observed=Coordinator.cost_gate(BoundView(),{},'formal',{'case_sizes':sizes})
 gate={'allowed':True,'forecast_s':observed}
except Exception as exc:gate={'allowed':False,'exception_type':type(exc).__name__,'message':str(exc)}
report={'actual_first_case':binding,'global_start_count':e['global_starts_after'],'remaining_formal_starts':65-e['global_starts_after'],'formal_spent_s':spent,'formal_phase_remaining_s':108000-spent,'global_exact_historical_wall_s':None,'known_total_wall_lower_bound_s':known,'global_remaining_optimistic_upper_bound_s':172800-known,'forecast_rows':rows,'remaining_formal_forecast_s':sum(x['forecast_s'] for x in rows),'unmodified_original_cost_gate':gate,'current_candidate_STOPPED':(ROOT/'STOPPED.json').exists(),'next_case_automatically_authorized':False,'other_case_cost_gate_waiver':False,'new_solver_launches_by_this_script':0}
report['single_case_wall_limit_removed_by_user']=(ROOT/'G0_W_NO_WALL_LIMIT_AUTHORIZATION.json').exists()
report['other_phase_and_global_caps_not_changed']=True
(ROOT/'COST_GATE_AFTER_G0_W.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['forecast_rows','actual_first_case']},indent=2))
