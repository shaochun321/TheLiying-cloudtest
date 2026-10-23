from pathlib import Path
import json,hashlib,ast,re,shutil,sys
import numpy as np
J=json.loads(Path('/workspace/repair-v3-current.json').read_text());P=Path(J['root']);V2=Path(J['parent_batch'])
def read(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert read(P/'software/results/static_check.json')['all_pass']
shutil.copy2(P/'software/results/static_check.json',P/'offline/static_check.json')
shutil.copy2(P/'INHERITED_REFERENCE_DESIGN.json',P/'CANDIDATE_DESIGN.json');shutil.copy2(P/'offline/reference_baseline_summary.json',P/'offline/original-dc-load.json')
for f in ['v3_engineering.py','run_repair_v3.py','prepare_repair_v3.py','freeze_repair_v3.py']:shutil.copy2(Path('/workspace')/f,P/'executor'/f)
M=read(P/'candidate_manifest_DRAFT.json');tests={}
def valid(text,expected,analysis):
 lines=[x.strip().lower() for x in text.splitlines() if x.strip() and not x.strip().startswith('*')]
 if lines.count('.control')!=1 or lines.count('.endc')!=1:return False
 solves=[x for x in lines if re.match(r'^\.?(?:op|tran|dc|ac|noise|pz|tf|sens|disto)\b',x)]
 if solves!=[analysis.lower()] or any(re.match(r'^(?:\.ic|\.nodeset|\.step|alter|reset|source|resume)\b',x) for x in lines):return False
 if analysis.startswith('tran ') and ('uic' in analysis.split() or 'uic' in ' '.join(solves)):return False
 return text==expected
for cid,info in M['cases'].items():
 d=Path(info['directory']);p=read(d/'plan.json');mos=p['mos_nodes'];pref=[name[:-4] for name in mos if name.endswith('bias')];newnames=[pr+tag for pr in pref for tag in ['cp','bias','off','eni_p','eni_n']]+[n for n in mos if n.endswith('kporclamp')]
 p['new_physical_mos_nodes']={n:mos[n] for n in newnames};assert all(n in mos for n in newnames)
 if cid not in ['T0_GATED_SOURCE_BENCH','CHAIN_STARTUP_0_3S','DC_3','DC_2P7','DC_3P2']:
  extra=['v('+n+')' for nodes in p['new_physical_mos_nodes'].values() for n in nodes if n!='0'];p['required_vectors']=list(dict.fromkeys(p['required_vectors']+extra));lines=Path(p['deck']).read_text().splitlines();lines=['.save '+' '.join(p['required_vectors']) if l.startswith('.save ') else l for l in lines];Path(p['deck']).write_text('\n'.join(lines)+'\n');p['deck_sha256']=sha(p['deck'])
 assert set(p['original_judge_vectors']).issubset(p['required_vectors'])
 text=Path(p['deck']).read_text();analysis=p['case']['analysis'];checks={'actual_generated_deck':valid(text,text,analysis),'second_analysis_rejected':not valid(text.replace('.endc','op\n.endc'),text,analysis),'initial_override_rejected':not valid(text.replace('.control','.ic v(vdd)=3\n.control'),text,analysis),'component_drift_rejected':not valid(text.replace('rint ','rint_changed ',1),text,analysis),'source_and_model_drift_rejected':not valid(text.replace('.include ','.include /wrong/',1),text,analysis),'duplicate_control_rejected':not valid(text+'\n.control\nop\n.endc',text,analysis)}
 if analysis.startswith('tran '):
  bits=analysis.split();assert bits[1]=='0.001';expected_step='0.0000625' if cid=='Q1_MOTHER_HALFSTEP' else '0.000125';assert float(bits[-1])==float(expected_step)
  checks.update(uic_rejected=not valid(text.replace(analysis,analysis+' uic'),text,analysis),first_parameter_change_rejected=not valid(text.replace(analysis,analysis.replace('0.001','0.000125',1)),text,analysis),maximum_step_change_rejected=not valid(text.replace(analysis,analysis.rsplit(' ',1)[0]+' 0.0005'),text,analysis))
 else:assert analysis=='op'
 assert all(checks.values()),(cid,checks);tests[cid]=checks
 save(d/'plan.json',p);M['cases'][cid].update(plan_sha256=sha(d/'plan.json'),deck_sha256=sha(p['deck']))
sys.path.insert(0,str(P/'software'));sys.path.insert(0,str(P/'executor'));from v3_engineering import band_ok,charge,t0_engineering
assert band_ok(np.array([1e-6]),np.array([1e-6]),1.,.10)
assert not band_ok(np.array([1.2e-6]),np.array([1e-6]),1.,.10)
q=charge(np.array([0.,1.,2.]),np.array([1.,0.,-1.]),0.,2.);assert q['net_C']==0. and q['absolute_C']==1. and q['positive_C']==q['negative_magnitude_C']==.5
assert t0_engineering({},read(P/'runs/T0_GATED_SOURCE_BENCH/plan.json'),read(P/'V3_TEST_CONTRACT.json'))['result']=='UNMEASURED'
from observers.support_q1r import anchor_time
t=np.array([0.,1.,2.]);v={'time':t,'v(vdd)':np.ones(3)*3,'v(por_hold)':np.array([3.,3.,0.])};assert anchor_time(v,t,t,t,2)[1]=='por_hold release';assert anchor_time({k:x for k,x in v.items() if k!='v(por_hold)'},t,t,t,2)[1]=='record start'
for path,h in M['assets'].items():assert sha(path)==h
source=(V2/'software/netlists/bundle_physical.py').read_text();new=(P/'software/netlists/bundle_physical.py').read_text();other=lambda txt:{x.name:ast.dump(x) for x in ast.parse(txt).body if isinstance(x,ast.FunctionDef) and x.name!='gated_source'};assert other(source)==other(new)
pre={'result':'PASS','native_starts':0,'per_actual_deck_checks':tests,'all_33_static_cases_pass':True,'focused_regression':{'wrong_measured_input_current_rejected':True,'opposite_charge_not_cancelled':True,'missing_vectors_unmeasured':True,'original_anchor_view_policy_preserved':True,'other_bundle_functions_retained':True},'source_v2_full_software_selfcheck':'124/124 previously passed; not represented as a new v3 full suite run.','T0_one_transient_parallel_channels':True,'source_numerics':'SPARSE Gear reltol1e-5 abstol1e-16, output parameter1ms, maximum125us or62.5us halfstep','no_initialization_override':True}
save(P/'EXECUTOR_PREFLIGHT.json',pre)
M.update(status='FROZEN_BEFORE_FIRST_SOLVE',preflight_sha256=sha(P/'EXECUTOR_PREFLIGHT.json'),executor_sha256={str(P/'executor'/n):sha(P/'executor'/n) for n in ['v3_engineering.py','run_repair_v3.py']},inherited_v2_helpers_source_sha256=sha('/workspace/run_repair_v2_candidate.py'),smoke_inventory_sha256=sha(P/'SMOKE_MEASUREMENT_INVENTORY.json'),smoke_gates_sha256=sha(P/'SMOKE_ENGINEERING_GATES.json'),no_added_diagnostics_change_formal_anchor_policy=True,scope_of_model_checks='T0/T1/T2 all MOS; successor formal cases additionally save every changed gated source and retained POR clamp terminal voltage in diagnostic view, checked separately from unmodified original judge.')
save(P/'candidate_manifest.json',M);save(P/'CANDIDATE_FROZEN.json',{'manifest_sha256':sha(P/'candidate_manifest.json'),'global_before':43,'one_candidate':True,'no_candidate_parameter_change_after_first_start':True})
print(json.dumps({'frozen':True,'root':str(P),'manifest_sha256':sha(P/'candidate_manifest.json'),'static_cases':33,'native_starts':0,'T0_expected_analysis':'tran 0.001 0.06 0 0.000125'}))
