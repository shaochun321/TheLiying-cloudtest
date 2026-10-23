"""Frozen v3 engineering observer; offline only, never starts a solver."""
import numpy as np
from observers.ledger_q1r import model_domain
def band_ok(i,ref,scale,tol):return bool(np.all((i>=(1-tol)*scale*ref)&(i<=(1+tol)*scale*ref)))
def at_window(t,x,a,b):
 m=(t>a)&(t<b);return np.r_[a,t[m],b],np.r_[np.interp(a,t,x),x[m],np.interp(b,t,x)]
def charge(t,i,a,b):
 tt,ii=at_window(t,i,a,b)
 return {'positive_C':float(np.trapezoid(np.maximum(ii,0),tt)),'negative_magnitude_C':float(np.trapezoid(np.maximum(-ii,0),tt)),'absolute_C':float(np.trapezoid(np.abs(ii),tt)),'net_C':float(np.trapezoid(ii,tt))}
def t0_engineering(V,p,contract):
 cfg=contract['T0'];missing=[n for n in p['required_vectors'] if n not in V]
 if missing:return {'result':'UNMEASURED','missing':missing}
 t=V['time'];fail=[];md=model_domain(V,p['mos_nodes'])
 if md['result']!='PASS' or md['covered']!=p['expected_mos_count']:fail.append('full model domain/coverage')
 out={'kind':'INDEPENDENT_GATED_SOURCE_BENCH','model_domain':md,'channels':[],'reference_perturbations':{},'failures':fail,'missing':[],'actual_end_s':float(t[-1])}
 bmask=(t>=.022)&(t<=.024);pmask=(t>=.024)&(t<=.060)
 for name in ['irefp_n','ilimp_n']:
  y=V['v('+name+')'];base=float(np.median(y[bmask]));delta=np.abs(y-base);idx=np.flatnonzero(pmask & (delta>cfg['reference_perturbation_limit_V']));k=int(np.argmax(np.where(pmask,delta,-1)))
  out['reference_perturbations'][name]={'baseline_V':base,'max_abs_delta_V':float(delta[k]),'peak_time_s':float(t[k]),'first_excess_time_s':float(t[idx[0]]) if len(idx) else None,'limit_V':cfg['reference_perturbation_limit_V']}
  if len(idx):fail.append('reference perturbation '+name)
 for ch in p['channels']:
  i=-V[ch['cp_drain_current_vector']];ref=V['i(va_'+ch['reference_current_resistor']+'_p)'];scale=ch['scale'];name=ch['prefix'];cg=V['v('+ch['gate_node']+')'];target=V['v('+ch['diode']+')'];r={'channel':name,'role':ch['role'],'boundary_class':ch['boundary_class'],'fixed_output_boundary_V':ch['output_boundary_V'],'charge_limit_C':ch['charge_limit_C'],'ON_plateaus':[],'OFF_windows':[],'ON_feedthrough':[],'establishment':[],'failures':[]}
  for a,b in cfg['steady_ON_windows_s']:
   m=(t>=a)&(t<=b);nom=scale*ref[m];values=i[m];ok=bool(np.any(m)) and band_ok(values,ref[m],scale,cfg['current_relative_tolerance']);err=float(np.max(np.abs(cg[m]-target[m])))
   row={'window_s':[a,b],'current_min_A':float(np.min(values)),'current_max_A':float(np.max(values)),'measured_scaled_reference_mean_A':float(np.mean(nom)),'within_original_10pct_band':ok,'max_gate_reference_error_V':err}
   r['ON_plateaus'].append(row)
   # Low output is measured and reported without qualifying ideal compliance there.
   if ch['boundary_class']!='low' and not ok:r['failures'].append('working output ON current bound')
   if err>cfg['selector_bias_error_limit_V']:r['failures'].append('ON gate not at physical reference')
  for a,b in cfg['OFF_charge_windows_s']:
   q=charge(t,i,a,b);r['OFF_windows'].append({'window_s':[a,b],**q})
   if q['absolute_C']>ch['charge_limit_C']:r['failures'].append('OFF absolute leakage/feedthrough charge')
  for a,b in cfg['ON_feedthrough_windows_s']:
   residual=np.maximum(i-(1+cfg['current_relative_tolerance'])*scale*ref,0)+np.maximum(-i,0);q=charge(t,residual,a,b)
   full=charge(t,i,a,b);r['ON_feedthrough'].append({'window_s':[a,b],'noncommanded_absolute_C':q['absolute_C'],'full_commanded_transition_charge':full})
   if q['absolute_C']>ch['charge_limit_C']:r['failures'].append('ON noncommanded feedthrough charge')
  # Freeze settling to the first time after edge end from which all samples remain valid until next command.
  for a,b,mode in [(.026,.035,'ON'),(.036,.045,'OFF'),(.046,.060,'ON')]:
   m=np.flatnonzero((t>=a)&(t<=b))
   if mode=='ON':valid=(np.abs(cg-target)<=cfg['selector_bias_error_limit_V']) & (i>=(1-cfg['current_relative_tolerance'])*scale*ref) & (i<=(1+cfg['current_relative_tolerance'])*scale*ref)
   else:valid=np.abs(cg-V['v(vdd)'])<=cfg['selector_bias_error_limit_V']
   bad=m[~valid[m]];last_bad=float(t[bad[-1]]) if len(bad) else a;settled=last_bad-a
   r['establishment'].append({'mode':mode,'edge_end_s':a,'last_invalid_sample_s':last_bad,'establish_delay_s':settled,'limit_s':cfg['establishment_after_edge_limit_s']})
   if ch['boundary_class']!='low' and settled>cfg['establishment_after_edge_limit_s']:r['failures'].append('establishment exceeds frozen reserve')
  for a,b in cfg['steady_OFF_windows_s']:
   m=(t>=a)&(t<=b);delta=float(np.max(np.abs(cg[m]-V['v(vdd)'][m])))
   if delta>cfg['selector_bias_error_limit_V']:r['failures'].append('OFF gate not at VDD')
  for a,b in [[.025,.026],[.035,.036],[.045,.046]]:
   r.setdefault('full_edge_absolute_charges',[]).append({'window_s':[a,b],**charge(t,i,a,b)})
  if r['failures']:fail.extend(name+': '+x for x in dict.fromkeys(r['failures']))
  out['channels'].append(r)
 # Actual terminal energy includes selector reference/gate charge; not a claim of ideal switching or free energy.
 term=[]
 for name,terms in p['all_MOS_terminal_measurements'].items():
  energy=0.;peaks=[]
  for node,vec,sign in terms:
   vv=0. if node=='0' else V['v('+node+')'];ii=V[vec]*sign;energy+=float(np.trapezoid(vv*ii,t));peaks.append(float(np.max(np.abs(ii))))
  term.append({'device':name,'all_four_terminal_currents_saved':len(terms)==4,'net_electrical_terminal_energy_J':energy,'max_abs_terminal_current_A':max(peaks)})
 out['MOS_port_energy']=term
 out['supply_energy_J']=-float(np.trapezoid(V['v(vsrc)']*V['i(vsrc)'],t))
 mon=-V['i(va_nmonitor_cp_d)'];out['independent_reference_monitor']={'baseline_current_A':float(np.median(mon[bmask])),'min_current_after24ms_A':float(np.min(mon[pmask])),'max_current_after24ms_A':float(np.max(mon[pmask]))}
 out['result']='FAIL' if fail else 'PASS';out['qualification_claimed']=False
 return out
