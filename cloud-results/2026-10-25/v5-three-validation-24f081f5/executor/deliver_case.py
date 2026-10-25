"""Upload only this independent batch and verify actual remote RAW retrieval."""
from pathlib import Path
import base64, gzip, hashlib, io, json, os, shutil, subprocess
from restore_template import PartStream
ROOT=Path(__file__).resolve().parent.parent
REPO=Path('/workspace/TheLiying-cloudtest')
BRANCH='validation/v5-three-2026-10-25-24f081f5'
PREFIX='cloud-results/2026-10-25/v5-three-validation-24f081f5'
BASE_COMMIT='a856e506d7d799e4228a15e174f5d1913e1b6223'
ENV=os.environ.copy()
for key in list(ENV):
    if key.startswith('GIT_TRACE') or key=='GIT_CURL_VERBOSE':ENV.pop(key)
ENV.update(GIT_TERMINAL_PROMPT='0',GH_PROMPT_DISABLED='1',GH_DEBUG='',GIT_AUTHOR_NAME='Codex',GIT_AUTHOR_EMAIL='codex@openai.com',GIT_COMMITTER_NAME='Codex',GIT_COMMITTER_EMAIL='codex@openai.com')

def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(cmd,env=None,inp=None):
    result=subprocess.run(cmd,env=env or ENV,input=inp,capture_output=True,text=True)
    if result.returncode:
        msg=result.stderr
        for key,value in ENV.items():
            if any(x in key.upper() for x in ['TOKEN','PASSWORD','SECRET']) and len(value)>8:msg=msg.replace(value,'[REDACTED]')
        raise RuntimeError('Command '+str(cmd[:4])+' failed rc='+str(result.returncode)+': '+msg[-3000:])
    return result.stdout.strip()
def git(args,env=None,inp=None):return run(['git','-C',str(REPO),*args],env,inp)

def pack(cid):
    directory=ROOT/cid;raw=directory/(cid+'.raw')
    if not raw.exists():return None
    ident=json.loads((directory/'RAW_IDENTITY.json').read_text());partsdir=directory/'raw-parts';partsdir.mkdir(exist_ok=False)
    record={'name':raw.name,'bytes':ident['bytes'],'sha256':ident['sha256'],'parts':[]}
    digest=hashlib.sha256();total=0;number=0
    with (directory/'compression.log').open('xb') as log:
        proc=subprocess.Popen(['pigz','-n','-p','4','-6','-c',str(raw)],stdout=subprocess.PIPE,stderr=log)
        while True:
            # read() on this buffered pipe fills a part except at EOF, never a large RAW in memory.
            block=proc.stdout.read(40*1024*1024)
            if not block:break
            relative='raw-parts/'+raw.name+'.gz.part'+str(number).zfill(4);p=directory/relative
            p.write_bytes(block);h=hashlib.sha256(block).hexdigest();digest.update(block);total+=len(block)
            record['parts'].append({'path':relative,'bytes':len(block),'sha256':h});number+=1
        proc.stdout.close();rc=proc.wait();assert rc==0,'Compression failed'
    record.update(gzip_bytes=total,gzip_sha256=digest.hexdigest())
    manifest={'files':[record],'compressed_total_bytes':total,'original_raw_unchanged':True,'compression':'Deterministic lossless gzip, <=40MiB parts','solver_starts_added_by_delivery':0}
    save(directory/'RAW_MANIFEST.json',manifest);shutil.copyfile(ROOT/'executor/restore_template.py',directory/'restore_raw.py')
    (directory/'ORIGINAL_SHA256SUMS').write_text(ident['sha256']+'  '+raw.name+'\n')
    (directory/'RAW_DOWNLOAD.md').write_text('下载本独立分支后，在本目录运行：\n\n```sh\npython restore_raw.py --output-dir raw-original\n```\n\n只需 Python 标准库；逐片及恢复原件 SHA256 均核验，不覆盖不同内容文件。原 RAW 本地原件保留。远端复核采用实际 API 下载全部分片并流式还原、核对完整原件身份。\n')
    return manifest

def update_summary():
    state=json.loads((ROOT/'STATE.json').read_text());rows=[]
    for cid in ['T0_GATED_SOURCE_BENCH','DC_3','CHAIN_12_W_F']:
        found=next((x for x in state['results'] if x['case_id']==cid),None)
        rows.append('| '+cid+' | '+(found['result'] if found else 'NOT_STARTED')+' | '+(str(found['solver_wall_s']) if found else '—')+' |')
    text='# v5 三项验证批次\n\n状态：'+state['status']+'；实际新增启动 '+str(state['actual_new_starts'])+'，累计 '+str(state['conservative_starts'])+'/84。\n\n| 用例 | 本批结果 | 实际求解墙钟秒 |\n|---|---|---:|\n'+'\n'.join(rows)+'\n\n原 v4 资格不继承，原 G0_W FAIL 不改判。首败或关键缺测后停线；无重试、调参、扫描或自动矩阵。每项目录含实际计划、命令、完成性、原评分、新工程评分、日志及 RAW 无损分片/恢复脚本。具体缺测与失败看对应 JSON。链路 8 小时为运行上限，不是预计耗时。\n'
    (ROOT/'SUMMARY.md').write_text(text)

def stage_push(label):
    update_summary();delivery=ROOT/'delivery';statefile=delivery/'git-state.json'
    st=json.loads(statefile.read_text()) if statefile.exists() else {'parent':BASE_COMMIT,'pushes':[]}
    stage=delivery/('stage-'+label);target=stage/PREFIX;target.mkdir(parents=True,exist_ok=False)
    hashes={}
    for manifest in ROOT.glob('*/RAW_MANIFEST.json'):
        record=json.loads(manifest.read_text())['files'][0]
        for part in record['parts']:hashes[str(manifest.parent.relative_to(ROOT)/part['path'])]=part['sha256']
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(ROOT)
        if rel.parts[0]=='delivery' or p.suffix=='.raw' or p.name in ['single-executor.lock','runner.log','FROZEN_HASHES.json.tmp']:continue
        dst=target/rel;dst.parent.mkdir(parents=True,exist_ok=True)
        if 'raw-parts' in rel.parts:os.link(p,dst)
        else:shutil.copyfile(p,dst)
    (target/'.gitattributes').write_text('* -text -filter\n*.part* -diff\n')
    paths=sorted(p for p in target.rglob('*') if p.is_file() and p!=target/'SHA256SUMS')
    (target/'SHA256SUMS').write_text(''.join((hashes.get(str(p.relative_to(target))) or sha(p))+'  '+str(p.relative_to(target))+'\n' for p in paths))
    head=git(['rev-parse','HEAD']);status=git(['status','--porcelain']);assert not status
    ix=delivery/('index-'+label);assert not ix.exists();custom=ENV|{'GIT_INDEX_FILE':str(ix),'GIT_WORK_TREE':str(stage)}
    git(['read-tree',st['parent']],custom);git(['add','-f','--',PREFIX],custom)
    tokens=git(['diff','--cached','--name-status','-z',st['parent']],custom).split('\0');assert tokens[-1]=='';tokens=tokens[:-1]
    changes=list(zip(tokens[::2],tokens[1::2]));assert changes and all(a in ['A','M'] and b.startswith(PREFIX+'/') for a,b in changes)
    tree=git(['write-tree'],custom);commit=git(['commit-tree',tree,'-p',st['parent']],inp='Preserve v5 authorized batch '+label+' evidence and exact RAW transport\n')
    old=st['parent'] if st['pushes'] else '0'*40;git(['update-ref','refs/heads/'+BRANCH,commit,old])
    st.update(local_commit=commit,push_in_progress=True);save(statefile,st)
    git(['-c','pack.window=0','-c','pack.compression=0','push','--porcelain','origin',commit+':refs/heads/'+BRANCH])
    remote=git(['ls-remote','--heads','origin','refs/heads/'+BRANCH]).split()[0];assert remote==commit
    assert git(['rev-parse','HEAD'])==head and git(['status','--porcelain'])==status
    st['pushes'].append({'label':label,'commit':commit,'remote_ref_verified':True});st.update(parent=commit,push_in_progress=False);save(statefile,st)
    print(json.dumps({'stage':'REMOTE_PUSH_VERIFIED','label':label,'commit':commit}),flush=True)
    return commit

class RemoteParts:
    def __init__(self,record,tree,cid):
        self.record,self.tree,self.cid=record,tree,cid;self.index=0;self.file=None;self.total_hash=hashlib.sha256();self.total_bytes=0
    def read(self,size=-1):
        result=bytearray()
        while size<0 or len(result)<size:
            if self.file is None:
                if self.index==len(self.record['parts']):break
                part=self.record['parts'][self.index];row=self.tree[PREFIX+'/'+self.cid+'/'+part['path']]
                # Actual independent remote download, no local object or source-file reuse.
                obj=json.loads(run(['gh','api','repos/shaochun321/TheLiying-cloudtest/git/blobs/'+row['sha']]))
                content=base64.b64decode(obj['content']);assert len(content)==part['bytes'] and hashlib.sha256(content).hexdigest()==part['sha256']
                self.file=io.BytesIO(content)
            block=self.file.read(4*1024*1024 if size<0 else size-len(result))
            if block:self.total_hash.update(block);self.total_bytes+=len(block);result.extend(block)
            else:self.file.close();self.file=None;self.index+=1
        return bytes(result)
    def finish(self):
        assert not self.read(1);assert self.total_bytes==self.record['gzip_bytes'] and self.total_hash.hexdigest()==self.record['gzip_sha256']

def verify_remote(cid,commit,manifest):
    tree=json.loads(run(['gh','api','repos/shaochun321/TheLiying-cloudtest/git/trees/'+commit+'?recursive=1']));assert not tree.get('truncated')
    entries={x['path']:x for x in tree['tree'] if x['type']=='blob'}
    # The remote manifest must itself equal the local immutable transport contract.
    row=entries[PREFIX+'/'+cid+'/RAW_MANIFEST.json'];obj=json.loads(run(['gh','api','repos/shaochun321/TheLiying-cloudtest/git/blobs/'+row['sha']]))
    assert json.loads(base64.b64decode(obj['content']))==manifest
    record=manifest['files'][0];stream=RemoteParts(record,entries,cid);digest=hashlib.sha256();count=0
    with gzip.GzipFile(fileobj=stream,mode='rb') as f:
        while True:
            block=f.read(4*1024*1024)
            if not block:break
            digest.update(block);count+=len(block)
    stream.finish();assert count==record['bytes'] and digest.hexdigest()==record['sha256']
    return {'result':'PASS','commit':commit,'branch':BRANCH,'case_id':cid,'method':'Independent GitHub API download of every part + streamed lossless RAW restoration',
      'restored_bytes':count,'restored_sha256':digest.hexdigest(),'all_parts_verified':len(record['parts']),'original_local_RAW_retained':True,'second_restored_disk_copy_created':False}

def deliver(cid):
    manifest=pack(cid);commit=stage_push(cid)
    if manifest:
        receipt=verify_remote(cid,commit,manifest);save(ROOT/cid/'REMOTE_RAW_RESTORATION.json',receipt)
    else:receipt={'result':'NO_RAW_PRODUCED','commit':commit,'branch':BRANCH,'case_id':cid,'small_evidence_uploaded':True}
    print(json.dumps({'stage':'REMOTE_RAW_RESTORATION','case_id':cid,'result':receipt['result']}),flush=True)
    return receipt

def finalize(state):
    commit=stage_push('FINAL')
    receipt={'result':'PASS','branch':BRANCH,'commit':commit,'repository_path':PREFIX,'batch_status':state['status'],'actual_new_starts':state['actual_new_starts'],'conservative_starts':state['conservative_starts'],'all_started_RAWs_remote_verified':all(d['result']=='PASS' for d in state.get('deliveries',[]))}
    save(ROOT/'delivery/FINAL_REMOTE_RECEIPT.json',receipt);print(json.dumps({'stage':'BATCH_FINISHED',**receipt}),flush=True)
