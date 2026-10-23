from pathlib import Path
import json,subprocess,os,time,traceback
J=json.loads(Path('/workspace/repair-v2-current.json').read_text());P=Path(J['root'])
with (P/'pipeline-once.json').open('x') as f:json.dump({'pid':os.getpid(),'wait_for_selfcheck_pid':66661,'no_repeat_native_execution':True},f)
def save(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n')
try:
 while True:
  try:os.kill(66661,0)
  except ProcessLookupError:break
  time.sleep(5)
 test=json.loads((P/'software/results/selfcheck.json').read_text())
 if test['n']!=test['n_pass']:raise RuntimeError('Original no-solver selfcheck failure; no candidate solve permitted.')
 for script,log in [('freeze_repair_v2_candidate.py','freeze.log'),('run_repair_v2_candidate.py','candidate-runner.log'),('export_repair_v2.py','export.log')]:
  with (P/log).open('wb') as f:
   rc=subprocess.run(['python','/workspace/'+script],stdout=f,stderr=subprocess.STDOUT).returncode
  if rc:raise RuntimeError(script+' returned '+str(rc))
 save(P/'PIPELINE_FINISHED.json',{'status':'LOCAL_EXPORT_READY','no_push_claimed':True})
except BaseException as ex:
 save(P/'PIPELINE_ERROR.json',{'error':repr(ex),'traceback':traceback.format_exc(),'no_automatic_retry':True});raise
