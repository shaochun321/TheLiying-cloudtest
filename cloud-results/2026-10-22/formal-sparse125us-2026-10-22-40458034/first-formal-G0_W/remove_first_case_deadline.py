"""Preserve the existing solver PID, suspend its old timeout waiter only.
Resume that waiter after ngspice has exited so it reaps the original child and
continues the original offline judgment. No solver process is created here.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,os,signal,time
ROOT=Path(__file__).resolve().parent
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def stat(pid):
 try:
  fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
  return {'state':fields[0],'ppid':int(fields[1]),'start_ticks':int(fields[19])}
 except FileNotFoundError:return None
def save(name,v):
 p=ROOT/name;temp=p.with_suffix(p.suffix+'.tmp')
 temp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');temp.replace(p)
e=json.loads((ROOT/'runs/G0_W/execution.json').read_text())
assert e['actual_solver_launches']==1 and not e.get('solver_process_reaped')
child=e['pid'];cs=stat(child);assert cs is not None
parent=cs['ppid'];ps=stat(parent)
assert b'run_first_formal.py' in Path(f'/proc/{parent}/cmdline').read_bytes()
assert ps and ps['state'] not in ['T','t','Z']
auth={'user_instruction':'暂不设置时间上限','effective_at':now(),'case_id':'G0_W','existing_solver_pid':child,'existing_solver_start_ticks':cs['start_ticks'],'new_solver_starts':0,'global_start_count':35,'single_case_wall_cap_s':None,'old_single_case_cap_s':2700,'old_watchdog_dispatch_s':2670,'scope':'Existing G0_W run only; no retry and no automatic next case. Original phase/global budgets remain recorded; no exact historical balance is invented.','original_timeout_waiter_pid':parent,'original_timeout_waiter_start_ticks':ps['start_ticks']}
with (ROOT/'G0_W_NO_WALL_LIMIT_AUTHORIZATION.json').open('x') as f:json.dump(auth,f,ensure_ascii=False,indent=2);f.write('\n')
os.kill(parent,signal.SIGSTOP)
for _ in range(100):
 if stat(parent)['state'] in ['T','t']:break
 time.sleep(.01)
assert stat(parent)['state'] in ['T','t']
save('G0_W_TIMEOUT_CONTROL.json',{'state':'OLD_TIMEOUT_WAITER_SUSPENDED','updated_at':now(),'solver_pid':child,'parent_pid':parent,'solver_continues':True,'additional_solver_launches':0})
print(json.dumps({'old_timeout_waiter_suspended':parent,'same_solver_pid_continues':child,'wall_limit_removed':True}),flush=True)
while True:
 current=stat(child)
 if current is None or current['start_ticks']!=cs['start_ticks'] or current['state']=='Z':break
 time.sleep(.25)
current_parent=stat(parent)
assert current_parent and current_parent['start_ticks']==ps['start_ticks']
os.kill(parent,signal.SIGCONT)
save('G0_W_TIMEOUT_CONTROL.json',{'state':'SOLVER_EXITED_ORIGINAL_WAITER_RESUMED','updated_at':now(),'solver_pid':child,'parent_pid':parent,'additional_solver_launches':0,'old_deadline_not_enforced':True})
print('Existing solver exited; original waiter resumed for reaping and offline judgment.',flush=True)
