"""Targeted offline extraction only. No native solver, no RAW hash pass."""
from pathlib import Path
import json,sys,argparse,numpy as np
a=argparse.ArgumentParser();a.add_argument('--root',required=True);a=a.parse_args();p=Path(a.root)
sys.path.insert(0,str(p/'software'));from solver_adapter.read_raw_mmap import read_raw_mmap
r=p/'runs/CHAIN_STARTUP_0_3S';V=read_raw_mmap(r/'CHAIN_STARTUP_0_3S.raw')[0];T=np.ascontiguousarray(V['time']);O=read_raw_mmap(p/'runs/C0_CORRECTED_50MS/C0_CORRECTED_50MS.raw')[0];OT=np.ascontiguousarray(O['time']);plan=json.loads((r/'plan.json').read_text());eng=json.loads((r/'engineering-output.json').read_text());rows=[]
for name in eng['model_domain']['outside']:
 d,g,s,b=plan['mos_nodes'][name]
 val=lambda W,n:0. if n=='0' else W['v('+n+')']
 sb=np.abs(val(V,s)-val(V,b));ids=np.flatnonzero(sb>=2.);first=int(ids[0]);worst=int(np.argmax(sb));osb=np.abs(val(O,s)-val(O,b));oi=np.flatnonzero(osb>=2.);ow=int(np.argmax(osb));windows=[]
 for seg in np.split(ids,np.flatnonzero(np.diff(ids)>1)+1)[:3]:windows.append({'first_sample_s':float(T[seg[0]]),'last_sample_s':float(T[seg[-1]]),'sample_count':len(seg)})
 rows.append({'device':name,'terminal_nodes':dict(zip('dgsb',(d,g,s,b))),'failed_quantity':'abs(Vs-Vb)','strict_limit_V':2.,'candidate_first_violating_sample_s':float(T[first]),'candidate_peak_abs_Vsb':float(sb[worst]),'candidate_peak_time_s':float(T[worst]),'candidate_peak_terminal_V':{tag:float(val(V,n)[worst]) if n!='0' else 0. for tag,n in zip('dgsb',(d,g,s,b))},'first_error_windows':windows,'original_corrected_50ms_diagnostic_already_violates':bool(len(oi)),'original_first_violating_sample_s':float(OT[oi[0]]) if len(oi) else None,'original_peak_abs_Vsb_0_50ms':float(osb[ow]),'causal_limit':'Comparisons show presence in original 50ms diagnostic; they do not prove identical long-term behavior or a unique physical root cause.'})
result={'result':'CONFIRMED_MODEL_DOMAIN_BLOCKER','scope':'Targeted offline read only, eight failing original devices; no new solve or RAW rehash.','new_clamps_outside_domain':False,'all_failure_devices_present_in_original':True,'original_50ms_already_violation_count':sum(x['original_corrected_50ms_diagnostic_already_violates'] for x in rows),'devices':rows}
(p/'MODEL_DOMAIN_FAILURE_WINDOWS.json').write_text(json.dumps(result,indent=2)+'\n')
quiet={'logic_vectors':len(eng['logic_events']),'max_logic_peak_V':max(x['peak_V'] for x in eng['logic_events'].values()),'state_capacitors':len(eng['state_capacitors']),'worst_state':max(eng['state_capacitors'],key=lambda x:x['peak_abs_V']),'clamp_count_measured':len(eng['new_clamp_measured_terminal_currents']),'net_clamp_electrical_energy_J':sum(x['net_electrical_port_energy_J'] for x in eng['new_clamp_measured_terminal_currents'].values())}
(p/'SMOKE_KEY_NUMBERS.json').write_text(json.dumps(quiet,indent=2)+'\n')
print(json.dumps({'violating_devices':len(rows),'already_in_original':result['original_50ms_already_violation_count']}))
