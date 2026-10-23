"""Fixed one-candidate C1-C8 sequence; one native start per case, first failure stops.
No changes to the original scientific modules; diagnostic and formal views stay separate.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,sys,subprocess,time,os,signal,types,traceback,gc
import numpy as np
J=json.loads(Path('/workspace/repair-v2-current.json').read_text());P=Path(J['root']);C=P/'software'
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 p=Path(p);q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n');q.replace(p)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def append(x):
 with (P/'repair-ledger.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False,default=float)+'\n');f.flush();os.fsync(f.fileno())
M=read(P/'candidate_manifest.json');assert read(P/'CANDIDATE_FROZEN.json')['manifest_sha256']==sha(P/'candidate_manifest.json')
assert M['status']=='FROZEN_BEFORE_FIRST_CANDIDATE_SOLVE' and M['max_new_native_starts_this_batch']==9
assert read(P/'runs/C0_CORRECTED_50MS/completion.json')['result']=='PASS'
assert sha(P/'SMOKE_MEASUREMENT_INVENTORY.json')==M['smoke_inventory_sha256']
assert sha(P/'CANDIDATE_DESIGN.json')==M['design_sha256'] and sha(P/'SMOKE_ENGINEERING_GATES.json')==M['smoke_gates_sha256']
for rel,h in M['candidate_software_sha256'].items():assert sha(C/rel)==h,rel
for path,h in M['assets'].items():assert sha(path)==h
with (P/'candidate-execution-once.json').open('x') as f:json.dump({'started_at':now(),'manifest_sha256':sha(P/'candidate_manifest.json'),'pid':os.getpid(),'maximum_candidate_starts':8},f,indent=2)
sys.path.insert(0,str(C))
from solver_adapter.read_raw_mmap import read_raw_mmap
from runtime.coordinator import Coordinator
from observers.judges import judge
from observers.observers_q1r import edges
from observers.ledger_q1r import model_domain
S=read(P/'CURRENT_STATUS.json');GLOBAL=read('/workspace/thermal-g3-latest-state.json');assert S['global_start_count']==GLOBAL['global_start_count']==41 and S['new_starts']==1
S.update(status='CANDIDATE_SEQUENCE_RUNNING',active_case=None,candidate_scientific_verdict='NOT_GRANTED',candidate_cases={})
def publish():
 save(P/'CURRENT_STATUS.json',S)
 GLOBAL.update(source_batch=str(P),global_start_count=S['global_start_count'],unused_start_slots=65-S['global_start_count'],matrix_batch_status=S['status'],all_new_solver_processes_reaped=S['active_case'] is None,new_batch_solver_wall_s=S['solver_wall_s'],exact_global_historical_wall_s=None,pushed=False,push_status='NOT_PUSHED',remote_evidence_commit=None,local_evidence_commit=None)
 save('/workspace/thermal-g3-latest-state.json',GLOBAL)
def load(raw):
 a=read_raw_mmap(raw);assert len(a)==1;V=a[0]
 if 'time' in V:
  old=V['time'];new=np.ascontiguousarray(old);assert np.array_equal(old.view(np.uint64),new.view(np.uint64));V['time']=new
 return V
def scoring_view(allv,plan):
 # The only filtered values are explicitly frozen additional diagnostics, never original measured quantities.
 out={k:allv[k] for k in plan['original_judge_vectors'] if k in allv}
 if 'time' in allv:out['time']=allv['time']
 assert ('v(por_hold)' in out)==('v(por_hold)' in plan['original_judge_vectors'])
 return out
def dc_engineering(V,p):
 des=read(P/'CANDIDATE_DESIGN.json');terms=p['physical_ledger_plan']['terms'].get('vrest',[]);records=[];missing=[]
 for x in terms:
  if x['vec'] not in V:missing.append(x['vec']);continue
  records.append({'element':x['element'],'kind':x['kind'],'current_out_of_vrest_A':float(V[x['vec']][0])*x['sign'],'measurement_vector':x['vec']})
 if missing or not records:return {'result':'UNMEASURED','missing':missing}
 vd=float(V['v(vdd)'][0]);vr=float(V['v(vrest)'][0]);IL=sum(r['current_out_of_vrest_A'] for r in records if r['element'] not in ['rvrestt','rvrestb','cvrestc','cpar_vrest']);res=sum(r['current_out_of_vrest_A'] for r in records)
 pred=vd/3-(1000/3)*IL;tol=1e-9
 old=next(x for x in read(P/'offline/original-dc-load.json') if x['case']==p['case']['case_id'])
 checks={'independent_full_node_kcl':abs(res)<=tol,'loaded_prediction_matches':abs(vr-pred)<=tol*(1000/3),'load_within_frozen_25pct_envelope':abs(IL)<=des['load_upper_bound_A'],'extra_supply_drop_within_20mV':old['actual_internal_vdd_V']-vd<=.020,'reference_error_within_design_epsilon':abs(vr-vd/3)<=des['epsilon_V']*vd/3}
 return {'result':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'actual_internal_vdd_V':vd,'vrest_V':vr,'unloaded_prediction_V':vd/3,'independently_measured_load_A':IL,'loaded_prediction_V':pred,'independent_node_residual_A':res,'residual_tolerance_A':tol,'branch_count':len(records),'branch_currents':records,'measurement_is_independent_of_divider_inference':True,'upper_divider_voltage_derived_current_A':(vd-vr)/1000,'lower_divider_voltage_derived_current_A':vr/500,'reference_dc_capacitor_current_expected_A':0}
def smoke_engineering(V,p):
 gates=read(P/'SMOKE_ENGINEERING_GATES.json');inv=read(P/'SMOKE_MEASUREMENT_INVENTORY.json');t=V['time'];thr=float(np.median(V['v(vdd)']))/2;fail=[];missing=[]
 def need(n):
  if n not in V:missing.append(n);return False
  return True
 for n in ['v(por_hold)','v(por_ok)','v(vdd)','v(vmid)','v(load_pos)','v(load_neg)']:need(n)
 if missing:return {'result':'UNMEASURED','missing':missing}
 hu,hd=edges(t,V['v(por_hold)'],thr);ou,od=edges(t,V['v(por_ok)'],thr)
 released=len(hd)>0 and len(ou)>0 and V['v(por_hold)'][-1]<.1*V['v(vdd)'][-1] and V['v(por_ok)'][-1]>.9*V['v(vdd)'][-1]
 if not released:fail.append('POR did not release and settle within 3s')
 events={}
 logic=list(dict.fromkeys(['v('+n+')' for n in inv['required_q_nodes']]+[n for n in V if n.startswith('v(') and n.endswith(('_op_aq)','_op_p)','_q)'))]))
 for n in logic:
  if not need(n):continue
  up,dn=edges(t,V[n],thr);events[n]={'up_count':len(up),'first_up_s':float(up[0]) if len(up) else None,'peak_V':float(np.max(V[n]))}
  if len(up) or np.any(V[n]>thr):fail.append('pre-stimulus logic event '+n)
 states=[]
 for x in inv['states']:
  key='v('+x['node']+')'
  if not need(key):continue
  y=V[key];peak=float(np.max(np.abs(y)));branches=[]
  for b in x['resistor_branches']:
   vals=[]
   for n in b['nodes']:
    if n=='0':vals.append(0.)
    elif need('v('+n+')'):vals.append(V['v('+n+')'])
   if len(vals)!=2:continue
   ii=(vals[0]-vals[1])/b['R_ohm'];into=-ii if b['nodes'][0]==x['node'] else ii
   branches.append({**b,'net_charge_into_node_C':float(np.trapezoid(into,t)),'peak_absolute_current_A':float(np.max(np.abs(ii)))})
  states.append({'capacitor':x['capacitor'],'node':x['node'],'C_F':x['C_F'],'peak_abs_V':peak,'end_V':float(y[-1]),'peak_absolute_state_charge_C':peak*x['C_F'],'net_state_charge_change_C':float((y[-1]-y[0])*x['C_F']),'resistor_current_readbacks':branches})
  if peak>gates['state_voltage_limit_V']:fail.append('abnormal stored state '+x['node'])
 rail=[];mask=t>=.02
 for n in ['v(load_pos)','v(load_neg)']:
  delta=float(np.max(np.abs(V[n][mask]-V['v(vmid)'][mask])));rail.append({'node':n,'max_abs_delta_from_vmid_after_ramp_V':delta})
  if delta>gates['rails_max_abs_deviation_from_vmid_after_rail_ramp_V']:fail.append('abnormal load rail '+n)
 probes=inv['new_clamp_probes'];by={}
 for x in probes.values():
  if not need(x['vec']):continue
  if x['node']!='0' and not need('v('+x['node']+')'):continue
  ii=V[x['vec']]*x['sign'];vv=0. if x['node']=='0' else V['v('+x['node']+')']
  row=by.setdefault(x['element'],{'terminals':{},'net_electrical_port_energy_J':0.})
  row['terminals'][x['terminal']]={'current_peak_abs_A':float(np.max(np.abs(ii))),'net_charge_C':float(np.trapezoid(ii,t))};row['net_electrical_port_energy_J']+=float(np.trapezoid(vv*ii,t))
 if len(by)!=28 or any(set(x['terminals'])!=set('dgsb') for x in by.values()):missing.append('complete new clamp terminal-current coverage')
 md=model_domain(V,p['mos_nodes'])
 if md['result']!='PASS' or md['covered']!=md['total']:fail.append('full model-domain coverage/range')
 result='UNMEASURED' if missing else ('FAIL' if fail else 'PASS')
 return {'result':result,'kind':'ENGINEERING_DIAGNOSTIC_ONLY','full_chain_qualification_claimed':False,'failures':fail,'missing':missing,'actual_end_s':float(t[-1]),'threshold_V':thr,'por_release_and_settle':bool(released),'por_hold_falling_edges_s':hd.tolist(),'por_ok_rising_edges_s':ou.tolist(),'logic_events':events,'state_voltage_limit_V':gates['state_voltage_limit_V'],'state_capacitors':states,'load_rails':rail,'new_clamp_measured_terminal_currents':by,'model_domain':md}
def run(cid):
 contract=M['cases'][cid];D=Path(contract['directory']);p=read(D/'plan.json');assert sha(D/'plan.json')==contract['plan_sha256'] and sha(p['deck'])==contract['deck_sha256']
 assert S['new_starts']<9 and S['global_start_count']<49 and not Path(p['raw']).exists()
 with (D/'one-shot-reservation.json').open('x') as f:json.dump({'reserved_at':now(),'global_before':S['global_start_count'],'manifest_sha256':sha(P/'candidate_manifest.json'),'max_starts':1,'effective_wall_limit_s':None},f,indent=2)
 e={'case_id':cid,'command':p['command'],'cwd':p['cwd'],'actual_solver_starts':0,'returncode':None,'spawn_error':None,'solver_wall_s':0.,'effective_wall_limit_s':None,'original_default_wall_s':p['case']['timeout_s'],'global_before':S['global_start_count'],'global_after':S['global_start_count'],'solver_process_reaped':False,'retry_count':0};proc=None;err=None;start=time.monotonic()
 S.update(active_case=cid);S['cases'][cid]='RUNNING';S['candidate_cases'][cid]={'status':'RUNNING','stage':'SOLVER'};publish()
 try:
  env=os.environ.copy();env['SPICE_SCRIPTS']='/workspace/thermal-g3-env/spice-scripts'
  with (D/'ngspice.log').open('wb') as log:
   try:proc=subprocess.Popen(p['command'],cwd=p['cwd'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   except OSError as ex:e['spawn_error']=repr(ex)
   if proc is not None:
    S['new_starts']+=1;S['global_start_count']+=1;e.update(actual_solver_starts=1,pid=proc.pid,started_at=now(),global_after=S['global_start_count']);save(D/'execution.json',e);append({'event':'start',**e});publish();e['returncode']=proc.wait()
 except BaseException as ex:err={'error':repr(ex),'traceback':traceback.format_exc()}
 finally:
  if proc is not None:
   if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait()
   e.update(returncode=proc.returncode,solver_wall_s=time.monotonic()-start,solver_process_reaped=True,ended_at=now())
  save(D/'execution.json',e)
 S['solver_wall_s']+=e['solver_wall_s'];S['candidate_cases'][cid]['stage']='OFFLINE_SCORE';publish()
 comp={'raw_exists':Path(p['raw']).exists(),'raw_sha256':None,'actual_end_s':None,'raw_bytes':0,'executor_error':err};Vall=None;V=None;baseline=None;out={'result':'UNMEASURED'};engineering={'result':'UNMEASURED'};tj=time.monotonic()
 try:
  if comp['raw_exists']:
   comp['raw_sha256']=sha(p['raw']);comp['raw_bytes']=Path(p['raw']).stat().st_size;Vall=load(p['raw']);comp.update(points=len(next(iter(Vall.values()))),variables=len(Vall),actual_end_s=float(Vall['time'][-1]) if 'time' in Vall else None)
  log=(D/'ngspice.log').read_text(errors='replace');fn=types.FunctionType(Coordinator.completion.__code__,{**Coordinator.completion.__globals__,'read_raw':lambda _:[Vall] if Vall is not None else []},Coordinator.completion.__name__,Coordinator.completion.__defaults__,Coordinator.completion.__closure__)
  failure=fn(Coordinator.__new__(Coordinator),e['returncode'],log,p['raw'],p['case'],p['required_vectors']);comp['original_completion_failure']=failure;comp['sparse_banner_seen']='Using SPARSE 1.3 as Direct Linear Solver' in log
  if failure or not comp['sparse_banner_seen'] or err:out={'result':'UNMEASURED','why':failure or 'executor error/missing SPARSE banner'}
  elif cid=='CHAIN_STARTUP_0_3S':
   engineering=smoke_engineering(Vall,p);out={'result':engineering['result'],'original_full_chain_score':'NOT_APPLICABLE_SHORT_DIAGNOSTIC','qualification_claimed':False}
  else:
   V=scoring_view(Vall,p)
   if p['baseline_case_id']:
    bd=P/'runs'/p['baseline_case_id'];bb=read(bd/'verdict-binding.json');assert bb['result']=='PASS';bp=read(bd/'plan.json');baseline=scoring_view(load(bp['raw']),bp)
   out=judge(p['case'],V,baseline,p['physical_ledger_plan'],ammeters=p['ammeters'],mos_nodes=p['mos_nodes'])
   if cid=='Q1_MOTHER_HALFSTEP':
    mothercase={**p['case'],'case_id':'Q1_MOTHER_PROTOCOL'};single=judge(mothercase,V,None,p['physical_ledger_plan'],ammeters=p['ammeters'],mos_nodes=p['mos_nodes']);save(D/'original-mother-single-step-gates.json',single)
    if single['result']!='PASS':out['result']=single['result'];out['halfstep_single_gate_result']=single['result']
   engineering=dc_engineering(Vall,p) if p['case']['analysis']=='op' else {'result':'PASS','why':'No added engineering gate; original full scientific scoring applies.'}
 except BaseException as ex:out={'result':'UNMEASURED','why':repr(ex),'traceback':traceback.format_exc()}
 scorewall=time.monotonic()-tj;result='PASS' if out['result']=='PASS' and engineering['result']=='PASS' else ('FAIL' if out['result']=='FAIL' or engineering['result']=='FAIL' else 'UNMEASURED')
 save(D/'completion.json',comp);save(D/'judge-output.json',out);save(D/'engineering-output.json',engineering)
 binding={'case_id':cid,'result':result,'original_judge_result':out['result'],'engineering_result':engineering['result'],'deck_sha256':p['deck_sha256'],'raw_path':p['raw'] if comp['raw_exists'] else None,'raw_sha256':comp['raw_sha256'],'actual_end_s':comp['actual_end_s'],'solver_wall_s':e['solver_wall_s'],'offline_score_wall_s':scorewall,'global_start_count':S['global_start_count'],'candidate_manifest_sha256':sha(P/'candidate_manifest.json'),'scoring_view_policy':p['source_anchor_policy'],'additional_diagnostic_vectors_never_entered_original_view':True,'judge_output_sha256':sha(D/'judge-output.json')}
 save(D/'verdict-binding.json',binding);append({'event':'verdict','time':now(),**binding});S['candidate_cases'][cid]={'status':result,'stage':'FINISHED',**binding};S['cases'][cid]=result;S['active_case']=None;publish()
 print(json.dumps(binding,ensure_ascii=False),flush=True);del Vall,V,baseline;gc.collect();return result
try:
 for cid in M['candidate_steps']:
  result=run(cid)
  if result!='PASS':S.update(stop_case=cid,stop_reason='First candidate scientific/engineering failure; no retry or parameter adjustment.');break
 allpass=all(S['cases'][x]=='PASS' for x in M['candidate_steps']);partial=any(S['cases'][x]=='PASS' for x in M['candidate_steps'])
 S.update(status='REPAIR_ACCEPTED' if allpass else ('REPAIR_PARTIAL' if partial else 'REPAIR_FAILED'),active_case=None,finished_at=now(),candidate_scientific_verdict='FIXED_SCOPE_ACCEPTED' if allpass else 'NOT_GRANTED')
 for cid in M['candidate_steps']:
  if S['cases'][cid]=='NOT_STARTED':S['cases'][cid]='BLOCKED_FIRST_FAILURE'
 publish();save(P/'TEST_MATRIX_RESULT.json',S);save(P/'REPAIR_FINISHED.json',S);print(json.dumps({'final_status':S['status'],'global_starts':S['global_start_count'],'solver_wall_s':S['solver_wall_s'],'stop_case':S.get('stop_case')}),flush=True)
except BaseException as ex:
 S.update(status='EXECUTION_FAILED',active_case=None,error=repr(ex),traceback=traceback.format_exc(),finished_at=now());publish();save(P/'TEST_MATRIX_RESULT.json',S);save(P/'REPAIR_FINISHED.json',S);raise
