"""Build the fixed Linux backend offline. Never runs a circuit analysis or grants permission."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from zipfile import ZipFile

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--work',required=True,help='new writable directory, or existing checkpoint with --resume')
ap.add_argument('--resume',action='store_true')
args=ap.parse_args()
if sys.platform!='linux' or platform.machine() not in ('x86_64','amd64'):
    raise SystemExit('This helper requires Linux x86-64. Nothing was built or executed.')
KIT=Path(__file__).resolve().parent
WORK=Path(args.work).expanduser().resolve()
if WORK==Path('/') or WORK==Path.home() or WORK==KIT:
    raise SystemExit('Choose a dedicated work directory.')
STATE=WORK/'BACKEND_PREPARATION_STATE.json'
meta=json.loads((KIT/'FIXED_ASSETS.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
if STATE.exists():
    if not args.resume:raise SystemExit('Checkpoint exists; use --resume, never erase or restart its ledger.')
    state=json.loads(STATE.read_text())
    if state.get('asset_identity')!=meta['asset_identity']:raise SystemExit('Checkpoint belongs to other assets.')
elif WORK.exists() and any(WORK.iterdir()):
    raise SystemExit('Work directory is not empty and has no recognized checkpoint; not overwriting it.')
else:
    WORK.mkdir(parents=True,exist_ok=True)
    state={'asset_identity':meta['asset_identity'],'completed':[],'circuit_analyses_started':0}
def save():
    STATE.write_text(json.dumps(state,indent=2),encoding='utf-8')
save()
logs=WORK/'logs';logs.mkdir(exist_ok=True)
def run(label,command,cwd,timeout):
    if label in state['completed']:return
    state.update(status='RUNNING',current_step=label,command=command);save()
    with (logs/(label+'.log')).open('wb') as f:
        p=subprocess.Popen(command,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL)
                p.wait()
            raise RuntimeError(f'{label}: timed out, process group stopped; read {logs/(label+".log")}')
    if p.returncode:raise RuntimeError(f'{label}: exit {p.returncode}; read {logs/(label+".log")}')
    state['completed'].append(label);save()
try:
    for rel,expected in meta['files'].items():
        if sha(KIT/rel)!=expected:raise RuntimeError('Asset hash mismatch: '+rel)
    if 'project_root' in state:
        project=Path(state['project_root'])
        if (project/'prereg/LAUNCH_PERMISSION.json').exists() or (project/'results/q1_ledger.jsonl').exists():
            raise RuntimeError('Launch permission or Q1 ledger exists: do not rebuild or overwrite this round.')
    for name in ('gcc','g++','make','ld'):
        if shutil.which(name) is None:raise RuntimeError('Missing compiler dependency: '+name)
    prefix=WORK/'native';(prefix/'bin').mkdir(parents=True,exist_ok=True)
    ov=prefix/'bin/openvaf'
    if not ov.exists():
        with gzip.open(KIT/'openvaf-dwarning-1.0.0-linux.gz','rb') as src,ov.open('wb') as dst:
            shutil.copyfileobj(src,dst)
        ov.chmod(0o755)
    if sha(ov)!=meta['openvaf_binary_sha256']:raise RuntimeError('OpenVAF decompressed binary mismatch')
    sources=WORK/'sources';sources.mkdir(exist_ok=True)
    if 'unpack_sources' not in state['completed']:
        with tarfile.open(KIT/'ngspice-47.tar.gz','r:gz') as z:
            for m in z.getmembers():
                p=PurePosixPath(m.name)
                if p.is_absolute() or '..' in p.parts:raise RuntimeError('Unsafe tar path')
            z.extractall(sources,filter='data')
        state['completed'].append('unpack_sources');save()
    execution=WORK/'execution';execution.mkdir(exist_ok=True)
    if 'unpack_project' not in state['completed']:
        with ZipFile(KIT/'thermal_g3_q1r_runpack_9d042b00.zip') as z:
            for n in z.namelist():
                p=PurePosixPath(n)
                if p.is_absolute() or '..' in p.parts:raise RuntimeError('Unsafe zip path')
            z.extractall(execution)
        found=list(execution.glob('**/thermal_g3_q1/tools/register_backend.py'))
        if len(found)!=1:raise RuntimeError('Cannot identify project directory')
        state['project_root']=str(found[0].parent.parent)
        state['completed'].append('unpack_project');save()
    project=Path(state['project_root'])
    ngsrc=sources/'ngspice-47'
    # Keep the default KLU and OSDI interfaces. GUI, readline and FFTW are not used by these cases.
    # Release tarball includes generated configure/parser files and bundled KLU; do not autoreconf.
    run('ngspice_configure',[str(ngsrc/'configure'),'--prefix='+str(prefix),'--with-x=no',
        '--with-readline=no','--with-fftw3=no','--enable-osdi','--enable-klu'],ngsrc,180)
    run('ngspice_make',['make','-j2'],ngsrc,1200)
    run('ngspice_install',['make','install'],ngsrc,300)
    ng=prefix/'bin/ngspice'
    run('openvaf_version',[str(ov),'--version'],WORK,30)
    run('ngspice_version',[str(ng),'-v'],WORK,30)
    ov_text=(logs/'openvaf_version.log').read_text(errors='replace')
    ng_text=(logs/'ngspice_version.log').read_text(errors='replace')
    if not re.search(r'\b1\.0\.0\b',ov_text):raise RuntimeError('Actual OpenVAF version differs; do not forge registration')
    if not re.search(r'ngspice[\s-]+47\b',ng_text,re.I):raise RuntimeError('Actual ngspice version differs')
    models=prefix/'models';models.mkdir(exist_ok=True)
    osdi=models/'ekv26_linux.osdi'
    run('ekv_compile',[str(ov),'-D__NGSPICE__','ekv26.va','-o',str(osdi)],project/'backend/ekv_src',180)
    if not osdi.is_file() or osdi.stat().st_size==0:raise RuntimeError('OSDI output missing')
    report={'status':'BUILT_REAL_BACKEND_FILES_NOT_CIRCUIT_QUALIFICATION','platform':platform.platform(),
        'ngspice':{'path':str(ng),'sha256':sha(ng),'version_output':ng_text},
        'openvaf':{'path':str(ov),'sha256':sha(ov),'version_output':ov_text},
        'osdi':{'path':str(osdi),'sha256':sha(osdi),'define':'__NGSPICE__'},
        'model_sources':{p.name:sha(p) for p in (project/'backend/ekv_src').iterdir() if p.is_file()},
        'project_root':str(project),'logs':str(logs),'circuit_analyses_started':0,
        'launch_permission_written':False,'source_project_modified':False}
    (WORK/'REAL_BACKEND_FILES.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    commands=[['python3','-B','tools/register_backend.py','--platform','linux-x64','--ngspice',str(ng),
        '--osdi',str(osdi),'--openvaf',str(ov),'--ngspice-version','ngspice-47','--openvaf-version','OpenVAF 1.0.0'],
        ['python3','-B','tools/static_check.py'],['python3','-B','tools/selfcheck_all.py'],
        ['python3','-B','tools/write_freeze.py']]
    followup='cd '+shlex.quote(str(project))+'\n'+'\n'.join(shlex.join(c) for c in commands)+'\n'
    (WORK/'NEXT_HOST_COMMANDS.txt').write_text(followup,encoding='utf-8')
    state.update(status='BACKEND_FILES_BUILT_AWAITING_HOST_CHECKS',current_step=None,
                 report=str(WORK/'REAL_BACKEND_FILES.json'));save()
    print(json.dumps(report,indent=2))
    print('Next: inspect NEXT_HOST_COMMANDS.txt; register/check/freeze on this host. No launch permission was granted.')
except Exception as e:
    state.update(status='STOPPED_AT_PREPARATION_ERROR',error=type(e).__name__+': '+str(e));save()
    print(json.dumps(state,indent=2),file=sys.stderr)
    raise SystemExit(1)
