"""Export finished continuation evidence only; never start or retry any case."""
from pathlib import Path
import gzip,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'delivery'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
S=read(ROOT/'CONTINUATION_FINISHED.json');M=read(ROOT/'CONTINUATION_MANIFEST.json')
assert S['active_case'] is None and S['original_records_unchanged']
OUT.mkdir(exist_ok=False)
sources=[p for p in ROOT.iterdir() if p.is_file() and not p.name.startswith(('.', 'AUTO_')) and p.name!='auto-finalizer.log']
for name in ['c05_ekv26_typ.lib','Q1_MOTHER_PROTOCOL-binding.json','Q1_MOTHER_HALFSTEP-binding.json']:
 p=ROOT/'inputs'/name
 if p.exists():sources.append(p)
for name in ['remaining_formal_execution_proposal.json','fixed_order_reconstruction.json','根因复算结论与正式验证续行方案.md','云端续行短指令.txt']:
 p=ROOT/'inputs/user-package'/name
 if p.exists():sources.append(p)
for cid,state in S['cases'].items():
 if state['status'] in ['PASS','FAIL','UNMEASURED']:
  sources.extend(p for p in (ROOT/'runs'/cid).rglob('*') if p.is_file())
raw_delivery=[]
for src in sorted(sources):
 rel=src.relative_to(ROOT);target=OUT/rel;target.parent.mkdir(parents=True,exist_ok=True)
 if src.suffix=='.raw' and src.stat().st_size>96*1024*1024:
  expected=read(src.parent/'completion.json')['raw_sha256'];temp=ROOT/('.'+src.name+'.delivery.gz')
  with src.open('rb') as inp,temp.open('wb') as compressed:
   with gzip.GzipFile(filename='',mode='wb',fileobj=compressed,compresslevel=6,mtime=0) as stream:shutil.copyfileobj(inp,stream,1024*1024)
  h=hashlib.sha256();n=0
  with gzip.open(temp,'rb') as stream:
   for b in iter(lambda:stream.read(1024*1024),b''):h.update(b);n+=len(b)
  assert h.hexdigest()==expected and n==src.stat().st_size
  parts=[]
  with temp.open('rb') as stream:
   index=1
   for b in iter(lambda:stream.read(48*1024*1024),b''):
    p=target.with_name(target.name+'.gz.part'+str(index).zfill(3));p.write_bytes(b)
    parts.append({'path':str(p.relative_to(OUT)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()});index+=1
  raw_delivery.append({'original_path':str(rel),'original_bytes':n,'original_sha256':expected,'encoding':'gzip, split into ordered binary chunks','compressed_bytes':temp.stat().st_size,'compressed_sha256':sha(temp),'parts':parts,'lossless_decompression_verified':True});temp.unlink()
 else:
  shutil.copy2(src,target);assert sha(src)==sha(target)
  if src.suffix=='.raw':raw_delivery.append({'original_path':str(rel),'original_bytes':src.stat().st_size,'original_sha256':sha(src),'encoding':'none','delivery_path':str(rel)})
(OUT/'RAW_DELIVERY.json').write_text(json.dumps(raw_delivery,indent=2)+'\n')
if raw_delivery:shutil.copy2('/workspace/thermal-g3-qualification/sparse-62p5us-qualification-2026-10-22-eca7cea1/restore_raw.py',OUT/'restore_raw.py')
summary=[]
for cid,state in S['cases'].items():
 row={'case_id':cid,**state}
 if state['status'] in ['PASS','FAIL','UNMEASURED']:
  score=read(ROOT/'runs'/cid/'judge-output.json');row['failed_top_level_gates']={k:v for k,v in score.get('gates',{}).items() if isinstance(v,dict) and v.get('result') in ['FAIL','UNMEASURED']}
 summary.append(row)
(OUT/'CASE_SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
lines=['# 独立分支续行结果','',f"批次：{ROOT.name}；状态：{S['status']}。本批实际新增启动 {S['actual_new_solver_starts']} 次，累计 {S['global_start_count']}/65。",'',
 '按用户“执行，暂时解除时间限制”执行本批临时墙钟豁免；原单项、阶段和全局时限保留为历史参照，没有声称原成本门通过。启动次数、每项一次、原依赖及原科学门均保留。旧 G0_W FAIL、STOPPED、账本未改写。','',
 f"本批实际求解墙钟合计 {S['solver_wall_s']:.6f} 秒；离线评分 {S['offline_judge_wall_s']:.6f} 秒。历史全局精确墙钟仍未知，不按零补齐。",'',
 '| 项目 | 原评分/状态 | 求解耗时（秒） | RAW 终点（秒） |','|---|---|---:|---:|']
for row in summary:
 end=row.get('actual_end_s');lines.append(f"| {row['case_id']} | {row['status']} | {row.get('solver_wall_s','—')} | {'不适用/未运行' if end is None else end} |")
lines+=['','各失败门及阻塞父项见 CASE_SUMMARY.json；原完整评分见各 runs/ 目录。供给的固定 BDF2 重构只作外部证据引用，未在本批重算或用于改判。','',
 'RAW_DELIVERY.json 绑定新增 RAW 的原件 SHA256 和无损分片；小 RAW 直接保存。运行 python3 restore_raw.py 可恢复并校验。没有重打包旧波形，也没有新增诊断或资格运行。',
 '本批有限矩阵调度已结束，不自动进入根因排查、精度调整或重跑。没有宣称原 31 项全覆盖或全部通过。']
(OUT/'README.md').write_text('\n'.join(lines)+'\n')
files=sorted(p for p in OUT.rglob('*') if p.is_file());assert all(p.stat().st_size<100*1024*1024 for p in files)
(OUT/'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(OUT))+'\n' for p in files))
print(json.dumps({'delivery':str(OUT),'files':len(files)+1,'bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),'status':S['status'],'global_starts':S['global_start_count'],'raw_delivery':raw_delivery},ensure_ascii=False,indent=2))
