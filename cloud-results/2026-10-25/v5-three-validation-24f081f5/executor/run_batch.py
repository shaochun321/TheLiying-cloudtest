"""One executor, <=3 native starts, exact wall caps, first failure and delivery stop."""
from pathlib import Path
from datetime import datetime, timezone
import fcntl, hashlib, json, os, re, shutil, signal, subprocess, sys, time, traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'frozen/software'
sys.path.insert(0,str(SOURCE))
from solver_adapter.read_raw import read_raw
from observers.judges import judge
from observers.support_q1r import anchor_time
import engineering_v5
IDS=['T0_GATED_SOURCE_BENCH','DC_3','CHAIN_12_W_F']

def save(p,d):
    with p.open('w') as f:json.dump(d,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
def append(d):
    with (ROOT/'batch-ledger.jsonl').open('a') as f:f.write(json.dumps(d,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def report(state):
    save(ROOT/'STATE.json',state)
    save(ROOT.parent/'current-v5-batch.json',{'batch':str(ROOT),'state':state['status'],'conservative_starts':state['conservative_starts'],'cap':84,'original_replay_state_untouched':True})
    print(json.dumps(state,ensure_ascii=False),flush=True)

def completion(run,plan,V,log):
    import numpy as np
    missing=[key for key in plan['required_vectors'] if key not in V]
    problems=[]
    if run['returncode']!=0:problems.append('native returncode '+str(run['returncode']))
    if run['timed_out']:problems.append('wall cap reached')
    if run.get('resource_abort'):problems.append(run['resource_abort'])
    for marker in ['timestep too small','transient analysis aborted','doanalyses:','unknown device','fatal error','error on line','error:']:
        if marker in log.lower():problems.append('native log: '+marker)
    if 'Using SPARSE 1.3 as Direct Linear Solver' not in log:problems.append('SPARSE 1.3 not confirmed by actual log')
    if missing:problems.append('missing required vectors')
    for key,val in V.items():
        if not np.all(np.isfinite(val)):problems.append('nonfinite '+key);break
    end=None
    if plan['analysis']!='op':
        t=V.get('time')
        if t is None or len(t)<2 or not np.all(np.diff(t)>0):problems.append('missing or invalid time axis')
        else:
            end=float(t[-1])
            if end<plan['required_end_s']*(1-1e-9):problems.append('RAW ended early')
            if any(len(val)!=len(t) for val in V.values()):problems.append('inconsistent vector length')
    elif any(len(val)!=1 for val in V.values()):problems.append('op is not exactly one point')
    return {'result':'PASS' if not problems else 'UNMEASURED','problems':problems,'missing':missing,
        'actual_end_s':end,'points':len(next(iter(V.values()))) if V else 0,'variables':len(V)}

def solver(cid,plan,state):
    directory=ROOT/cid;raw=Path(plan['raw'])
    with (directory/'one-start-lock.json').open('x') as f:json.dump({'maximum_launches':1,'count_before':state['conservative_starts'],'registered_deck_sha256':plan['deck_sha256']},f)
    manifest=json.loads((ROOT/'frozen/FROZEN_HASHES.json').read_text())
    for path,digest in manifest.items():assert sha(ROOT/path)==digest,'Frozen input changed: '+path
    assert sha(Path(plan['deck']))==plan['deck_sha256']
    if cid=='CHAIN_12_W_F':assert shutil.disk_usage(ROOT).free>=12_000_000_000,'Insufficient actual free space before chain'
    run={'case_id':cid,'command':plan['command'],'cwd':str(directory),'actual_solver_starts':0,'wall_cap_s':plan['wall_cap_s'],
      'timed_out':False,'automatic_retry':False,'conservative_before':state['conservative_starts']}
    save(directory/'execution.json',run)
    env=os.environ.copy();env['SPICE_SCRIPTS']='/workspace/thermal-g3-env/spice-scripts'
    begin=time.monotonic()
    # The ten-second termination grace is inside the authorized per-case cap.
    wall=min(plan['wall_cap_s'],31200-state['solver_wall_s']);assert wall>10
    with (directory/'ngspice.log').open('xb') as log:
        process=subprocess.Popen(plan['command'],cwd=directory,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        run.update(actual_solver_starts=1,pid=process.pid,started_at_UTC=now(),conservative_after=state['conservative_starts']+1)
        state['conservative_starts']+=1;state['actual_new_starts']+=1;state.update(status='SOLVING',current_case=cid)
        save(directory/'execution.json',run);append({'record':'ACTUAL_START',**run});report(state)
        last=begin
        while process.poll() is None:
            elapsed=time.monotonic()-begin;remaining=wall-10-elapsed
            free=shutil.disk_usage(ROOT).free
            if remaining<=0 or free<1_000_000_000:
                run['timed_out']=remaining<=0
                if free<1_000_000_000:run['resource_abort']='Actual free disk below 1GB'
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=max(.1,min(10,wall-(time.monotonic()-begin))))
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                break
            try:process.wait(timeout=min(15,remaining))
            except subprocess.TimeoutExpired:pass
            if time.monotonic()-last>=60:
                save(ROOT/'HEARTBEAT.json',{'case_id':cid,'elapsed_solver_wall_s':time.monotonic()-begin,'free_disk_bytes':free,'raw_exists':raw.exists(),'conservative_starts':state['conservative_starts']})
                print(json.dumps({'progress':'SOLVING','case_id':cid,'elapsed_s':round(time.monotonic()-begin,1),'cap_s':wall,'starts':state['conservative_starts']}),flush=True);last=time.monotonic()
    run.update(returncode=process.returncode,elapsed_solver_wall_s=time.monotonic()-begin,ended_at_UTC=now(),process_reaped=True)
    state['solver_wall_s']+=run['elapsed_solver_wall_s'];save(directory/'execution.json',run);append({'record':'ACTUAL_END',**run})
    return run

def score(cid,plan,run):
    directory=ROOT/cid;raw=Path(plan['raw']);V=None
    original={'result':'UNMEASURED','why':'No usable RAW'};eng=dict(original);complete=dict(original)
    try:
        if not raw.exists():raise FileNotFoundError('No RAW produced')
        binding={'bytes':raw.stat().st_size,'sha256':sha(raw)};save(directory/'RAW_IDENTITY.json',binding)
        V=read_raw(str(raw))[-1]  # one read; contiguous vectors reused by all observers
        complete=completion(run,plan,V,(directory/'ngspice.log').read_text(errors='replace'))
        complete.update(raw_bytes=binding['bytes'],raw_sha256=binding['sha256'])
        if complete['result']=='PASS':
            if cid=='T0_GATED_SOURCE_BENCH':
                contract=json.loads((ROOT/'frozen/input-package/reference/ORIGINAL_V3_TEST_CONTRACT.json').read_text())
                limits=json.loads((ROOT/'frozen/NMOS_BIAS_LIMITS_REPRODUCED.json').read_text())
                eng=engineering_v5.t0(V,plan,contract,limits)
                original={'result':eng['original_engineering_result'],'scope':'Original complete T0 engineering gates; copied unchanged observer'}
            else:
                science=V if cid=='DC_3' else {key:V[key] for key in plan['science_view_vectors']}
                original=judge(plan['case'],science,plan=plan['physical_ledger_plan'],mos_nodes=plan['mos_nodes'])
                # Score every agreed observer on this one RAW even if an original gate fails.
                eng=engineering_v5.dc(V,plan) if cid=='DC_3' else engineering_v5.chain(V,plan)
                if cid=='CHAIN_12_W_F':
                    actual_anchor=anchor_time(science,science['time'],science['v(cdw12f_vm)'],science['v(vrest)'],0)
                    save(directory/'ACTUAL_SCORING_VIEW.json',{'whitelist':list(science),'por_hold_in_scientific_view':'v(por_hold)' in science,'actual_anchor_s':actual_anchor[0],'actual_anchor_reason':actual_anchor[1],'actual_max_step_s':plan['case']['max_step_s']})
        else:
            original={'result':'UNMEASURED','why':'Incomplete/missing trace; no extrapolation of absent contract windows'};eng=dict(original)
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc(),'solver_restarted':False}
        save(directory/'SCORING_ERROR.json',error);eng={'result':'UNMEASURED','why':str(exc)}
    save(directory/'completion.json',complete);save(directory/'original-score.json',original);save(directory/'engineering-score.json',eng)
    if V is not None:
        if cid=='T0_GATED_SOURCE_BENCH' and eng.get('result')!='PASS':
            times=[eng.get('first_exact_failure_time_s')]
            times=[x for x in times if x is not None];center=min(times) if times else .025
            import numpy as np
            t=V.get('time');window=[]
            if t is not None:
                k=int(np.argmin(np.abs(t-center)))
                for idx in range(max(0,k-2),min(len(t),k+3)):
                    keys=['v(vdd)','v(iref_n)','v(ilim_n)','v(irefp_n)','v(ilimp_n)','i(va_nmonitor_cp_d)','i(va_riref_p)']
                    window.append({'time_s':float(t[idx]),**{key:float(V[key][idx]) for key in keys if key in V}})
            save(directory/'EARLIEST_FAILURE_WINDOW.json',{'first_exact_failure_s':eng.get('first_exact_failure_time_s'),'window_samples':window,'original_window_failures':eng.get('original_window_failures',[]),'facts':'Measured voltages and currents only; switching mechanism remains hypothesis without full causal separation','missing':eng.get('missing',[]),'no_additional_solver_started':True})
        del V
    verdict='UNMEASURED' if 'UNMEASURED' in [complete.get('result'),original.get('result'),eng.get('result')] else ('FAIL' if 'FAIL' in [original.get('result'),eng.get('result')] else 'PASS')
    return {'case_id':cid,'result':verdict,'completion':complete.get('result'),'original':original.get('result'),'engineering':eng.get('result'),'actual_end_s':complete.get('actual_end_s'),'solver_wall_s':run['elapsed_solver_wall_s']}

def main():
    lock=(ROOT/'single-executor.lock').open('x');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert json.loads((ROOT/'frozen/PREFLIGHT.json').read_text())['result']=='PASS'
    state={'status':'AUTHORIZED_READY','actual_new_starts':0,'conservative_starts':54,'global_cap':84,'solver_wall_s':0.,'results':[],'current_case':None,'remaining_not_started':IDS.copy()}
    report(state)
    for cid in IDS:
        assert all(x['result']=='PASS' for x in state['results'])
        plan=json.loads((ROOT/cid/'plan.json').read_text())
        run=solver(cid,plan,state);state.update(status='SCORING',current_case=cid);report(state)
        verdict=score(cid,plan,run);state['results'].append(verdict);state['remaining_not_started'].remove(cid)
        append({'record':'VERDICT','count':state['conservative_starts'],**verdict})
        state['status']='CASE_PASS_DELIVERY_PENDING' if verdict['result']=='PASS' else ('STOPPED_UNMEASURED' if verdict['result']=='UNMEASURED' else 'STOPPED_FAILURE')
        if verdict['result']!='PASS':save(ROOT/'STOPPED.json',{'status':state['status'],'case_id':cid,'verdict':verdict,'not_started':state['remaining_not_started'],'automatic_retry':False})
        report(state)
        from deliver_case import deliver
        try:
            receipt=deliver(cid);state.setdefault('deliveries',[]).append(receipt)
            report(state)
        except Exception as exc:
            save(ROOT/'DELIVERY_ERROR.json',{'error':str(exc),'traceback':traceback.format_exc(),'case_id':cid,'raw_original_preserved':True,'no_later_case_started':True})
            state['status']='STOPPED_DELIVERY_ERROR';report(state);return
        if verdict['result']!='PASS':break
    if len(state['results'])==3 and all(x['result']=='PASS' for x in state['results']):state['status']='BATCH_PASS_SCOPE_LIMITED'
    state['current_case']=None;report(state)
    # Publish the final state and remote-restoration receipt; never starts another solver.
    from deliver_case import finalize
    finalize(state)

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        save(ROOT/'EXECUTOR_ERROR.json',{'error':str(exc),'traceback':traceback.format_exc(),'automatic_retry':False})
        raise
