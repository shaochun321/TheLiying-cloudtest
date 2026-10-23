from pathlib import Path
import json,hashlib,shutil,gzip,io,subprocess,datetime
J=json.loads(Path('/workspace/repair-v2-current.json').read_text());P=Path(J['root']);S=Path(J['source']);OLD=Path(J['prior_error_batch'])
def read(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert (P/'REPAIR_FINISHED.json').exists(),'Cannot export an unfinished batch as delivered.'
status=read(P/'REPAIR_FINISHED.json');assert status['active_case'] is None
manifest=read(P/'candidate_manifest.json') if (P/'candidate_manifest.json').exists() else None
design=read(P/'CANDIDATE_DESIGN.json') if (P/'CANDIDATE_DESIGN.json').exists() else None
obs=read(P/'STARTUP_CAUSAL_OBSERVATION.json') if (P/'STARTUP_CAUSAL_OBSERVATION.json').exists() else None
rows=[]
for cid,v in status['cases'].items():
 d=P/'runs'/cid;e=read(d/'execution.json') if (d/'execution.json').exists() else None;c=read(d/'completion.json') if (d/'completion.json').exists() else None;b=read(d/'verdict-binding.json') if (d/'verdict-binding.json').exists() else None
 rows.append({'case_id':cid,'status':v,'actual_solver_starts':e.get('actual_solver_starts',0) if e else 0,'solver_wall_s':e.get('solver_wall_s',0) if e else None,'returncode':e.get('returncode') if e else None,'actual_end_s':c.get('actual_end_s') if c else None,'raw_sha256':c.get('raw_sha256') if c else None,'raw_bytes':c.get('raw_bytes',0) if c else 0,'original_judge_result':b.get('original_judge_result') if b else None,'engineering_result':b.get('engineering_result') if b else None,'evidence_directory':'runs/'+cid if d.exists() else None})
save(P/'TEST_MATRIX_RESULT.json',{'status':status['status'],'global_starts_before':40,'global_starts_after':status['global_start_count'],'actual_new_starts':status['new_starts'],'global_cap':65,'max_allowed_this_batch':9,'solver_wall_s':status['solver_wall_s'],'exact_global_historical_wall_s':None,'effective_wall_limit_s':None,'stop_case':status.get('stop_case'),'stop_reason':status.get('stop_reason'),'candidate_qualification':status.get('candidate_scientific_verdict','NOT_GRANTED'),'cases':rows})
causes={'original_error_retained':{'commit':'62a6b07e106e46d4bdb3652f63f34c728b46afd8','start_index':40,'result':'INVALID_TERMINATED','scientific_result':'UNMEASURED','not_deleted_or_refunded':True},'corrected_diagnostic':rows[0],'startup':{'evidence':'STARTUP_CAUSAL_OBSERVATION.json','facts':[],'interpretation':None},'reference':{'prior_evidence':'offline/original-dc-load.json','no_old_raw_download_or_rehash':True,'missing_old_mos_currents_remain_unmeasured':True,'candidate_design':'CANDIDATE_DESIGN.json','candidate_actual_evidence':'runs/DC_3/engineering-output.json' if (P/'runs/DC_3/engineering-output.json').exists() else None}}
if obs:
 causes['startup']['facts']=[r for r in obs['cores'] if r['core'] in ['gw1_e1_','gw1_col_','thw12f_','sgw12f_','cdw12f_']]
 causes['startup']['interpretation']='At the old absolute crossing threshold, measured POR hold is high, POR ok is near zero, and vm<h in every observed core. Comparator o1 nevertheless drives the unchanged inverter chain into rail-tracking q with qb low, causing actual recovery/activity-state charging. Earliest different-stage crossing times within roughly 25ps cannot establish serial causality; common power-up transient is directly measured.'
 causes['startup']['remaining_uncertainty']='Sub-rail/low-voltage internal device-current decomposition was not measured by the original diagnostic. Newly added clamp terminal currents are measured in candidate smoke only if reached.'
save(P/'ROOT_CAUSE_TABLE.json',causes)
checks={}
for f,h in read(Path(J['previous_batch'])/'CONTINUATION_MANIFEST.json')['protected_original_files_sha256'].items():checks[f]=sha(f)==h
assert all(checks.values());save(P/'OLD_RECORDS_UNCHANGED.json',{'protected_old_stopped_batch_records':checks,'scope':'Six small protected record files only; no repeat environment, repository, RAW or history audit.'})
brief={'status':status['status'],'global_starts':status['global_start_count'],'new_starts':status['new_starts'],'new_solver_wall_s':status['solver_wall_s'],'candidate_qualification':status.get('candidate_scientific_verdict','NOT_GRANTED'),'stop_case':status.get('stop_case'),'results':[{k:r[k] for k in ['case_id','status','actual_solver_starts','solver_wall_s','actual_end_s','original_judge_result','engineering_result']} for r in rows],'old_records_unchanged':True,'no_automatic_followup':True}
save(P/'RESULTS_BRIEF.json',brief)
passed=[r['case_id'] for r in rows[1:] if r['status']=='PASS'];notrun=[r['case_id'] for r in rows if r['actual_solver_starts']==0]
text=f'''# 执行器纠错与整改续接结果：{status['status']}

纠正补测严格使用 `tran 0.001 0.05 0 0.000125`，无 uic、无初态覆盖、无额外分析。实际生成网表通过执行器正反例门后，仅启动一次。完成结果见逐项表；旧错误启动仍保留并扣账。本批新增 {status['new_starts']} 次，累计 {status['global_start_count']}/65，耗时 {status['solver_wall_s']:.6f} 秒；墙钟限制仅本批按用户指示解除，未知历史耗时不补零。

纠正后的内部观测确认：约 10.214 ms 时 POR 实际保持有效，膜电位均低于阈值，但比较器首级使 q 随轨升高、qb 偏低，恢复和活动电容受到误充电。不同核心交越几乎同时，不能把微小时间差当作逐级因果链。此前缺少的 POR/内部节点证据现已保存；原绝对阈值和早期事件没有删除。

唯一候选在每个 N-RC 的比较器 o1 加一个原模型 NMOS（4 μm/1 μm，gate=por_hold，source/bulk=0），不改 q/qb 反相链、反馈或放电连接；vrest 分压由 2k/1k 改为 1k/500Ω，比例不变。设计纳入 25% 负载包络、约 10mV 额外供电压降、功耗和 3.33ms 参考时间尺度。正式评分只接收原用例固定视图；新增 por_hold 不改变来源账锚点。

已通过的候选项目：{', '.join(passed) or '无'}。停止项目：{status.get('stop_case') or '无'}。尚未启动：{', '.join(notrun) or '无'}。候选资格状态：{status.get('candidate_scientific_verdict','NOT_GRANTED')}。原评分、工程门、真实终点及 RAW 散列逐项保留；诊断短测不抵扣完整资格，旧资格不继承。首个验收失败即停，没有调整参数、重试或扩大矩阵。旧 STOPPED、FAIL 和账本保持原样。本轮结束，不自动进入下一轮。
'''
(P/'REPAIR_SUMMARY.md').write_text(text,encoding='utf-8')
dest=P/'delivery';dest.mkdir()
allowedroot=['PACKAGE_CHECK.json','AUTHORIZATION.json','EXECUTOR_PREFLIGHT.json','STARTUP_CAUSAL_OBSERVATION.json','ROOT_CAUSE_TABLE.json','CANDIDATE_DESIGN.json','candidate_manifest.json','CANDIDATE_FROZEN.json','candidate.diff','SMOKE_ENGINEERING_GATES.json','SMOKE_MEASUREMENT_INVENTORY.json','TEST_MATRIX_RESULT.json','RESULTS_BRIEF.json','OLD_RECORDS_UNCHANGED.json','REPAIR_SUMMARY.md','REPAIR_FINISHED.json','CURRENT_STATUS.json','repair-ledger.jsonl','candidate-execution-once.json']
for n in allowedroot:
 if (P/n).exists():shutil.copy2(P/n,dest/n)
for folder in ['inputs','offline']:
 shutil.copytree(P/folder,dest/folder,ignore=shutil.ignore_patterns('original-chain-startup.json','original-dc-load.json','vrest-branch-inventory.json'))
# Deliver only new changed physical source and infrastructure scripts, not duplicate source history.
(dest/'candidate-source/netlists').mkdir(parents=True)
for n in ['neuron_nrc.py','params.py']:shutil.copy2(P/'software/netlists'/n,dest/'candidate-source/netlists'/n)
(dest/'executor').mkdir()
for n in ['prepare_repair_v2.py','preflight_repair_v2.py','run_repair_v2_diagnostic.py','analyze_repair_v2_startup.py','build_repair_v2_candidate.py','freeze_repair_v2_candidate.py','run_repair_v2_candidate.py','export_repair_v2.py']:
 shutil.copy2(Path('/workspace')/n,dest/'executor'/n)
delivery_index=[]
for d in sorted((P/'runs').iterdir()):
 target=dest/'runs'/d.name;target.mkdir(parents=True)
 for f in d.iterdir():
  if f.is_file() and f.suffix!='.raw':shutil.copy2(f,target/f.name)
 raw=d/(d.name+'.raw')
 if not raw.exists():
  save(target/'RAW_DELIVERY.json',{'raw_available':False,'reason':'Case not started or native did not create RAW.','sha256':None});continue
 comp=read(d/'completion.json');expected=comp['raw_sha256'];assert expected
 if raw.stat().st_size<40*1024*1024:
  shutil.copy2(raw,target/raw.name);record={'raw_available':True,'format':'original-binary-raw','path':raw.name,'raw_sha256':expected,'raw_bytes':raw.stat().st_size,'actual_end_s':comp.get('actual_end_s')}
 else:
  chunks=[];chunklimit=40*1024*1024
  class Chunks(io.RawIOBase):
   def __init__(self):self.file=None;self.size=0
   def writable(self):return True
   def write(self,b):
    total=len(b);pos=0
    while pos<len(b):
     if self.file is None or self.size==chunklimit:
      if self.file:self.file.close()
      name=raw.name+'.gz.part'+str(len(chunks)+1).zfill(3);chunks.append(name);self.file=(target/name).open('wb');self.size=0
     n=min(len(b)-pos,chunklimit-self.size);self.file.write(b[pos:pos+n]);self.size+=n;pos+=n
    return total
   def finish(self):
    if self.file:self.file.close()
  out=Chunks()
  with gzip.GzipFile(filename='',mode='wb',fileobj=out,mtime=0,compresslevel=6) as gz,raw.open('rb') as source:
   shutil.copyfileobj(source,gz,1024*1024)
  out.finish()
  class Cat(io.RawIOBase):
   def __init__(self,names):self.names=iter(names);self.file=None
   def readable(self):return True
   def readinto(self,b):
    while True:
     if self.file is None:
      name=next(self.names,None)
      if name is None:return 0
      self.file=(target/name).open('rb')
     n=self.file.readinto(b)
     if n:return n
     self.file.close();self.file=None
  h=hashlib.sha256();total=0
  with gzip.GzipFile(fileobj=io.BufferedReader(Cat(chunks)),mode='rb') as gz:
   while True:
    b=gz.read(1024*1024)
    if not b:break
    h.update(b);total+=len(b)
  assert h.hexdigest()==expected and total==raw.stat().st_size
  record={'raw_available':True,'format':'single-gzip-stream-lossless-split','chunks':chunks,'raw_sha256':expected,'raw_bytes':total,'actual_end_s':comp.get('actual_end_s'),'decompression_identity_verified':True,'restore_command':'cat '+raw.name+'.gz.part* | gzip -dc > '+raw.name,'compressed_bytes':sum((target/n).stat().st_size for n in chunks)}
 save(target/'RAW_DELIVERY.json',record);delivery_index.append({'case_id':d.name,**record})
save(dest/'EVIDENCE_INDEX.json',delivery_index)
(dest/'README.md').write_text('''# v2 执行器纠错及单候选整改证据

先读 REPAIR_SUMMARY.md、RESULTS_BRIEF.json、TEST_MATRIX_RESULT.json；预检见 EXECUTOR_PREFLIGHT.json，冻结与最小差异见 candidate_manifest.json、candidate.diff。所有正式科学模块保持原文件；追加诊断向量与原评分输入视图分离，来源锚点政策已冻结。

旧错误启动记录仍在父提交 62a6b07e106e46d4bdb3652f63f34c728b46afd8，旧完整运行证据在 708e1033c5cb43e6f917f2ac156b041a8f2d1541。旧完整 RAW 未重复下载、散列、评分或打包。

每个 runs/<id>/RAW_DELIVERY.json 指明原 RAW、散列、真实终点及恢复方法。分片是一条 gzip 流，须按编号拼接后解压；完整解压内容已与运行时 RAW SHA256 核对。没有启动的项目没有 RAW，不记 PASS。实际命令引用云端绝对路径；移植时仅替换模型卡、原 OSDI 和输出文件路径，不能改变分析/电路/刺激/容差。

使用 GitHub 本分支 Code → Download ZIP 或 git clone 后取得整个目录，再在目录内执行 `sha256sum -c SHA256SUMS`。单个小报告可在 GitHub 文件页点击 Raw/Download raw file。
''',encoding='utf-8')
files=sorted(f for f in dest.rglob('*') if f.is_file());(dest/'SHA256SUMS').write_text(''.join(sha(f)+'  '+str(f.relative_to(dest))+'\n' for f in files),encoding='utf-8')
ck=subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=dest,capture_output=True,text=True);assert ck.returncode==0
save(P/'EXPORT_READY.json',{'directory':str(dest),'files':len(files)+1,'bytes':sum(f.stat().st_size for f in dest.rglob('*') if f.is_file()),'status':'LOCAL_PACKET_NOT_PUSHED','all_packet_checksums_verified':True,'new_raws_losslessly_verified':True})
print(json.dumps({'status':status['status'],'directory':str(dest),'files':len(files)+1,'bytes':sum(f.stat().st_size for f in dest.rglob('*') if f.is_file())}))
