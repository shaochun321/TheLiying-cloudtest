from pathlib import Path
import json,sys,numpy as np
J=json.loads(Path('/workspace/repair-v2-current.json').read_text());P=Path(J['root']);D=P/'runs/C0_CORRECTED_50MS';c=json.loads((D/'completion.json').read_text());assert c['result']=='PASS'
sys.path.insert(0,J['source']);from solver_adapter.read_raw_mmap import read_raw_mmap
from observers.observers_q1r import edges
from runtime.decks import case_assets
V=read_raw_mmap(D/'C0_CORRECTED_50MS.raw')[0];t=np.ascontiguousarray(V['time']);V['time']=t
A=case_assets('CHAIN_12_W_F');prefix=sorted(e[0][1:-3] for e in A['netlist'].elements if e[1]=='M' and e[0].endswith('km4'))
old=json.loads((P/'offline/original-chain-startup.json').read_text());thr=old['events'][0]['absolute_threshold_V']
at=lambda n,x:float(np.interp(x,t,V['v('+n+')']))
rows=[]
for p in prefix:
 up,dn=edges(t,V['v('+p+'q)'],thr);x=float(up[0]) if len(up) else .010213751922758292
 nodes=['vdd','vrest','vthe','vthr','porc','porx','por_hold','por_ok',p+'vm',p+'h',p+'ko1',p+'q',p+'qb',p+'rec']
 vv={n:at(n,x) for n in nodes}
 ref='vthe' if p.startswith('g') else 'vthr'
 cur={n:float(np.interp(x,t,a)) for n,a in V.items() if n.startswith('i(') and (p+'porm' in n or p+'porh' in n)}
 rows.append({'core':p,'first_q_up_s':float(up[0]) if len(up) else None,'first_q_down_s':float(dn[0]) if len(dn) else None,'sample_time_s':x,'sample_V':vv,'q_to_vdd':vv[p+'q']/vv['vdd'],'vm_minus_h_V':vv[p+'vm']-vv[p+'h'],'por_membrane_switch_vgs_V':vv['por_hold']-vv['vrest'],'por_threshold_switch_vgs_V':vv['por_hold']-vv[ref],'available_por_terminal_currents_A':cur,'missing_por_current':'UNMEASURED' if not cur else None,'q_max_V':float(np.max(V['v('+p+'q)']))})
samples=[]
for x in [.001,.005,.01,.010213751922758292,.012,.02,.05]:
 samples.append({'time_s':x,'nodes_V':{n:at(n,x) for n in ['vdd','vrest','vthe','vthr','porc','porx','por_hold','por_ok','gw1_e1_ko1','gw1_e1_q','gw1_e1_qb','gw1_col_ko1','gw1_col_q','thw12f_ko1','thw12f_q','hw1','hw2']}})
state=[]
for n,y in V.items():
 if not n.startswith('v(') or not (n.endswith(('_rec)','op_at)','_bt)','_h1)','_hs)','_hc)')) or n in ['v(hw1)','v(hw2)','v(load_pos)','v(load_neg)']):continue
 state.append({'node':n,'initial_V':float(y[0]),'maximum_0_50ms_V':float(np.max(y)),'end_50ms_V':float(y[-1]),'charge_if_history_c2_C_F':.47e-6 if n in ['v(hw1)','v(hw2)'] or n.endswith(('_hs)','_hc)')) else None})
out={'result':'OBSERVATION_COMPLETE','diagnostic_raw_sha256':c['raw_sha256'],'points':len(t),'variables':len(V),'old_absolute_threshold_V':thr,'core_count':len(prefix),'cores':rows,'time_samples':samples,'state_responses':state,'no_raw_identity_rehash':True,'qualification_claimed':False,'diagnostic_por_vectors_not_formal_scoring_view':True}
(P/'STARTUP_CAUSAL_OBSERVATION.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'core_count':len(prefix),'firing_core_count':sum(x['first_q_up_s'] is not None for x in rows),'core_samples':[r for r in rows if r['core'] in ['gw1_e1_','gw1_col_','thw12f_','sgw12f_','cdw12f_']],'control_samples':samples[2:5],'state_examples':state[:5]},ensure_ascii=False))
