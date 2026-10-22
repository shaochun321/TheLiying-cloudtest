"""Package only the new G0_W evidence; no simulation or old RAW access."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import gzip,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'first-formal-delivery'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
assert (ROOT/'FIRST_FORMAL_FINISHED.json').exists()
assert read(ROOT/'G0_W_TIMEOUT_CONTROL.json')['state']=='SOLVER_EXITED_ORIGINAL_WAITER_RESUMED'
e=read(ROOT/'runs/G0_W/execution.json');b=read(ROOT/'runs/G0_W/verdict-binding.json')
c=read(ROOT/'runs/G0_W/completion.json');cost=read(ROOT/'COST_GATE_AFTER_G0_W.json')
assert e['actual_solver_launches']==1 and e['global_starts_after']==35
effective={**e,'initial_wall_cap_s':e['wall_cap_s'],'initial_watchdog_dispatch_s':e['watchdog_dispatch_s'],
 'wall_cap_s':None,'watchdog_dispatch_s':None,'wall_within_cap':None,
 'initial_timeout_control_snapshot_sha256':sha(ROOT/'runs/G0_W/execution.json'),
 'effective_limit_authorization':'G0_W_NO_WALL_LIMIT_AUTHORIZATION.json',
 'initial_execution_json_is_historical_configuration_snapshot':True,
 'old_deadline_waiter_was_suspended_while_same_solver_continued':True}
save(ROOT/'runs/G0_W/execution-effective.json',effective)
status={'updated_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
 'preflight_pushed_commit':'ee029ce94e2e103676b452d4919626a97b248af0',
 'case_id':'G0_W','scientific':b['scientific'],'complete_transient':b['complete_transient'],
 'actual_end_s':b['actual_end_s'],'actual_new_solver_launches':1,'global_starts':35,
 'remaining_unstarted_formal_cases':30,'solver_wall_s':e['solver_wall_s'],
 'single_case_wall_cap_s':None,'timed_out':e['timed_out'],'next_case_started':False,
 'original_remaining_cost_gate':cost['unmodified_original_cost_gate'],
 'no_automatic_retry_or_next_case':True,'main_and_original_deliveries_unchanged':True,
 'preflight_NOT_STARTED_and_PREFLIGHT_STATUS_are_historical_snapshots':True}
save(ROOT/'CURRENT_STATUS.json',status)
OUT.mkdir(exist_ok=False)
names=['FORMAL_MANIFEST.json','FIRST_FORMAL_EXCEPTION_AUTHORIZATION.json','G0_W_NO_WALL_LIMIT_AUTHORIZATION.json',
 'G0_W_TIMEOUT_CONTROL.json','formal-ledger.jsonl','formal-budget-summary.json','FIRST_FORMAL_FINISHED.json',
 'COST_GATE_AFTER_G0_W.json','CURRENT_STATUS.json','STOPPED.json','run_first_formal.py',
 'remove_first_case_deadline.py','recompute_after_first.py','export_first_evidence.py']
sources=[ROOT/n for n in names if (ROOT/n).exists()]
sources+=sorted(p for p in (ROOT/'runs/G0_W').rglob('*') if p.is_file())
raw_delivery=[]
for src in sources:
 rel=src.relative_to(ROOT);target=OUT/rel;target.parent.mkdir(parents=True,exist_ok=True)
 if src.suffix=='.raw' and src.stat().st_size>96*1024*1024:
  expected=c['raw_sha256'];temp=ROOT/'.first-formal.raw.gz'
  with src.open('rb') as inp,temp.open('wb') as compressed:
   with gzip.GzipFile(filename='',mode='wb',fileobj=compressed,compresslevel=6,mtime=0) as out:shutil.copyfileobj(inp,out,1024*1024)
  h=hashlib.sha256();n=0
  with gzip.open(temp,'rb') as stream:
   for block in iter(lambda:stream.read(1024*1024),b''):h.update(block);n+=len(block)
  assert h.hexdigest()==expected and n==src.stat().st_size
  parts=[]
  with temp.open('rb') as stream:
   index=1
   for block in iter(lambda:stream.read(48*1024*1024),b''):
    p=target.with_name(target.name+'.gz.part'+str(index).zfill(3));p.write_bytes(block)
    parts.append({'path':str(p.relative_to(OUT)),'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest()});index+=1
  raw_delivery.append({'original_path':str(rel),'original_bytes':n,'original_sha256':expected,'encoding':'gzip, split into ordered binary chunks','compressed_bytes':temp.stat().st_size,'compressed_sha256':sha(temp),'lossless_decompression_verified':True,'parts':parts})
  temp.unlink()
 else:
  shutil.copy2(src,target);assert sha(src)==sha(target)
  if src.suffix=='.raw':raw_delivery.append({'original_path':str(rel),'original_bytes':src.stat().st_size,'original_sha256':sha(src),'encoding':'none','delivery_path':str(rel)})
save(OUT/'RAW_DELIVERY.json',raw_delivery)
restore=Path('/workspace/thermal-g3-qualification/sparse-62p5us-qualification-2026-10-22-eca7cea1/restore_raw.py')
if raw_delivery:shutil.copy2(restore,OUT/'restore_raw.py')
(OUT/'README.md').write_text(f'''# G0_W 单次正式运行证据\n\n本目录为预检提交之后的新证据，预检目录中的 NOT_STARTED/PREFLIGHT_STATUS 是启动前历史快照。\n\n本次仅启动 G0_W 一次，累计 35/65，其他 30 项未启动。原 2700 秒单项限制在运行中经用户“暂不设置时间上限”撤销；暂停旧超时等待器，原 ngspice PID 连续运行至退出，再恢复等待器进行原离线评分。无重启、调参或模型替换。execution.json 保留初始限制快照，execution-effective.json 记录最终有效限制。\n\n实际求解耗时 {e['solver_wall_s']:.6f} 秒；返回码 {e['returncode']}；RAW 实际终点 {b['actual_end_s']} 秒；原评分 {b['scientific']}。达到终点与科学评分分别记录。\n\n剩余正式项原成本预测为 {cost['remaining_formal_forecast_s']:.3f} 秒；正式阶段剩余 {cost['formal_phase_remaining_s']:.3f} 秒。精确历史总墙钟不全，只报告已知下界及全局剩余的乐观上界。未放宽其他项成本门、阶段或全局预算，未自动进入下一项。旧冻结、STOPPED、账本和 main 均未修改。\n\nRAW_DELIVERY.json 记录本次新增 RAW 的无损交付方式、原始 SHA256 和分片校验。若有分片，在本目录运行 python3 restore_raw.py；SHA256SUMS 覆盖本目录交付文件。\n''')
files=sorted(p for p in OUT.rglob('*') if p.is_file())
assert all(p.stat().st_size<100*1024*1024 for p in files)
(OUT/'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(OUT))+'\n' for p in files))
print(json.dumps({'delivery':str(OUT),'files':len(files)+1,'bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),'scientific':b['scientific'],'raw_delivery':raw_delivery},indent=2))
