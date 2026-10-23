"""Prepare exactly one v3 candidate and fixed nine-test contract; zero native starts."""
from pathlib import Path
import json,hashlib,shutil,sys,uuid,ast,difflib,re
V2=Path('/workspace/thermal-g3-repair/executor-correction-v2-2026-10-23-b4ddf97a');RV=Path(json.loads(Path('/workspace/v3-review-current.json').read_text())['root']);SOURCE=V2/'software'
P=Path('/workspace/thermal-g3-repair')/('gated-source-v3-2026-10-23-'+uuid.uuid4().hex[:8]);P.mkdir()
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n')
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
state=read('/workspace/thermal-g3-latest-state.json');assert state['global_start_count']==43 and state['all_new_solver_processes_reaped']
save('/workspace/repair-v3-current.json',{'root':str(P),'source':str(SOURCE),'parent_batch':str(V2),'review':str(RV)})
shutil.copytree(RV/'preview-software',P/'software',ignore=shutil.ignore_patterns('__pycache__','results'))
shutil.copytree(RV/'inputs',P/'inputs');shutil.copy2(V2/'inputs/c05_ekv26_typ.lib',P/'inputs/c05_ekv26_typ.lib');shutil.copy2(RV/'gated_source_preview.diff',P/'candidate.diff')
(P/'offline').mkdir();(P/'executor').mkdir();(P/'runs').mkdir()
save(P/'AUTHORIZATION.json',{'user_instruction':'请执行，解除时间限制','scope':'One v3 gated-source candidate; T0-T8 exactly, one native start each, first science/engineering failure stops all remaining tests.','global_starts_before':43,'global_cap':65,'max_new_starts':9,'max_global_after':52,'minimum_slots_left_if_all_started':13,'budget_revision':'v2 max49 -> v3 max52; three additional version-specific validation slots explicitly part of authorized v3 plan.','effective_run_wall_cap_s':None,'effective_batch_wall_cap_s':None,'waiver_scope':'This v3 batch only. Counts, one candidate and first-failure stop remain enforced.','default_reference_batch_wall_s':36600,'exact_global_historical_wall_s':None,'automatic_retries':0,'old_results_and_records_unchanged':True,'old_qualification_inherited':False})
sys.path.insert(0,str(P/'software'))
from netlists.build import Netlist,WELL
from netlists.neuron_nrc import supply_ramp,references
from netlists.bundle_physical import gated_source
from netlists.params import v
from analysis.input_bounds import supply_and_refs
from runtime.decks import case_assets,netlist_for
from netlists.ledger_plan import ledger_nodes,ledger_terminals,plan_from_netlist,save_vectors
cert=read(SOURCE/'analysis/input_bounds.json')['nom'];proto=read(SOURCE/'prereg/protocol_q1r_joint.json');edge=proto['edge_s'];assert edge==.001
R=supply_and_refs(3.2);tol=.10;v_eps=.020;settle=.05*min(x['q_width_min_s'] for x in cert['roles'].values())
charges={role:.01*x['Cm']*x['u_entry_V'] for role,x in cert['roles'].items()}
contract={'kind':'V3_FIXED_CONTRACT_BEFORE_FIRST_SOLVE','T0':{'analysis':'tran 0.001 0.06 0 0.000125','source_setpoint_V':3.2,'supply_ramp_s':.02,'edge_s':edge,'commands_s':{'first_ON_start':.025,'first_ON_end_edge':.026,'OFF_start':.035,'OFF_end_edge':.036,'second_ON_start':.045,'second_ON_end_edge':.046},'steady_ON_windows_s':[[.030,.034],[.050,.058]],'steady_OFF_windows_s':[[.022,.024],[.040,.044]],'OFF_charge_windows_s':[[0.,.025],[.0355,.045]],'OFF_charge_policy':'Original absolute logic midpoint at OFF rising edge defines disabled logical interval; full transition charge also separately reported. Integrate positive, negative and absolute magnitudes without cancellation.','ON_feedthrough_windows_s':[[.025,.026+settle],[.045,.046+settle]],'ON_feedthrough_policy':'Non-commanded excess over original +10% measured-reference current envelope, plus negative output current; ordinary commanded ON transfer is reported separately.','role_mapping':{'collector':'G0','spatial':'Sigma','load':'Theta_Cdir'},'charge_limit_C_by_certificate_role':charges,'current_relative_tolerance':tol,'current_limit_source':'Original MIRROR_TOL=10% applied to actual physically measured reference resistor current, unchanged copy W/L scale; all actual working-output channel plateaus tested. Low output separately reported, not claimed ideal current source.','reference_perturbation_limit_V':v_eps,'reference_perturbation_basis':'Original certificate DELTA_V=20mV allowance; peak deviation after24ms from pre-ON22-24ms baseline. Both ilimp_n and irefp_n, including switching transients.','selector_bias_error_limit_V':v_eps,'establishment_after_edge_limit_s':settle,'establishment_basis':'5% of original shortest certified pulse (5.08ms), reserve95% for physical pulse transfer; after external1ms edge. No result-dependent extension.','model_domain':'Every MOS: abs(Vsb)<2V; abs(Vgb),abs(Vdb)<3.3V; original W/L ranges. Entire0-60ms.','port_energy':'All actual MOS terminal currents and voltages, reference resistor currents, output boundary and supply currents saved.','boundary_voltage_source_policy':'Fixed testbench output PWLs only, not inserted into formal circuit; no source forces cg or internal selector state.','conditional_design_refs':R},'default_reference_wall_s':{'T0_GATED_SOURCE_BENCH':300,'DC_3':900,'CHAIN_STARTUP_0_3S':1200,'Q1_MOTHER_PROTOCOL':3600,'Q1_MOTHER_HALFSTEP':3600,'CHAIN_12_W_F':14400,'G0_W':10800,'DC_2P7':900,'DC_3P2':900},'effective_wall_cap_s':None,'stop_policy':'first science/engineering failure, no retry, no parameter scan','candidate_steps':['T0_GATED_SOURCE_BENCH','DC_3','CHAIN_STARTUP_0_3S','Q1_MOTHER_PROTOCOL','Q1_MOTHER_HALFSTEP','CHAIN_12_W_F','G0_W','DC_2P7','DC_3P2']}
save(P/'V3_TEST_CONTRACT.json',contract)
def finish_plan(cid,nl,c,original_view,plan=None,more=None):
 d=P/'runs'/cid;d.mkdir();raw=d/(cid+'.raw');deck=d/(cid+'.cir');sv=list(original_view)
 if cid in ['T0_GATED_SOURCE_BENCH','CHAIN_STARTUP_0_3S'] or c['analysis']=='op':sv+=['v('+n+')' for n in sorted(nl.domain) if nl.domain[n]=='elec']
 sv+=list(dict.fromkeys(t[1] for t in nl.terms)) if cid=='T0_GATED_SOURCE_BENCH' else save_vectors(plan)
 sv=list(dict.fromkeys(sv));mos={e[0]:e[3]['nodes'] for e in nl.elements if e[1]=='M'}
 deck.write_text('\n'.join([f'* THERMAL-G3 v3 one candidate {cid}',f'.include {P}/inputs/c05_ekv26_typ.lib',nl.text(),'.options sparse method=gear reltol=1e-5 abstol=1e-16','.save '+' '.join(sv),'.control','pre_osdi /workspace/thermal-g3-env/host/native/models/ekv26_linux.osdi','set filetype=binary',c['analysis'],'write '+str(raw),'quit','.endc','.end','']))
 p={'case':c,'logical_test_id':cid,'deck':str(deck),'raw':str(raw),'deck_sha256':sha(deck),'command':['/workspace/thermal-g3-env/host/native/bin/ngspice','-n','-b',str(deck)],'cwd':str(d),'required_vectors':sv,'original_judge_vectors':original_view,'source_anchor_policy':('not applicable independent bench' if cid=='T0_GATED_SOURCE_BENCH' else 'por_hold release' if 'v(por_hold)' in original_view else 'record start'),'physical_ledger_plan':plan,'mos_nodes':mos,'ammeters':[x for x in original_view if x.startswith('i(v') and x!='i(vsrc)' and not x.startswith('i(va_')],'baseline_case_id':'Q1_MOTHER_PROTOCOL' if cid=='Q1_MOTHER_HALFSTEP' else None,'original_default_wall_s':contract['default_reference_wall_s'][cid]}
 if more:p.update(more)
 save(d/'plan.json',p);return p
# T0: one transient, nine simultaneous independent channels; only fixed external test boundaries.
nl=Netlist(instrument=True);supply_ramp(nl,3.2);references(nl);nl.R('ilim','vdd','ilim_n',v('ILIM_R'));nl.M('ilimd','ilim_n','ilim_n','0','0','nch',v('BIAS_W'),v('BIAS_L'));nl.M('ilimm','ilimp_n','ilim_n','0','0','nch',v('BIAS_W'),v('BIAS_L'));nl.M('ilimpd','ilimp_n','ilimp_n','vdd',WELL,'pch',v('BIAS_W'),v('BIAS_L'))
gate='PWL(0 0 0.02 3.2 0.025 3.2 0.026 0 0.035 0 0.036 3.2 0.045 3.2 0.046 0 0.06 0)';nl.V('enable','enable_b','0',gate)
channels=[]
for kind,diode,scale,refrole in [('collector','ilimp_n',1.,'G0'),('spatial','irefp_n',.5,'Sigma'),('load','irefp_n',1.,'Theta_Cdir')]:
 vals={'low':0.,'work_low':R['vrest'] if kind=='collector' else R['vmid'],'work_high':R['vrest']+.6 if kind=='collector' else R['vmid']+1.1*R['Iref']*(v('SP_INJ_N')*v('SP_RL') if kind=='spatial' else v('LOAD_R'))}
 for tag,voltage in vals.items():
  name=f't0_{kind}_{tag}_';out=name+'out';nl.V(name+'boundary',out,'0',f'PWL(0 0 0.02 {voltage:.12g})');gated_source(nl,name,diode,out,'enable_b',W=v('BIAS_W'),L=v('BIAS_L'),scale=scale)
  channels.append({'prefix':name,'role':kind,'certificate_role':refrole,'boundary_class':tag,'output_boundary_V':voltage,'diode':diode,'scale':scale,'charge_limit_C':charges[refrole],'cp_drain_current_vector':'i(va_n'+name+'cp_d)','gate_node':name+'cg','inverted_enable_node':name+'ena','output_node':out,'reference_current_resistor':'r'+('ilim' if kind=='collector' else 'iref')})
# Real continuously conducting copy exposes common-reference coupling independently of selector outputs.
nl.V('monitor_boundary','monitor_out','0',f'PWL(0 0 0.02 {R["vmid"]:.12g})');nl.M('monitor_cp','monitor_out','irefp_n','vdd',WELL,'pch',v('BIAS_W'),v('BIAS_L'))
for n in sorted(n for n,d in list(nl.domain.items()) if d=='elec' and n!='vsrc'):nl.C('par_'+n,n,'0',v('C_NODE'))
terms={name:terms for name,kind,terms,extra in nl.elements if kind=='M'}
t0=finish_plan('T0_GATED_SOURCE_BENCH',nl,{'case_id':'T0_GATED_SOURCE_BENCH','analysis':'tran 0.001 0.06 0 0.000125','x_stop':.06,'max_step_s':.000125,'group':'INDEPENDENT_ENGINEERING_BENCH'},[],{'nodes':[],'terms':{},'probes':{}},{'channels':channels,'all_MOS_terminal_measurements':terms,'expected_mos_count':len(terms),'physical_test_fixture_only':True})
save(P/'T0_CHANNELS.json',channels)
# Rebuild each fixed successor from actual v2 registered case and numerics; do not inherit its verdict.
plans={'T0_GATED_SOURCE_BENCH':t0}
for cid in contract['candidate_steps'][1:]:
 parent=read(V2/'runs'/cid/'plan.json');c=parent['case'];baseid='CHAIN_12_W_F' if cid=='CHAIN_STARTUP_0_3S' else cid;A=case_assets(baseid);reg=A['case'];nodes=['vrest'] if c['analysis']=='op' else ledger_nodes(reg);ts=ledger_terminals(reg)
 gated_names=[]
 if cid=='CHAIN_STARTUP_0_3S':
  test,_=netlist_for(reg)
  pref=[e[0][1:-len('bias')] for e in test.elements if e[1]=='M' and e[0].endswith('bias') and e[3]['model']=='pch']
  gated_names=['n'+pr+suffix for pr in pref for suffix in ['cp','bias','off','eni_p','eni_n']]
  ts=ts+[(r'n.*kporclamp',tag) for tag in 'dgsb']+[(re.escape(n),tag) for n in gated_names for tag in 'dgsb']
 n,meta=netlist_for(reg,nodes,ts);lp=plan_from_netlist(n,nodes) if nodes or n.probes else {'nodes':[],'terms':{},'probes':{}}
 p=finish_plan(cid,n,c,A['save'],lp,{'original_registered_case':reg,'new_gated_device_names':gated_names,'v2_parent_plan_sha256':sha(V2/'runs'/cid/'plan.json')});plans[cid]=p
 if cid=='CHAIN_STARTUP_0_3S':
  oldinv=read(V2/'SMOKE_MEASUREMENT_INVENTORY.json');oldinv['new_clamp_probes']={k:x for k,x in lp['probes'].items() if x['element'].endswith('kporclamp')};oldinv['new_selector_probes']={k:x for k,x in lp['probes'].items() if x['element'] in gated_names};assert len(oldinv['new_clamp_probes'])==112 and len(oldinv['new_selector_probes'])==160;save(P/'SMOKE_MEASUREMENT_INVENTORY.json',oldinv)
shutil.copy2(V2/'SMOKE_ENGINEERING_GATES.json',P/'SMOKE_ENGINEERING_GATES.json');shutil.copy2(V2/'CANDIDATE_DESIGN.json',P/'INHERITED_REFERENCE_DESIGN.json');shutil.copy2(V2/'offline/original-dc-load.json',P/'offline/reference_baseline_summary.json')
# Standalone frozen-case manifest; only bundle_physical is a new physical change from v2.
parenthash=read(V2/'candidate_manifest.json')['candidate_software_sha256'];changes=[]
for rel,h in parenthash.items():
 if sha(P/'software'/rel)!=h:changes.append(rel)
assert changes==['netlists/bundle_physical.py']
manifest={'status':'DESIGNED_PENDING_ZERO_SOLVER_PREFLIGHT','parent_commit':'1faf29a6e6b5041032effbae1c5c4f367076ed67','physical_changed_files':changes,'candidate_steps':contract['candidate_steps'],'cases':{k:{'directory':str(P/'runs'/k),'plan_sha256':sha(P/'runs'/k/'plan.json'),'deck_sha256':p['deck_sha256']} for k,p in plans.items()},'contract_sha256':sha(P/'V3_TEST_CONTRACT.json'),'candidate_software_sha256':{str(f.relative_to(P/'software')):sha(f) for f in (P/'software').rglob('*.py') if '__pycache__' not in f.parts},'parent_software_sha256':parenthash,'assets':{'/workspace/thermal-g3-env/host/native/bin/ngspice':sha('/workspace/thermal-g3-env/host/native/bin/ngspice'),'/workspace/thermal-g3-env/host/native/models/ekv26_linux.osdi':sha('/workspace/thermal-g3-env/host/native/models/ekv26_linux.osdi'),str(P/'inputs/c05_ekv26_typ.lib'):sha(P/'inputs/c05_ekv26_typ.lib')},'global_start_before':43,'max_new_starts':9,'global_cap':65,'max_global_after':52,'effective_wall_cap_s':None,'no_qualification_inherited':True,'new_physical_function_interface_unchanged':True,'diff_sha256':sha(P/'candidate.diff')}
save(P/'candidate_manifest_DRAFT.json',manifest);save(P/'CURRENT_STATUS.json',{'status':'ZERO_SOLVER_PREFLIGHT','global_start_count':43,'new_starts':0,'solver_wall_s':0.,'active_case':None,'cases':{cid:'NOT_STARTED' for cid in contract['candidate_steps']},'candidate_scientific_verdict':'NOT_GRANTED'})
print(json.dumps({'root':str(P),'T0_channels':len(channels),'T0_mos':len(terms),'steps':contract['candidate_steps'],'settle_after_edge_limit_s':settle,'charge_limits_C':charges,'new_solver_starts':0}))
