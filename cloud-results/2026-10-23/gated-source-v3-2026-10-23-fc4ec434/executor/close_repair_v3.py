from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,shutil,subprocess,os
J=json.loads(Path('/workspace/repair-v3-current.json').read_text());P=Path(J['root']);V2=Path(J['parent_batch'])
def read(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
S=read(P/'REPAIR_FINISHED.json');assert S['status']=='REPAIR_FAILED' and S['global_start_count']==44 and S['new_starts']==1
d=P/'runs/T0_GATED_SOURCE_BENCH';e=read(d/'execution.json');comp=read(d/'completion.json');eng=read(d/'engineering-output.json');key=read(P/'T0_KEY_NUMBERS.json')
assert e['returncode']==0 and e['solver_process_reaped'] and comp['actual_end_s']==.06 and e['actual_solver_starts']==1
try:os.kill(e['pid'],0)
except ProcessLookupError:pass
else:raise RuntimeError('Native PID unexpectedly remains present.')
rows=[]
for cid,status in S['cases'].items():
 dd=P/'runs'/cid;ee=read(dd/'execution.json') if (dd/'execution.json').exists() else None;cc=read(dd/'completion.json') if (dd/'completion.json').exists() else None
 rows.append({'case_id':cid,'status':status,'actual_starts':ee['actual_solver_starts'] if ee else 0,'actual_analysis':read(dd/'plan.json')['case']['analysis'],'solver_wall_s':ee['solver_wall_s'] if ee else None,'returncode':ee['returncode'] if ee else None,'actual_end_s':cc['actual_end_s'] if cc else None,'raw_sha256':cc['raw_sha256'] if cc else None,'raw_bytes':cc['raw_bytes'] if cc else 0,'scientific_qualification':'NOT_GRANTED','reason':'Reference-disturbance engineering FAIL' if ee else 'Blocked by first failure; no analysis started.'})
S.update(stop_reason='T0 completes60ms and passes57/57 model domain, but irefp_n/ilimp_n shift0.88237/0.90100V, exceeding frozen20mV reference-disturbance engineering limit; eight successor tests blocked.',remaining_global_start_slots=21,all_new_solver_processes_reaped=True)
save(P/'REPAIR_FINISHED.json',S);save(P/'CURRENT_STATUS.json',S)
save(P/'TEST_MATRIX_RESULT.json',{'result':'REPAIR_FAILED','global_starts_before':43,'global_starts_after':44,'actual_new_starts':1,'batch_max_new_starts':9,'global_cap':65,'remaining_slots':21,'solver_wall_s':e['solver_wall_s'],'effective_wall_limit_s':None,'waiver_scope':'This now-ended v3 batch only.','historical_exact_global_wall_s':None,'cases':rows,'stop_reason':S['stop_reason'],'automatic_retries':0})
with (P/'repair-ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'batch_end','time':datetime.now(timezone(timedelta(hours=8))).isoformat(),'result':'REPAIR_FAILED','actual_new_starts':1,'global_start_count':44,'actual_solver_wall_s':e['solver_wall_s'],'native_returncode':0,'all_native_processes_reaped':True,'other_tests_started':0})+'\n')
protected={}
for rel in ['candidate_manifest.json','candidate.diff','repair-ledger.jsonl','TEST_MATRIX_RESULT.json','runs/DC_3/verdict-binding.json','runs/CHAIN_STARTUP_0_3S/verdict-binding.json']:
 protected[rel]=sha(V2/rel)==sha(V2/'delivery'/rel)
assert all(protected.values());save(P/'PARENT_RECORDS_UNCHANGED.json',{'parent_commit':'1faf29a6e6b5041032effbae1c5c4f367076ed67','checks':protected,'scope':'Six small directly related v2 records compared with its delivered originals. No historical RAW/environment/repository audit repeated.'})
brief={'result':'REPAIR_FAILED','actual_new_starts':1,'global_start_count':44,'remaining_start_slots':21,'solver_wall_s':e['solver_wall_s'],'actual_end_s':.06,'native_returncode':0,'model_domain':eng['model_domain'],'reference_disturbance':eng['reference_perturbations'],'current_charge_establishment_gates_passed':True,'independent_reference_monitor':eng['independent_reference_monitor'],'blocked_successor_count':8,'candidate_qualification':'NOT_GRANTED','scope':'Frozen9-channel simultaneous standalone T0 bench only; no full DC or full-chain claim.','no_automatic_followup':True}
save(P/'RESULTS_BRIEF.json',brief)
text='''# v3 收口：REPAIR_FAILED（工程验收失败，非执行错误）

唯一候选只替换公共 gated_source()：cp源端固定VDD，以实际PMOS和反相器切换栅偏置；保留and_tree、POR钳位、1kΩ/500Ω参考及原科学观察器。33个静态用例和执行器定点正反例通过。原判据和来源账政策未改，新增观测与正式评分视图分离。

唯一一次T0以3.2V、20ms爬升、原1ms控制边沿和125μs最大步长运行，9个独立输出通道共享真实参考。正常完成至60ms，1353点、349变量，返回码0，耗时2.614622s。57/57 MOS全程在原模型域内；工作电位稳态电流、关断/非期望馈通电荷和边沿后的建立时间均通过冻结工程门。

候选整体仍FAIL：irefp_n、ilimp_n峰值扰动分别为0.882372V和0.901000V，是冻结20mV工程限值的44.1及45.0倍。首个越限样本约25.194ms。实测显示off与bias两PMOS在控制边沿重叠导通，形成VDD→off→cg→bias→公共参考的真实支路，把参考拉近电源；持续导通的独立监测镜像电流由约1.13μA降至接近零。详见 REFERENCE_FAILURE_WINDOWS.json 的首几个窗口、实际栅偏置及端口电流。

这证明该冻结九通道测试台下的公共参考耦合未合格，不能据此宣称原8管问题已在完整电路修好，也不外推单通道或全网结论。T1–T8全部未启动、未记PASS。未改尺寸、未扫描、未重试、未追加另一候选。

本批新增1次，累计44/65，余21次；本批墙钟限制按用户指示解除，次数和失败停线保持。未知历史精确耗时不补零。父候选的冻结、FAIL、账本及既有STOPPED只读，本轮未获新资格，完成交付后结束。
'''
(P/'REPAIR_SUMMARY.md').write_text(text,encoding='utf-8')
zipfile=Path('/workspace/attachments/a6650232-cf49-4027-a98a-b95b24654587/THERMAL-G3_门控电流源整改方案_v3_含原型与离线估计_2026-10-23.zip');checkfile=Path('/workspace/attachments/3d18a637-13d7-4f32-96df-1fbb9a404cd3/THERMAL-G3_门控电流源整改方案_v3_含原型与离线估计_2026-10-23.zip.sha256');assert sha(zipfile)==checkfile.read_text().split()[0]
shutil.copy2(zipfile,P/'inputs'/zipfile.name);shutil.copy2(checkfile,P/'inputs'/checkfile.name);save(P/'PACKAGE_CHECK.json',{'input_zip_sha256':sha(zipfile),'review_record':str(Path(J['review'])/'V3_ATTACHMENT_REVIEW.json'),'integrity_verified':True,'prototype_and_static_estimate_are_not_qualification':True})
D=P/'delivery';D.mkdir()
rootfiles=['AUTHORIZATION.json','PACKAGE_CHECK.json','EXECUTOR_PREFLIGHT.json','candidate_manifest.json','candidate_manifest_DRAFT.json','CANDIDATE_FROZEN.json','candidate.diff','V3_TEST_CONTRACT.json','T0_CHANNELS.json','REFERENCE_FAILURE_WINDOWS.json','T0_KEY_NUMBERS.json','RESULTS_BRIEF.json','TEST_MATRIX_RESULT.json','REPAIR_SUMMARY.md','REPAIR_FINISHED.json','CURRENT_STATUS.json','repair-ledger.jsonl','execution-once.json','PARENT_RECORDS_UNCHANGED.json','SMOKE_ENGINEERING_GATES.json','SMOKE_MEASUREMENT_INVENTORY.json','INHERITED_REFERENCE_DESIGN.json','runner.log']
for n in rootfiles:shutil.copy2(P/n,D/n)
shutil.copytree(P/'inputs',D/'inputs');shutil.copytree(P/'offline',D/'offline',ignore=shutil.ignore_patterns('original-dc-load.json','reference_baseline_summary.json'));shutil.copytree(P/'executor',D/'executor',ignore=shutil.ignore_patterns('__pycache__'))
for n in ['analyze_v3_failure.py','close_repair_v3.py']:shutil.copy2(Path('/workspace')/n,D/'executor'/n)
(D/'candidate-source/netlists').mkdir(parents=True);shutil.copy2(P/'software/netlists/bundle_physical.py',D/'candidate-source/netlists/bundle_physical.py')
index=[]
for dd in sorted((P/'runs').iterdir()):
 target=D/'runs'/dd.name;target.mkdir(parents=True)
 for f in dd.iterdir():
  if f.is_file():shutil.copy2(f,target/f.name)
 raw=dd/(dd.name+'.raw')
 if raw.exists():
  c=read(dd/'completion.json');assert sha(target/raw.name)==c['raw_sha256'];record={'raw_available':True,'format':'original-binary-raw','file':raw.name,'raw_sha256':c['raw_sha256'],'bytes':c['raw_bytes'],'actual_end_s':c['actual_end_s'],'byte_copy_identity_verified':True,'large_waveforms_repacked':False}
 else:record={'raw_available':False,'reason':'Not started due first T0 failure.','raw_sha256':None,'actual_end_s':None}
 save(target/'RAW_DELIVERY.json',record);index.append({'case_id':dd.name,**record})
save(D/'EVIDENCE_INDEX.json',index)
(D/'README.md').write_text('''# v3 唯一候选失败证据

先读 REPAIR_SUMMARY.md、RESULTS_BRIEF.json 和 TEST_MATRIX_RESULT.json。T0正常完成，但公共参考扰动超过冻结工程门，因此首个失败停线。此项是物理候选的工程失败，不是执行器异常；后续八项没有运行。

REFERENCE_FAILURE_WINDOWS.json 给出首几个越限窗口、共同导通的开关偏置和实测支路电流。V3_TEST_CONTRACT.json 和 candidate_manifest.json 在首次启动前已冻结；candidate.diff 仅改变bundle中的gated_source函数。不能以57管模型域通过冒充完整电路或完整资格通过。

本目录只有本批新增RAW、网表、日志及小报告。原二进制RAW约3.79MB，未重新打包旧大波形。每次实际运行的RAW_DELIVERY.json列出终点、散列和复制校验；未运行项标明无RAW。所有源文件、模型和网表中绝对路径为当时云端实际路径，移植时只替换必要资产/输出路径，不能更改物理参数、刺激或数值配置。

父版本证据提交：1faf29a6e6b5041032effbae1c5c4f367076ed67。复现离线继承观察器需要父交付的executor/run_repair_v3前身v2脚本；该依赖的散列已固定，原科学模块仍来自冻结软件包。附带Windows离线估计脚本作为原输入保存，未在云端执行，也不替代实际T0数据。

完整下载可使用本分支Code → Download ZIP，或git clone后切换到本分支；在本目录运行 `sha256sum -c SHA256SUMS` 验证。单个报告可在文件页点击Raw/Download raw file。
''',encoding='utf-8')
# Include the exact pinned offline helper source for self-contained review; it is not a new simulation execution.
shutil.copy2('/workspace/run_repair_v2_candidate.py',D/'executor/inherited_v2_offline_helpers_source.py')
files=sorted(f for f in D.rglob('*') if f.is_file());(D/'SHA256SUMS').write_text(''.join(sha(f)+'  '+str(f.relative_to(D))+'\n' for f in files),encoding='utf-8');r=subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=D,capture_output=True,text=True);assert r.returncode==0
export={'directory':str(D),'files':len(files)+1,'bytes':sum(f.stat().st_size for f in D.rglob('*') if f.is_file()),'status':'LOCAL_PACKET_NOT_PUSHED','all_checksums_verified':True,'new_raw_copy_verified':True,'no_old_large_raw_repack':True};save(P/'EXPORT_READY.json',export)
repo=Path('/workspace/TheLiying-cloudtest');work=Path('/workspace/thermal-g3-delivery')/P.name;rel=Path('cloud-results/2026-10-23')/P.name;branch='repair/'+P.name;base='1faf29a6e6b5041032effbae1c5c4f367076ed67'
subprocess.run(['git','-C',str(repo),'worktree','add','--no-checkout','-b',branch,str(work),base],check=True,capture_output=True);subprocess.run(['git','-C',str(work),'sparse-checkout','set','--no-cone','/'+str(rel)+'/'],check=True,capture_output=True);subprocess.run(['git','-C',str(work),'read-tree','--reset','-u','HEAD'],check=True,capture_output=True);assert subprocess.check_output(['git','-C',str(work),'status','--porcelain'],text=True)==''
target=work/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(D,target);subprocess.run(['git','-C',str(work),'add','--',str(rel)],check=True);names=subprocess.check_output(['git','-C',str(work),'diff','--cached','--name-only','-z']).decode().split('\0');assert all(n.startswith(str(rel)+'/') for n in names if n)
subprocess.run(['git','-C',str(work),'-c','user.name=Codex','-c','user.email=codex@openai.com','commit','-m','Record v3 gate-selector reference-coupling failure and stop'],check=True,capture_output=True);commit=subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD'],text=True).strip()
ready={**export,'status':'LOCAL_COMMIT_NOT_PUSHED','branch':branch,'commit':commit,'worktree':str(work),'repository_path':str(rel),'base_commit':base};save(P/'PUSH_READY.json',ready)
g=read('/workspace/thermal-g3-latest-state.json');g.update(source_batch=str(P),source_finished_marker=str(P/'REPAIR_FINISHED.json'),global_start_count=44,unused_start_slots=21,matrix_batch_status='REPAIR_FAILED',all_new_solver_processes_reaped=True,local_evidence_commit=commit,remote_evidence_commit=None,pushed=False,push_status='LOCAL_COMMIT_NOT_PUSHED',temporary_wall_limit_waiver_scope='This now-ended v3 batch only.');save('/workspace/thermal-g3-latest-state.json',g)
print(json.dumps(ready))
