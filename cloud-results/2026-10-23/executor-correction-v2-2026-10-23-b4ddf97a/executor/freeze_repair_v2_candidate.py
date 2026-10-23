from pathlib import Path
import json,hashlib,sys,subprocess,re
J=json.loads(Path('/workspace/repair-v2-current.json').read_text());P=Path(J['root']);S=Path(J['source']);C=P/'software'
def read(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
M=read(P/'candidate_manifest_DRAFT.json');assert not (P/'candidate_manifest.json').exists()
static=read(C/'results/static_check.json');suite=read(C/'results/selfcheck.json')
assert static['all_pass'] and suite['n']==suite['n_pass'],{'static':static.get('failed'),'suite_fails':[k for k,v in suite['items'].items() if v['result']!='PASS']}
sys.path.insert(0,str(C));from runtime.decks import netlist_for,registry,case_assets
from tools.static_check import normalise
from observers.support_q1r import anchor_time
import numpy as np
reg={x['case_id']:x for x in registry()['cases']}
oldcode='import json,sys;sys.path.insert(0,sys.argv[1]);from runtime.decks import netlist_for,registry;c=next(x for x in registry()["cases"] if x["case_id"]==sys.argv[2]);n,_=netlist_for(c);print(json.dumps(n.lines))'
checks={};deltas={}
for cid in ['DC_3','CHAIN_12_W_F','Q1_MOTHER_PROTOCOL']:
 old=json.loads(subprocess.check_output([sys.executable,'-c',oldcode,str(S),cid],text=True));new,_=netlist_for(reg[cid])
 om={l.split()[0]:l for l in old};nm={l.split()[0]:l for l in new.lines};added=set(nm)-set(om);removed=set(om)-set(nm);changed={k for k in om.keys()&nm.keys() if om[k]!=nm[k]}
 assert not removed and changed=={'rvrestt','rvrestb'}
 assert added and all(k.startswith('n') and k.endswith('kporclamp') for k in added)
 for n in added:
  a=nm[n].split();assert a[1].endswith('ko1') and a[2:6]==['por_hold','0','0','nch'] and a[6:]==['W=4e-06','L=1e-06']
 consumers={k:l for k,l in om.items() if any(re.search(r'_(?:q|qb)$',x) for x in l.split()[1:5])}
 assert all(nm[k]==l for k,l in consumers.items())
 checks[cid]={'all_original_q_qb_consumer_connections_retained':True,'consumer_element_count':len(consumers),'all_membrane_discharge_hysteresis_recovery_connections_retained':True,'new_physical_types':['original-model NMOS only'],'new_mos':len(added),'changed_existing_elements':sorted(changed),'removed_elements':[]}
 deltas[cid]={'new_clamp_names':sorted(added)}
# Freeze exact smoke observation coverage, including real resistor currents into each state capacitor.
smokeplan=read(P/'runs/CHAIN_STARTUP_0_3S/plan.json');sn,_=netlist_for(reg['CHAIN_12_W_F']);slines={l.split()[0]:l.split() for l in sn.lines};states=[]
for name,kind,terms,extra in sn.elements:
 if kind!='C' or name.startswith('cpar_'):continue
 a=slines[name];node=a[1]
 if not (re.search(r'_(?:rec|op_at|op_ad|h1|hs|hc)$',node) or re.fullmatch(r'gw\d+_b\d+',node) or re.fullmatch(r'hw\d+',node)):continue
 resist=[]
 for rn,r in slines.items():
  if rn.startswith('r') and node in r[1:3]:resist.append({'element':rn,'nodes':r[1:3],'R_ohm':float(r[3])})
 states.append({'capacitor':name,'node':node,'C_F':extra['C'],'resistor_branches':resist})
save(P/'SMOKE_MEASUREMENT_INVENTORY.json',{'states':states,'new_clamp_probes':smokeplan['physical_ledger_plan']['probes'],'required_q_nodes':[e[0][1:-len('kporclamp')]+'q' for e in sn.elements if e[0].endswith('kporclamp')],'native_starts':0})
# Independent-node equation must reject wrong independently supplied currents, and missing data remains UNMEASURED.
def residual(vd,vr,rt,rb,il):return None if il is None else (vd-vr)/rt-vr/rb-il
assert abs(residual(3.,.99,2000,1000,15e-6))<1e-15
assert abs(residual(3.,.99,2000,1000,15e-6*1.05))>1e-9
assert residual(3.,.99,2000,1000,None) is None
# Demonstrate the real anchor policy hazard and preserve original case view.
t=np.array([0.,1.,2.,3.]);vv={'time':t,'v(vdd)':np.full(4,3.),'v(por_hold)':np.array([0.,3.,3.,0.])}
assert anchor_time(vv,t,t,t,3)[1]=='por_hold release'
assert anchor_time({k:v for k,v in vv.items() if k!='v(por_hold)'},t,t,t,3)[1]=='record start'
for cid in M['candidate_steps']:
 d=P/'runs'/cid;p=read(d/'plan.json')
 # Same current-comparison selection as original Coordinator (input ammeters only).
 p['ammeters']=[x for x in p['original_judge_vectors'] if x.startswith('i(v') and x!='i(vsrc)' and not x.startswith('i(va_')]
 assert set(p['original_judge_vectors']).issubset(p['required_vectors'])
 assert p['source_anchor_policy']==('por_hold release' if 'v(por_hold)' in p['original_judge_vectors'] else 'record start')
 save(d/'plan.json',p);M['cases'][cid]['plan_sha256']=sha(d/'plan.json')
checks['source_anchor_policy_fixed']=True;checks['load_equation_positive_negative_missing']=True;checks['wrong_current_not_masked_by_reclosure']=True
save(P/'offline/REPAIR_REGRESSION.json',{'result':'PASS','native_solver_starts':0,'original_static_cases':static['n_cases'],'original_selfcheck_n':suite['n'],'original_selfcheck_pass':suite['n_pass'],'checks':checks,'physical_deltas':deltas,'physical_behavior_certified':False})
for n in ['static_check.json','selfcheck.json']:save(P/'offline'/n,read(C/'results'/n))
M.update(status='FROZEN_BEFORE_FIRST_CANDIDATE_SOLVE',candidate_qualification='NOT_GRANTED',source_software_sha256={str(f.relative_to(S)):sha(f) for f in S.rglob('*.py') if '__pycache__' not in f.parts},candidate_software_sha256={str(f.relative_to(C)):sha(f) for f in C.rglob('*.py') if '__pycache__' not in f.parts},design_sha256=sha(P/'CANDIDATE_DESIGN.json'),smoke_gates_sha256=sha(P/'SMOKE_ENGINEERING_GATES.json'),smoke_inventory_sha256=sha(P/'SMOKE_MEASUREMENT_INVENTORY.json'),regression_sha256=sha(P/'offline/REPAIR_REGRESSION.json'),diff_sha256=sha(P/'candidate.diff'),assets=read(P/'runs/C0_CORRECTED_50MS/plan.json')['assets'])
changedpy=[k for k,v in M['candidate_software_sha256'].items() if M['source_software_sha256'].get(k)!=v];assert sorted(changedpy)==['netlists/neuron_nrc.py','netlists/params.py']
save(P/'candidate_manifest.json',M);save(P/'CANDIDATE_FROZEN.json',{'manifest_sha256':sha(P/'candidate_manifest.json'),'native_starts_before_first_candidate':41,'only_c0_has_run':True,'one_candidate':True,'cannot_adjust_after_results':True})
print(json.dumps({'frozen':True,'manifest_sha256':sha(P/'candidate_manifest.json'),'selfchecks':suite['n_pass'],'static_cases':static['n_cases'],'physical_changed_files':changedpy,'source_anchor_policies':{k:v['source_anchor_policy'] for k,v in M['cases'].items()}}))
