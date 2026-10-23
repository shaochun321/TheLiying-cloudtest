from pathlib import Path
import json,hashlib,difflib,sys,shutil,re,subprocess
J=json.loads(Path('/workspace/repair-v2-current.json').read_text());P=Path(J['root']);S=Path(J['source']);C=P/'software'
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
obs=json.loads((P/'STARTUP_CAUSAL_OBSERVATION.json').read_text());assert obs['result']=='OBSERVATION_COMPLETE'
assert all(r['sample_V']['por_hold']>.99*r['sample_V']['vdd'] and r['sample_V']['por_ok']<1e-4 and r['vm_minus_h_V']<0 for r in obs['cores'])
assert not (P/'candidate_manifest.json').exists()
f=C/'netlists/neuron_nrc.py';before=f.read_text();needle='    # Output inverters: o1 -> qb -> q (v1.1 §4.2 minimal chain)'
assert before.count(needle)==1
after=before.replace(needle,'    # v2 repair: physical POR hold clamps comparator o1 LOW before both output inverters.\n    # vm/h, regenerative qb feedback and q-controlled real discharge stay wired as before.\n    # After physical POR release the clamp is off; no external timer or behavioral source.\n    nl.M(kp + "porclamp", kp + "o1", "por_hold", "0", "0", "nch", 4e-6, 1e-6)\n'+needle)
f.write_text(after)
g=C/'netlists/params.py';pb=g.read_text();pa=pb.replace('"VREST_RT": (2e3, "DERIVED", "vrest = VDD/3 = 1.0 V @3 V (plan rest ~1.0 V): Rt 2k / Rb 1k")','"VREST_RT": (1e3, "DERIVED", "v2 single candidate: alpha=1/3, Rth=333.333 ohm; 25% load envelope from three old DC points; see candidate design")').replace('"VREST_RB": (1e3, "DERIVED", "see VREST_RT")','"VREST_RB": (500.0, "DERIVED", "v2: retain 1/3 divider ratio, see VREST_RT")')
assert pa!=pb and pa.count('"VREST_RT": (1e3')==1 and pa.count('"VREST_RB": (500.0')==1;g.write_text(pa)
delta=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original/netlists/neuron_nrc.py',tofile='candidate/netlists/neuron_nrc.py'))+''.join(difflib.unified_diff(pb.splitlines(True),pa.splitlines(True),fromfile='original/netlists/params.py',tofile='candidate/netlists/params.py'))
(P/'candidate.diff').write_text(delta)
# Dependency for the original no-solver suite, copied read-only input; no old ledger changed.
v1=P/'thermal_g3_v1/results';v1.mkdir(parents=True);shutil.copy2(S.parent/'thermal_g3_v1/results/analysis_ledger.jsonl',v1/'analysis_ledger.jsonl')
dc=json.loads((P/'offline/original-dc-load.json').read_text());imax=max(abs(x['inferred_net_load_A']) for x in dc)*1.25;vmin=(min(x['actual_internal_vdd_V'] for x in dc)-.020)/3;eps=.0095
assert (1000/3)*imax <= eps*vmin
design={'rt_ohm':1000.,'rb_ohm':500.,'alpha':1/3,'rth_ohm':1000/3,'reference_C_F':1e-5,'tau_s':1e-5*1000/3,'old_inferred_max_load_A':imax/1.25,'load_upper_bound_A':imax,'load_margin_fraction':.25,'epsilon_V':eps,'minimum_target_for_bound_V':vmin,'maximum_bound_error_V':imax*1000/3,'maximum_relative_error_bound':imax*1000/3/vmin,'variation_assumption':'Up to 25% change from maximum old inferred load, checked independently at candidate DC; no fitting or adjustment after first solve.','additional_supply_drop_allowance_V':.020,'coupled_prediction':[],'clamp':{'model':'nch original C05 EKV','W_m':4e-6,'L_m':1e-6,'drain':'<core>ko1','gate':'por_hold','source':'0','bulk':'0','high_supply_Ron_estimate_ohm':1/(169e-6*4*(1.4824-.61)),'assumptions':'Long-channel linear-region order-of-magnitude estimate only; exact low-rail, contention and release require C2 measured currents. Tail bias approximately <=(3.2-0.61)/1e6=2.59uA per core at high rail.','full124core_contention_power_upper_order_W':124*3.2*2.59e-6,'gate_oxide_added_F_estimate':124*3.4e-3*4e-6*1e-6,'pulse_termination':'Unchanged vm/h comparator polarity, qb->h positive feedback and q->NMOS/Rdis discharge. Clamp overrides o1 only while actual por_hold is high. No gate inserted into feedback.','q_and_qb_consumers':'Original q/qb inverter chain and all consumer wiring retained. A forced-low o1 makes q low and qb high, disabling PMOS-controlled recovery/activity/history charge switches.'}}
for x in dc:
 vd=x['actual_internal_vdd_V'];newvd=vd*(1+10/3000)/(1+10/1500);il=x['inferred_net_load_A']
 design['coupled_prediction'].append({'case':x['case'],'old_internal_vdd_V':vd,'new_internal_vdd_const_other_load_prediction_V':newvd,'incremental_supply_current_A':(vd-newvd)/10,'additional_internal_drop_V':vd-newvd,'old_unloaded_divider_power_W':vd*vd/3000,'new_unloaded_divider_power_W':newvd*newvd/1500,'loaded_vrest_constant_IL_prediction_V':newvd/3-(1000/3)*il,'disclaimer':'Estimated; candidate DC measures true load and other references/bias/model domain.'})
save(P/'CANDIDATE_DESIGN.json',design)
sys.path.insert(0,str(C));from runtime import decks
from netlists.ledger_plan import ledger_nodes,ledger_terminals,plan_from_netlist,save_vectors
registry={x['case_id']:x for x in decks.registry()['cases']}
steps=['DC_3','CHAIN_STARTUP_0_3S','Q1_MOTHER_PROTOCOL','Q1_MOTHER_HALFSTEP','CHAIN_12_W_F','G0_W','DC_2P7','DC_3P2'];plans={}
for cid in steps:
 parent='CHAIN_12_W_F' if cid=='CHAIN_STARTUP_0_3S' else cid;A=decks.case_assets(parent);orig=A['case'];c=json.loads(json.dumps(orig))
 c['max_step_s']=None if c['analysis']=='op' else (.0000625 if cid=='Q1_MOTHER_HALFSTEP' else .000125)
 if c['analysis']!='op':
  bits=c['analysis'].split();assert bits[0]=='tran';bits[-1]=str(c['max_step_s'])
  if cid=='CHAIN_STARTUP_0_3S':bits[2]='3';c['x_stop']=3.
  c['analysis']=' '.join(bits)
 # Original judge view is fixed BEFORE adding diagnostic/probe vectors. Includes all original required/ledger vectors.
 original_view=list(A['save']);nodes=ledger_nodes(orig);terminals=ledger_terminals(orig)
 if orig['analysis']=='op':nodes=['vrest']
 if cid=='CHAIN_STARTUP_0_3S':terminals=terminals+[(r'n.*kporclamp',tag) for tag in 'dgsb']
 nl,meta=decks.netlist_for(orig,nodes,terminals)
 plan=plan_from_netlist(nl,nodes) if nodes or nl.probes else {'nodes':[],'terms':{},'probes':{}}
 sv=list(original_view)
 if orig['analysis']=='op' or cid=='CHAIN_STARTUP_0_3S':sv+=['v('+n+')' for n in sorted(nl.domain) if nl.domain[n]=='elec']
 sv+=save_vectors(plan)
 sv=list(dict.fromkeys(sv));mos={e[0]:e[3]['nodes'] for e in nl.elements if e[1]=='M'}
 d=P/'runs'/cid;d.mkdir();raw=d/(cid+'.raw');deck=d/(cid+'.cir')
 lines=[f'* THERMAL-G3 v2 one frozen candidate: {cid}',f'.include {P}/inputs/c05_ekv26_typ.lib',nl.text(),'.options sparse method=gear reltol=1e-5 abstol=1e-16','.save '+' '.join(sv),'.control','pre_osdi /workspace/thermal-g3-env/host/native/models/ekv26_linux.osdi','set filetype=binary',c['analysis'],'write '+str(raw),'quit','.endc','.end','']
 deck.write_text('\n'.join(lines))
 out={'case':c,'logical_test_id':cid,'original_registered_case':orig,'deck':str(deck),'raw':str(raw),'deck_sha256':sha(deck),'required_vectors':sv,'original_judge_vectors':original_view,'source_anchor_policy':'por_hold release' if 'v(por_hold)' in original_view else 'record start','diagnostic_only_added_vectors':sorted(set(sv)-set(original_view)),'physical_ledger_plan':plan,'ammeters':list(dict.fromkeys(t[1] for t in nl.terms)),'mos_nodes':mos,'command':['/workspace/thermal-g3-env/host/native/bin/ngspice','-n','-b',str(deck)],'cwd':str(d),'qualification_claimed':False,'new_clamp_instances':sum(e[0].endswith('kporclamp') for e in nl.elements),'baseline_case_id':'Q1_MOTHER_PROTOCOL' if cid=='Q1_MOTHER_HALFSTEP' else None}
 save(d/'plan.json',out);plans[cid]={'directory':str(d),'plan_sha256':sha(d/'plan.json'),'deck_sha256':out['deck_sha256'],'source_anchor_policy':out['source_anchor_policy'],'new_clamp_instances':out['new_clamp_instances']}
# Freeze engineering smoke gates now, before first candidate solve. No widening after observed outcomes.
smoke={'actual_stop_s':3.,'must_have_por_release':True,'por_release_threshold':'median(measured vdd)/2','no_original_absolute_threshold_q_up_events':True,'all_28_core_outputs_checked':True,'state_voltage_limit_V':.01*1.1884394856804668,'state_limit_basis':'1% of original minimum valid history level (1.1884394856804668V); engineering quiet-state ceiling, does not replace any original science gate.','state_nodes':'Every NRC rec; every occurrence/activity trace capacitor and every actual history capacitor. Voltage and C*dV charge reported with real branch current identities.','ports_no_original_threshold_up_events':True,'rails_max_abs_deviation_from_vmid_after_rail_ramp_V':.01*1.1884394856804668,'new_clamp_current_and_power_measured':True,'all_mos_domain_coverage_required':True,'formal_judge_inputs':'Unchanged original view; no added por_hold if absent originally.'}
save(P/'SMOKE_ENGINEERING_GATES.json',smoke)
save(P/'candidate_manifest_DRAFT.json',{'status':'DESIGNED_WAITING_NO_SOLVER_REGRESSIONS','candidate_id':'one-POR-o1-clamp-and-half-Rth','source_evidence_commit':'62a6b07e106e46d4bdb3652f63f34c728b46afd8','parent_full_evidence_commit':'708e1033c5cb43e6f917f2ac156b041a8f2d1541','source_software':str(S),'old_qualification_not_inherited':True,'physical_changed_files':['netlists/neuron_nrc.py','netlists/params.py'],'physical_changes':['One original-model NMOS 4um/1um per NRC, o1 to ground, gate common por_hold.','VREST_RT 2000->1000ohm, VREST_RB 1000->500ohm; ratio remains 1/3.'],'candidate_steps':steps,'cases':plans,'no_scanning':True,'max_new_native_starts_this_batch':9,'global_starts_before_batch':40,'default_wall_reference_total_s':36600,'effective_wall_limit_s':None,'reference_design':'CANDIDATE_DESIGN.json','smoke_gates':'SMOKE_ENGINEERING_GATES.json','diff':'candidate.diff'})
print(json.dumps({'root':str(P),'candidate_steps':steps,'clamp_counts':{k:x['new_clamp_instances'] for k,x in plans.items()},'reference_relative_bound':design['maximum_relative_error_bound'],'candidate_solves_started':0}))
