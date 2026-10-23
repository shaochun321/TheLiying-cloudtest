from pathlib import Path
import json,os,subprocess,time,hashlib,sys
from datetime import datetime,timezone
J=json.loads(Path('/workspace/repair-current.json').read_text());P=Path(J['root']);D=P/'runs/C0_ORIGINAL_50MS'
def save(p,x):
 p=Path(p);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(x,indent=2)+'\n');q.replace(p)
p=json.loads((D/'plan.json').read_text());assert hashlib.sha256(Path(p['deck']).read_bytes()).hexdigest()==p['deck_sha256']
with (D/'one-shot-reservation.json').open('x') as f:json.dump({'max_starts':1,'global_before':39,'effective_wall_cap_s':None},f)
e={'actual_solver_launches':0,'global_before':39,'global_after':39,'effective_wall_cap_s':None,'original_reference_wall_cap_s':300,'retry_count':0,'started_at':datetime.now(timezone.utc).isoformat()}
env=os.environ.copy();env['SPICE_SCRIPTS']='/workspace/thermal-g3-env/spice-scripts';t=time.monotonic()
with (D/'ngspice.log').open('wb') as log:
 proc=subprocess.Popen(['/workspace/thermal-g3-env/host/native/bin/ngspice','-n','-b',p['deck']],cwd=D,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 e.update(actual_solver_launches=1,global_after=40,pid=proc.pid);save(D/'execution.json',e)
 with (P/'repair-ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'start','case':'C0_ORIGINAL_50MS',**e})+'\n');f.flush();os.fsync(f.fileno())
 state=json.loads(Path('/workspace/thermal-g3-latest-state.json').read_text());state.update(source_batch=str(P),global_start_count=40,unused_start_slots=25,matrix_batch_status='REPAIR_DIAGNOSTIC_RUNNING',all_new_solver_processes_reaped=False,pushed=False);save('/workspace/thermal-g3-latest-state.json',state)
 e['returncode']=proc.wait();e['solver_wall_s']=time.monotonic()-t;e['solver_process_reaped']=True;e['ended_at']=datetime.now(timezone.utc).isoformat();save(D/'execution.json',e)
sys.path.insert(0,J['source']);import numpy as np
from solver_adapter.read_raw_mmap import read_raw_mmap
raw=Path(p['raw']);V=read_raw_mmap(raw)[0] if raw.exists() else {};missing=[n for n in p['required_vectors'] if n not in V]
end=float(V['time'][-1]) if 'time' in V else None
with raw.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
c={'engineering_result':'PASS' if e['returncode']==0 and end is not None and abs(end-.05)<1e-9 and not missing and all(np.all(np.isfinite(x)) for x in V.values()) else 'UNMEASURED','actual_end_s':end,'raw_sha256':h,'raw_bytes':raw.stat().st_size,'variables':len(V),'points':len(V.get('time',[])),'missing_vectors':missing,'qualification_claimed':False}
save(D/'completion.json',c)
state.update(matrix_batch_status='REPAIR_OFFLINE_DESIGN',all_new_solver_processes_reaped=True,new_batch_solver_wall_s=e['solver_wall_s']);save('/workspace/thermal-g3-latest-state.json',state)
with (P/'repair-ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'end','case':'C0_ORIGINAL_50MS',**e,**c})+'\n')
print(json.dumps({**e,**c}),flush=True)
