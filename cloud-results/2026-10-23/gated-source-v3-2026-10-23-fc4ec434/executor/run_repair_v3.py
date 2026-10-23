"""Authorized one-candidate fixed T0-T8 sequence. No retries; first failure ends batch."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import ast,json,hashlib,sys,subprocess,os,time,signal,types,traceback,gc
import numpy as np
J=json.loads(Path('/workspace/repair-v3-current.json').read_text());P=Path(J['root']);C=P/'software'
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 p=Path(p);q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n');q.replace(p)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def append(x):
 with (P/'repair-ledger.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False,default=float)+'\n');f.flush();os.fsync(f.fileno())
M=read(P/'candidate_manifest.json');contract=read(P/'V3_TEST_CONTRACT.json');F=read(P/'CANDIDATE_FROZEN.json');assert F['manifest_sha256']==sha(P/'candidate_manifest.json')
assert M['status']=='FROZEN_BEFORE_FIRST_SOLVE' and M['global_start_before']==43 and M['max_new_starts']==9
assert sha(P/'V3_TEST_CONTRACT.json')==M['contract_sha256']
assert sha('/workspace/run_repair_v2_candidate.py')==M['inherited_v2_helpers_source_sha256']
for rel,h in M['candidate_software_sha256'].items():assert sha(C/rel)==h,rel
for path,h in M['assets'].items():assert sha(path)==h
for path,h in M['executor_sha256'].items():assert sha(path)==h
with (P/'execution-once.json').open('x') as f:json.dump({'pid':os.getpid(),'started_at':now(),'manifest_sha256':sha(P/'candidate_manifest.json'),'max_actual_starts':9},f,indent=2)
sys.path.insert(0,str(C));sys.path.insert(0,str(P/'executor'))
from solver_adapter.read_raw_mmap import read_raw_mmap
from runtime.coordinator import Coordinator
from observers.judges import judge
from observers.observers_q1r import edges
from observers.ledger_q1r import model_domain
from v3_engineering import t0_engineering
# Reuse proven v2 offline helpers only. Compile function definitions without executing its top-level runner.
tree=ast.parse(Path('/workspace/run_repair_v2_candidate.py').read_text());wanted={'load','scoring_view','dc_engineering','smoke_engineering'};exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted],type_ignores=[]),'inherited_v2_offline_helpers','exec'),globals())
S=read(P/'CURRENT_STATUS.json');G=read('/workspace/thermal-g3-latest-state.json');assert S['global_start_count']==G['global_start_count']==43 and G['all_new_solver_processes_reaped']
S.update(status='V3_SEQUENCE_RUNNING',candidate_cases={})
def publish():
 save(P/'CURRENT_STATUS.json',S);G.update(source_batch=str(P),source_finished_marker=None,global_start_count=S['global_start_count'],unused_start_slots=65-S['global_start_count'],matrix_batch_status=S['status'],all_new_solver_processes_reaped=S['active_case'] is None,new_batch_solver_wall_s=S['solver_wall_s'],exact_global_historical_wall_s=None,temporary_wall_limit_waiver_scope='This v3 batch only.',pushed=False,push_status='NOT_PUSHED',local_evidence_commit=None,remote_evidence_commit=None);save('/workspace/thermal-g3-latest-state.json',G)
def run(cid):
 d=P/'runs'/cid;p=read(d/'plan.json');pinned=M['cases'][cid];assert sha(d/'plan.json')==pinned['plan_sha256'] and sha(p['deck'])==pinned['deck_sha256']
 assert S['new_starts']<9 and S['global_start_count']<52 and not Path(p['raw']).exists()
 with (d/'one-shot-reservation.json').open('x') as f:json.dump({'reserved_at':now(),'global_before':S['global_start_count'],'max_starts':1,'effective_wall_limit_s':None,'manifest_sha256':sha(P/'candidate_manifest.json')},f,indent=2)
 e={'case_id':cid,'actual_solver_starts':0,'command':p['command'],'cwd':p['cwd'],'actual_analysis':p['case']['analysis'],'global_before':S['global_start_count'],'global_after':S['global_start_count'],'returncode':None,'spawn_error':None,'solver_wall_s':0.,'solver_process_reaped':False,'retry_count':0,'effective_wall_limit_s':None,'v3_default_reference_wall_s':p['original_default_wall_s']};proc=None;err=None;start=time.monotonic()
 S['active_case']=cid;S['cases'][cid]='RUNNING';S['candidate_cases'][cid]={'stage':'SOLVER','status':'RUNNING'};publish()
 try:
  env=os.environ.copy();env['SPICE_SCRIPTS']='/workspace/thermal-g3-env/spice-scripts'
  with (d/'ngspice.log').open('wb') as log:
   try:proc=subprocess.Popen(p['command'],cwd=p['cwd'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   except OSError as ex:e['spawn_error']=repr(ex)
   if proc is not None:
    S['new_starts']+=1;S['global_start_count']+=1;e.update(actual_solver_starts=1,global_after=S['global_start_count'],pid=proc.pid,started_at=now());save(d/'execution.json',e);append({'event':'start',**e});publish();e['returncode']=proc.wait()
 except BaseException as ex:err={'error':repr(ex),'traceback':traceback.format_exc()}
 finally:
  if proc is not None:
   if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait()
   e.update(returncode=proc.returncode,solver_wall_s=time.monotonic()-start,solver_process_reaped=True,ended_at=now())
  save(d/'execution.json',e)
 S['solver_wall_s']+=e['solver_wall_s'];S['candidate_cases'][cid]['stage']='OFFLINE_SCORE';publish()
 comp={'raw_exists':Path(p['raw']).exists(),'raw_sha256':None,'raw_bytes':0,'actual_end_s':None,'executor_error':err};Vall=V=base=None;score={'result':'UNMEASURED'};engineering={'result':'UNMEASURED'};tj=time.monotonic()
 try:
  if comp['raw_exists']:
   comp.update(raw_sha256=sha(p['raw']),raw_bytes=Path(p['raw']).stat().st_size);Vall=load(p['raw']);comp.update(points=len(next(iter(Vall.values()))),variables=len(Vall),actual_end_s=float(Vall['time'][-1]) if 'time' in Vall else None)
  log=(d/'ngspice.log').read_text(errors='replace');f=Coordinator.completion;fn=types.FunctionType(f.__code__,{**f.__globals__,'read_raw':lambda _:[Vall] if Vall is not None else []},f.__name__,f.__defaults__,f.__closure__);why=fn(Coordinator.__new__(Coordinator),e['returncode'],log,p['raw'],p['case'],p['required_vectors']);comp.update(original_completion_failure=why,sparse_banner_seen='Using SPARSE 1.3 as Direct Linear Solver' in log)
  if why or err or not comp['sparse_banner_seen']:score={'result':'UNMEASURED','why':why or 'executor error/missing SPARSE banner'}
  elif cid=='T0_GATED_SOURCE_BENCH':engineering=t0_engineering(Vall,p,contract);score={'result':engineering['result'],'scope':'INDEPENDENT_ENGINEERING_BENCH_ONLY','original_formal_judge':'NOT_APPLICABLE','qualification_claimed':False}
  elif cid=='CHAIN_STARTUP_0_3S':
   engineering=smoke_engineering(Vall,p)
   inv=read(P/'SMOKE_MEASUREMENT_INVENTORY.json');missing=[x['vec'] for x in inv['new_selector_probes'].values() if x['vec'] not in Vall];energies={}
   for x in inv['new_selector_probes'].values():
    if x['vec'] not in Vall:continue
    vv=0. if x['node']=='0' else Vall['v('+x['node']+')'];energies.setdefault(x['element'],0.);energies[x['element']]+=float(np.trapezoid(vv*Vall[x['vec']]*x['sign'],Vall['time']))
   engineering.update(new_selector_missing=missing,new_selector_device_port_energy_J=energies)
   if missing or len(energies)!=40:engineering['result']='UNMEASURED'
   score={'result':engineering['result'],'scope':'SHORT_ENGINEERING_DIAGNOSTIC_ONLY','original_formal_judge':'NOT_APPLICABLE','qualification_claimed':False}
  else:
   V=scoring_view(Vall,p)
   if p['baseline_case_id']:
    bd=P/'runs'/p['baseline_case_id'];assert read(bd/'verdict-binding.json')['result']=='PASS';bp=read(bd/'plan.json');base=scoring_view(load(bp['raw']),bp)
   score=judge(p['case'],V,base,p['physical_ledger_plan'],ammeters=p['ammeters'],mos_nodes=p['mos_nodes'])
   if cid=='Q1_MOTHER_HALFSTEP':
    original_mother=judge({**p['case'],'case_id':'Q1_MOTHER_PROTOCOL'},V,None,p['physical_ledger_plan'],ammeters=p['ammeters'],mos_nodes=p['mos_nodes']);save(d/'original-mother-single-step-gates.json',original_mother)
    if original_mother['result']!='PASS':score['result']=original_mother['result']
   engineering=dc_engineering(Vall,p) if p['case']['analysis']=='op' else {'result':'PASS','scope':'Original full scientific gates apply unchanged.'}
   changed_domain=model_domain(Vall,p['new_physical_mos_nodes']);engineering['changed_devices_model_domain']=changed_domain
   if changed_domain['result']!='PASS' or changed_domain['covered']!=changed_domain['total']:engineering['result']=changed_domain['result'] if changed_domain['result']=='FAIL' else 'UNMEASURED'
 except BaseException as ex:score={'result':'UNMEASURED','why':repr(ex),'traceback':traceback.format_exc()}
 result='PASS' if score['result']==engineering['result']=='PASS' else 'FAIL' if 'FAIL' in [score['result'],engineering['result']] else 'UNMEASURED'
 for n,x in [('completion.json',comp),('judge-output.json',score),('engineering-output.json',engineering)]:save(d/n,x)
 b={'case_id':cid,'result':result,'original_or_engineering_judge_result':score['result'],'engineering_result':engineering['result'],'deck_sha256':p['deck_sha256'],'raw_path':p['raw'] if comp['raw_exists'] else None,'raw_sha256':comp['raw_sha256'],'actual_end_s':comp['actual_end_s'],'solver_wall_s':e['solver_wall_s'],'offline_score_wall_s':time.monotonic()-tj,'global_start_count':S['global_start_count'],'manifest_sha256':sha(P/'candidate_manifest.json'),'judge_output_sha256':sha(d/'judge-output.json'),'scoring_source_anchor_policy':p['source_anchor_policy']};save(d/'verdict-binding.json',b);append({'event':'verdict','time':now(),**b});S['cases'][cid]=result;S['candidate_cases'][cid]={'stage':'FINISHED',**b};S['active_case']=None;publish();print(json.dumps(b),flush=True);del Vall,V,base;gc.collect();return result
try:
 for cid in M['candidate_steps']:
  result=run(cid)
  if result!='PASS':S.update(stop_case=cid,stop_reason='First v3 engineering/scientific failure; no retry or candidate adjustment.');break
 allpass=all(S['cases'][x]=='PASS' for x in M['candidate_steps']);partial=any(S['cases'][x]=='PASS' for x in M['candidate_steps']);S.update(status='REPAIR_ACCEPTED' if allpass else 'REPAIR_PARTIAL' if partial else 'REPAIR_FAILED',candidate_scientific_verdict='FIXED_SCOPE_ACCEPTED' if allpass else 'NOT_GRANTED',finished_at=now(),active_case=None,remaining_global_start_slots=65-S['global_start_count'])
 for cid in M['candidate_steps']:
  if S['cases'][cid]=='NOT_STARTED':S['cases'][cid]='BLOCKED_FIRST_FAILURE'
 publish();save(P/'TEST_MATRIX_RESULT.json',S);save(P/'REPAIR_FINISHED.json',S);print(json.dumps({'status':S['status'],'starts':S['global_start_count'],'wall_s':S['solver_wall_s'],'stop_case':S.get('stop_case')}),flush=True)
except BaseException as ex:
 S.update(status='EXECUTION_FAILED',error=repr(ex),traceback=traceback.format_exc(),active_case=None,finished_at=now());publish();save(P/'TEST_MATRIX_RESULT.json',S);save(P/'REPAIR_FINISHED.json',S);raise
