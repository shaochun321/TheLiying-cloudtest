from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,sys,subprocess,os,time,signal,traceback,types
J=json.loads(Path('/workspace/repair-v2-current.json').read_text());P=Path(J['root']);D=P/'runs/C0_CORRECTED_50MS'
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 p=Path(p);q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n');q.replace(p)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def append(x):
 with (P/'repair-ledger.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False,default=float)+'\n');f.flush();os.fsync(f.fileno())
p=read(D/'plan.json');pre=read(P/'EXECUTOR_PREFLIGHT.json');auth=read(P/'AUTHORIZATION.json');state=read('/workspace/thermal-g3-latest-state.json');S=read(P/'CURRENT_STATUS.json')
assert state['global_start_count']==40 and state['all_new_solver_processes_reaped']
assert auth['global_starts_before']==40 and auth['max_new_starts']==9 and auth['effective_wall_limit_s'] is None
assert pre['result']=='PASS' and pre['deck_sha256']==sha(p['deck'])==p['deck_sha256']
assert all(sha(a)==h for a,h in p['assets'].items())
assert p['case']['analysis']=='tran 0.001 0.05 0 0.000125'
with (D/'one-shot-reservation.json').open('x') as f:json.dump({'max_actual_starts':1,'reserved_at':now(),'deck_sha256':p['deck_sha256'],'global_before':40},f,indent=2)
assert not Path(p['raw']).exists()
e={'case_id':'C0_CORRECTED_50MS','command':p['command'],'cwd':p['cwd'],'actual_solver_starts':0,'global_before':40,'global_after':40,'effective_wall_limit_s':None,'original_default_wall_s':300,'returncode':None,'spawn_error':None,'solver_wall_s':0.,'solver_process_reaped':False,'retry_count':0}
proc=None;begin=time.monotonic();error=None
try:
 env=os.environ.copy();env['SPICE_SCRIPTS']='/workspace/thermal-g3-env/spice-scripts'
 with (D/'ngspice.log').open('wb') as log:
  try:proc=subprocess.Popen(p['command'],cwd=p['cwd'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  except OSError as ex:e['spawn_error']=repr(ex)
  if proc is not None:
   e.update(actual_solver_starts=1,global_after=41,pid=proc.pid,started_at=now());save(D/'execution.json',e);append({'event':'start',**e})
   S.update(status='DIAGNOSTIC_RUNNING',global_start_count=41,new_starts=1,active_case='C0_CORRECTED_50MS');S['cases']['C0_CORRECTED_50MS']='RUNNING';save(P/'CURRENT_STATUS.json',S)
   state.update(source_batch=str(P),source_finished_marker=None,global_start_count=41,unused_start_slots=24,matrix_batch_status='DIAGNOSTIC_RUNNING',all_new_solver_processes_reaped=False,pushed=False,push_status='NOT_PUSHED',local_evidence_commit=None,remote_evidence_commit=None);save('/workspace/thermal-g3-latest-state.json',state)
   e['returncode']=proc.wait()
except BaseException as ex:error={'exception':repr(ex),'traceback':traceback.format_exc()}
finally:
 if proc is not None:
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait()
  e.update(returncode=proc.returncode,solver_wall_s=time.monotonic()-begin,solver_process_reaped=True,ended_at=now())
 save(D/'execution.json',e)
c={'result':'UNMEASURED','original_completion_failure':None,'raw_exists':Path(p['raw']).exists(),'raw_sha256':None,'raw_bytes':0,'actual_end_s':None,'qualification_claimed':False,'executor_error':error,'sparse_banner_seen':False}
try:
 sys.path.insert(0,J['source']);from solver_adapter.read_raw_mmap import read_raw_mmap
 from runtime.coordinator import Coordinator
 import numpy as np
 V=None
 if c['raw_exists']:
  c['raw_sha256']=sha(p['raw']);c['raw_bytes']=Path(p['raw']).stat().st_size
  plots=read_raw_mmap(p['raw']);assert len(plots)==1;V=plots[0]
  if 'time' in V:V['time']=np.ascontiguousarray(V['time']);c.update(actual_end_s=float(V['time'][-1]),points=len(V['time']),variables=len(V))
 log=(D/'ngspice.log').read_text(errors='replace');c['sparse_banner_seen']='Using SPARSE 1.3 as Direct Linear Solver' in log
 fn=types.FunctionType(Coordinator.completion.__code__,{**Coordinator.completion.__globals__,'read_raw':lambda _:[V] if V is not None else []},Coordinator.completion.__name__,Coordinator.completion.__defaults__,Coordinator.completion.__closure__)
 fail=fn(Coordinator.__new__(Coordinator),e['returncode'],log,p['raw'],p['case'],p['required_vectors']);c['original_completion_failure']=fail
 if error is None and fail is None and c['sparse_banner_seen'] and abs(c['actual_end_s']-.05)<1e-9:c['result']='PASS'
except BaseException as ex:c.update(result='UNMEASURED',completion_exception=repr(ex),completion_traceback=traceback.format_exc())
save(D/'completion.json',c);save(D/'judge-output.json',{'result':'NOT_APPLICABLE_DIAGNOSTIC_ONLY','engineering_completion':c['result'],'qualification_claimed':False})
append({'event':'end',**e,'completion':c})
S.update(status='DIAGNOSTIC_COMPLETE_READY_FOR_CAUSAL_REVIEW' if c['result']=='PASS' else 'EXECUTION_FAILED',active_case=None,solver_wall_s=e['solver_wall_s']);S['cases']['C0_CORRECTED_50MS']=c['result'];save(P/'CURRENT_STATUS.json',S)
state.update(matrix_batch_status=S['status'],all_new_solver_processes_reaped=bool(e['solver_process_reaped']),new_batch_solver_wall_s=e['solver_wall_s'],exact_global_historical_wall_s=None);save('/workspace/thermal-g3-latest-state.json',state)
print(json.dumps({'execution':e,'completion':c},ensure_ascii=False),flush=True)
