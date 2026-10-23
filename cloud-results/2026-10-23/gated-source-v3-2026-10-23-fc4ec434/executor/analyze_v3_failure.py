"""One targeted offline extraction of the first reference-disturbance windows."""
from pathlib import Path
import json,sys,numpy as np
J=json.loads(Path('/workspace/repair-v3-current.json').read_text());P=Path(J['root']);sys.path.insert(0,str(P/'software'));sys.path.insert(0,str(P/'executor'))
from solver_adapter.read_raw_mmap import read_raw_mmap
from v3_engineering import charge
d=P/'runs/T0_GATED_SOURCE_BENCH';p=json.loads((d/'plan.json').read_text());eng=json.loads((d/'engineering-output.json').read_text());comp=json.loads((d/'completion.json').read_text());assert eng['result']=='FAIL' and eng['model_domain']['result']=='PASS'
V=read_raw_mmap(p['raw'])[0];t=np.ascontiguousarray(V['time']);V['time']=t
out={'scope':'Targeted offline failure windows only; no native start, no RAW rehash.','raw_sha256':comp['raw_sha256'],'model_domain':eng['model_domain'],'reference_windows':[],'causal_path':'VDD -> off PMOS -> cg -> bias PMOS -> shared reference diode node during overlapping physical conduction.','scope_limit':'Measured in the frozen nine-channel simultaneous testbench. No independent single-channel or full-circuit result is claimed.'}
for ref,summary in eng['reference_perturbations'].items():
 y=V['v('+ref+')'];delta=np.abs(y-summary['baseline_V']);idx=np.flatnonzero((t>=.024)&(delta>summary['limit_V']));segments=np.split(idx,np.flatnonzero(np.diff(idx)>1)+1);peers=[x for x in p['channels'] if x['diode']==ref];inj=sum(-V['i(va_n'+x['prefix']+'bias_d)'] for x in peers);src=sum(-V['i(va_n'+x['prefix']+'off_d)'] for x in peers)
 for seg in segments[:3]:
  k=int(seg[np.argmax(delta[seg])]);a=float(t[seg[0]]);b=float(t[seg[-1]]);row={'reference':ref,'first_violating_sample_s':a,'last_violating_sample_s':b,'peak_time_s':float(t[k]),'baseline_V':summary['baseline_V'],'peak_actual_V':float(y[k]),'peak_abs_delta_V':float(delta[k]),'limit_V':summary['limit_V'],'enable_b_at_peak_V':float(V['v(enable_b)'][k]),'vdd_at_peak_V':float(V['v(vdd)'][k]),'simultaneous_channel_count':len(peers),'total_bias_drain_current_into_reference_at_peak_A':float(inj[k]),'total_off_drain_current_into_gate_at_peak_A':float(src[k]),'reference_injected_charge_over_error_window':charge(t,inj,a,b),'device_examples':[]}
  for x in peers[:2]:
   n=x['prefix'];cg=float(V['v('+n+'cg)'][k]);ena=float(V['v('+n+'ena)'][k]);row['device_examples'].append({'prefix':n,'cg_V':cg,'enable_a_V':ena,'bias_vsg_V':cg-float(V['v(enable_b)'][k]),'off_vsg_V':float(V['v(vdd)'][k])-ena,'bias_drain_injection_A':float(-V['i(va_n'+n+'bias_d)'][k]),'off_drain_charge_current_A':float(-V['i(va_n'+n+'off_d)'][k])})
  out['reference_windows'].append(row)
key={'result':'REPAIR_FAILED','failure_gate':'Reference disturbance exceeds frozen20mV engineering limit','reference_peak_delta_V':{k:x['max_abs_delta_V'] for k,x in eng['reference_perturbations'].items()},'reference_peak_limit_factors':{k:x['max_abs_delta_V']/x['limit_V'] for k,x in eng['reference_perturbations'].items()},'model_domain_passed':57,'work_current_windows_all_passed':all(x['within_original_10pct_band'] for c in eng['channels'] if c['boundary_class']!='low' for x in c['ON_plateaus']),'all_channel_charge_and_settling_gates_passed':all(not c['failures'] for c in eng['channels']),'largest_OFF_charge_limit_fraction':max(w['absolute_C']/c['charge_limit_C'] for c in eng['channels'] for w in c['OFF_windows']),'independent_reference_monitor':eng['independent_reference_monitor'],'actual_end_s':comp['actual_end_s']}
(P/'REFERENCE_FAILURE_WINDOWS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');(P/'T0_KEY_NUMBERS.json').write_text(json.dumps(key,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'key':key,'first_windows':out['reference_windows'][:2]},ensure_ascii=False))
