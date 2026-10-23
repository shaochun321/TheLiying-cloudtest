from pathlib import Path
import hashlib,json,sys,uuid,shutil,re
import numpy as np
S=Path('/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea/software/thermal_g3_q1')
R=Path('/workspace/thermal-g3-formal/independent-continuation-2026-10-23-d2e498c3')
P=Path('/workspace/thermal-g3-repair')/('startup-vrest-2026-10-23-'+uuid.uuid4().hex[:8])
P.mkdir(parents=True);(P/'offline').mkdir();(P/'inputs').mkdir()
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
save('/workspace/repair-current.json',{'root':str(P),'source':str(S),'previous_batch':str(R)})
for d in Path('/workspace/attachments').iterdir():
 for f in d.iterdir():
  if f.name in ['给云端agent的执行说明.txt','THERMAL-G3_启动隔离与参考负载定点整改方案_2026-10-23.md','THERMAL-G3_定点整改方案与执行说明_2026-10-23.zip','THERMAL-G3_定点整改方案与执行说明_2026-10-23.zip.sha256']:
   shutil.copy2(f,P/'inputs'/f.name)
shutil.copytree(S,P/'software',ignore=shutil.ignore_patterns('__pycache__','results'))
save(P/'source-files-sha256.json',{str(f.relative_to(S)):sha(f) for f in S.rglob('*') if f.is_file() and f.suffix=='.py'})
save(P/'AUTHORIZATION.json',{'user_instruction':'执行，暂时接触时间限制','interpretation':'执行，暂时解除时间限制','scope':'One physical candidate and fixed C0-C8 sequence; stop at first candidate scientific/engineering failure. No retries or other formal matrix.','global_starts_before':39,'global_start_cap':65,'max_new_starts':9,'effective_per_run_wall_cap_s':None,'effective_batch_wall_cap_s':None,'reference_plan_total_cap_s':36600,'wall_waiver_scope':'this batch only, explicit current user instruction','exact_global_historical_wall_s':None,'original_qualification_not_inherited':True})
sys.path.insert(0,str(S))
from solver_adapter.read_raw_mmap import read_raw_mmap
from runtime import decks
from observers.observers_q1r import edges
raw=R/'runs/CHAIN_12_W_F/CHAIN_12_W_F.raw'
h=sha(raw);assert h=='824fff1380e0e78c7efd2f52ebd0edede03a04b91b33296cb0a6ed703764bdf8'
V=read_raw_mmap(raw)[0];t=np.ascontiguousarray(V['time']);V['time']=t
thr=float(np.median(V['v(vdd)']))/2
rows=[]
for n in V:
 if not n.startswith('v('):continue
 up,dn=edges(t,V[n],thr);u=up[up<10.6];d=dn[dn<10.6]
 if n.endswith(('_q)','_qb)','_aq)','_p)')) or n in ['v(hw1)','v(hw2)','v(load_pos)','v(load_neg)','v(cd w12f_hs)']:
  rows.append({'node':n,'first_up_before_stimulus_s':float(u[0]) if len(u) else None,'first_down_before_stimulus_s':float(d[0]) if len(d) else None,'absolute_threshold_V':thr,'voltage_at_10p214ms':float(np.interp(.010213751923,t,V[n])),'ratio_to_vdd_at_10p214ms':float(np.interp(.010213751923,t,V[n])/np.interp(.010213751923,t,V['v(vdd)'])),'maximum_0_50ms_V':float(np.max(V[n][t<=.05])),'voltage_at_50ms':float(np.interp(.05,t,V[n])),'maximum_0_3s_V':float(np.max(V[n][t<=3])),'voltage_at_3s':float(np.interp(3,t,V[n]))})
windows=[]
for lo,hi in [(0,.05),(1.2,2),(3,10.6)]:
 m=(t>=lo)&(t<=hi);windows.append({'window_s':[lo,hi],'points':int(m.sum()),'nodes':{n:{'min_V':float(np.min(V[n][m])),'max_V':float(np.max(V[n][m])),'first_V':float(V[n][m][0]),'last_V':float(V[n][m][-1])} for n in V if n.startswith('v(')}})
missing=[n for n in ['v(por_hold)','v(por_ok)','v(porc)','v(porx)','v(gw1_col_ko1)','v(gw1_col_qb)','v(gw1_col_vm)','v(gw1_col_h)'] if n not in V]
save(P/'offline/original-chain-startup.json',{'raw':str(raw),'raw_sha256_verified_once':h,'points':len(t),'variables':len(V),'actual_end_s':float(t[-1]),'event_definition':'unchanged original absolute threshold = median(measured vdd)/2','missing_critical_vectors':missing,'optional_original_50ms_needed':bool(missing),'events':rows,'windows':windows})
dc=[];inventory=[]
for cid in ['DC_2P7','DC_3','DC_3P2']:
 A=decks.case_assets(cid);U=read_raw_mmap(R/'runs'/cid/(cid+'.raw'))[0]
 val=lambda n:0. if n=='0' else float(U['v('+n+')'][0])
 resistors=[];mos=[];caps=[]
 # DC saves all node voltages, including 0-V probe internal nodes. Recover original external nodes.
 alias={l.split()[2]:l.split()[1] for l in A['netlist'].lines if l.startswith('va_')}
 for l in A['netlist'].lines:
  e=l.split();name=e[0];nodes=[alias.get(n,n) for n in e[1:5 if name.startswith('n') else 3]]
  if 'vrest' not in nodes:continue
  inventory.append({'case':cid,'element':name,'nodes':nodes,'line':l})
  if name.startswith('r'):
   a,b=nodes;current=(val(a)-val(b))/float(e[3]);current_out=current if a=='vrest' else -current
   resistors.append({'element':name,'nodes':nodes,'current_out_of_vrest_A':current_out})
  elif name.startswith('n'):
   for tag,n in zip('dgsb',nodes):
    if n=='vrest':mos.append({'element':name,'terminal':tag,'current_A':None,'status':'UNMEASURED','reason':'No original terminal probe; candidate DC will measure this current.'})
  elif name.startswith('c'):caps.append({'element':name,'steady_state_current_A':0.})
 vd,vr=val('vdd'),val('vrest');iu=(vd-vr)/2000;ib=vr/1000;load=iu-ib
 resistor_load=sum(x['current_out_of_vrest_A'] for x in resistors if x['element'] not in ['rvrestt','rvrestb'])
 dc.append({'case':cid,'actual_internal_vdd_V':vd,'vrest_V':vr,'unloaded_prediction_V':vd/3,'upper_divider_current_A':iu,'lower_divider_current_A':ib,'inferred_net_load_A':load,'independently_recovered_resistor_load_A':resistor_load,'unmeasured_mos_terminal_count':len(mos),'unmeasured_net_mos_load_A_by_difference_only':load-resistor_load,'independent_full_load_A':None,'independent_node_residual_A':None,'independent_load_status':'UNMEASURED','tautological_loaded_prediction_not_claimed_independent':True,'resistor_branches':resistors,'mos_terminals':mos,'capacitors':caps})
save(P/'offline/original-dc-load.json',dc);save(P/'offline/vrest-branch-inventory.json',inventory)
save(P/'ROOT_CAUSE_TABLE.json',{'phase':'A_OFFLINE','startup':{'fact':'Original pre-stimulus threshold events preserved, no event exclusion. POR and comparator not saved in old CHAIN RAW.','evidence':'offline/original-chain-startup.json','missing':missing,'next':'One original 0-50ms measured diagnostic; no qualification.'},'reference':{'fact':'Reference error and resistor contributions recovered from three existing DC records. MOS terminal currents missing; total load derived from divider is an inference.','evidence':'offline/original-dc-load.json','next':'Measure every vrest terminal in the first candidate DC; no separate old full DC.'}})
print(json.dumps({'root':str(P),'chain_raw_hash':h,'critical_missing':missing,'early_events':rows[:4],'dc_summary':[{k:x[k] for k in ['case','actual_internal_vdd_V','vrest_V','inferred_net_load_A','independently_recovered_resistor_load_A','unmeasured_mos_terminal_count']} for x in dc]},ensure_ascii=False))
