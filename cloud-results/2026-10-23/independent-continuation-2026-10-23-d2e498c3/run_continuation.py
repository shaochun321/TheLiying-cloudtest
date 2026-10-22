"""Authorized one-shot independent-branch continuation, original scientific judges.
No original coordinator, scientific source, freeze, STOPPED or ledger is edited.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,gc,hashlib,json,os,signal,subprocess,sys,time,traceback,types
import numpy as np
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(p,v):
 p=Path(p);temp=p.with_name(p.name+'.tmp');temp.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=float)+'\n');temp.replace(p)
def append(v):
 with (ROOT/'continuation-ledger.jsonl').open('a') as f:f.write(json.dumps(v,ensure_ascii=False,default=float)+'\n');f.flush();os.fsync(f.fileno())
ap=argparse.ArgumentParser();ap.add_argument('--execute-authorized-batch',action='store_true',required=True);args=ap.parse_args()
M=read(ROOT/'CONTINUATION_MANIFEST.json');AUTH=read(ROOT/'AUTHORIZATION.json')
assert AUTH['manifest_sha256']==sha(ROOT/'CONTINUATION_MANIFEST.json')
assert M['global_starts_before']==35 and M['global_start_cap']==65 and M['max_new_starts']==30
assert M['automatic_retries']==0 and M['per_case_max_starts']==1
assert all(x is None for x in M['effective_wall_limits_s'].values())
assert len(M['cases'])==30 and 'G0_W' not in M['cases']
for p,want in M['protected_original_files_sha256'].items():assert sha(p)==want
for cid,b in M['initial_bound_verdicts'].items():
 assert sha(b['binding_path'])==b['binding_sha256']
 assert read(b['binding_path'])['scientific']==b['scientific']
software=Path(M['source_software']);approved=read(M['approved_formal_manifest'])
assert sha(M['approved_formal_manifest'])==M['approved_formal_manifest_sha256']
for rel,want in approved['source_software_sha256'].items():
 if rel.startswith('observers/') or rel in ['solver_adapter/read_raw_mmap.py','config.py','runtime/coordinator.py']:
  assert sha(software/rel)==want,rel
assert sha(software/'prereg/cases_q1r.json')==M['source_registry_sha256']
with (ROOT/'execution-once.json').open('x') as f:json.dump({'pid':os.getpid(),'started_at':now(),'manifest_sha256':sha(ROOT/'CONTINUATION_MANIFEST.json'),'max_new_starts':30},f,indent=2)
sys.path.insert(0,str(software))
from solver_adapter.read_raw_mmap import read_raw_mmap
from runtime.coordinator import Coordinator
from observers.judges import judge
ORIGINAL_COMPLETION=Coordinator.completion
S={'status':'RUNNING','started_at':now(),'global_starts_before':35,'global_start_count':35,'actual_new_solver_starts':0,
 'solver_wall_s':0.0,'offline_judge_wall_s':0.0,'active_case':None,'original_global_exact_historical_wall_s':None,
 'wall_limits_temporarily_waived':True,'original_all_matrix_cost_gate_not_claimed_passed':True,'cases':{cid:{'status':'WAITING_DEPENDENCY'} for cid in M['cases']}}
def publish():save(ROOT/'CURRENT_STATUS.json',S)
def bound_result(cid):
 if cid in M['initial_bound_verdicts']:return M['initial_bound_verdicts'][cid]['scientific']
 return S['cases'][cid]['status']
def deps(cid):
 c=M['cases'][cid];return list(dict.fromkeys(c['depends_on']+([c['baseline_case_id']] if c['baseline_case_id'] else [])))
def update_frontier():
 changed=True
 while changed:
  changed=False
  for cid,state in S['cases'].items():
   if state['status'] not in ['WAITING_DEPENDENCY','READY']:continue
   bad=[d for d in deps(cid) if bound_result(d) in ['FAIL','UNMEASURED','BLOCKED_DEPENDENCY','BLOCKED_START_LIMIT']]
   if bad:state.update(status='BLOCKED_DEPENDENCY',blocking_parents=bad);changed=True
   elif all(bound_result(d)=='PASS' for d in deps(cid)):state.update(status='READY')
 return [cid for cid,state in S['cases'].items() if state['status']=='READY']
def load_plot(raw,layout_path=None):
 plots=read_raw_mmap(str(raw));assert len(plots)==1;V=plots[0]
 if 'time' in V:
  old=V['time'];new=np.ascontiguousarray(old)
  assert np.array_equal(old.view(np.uint64),new.view(np.uint64));V['time']=new
  if layout_path:save(layout_path,{'old_stride':old.strides[0],'new_stride':new.strides[0],'bit_patterns_identical':True,'interpolation':False,'points':len(new)})
 return V
def execute(cid):
 contract=M['cases'][cid];run=Path(contract['directory']);p=read(run/'plan.json')
 assert S['global_start_count']<65 and S['actual_new_solver_starts']<30
 assert all(bound_result(d)=='PASS' for d in deps(cid))
 assert sha(run/'plan.json')==contract['plan_sha256'] and sha(p['deck'])==contract['deck_sha256']
 raw=run/(cid+'.raw');assert not raw.exists()
 with (run/'one-shot-reservation.json').open('x') as f:json.dump({'case_id':cid,'reserved_at':now(),'parents':{d:bound_result(d) for d in deps(cid)},'max_starts':1,'effective_wall_cap_s':None,'next_global_index_if_launched':S['global_start_count']+1},f,indent=2)
 e={'case_id':cid,'phase':'formal','command':[M['backend']['ngspice']['path'],'-n','-b',p['deck']],
 'actual_solver_launches':0,'automatic_retries':0,'original_case_timeout_s':contract['original_timeout_s'],'effective_wall_cap_s':None,
 'global_starts_before':S['global_start_count'],'global_starts_after':S['global_start_count'],'returncode':None,'spawn_error':None,
 'timed_out':False,'solver_wall_s':0.0,'started_at':None,'solver_process_reaped':False}
 S['active_case']=cid;S['cases'][cid].update(status='RUNNING',stage='SOLVER');publish()
 proc=None;t0=time.monotonic()
 try:
  env=os.environ.copy();env['SPICE_SCRIPTS']=M['spice_scripts']
  with (run/'ngspice.log').open('wb') as log:
   try:proc=subprocess.Popen(e['command'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   except OSError as exc:e['spawn_error']=repr(exc)
   if proc is not None:
    S['actual_new_solver_starts']+=1;S['global_start_count']+=1
    e.update(actual_solver_launches=1,global_starts_after=S['global_start_count'],started_at=now(),pid=proc.pid)
    append({'rec':'start','case_id':cid,'t':e['started_at'],'pid':proc.pid,'global_start_index':S['global_start_count']})
    save(run/'execution.json',e);publish()
    e['returncode']=proc.wait()  # No deadline under this batch's explicit user waiver.
    e['solver_wall_s']=time.monotonic()-t0
 finally:
  if proc is not None and proc.poll() is None:
   os.killpg(proc.pid,signal.SIGKILL);proc.wait();e['returncode']=proc.returncode;e['solver_wall_s']=time.monotonic()-t0
  e.update(ended_at=now(),solver_process_reaped=proc is not None and proc.poll() is not None)
  save(run/'execution.json',e)
 S['solver_wall_s']+=e['solver_wall_s'];S['cases'][cid]['stage']='ORIGINAL_OFFLINE_JUDGE';publish()
 comp={'analysis':p['case']['analysis'],'raw_exists':raw.exists(),'actual_end_s':None,'expected_end_s':p['case']['x_stop']}
 V=None;raw_sha=None;parse_error=None
 if raw.exists():
  raw_sha=sha(raw)
  try:
   V=load_plot(raw,run/'time-layout.json')
   comp.update(raw_sha256=raw_sha,raw_bytes=raw.stat().st_size,variables=len(V),points=len(next(iter(V.values()))))
   if 'time' in V:comp['actual_end_s']=float(V['time'][-1])
  except Exception as exc:parse_error=repr(exc)
 log=(run/'ngspice.log').read_text(errors='replace')
 comp['expected_solver_banner_seen']='Using SPARSE 1.3 as Direct Linear Solver' in log
 if e['spawn_error']:failure=e['spawn_error']
 elif parse_error:failure='raw_parse_error '+parse_error
 else:
  fn=types.FunctionType(ORIGINAL_COMPLETION.__code__,{**ORIGINAL_COMPLETION.__globals__,'read_raw':lambda _: [V] if V is not None else []},ORIGINAL_COMPLETION.__name__,ORIGINAL_COMPLETION.__defaults__,ORIGINAL_COMPLETION.__closure__)
  failure=fn(Coordinator.__new__(Coordinator),e['returncode'],log,str(raw),p['case'],p['required_vectors'])
 comp['completion_failure']=failure;save(run/'completion.json',comp)
 append({'rec':'end','case_id':cid,'status':failure or 'complete','wall_s':e['solver_wall_s'],'global_start_count':S['global_start_count']})
 tj=time.monotonic();base=None
 if failure:out={'result':'UNMEASURED','why':failure}
 else:
  try:
   bid=contract['baseline_case_id']
   if bid:
    assert S['cases'][bid]['status']=='PASS'
    bb=read(Path(M['cases'][bid]['directory'])/'verdict-binding.json')
    assert bb['scientific']=='PASS';base=load_plot(Path(bb['raw_path']))
   out=judge(p['case'],V,base,p['physical_ledger_plan'],ammeters=p['ammeters'],mos_nodes=p['mos_nodes'])
  except Exception as exc:out={'result':'UNMEASURED','why':repr(exc),'traceback':traceback.format_exc()}
 judge_wall=time.monotonic()-tj
 save(run/'judge-output.json',out)
 binding={'case_id':cid,'scientific':out['result'],'complete_analysis':failure is None,'complete_transient':p['case']['analysis']!='op' and failure is None,
 'actual_end_s':comp['actual_end_s'],'raw_sha256':raw_sha,'raw_path':str(raw) if raw.exists() else None,'deck_sha256':p['deck_sha256'],
 'judge_output_sha256':sha(run/'judge-output.json'),'global_start_count':S['global_start_count'],'judge_wall_s':judge_wall,'original_scientific_judge_used_once':True}
 save(run/'verdict-binding.json',binding);append({'rec':'verdict','t':now(),**binding})
 assert out['result'] in ['PASS','FAIL','UNMEASURED']
 S['offline_judge_wall_s']+=judge_wall
 S['cases'][cid].update(status=out['result'],stage='FINISHED',solver_wall_s=e['solver_wall_s'],completion_failure=failure,actual_end_s=comp['actual_end_s'],binding_path=str(run/'verdict-binding.json'))
 S['active_case']=None;publish()
 print(json.dumps({'case_id':cid,'scientific':out['result'],'solver_wall_s':e['solver_wall_s'],'actual_end_s':comp['actual_end_s'],'global_starts':S['global_start_count']},ensure_ascii=False),flush=True)
 del V,base;gc.collect()
publish()
try:
 while True:
  ready=update_frontier();publish()
  if not ready:break
  if S['global_start_count']>=65:
   for cid in ready:S['cases'][cid].update(status='BLOCKED_START_LIMIT')
   update_frontier();break
  priority={cid:i for i,cid in enumerate(M['priority'])}
  cid=min(ready,key=lambda x:(priority.get(x,len(priority)),list(M['cases']).index(x)))
  execute(cid)
 S['status']='PASS' if all(v['status']=='PASS' for v in S['cases'].values()) else 'PARTIAL'
 S['ended_at']=now();S['remaining_global_start_slots']=65-S['global_start_count']
 S['counts']={k:sum(v['status']==k for v in S['cases'].values()) for k in sorted({v['status'] for v in S['cases'].values()})}
 S['original_records_unchanged']=all(sha(p)==want for p,want in M['protected_original_files_sha256'].items())
 assert S['original_records_unchanged']
 publish();save(ROOT/'CONTINUATION_FINISHED.json',S)
 print(json.dumps({k:v for k,v in S.items() if k!='cases'},ensure_ascii=False,indent=2),flush=True)
except BaseException as exc:
 S.update(status='EXECUTOR_STOPPED_NO_RETRY',executor_error=repr(exc),executor_traceback=traceback.format_exc(),ended_at=now());publish()
 save(ROOT/'EXECUTOR_STOPPED.json',S);raise
