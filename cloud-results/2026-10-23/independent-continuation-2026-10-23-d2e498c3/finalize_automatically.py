"""Wait for the existing batch, export and commit evidence locally. No solver or push."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,os,shutil,subprocess,sys,time,traceback
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(name,v):
 p=ROOT/name;temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');temp.replace(p)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
with (ROOT/'AUTO_FINALIZER_ONCE.json').open('x') as f:json.dump({'pid':os.getpid(),'started_at':now(),'additional_solver_starts':0,'automatic_push':False},f,indent=2)
try:
 save('AUTO_DELIVERY_STATUS.json',{'status':'WAITING_FOR_EXISTING_BATCH','updated_at':now(),'new_solver_starts':0})
 executor=read(ROOT/'execution-once.json')['pid']
 while not (ROOT/'CONTINUATION_FINISHED.json').exists():
  if (ROOT/'EXECUTOR_STOPPED.json').exists():raise RuntimeError('Existing executor stopped. No simulation retry or speculative continuation.')
  if not Path(f'/proc/{executor}').exists():raise RuntimeError('Existing executor absent without a finished marker. No solver restart.')
  time.sleep(5)
 s=read(ROOT/'CONTINUATION_FINISHED.json');assert s['active_case'] is None and s['original_records_unchanged']
 assert s['global_start_count']<=65
 s['termination_reason']='NO_LEGAL_DEPENDENCY_FRONTIER' if any(v['status'].startswith('BLOCKED') for v in s['cases'].values()) else 'ORIGINAL_REMAINING_MATRIX_FINISHED'
 save('CONTINUATION_FINISHED.json',s);save('CURRENT_STATUS.json',s)
 save('AUTO_DELIVERY_STATUS.json',{'status':'EXPORTING_NEW_EVIDENCE','updated_at':now(),'new_solver_starts':0})
 subprocess.run([sys.executable,'-B',str(ROOT/'export_continuation.py')],check=True)
 info=read(ROOT/'delivery-worktree.json');w=Path(info['worktree']);branch=info['branch']
 def git(*args):return subprocess.check_output(['git','-C',str(w),*args],text=True).strip()
 assert git('rev-parse','HEAD')==info['base_commit'] and git('branch','--show-current')==branch
 assert not git('status','--porcelain')
 rel=Path('cloud-results/2026-10-23')/ROOT.name;target=w/rel;shutil.copytree(ROOT/'delivery',target)
 manifest=(target/'SHA256SUMS').read_text().splitlines()
 for line in manifest:
  expected,name=line.split('  ',1);assert sha(target/name)==expected,name
 subprocess.run(['git','-C',str(w),'add','--',str(rel)],check=True)
 changed=[x for x in git('diff','--cached','--name-only','-z').split('\0') if x];assert changed and all(x.startswith(str(rel)+'/') for x in changed)
 subprocess.run(['git','-C',str(w),'-c','user.name=Codex','-c','user.email=codex@openai.com','commit','-m','Record independent formal continuation results and dependency blocking'],check=True)
 commit=git('rev-parse','HEAD');files=[p for p in target.rglob('*') if p.is_file()]
 result={'status':'LOCAL_EVIDENCE_COMMIT_READY_NOT_PUSHED','updated_at':now(),'commit':commit,'branch':branch,'base_commit':info['base_commit'],
 'repository':'shaochun321/TheLiying-cloudtest','repo_path':str(rel),'worktree':str(w),'files':len(files),'bytes':sum(p.stat().st_size for p in files),
 'scientific_batch_status':s['status'],'case_counts':s['counts'],'new_solver_starts':s['actual_new_solver_starts'],'global_starts':s['global_start_count'],
 'original_records_unchanged':s['original_records_unchanged'],'sha256_manifest_verified_after_copy':True,'pushed':False,'automatic_push':False}
 save('AUTO_DELIVERY_STATUS.json',result);save('PUSH_READY.json',result)
 print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
except BaseException as exc:
 save('AUTO_DELIVERY_STATUS.json',{'status':'FINALIZER_STOPPED_NO_SIMULATION_RETRY','updated_at':now(),'error':repr(exc),'traceback':traceback.format_exc(),'new_solver_starts_by_finalizer':0,'pushed':False})
 raise
