"""Read-only batch engineering checks. No solver, no result-dependent thresholds."""
import numpy as np
from observers.ledger_q1r import model_domain, ledger
from original_engineering_v3 import t0_engineering


def current_band(t, current, reference, mask, tolerance=.10):
    if not np.any(mask) or not np.all(reference[mask]>0):
        return {'result':'UNMEASURED','why':'empty current window or nonpositive reference'}
    ratio=current[mask]/reference[mask]
    bad=mask & ((current<(1-tolerance)*reference)|(current>(1+tolerance)*reference))
    return {'result':'FAIL' if np.any(bad) else 'PASS','ratio_min':float(ratio.min()),'ratio_max':float(ratio.max()),
            'first_failure_s':float(t[np.flatnonzero(bad)[0]]) if np.any(bad) else None,'tolerance':tolerance}


def full_domain(V, mos):
    result=model_domain(V,mos)
    if result['covered']!=len(mos):result['result']='UNMEASURED'
    earliest=None
    for name,(d,g,s,b) in mos.items():
        if any(n!='0' and 'v('+n+')' not in V for n in (d,g,s,b)):continue
        vd,vg,vs,vb=[0. if n=='0' else V['v('+n+')'] for n in (d,g,s,b)]
        bad=(np.abs(vs-vb)>=2.)|(np.abs(vg-vb)>=3.3)|(np.abs(vd-vb)>=3.3)
        indices=np.flatnonzero(np.atleast_1d(bad))
        if len(indices):
            k=int(indices[0]);at=float(V['time'][k]) if 'time' in V else 0.
            if earliest is None or at<earliest['time_s']:earliest={'device':name,'time_s':at,'sample_index':k}
    result['earliest_violation']=earliest
    return result


def t0(V, plan, contract, limits):
    # Missing/nonfinite required vectors are rejected before any window arithmetic.
    missing=[key for key in plan['required_vectors'] if key not in V]
    if missing:return {'result':'UNMEASURED','missing':missing}
    out=t0_engineering(V,plan,contract)
    out['original_engineering_result']=out['result']
    out['model_domain']=full_domain(V,plan['mos_nodes'])
    fail=list(out['failures']);unknown=[]
    if out['model_domain']['result']=='UNMEASURED':unknown.append('full model-domain coverage')
    t=V['time'];baseline=(t>=.022)&(t<=.024);active=(t>=.024)&(t<=.06)
    monitor=current_band(t,-V['i(va_nmonitor_cp_d)'],V['i(va_riref_p)'],active)
    out['continuous_independent_monitor_gate']=monitor
    if monitor['result']!='PASS':(unknown if monitor['result']=='UNMEASURED' else fail).append('continuous independent monitor +/-10%')
    bias={}
    for name,cfg in limits['records'].items():
        y=V['v('+name+')'];base=float(np.median(y[baseline]));lo,hi=cfg['gate_baseline_grid_V']
        applicable=lo<=base<=hi;drains=[]
        for dev,nodes in plan['mos_nodes'].items():
            if nodes[1]==name and nodes[2:]==['0','0']:
                values=V['v('+nodes[0]+')'][active]
                valid=bool(np.all((values>=cfg['drain_grid_V'][0])&(values<=cfg['drain_grid_V'][1])))
                drains.append({'device':dev,'min_V':float(values.min()),'max_V':float(values.max()),'in_design_box':valid});applicable &= valid
        assert drains
        delta=np.abs(y-base);k=int(np.argmax(np.where(active,delta,-1.)))
        bad=active & (delta>cfg['engineering_limit_V'])
        result='UNMEASURED' if not applicable else ('FAIL' if np.any(bad) else 'PASS')
        bias[name]={'result':result,'baseline_V':base,'baseline_design_range_V':[lo,hi],'limit_V':cfg['engineering_limit_V'],
                    'maximum_delta_V':float(delta[k]),'peak_time_s':float(t[k]),'first_failure_s':float(t[np.flatnonzero(bad)[0]]) if np.any(bad) else None,'copied_NMOS_drains':drains}
        if result!='PASS':(unknown if result=='UNMEASURED' else fail).append('NMOS bias '+name)
    out['NMOS_bias_gates']=bias
    continuous=[];local=[]
    for ch in plan['channels']:
        cur=-V[ch['cp_drain_current_vector']];ref=V['i(va_'+ch['reference_current_resistor']+'_p)']*ch['scale']
        if ch['boundary_class']!='low':
            for start,end in [(.026+contract['T0']['establishment_after_edge_limit_s'],.035),(.046+contract['T0']['establishment_after_edge_limit_s'],.06)]:
                row={'channel':ch['prefix'],'window_s':[start,end],**current_band(t,cur,ref,(t>=start)&(t<=end))};continuous.append(row)
                if row['result']!='PASS':(unknown if row['result']=='UNMEASURED' else fail).append(ch['prefix']+' continuous working output current')
        gate=V['v('+ch['gate_node']+')'];target=V['v('+ch['local_reference_node']+')']
        local.append({'channel':ch['prefix'],'local_bias_selector_peak_error_V':float(np.max(np.abs(gate-target))),
                      'diagnostic_only':True,'original_public_reference_gate_preserved':True})
    out['continuous_working_output_gates']=continuous;out['local_bias_diagnostics']=local
    out['failures']=list(dict.fromkeys(fail));out['unmeasured']=unknown
    out['result']='UNMEASURED' if unknown else ('FAIL' if fail else 'PASS')
    candidates=[]
    if out['model_domain']['earliest_violation']:candidates.append(out['model_domain']['earliest_violation']['time_s'])
    for row in [monitor,*bias.values(),*continuous]:
        if row.get('first_failure_s') is not None:candidates.append(row['first_failure_s'])
    for row in out['reference_perturbations'].values():
        if row.get('first_excess_time_s') is not None:candidates.append(row['first_excess_time_s'])
    # Original integrated window failures have a window, not an invented exact crossing.
    window_failures=[]
    for row in out['channels']:
        if row['failures']:
            window_failures.append({'channel':row['channel'],'failures':row['failures'],'source':'Original frozen T0 windows; full per-window values retained'})
    out['first_exact_failure_time_s']=min(candidates) if candidates else None
    out['original_window_failures']=window_failures
    return out


def dc(V, plan):
    out={'model_domain':full_domain(V,plan['mos_nodes']),'reference':{},'new_device_currents':{}}
    items=plan['diagnostic_reference_plan']['terms']['vrest'];missing=[];total=0.;through=0.;loads=0.
    for it in items:
        if it['vec'] not in V:missing.append(it['vec']);continue
        val=it['sign']*float(np.ravel(V[it['vec']])[0]);total+=val;through+=abs(val)
        if it['element'] not in ['rvrestt','rvrestb','cvrestc']:loads+=val
    vdd=float(V['v(vdd)'][0]);vr=float(V['v(vrest)'][0]);top=float(V['i(va_rvrestt_p)'][0]);bottom=float(V['i(va_rvrestb_p)'][0])
    limit=max(1e-3*through,1e-12)
    out['reference']={'result':'UNMEASURED' if missing else ('PASS' if abs(total)<=limit else 'FAIL'),
        'missing':missing,'top_current_A':top,'bottom_current_A':bottom,'net_load_out_of_vrest_A':loads,
        'KCL_signed_residual_A':total,'KCL_limit_A':limit,'actual_internal_VDD_V':vdd,'vrest_V':vr,
        'loaded_prediction_V':vdd/3-(1000*500/1500)*loads,'unloaded_prediction_V':vdd/3}
    out['supply']={'current_A':-float(V['i(vsrc)'][0]),'external_power_W':-float(V['v(vsrc)'][0]*V['i(vsrc)'][0]),'internal_VDD_V':vdd}
    for name in plan['new_or_changed_MOS']:
        out['new_device_currents'][name]={tag:float(V['i(va_'+name+'_'+tag+')'][0]) for tag in 'dgsb'}
    gates=[out['model_domain']['result'],out['reference']['result']]
    out['result']='UNMEASURED' if 'UNMEASURED' in gates else ('FAIL' if 'FAIL' in gates else 'PASS')
    return out


def chain(V, plan):
    from observers.judges import _events
    out={'model_domain':full_domain(V,plan['mos_nodes']),'startup_events':{},'source_anchor_policy':plan['anchor_policy']}
    t=V['time'];threshold=float(np.median(V['v(vdd)']))/2;first=plan['first_stimulus_s'];early=[]
    for core in ['gw1_col_','gw2_col_','thw12f_','thw12r_','sgw12f_','sgw12r_','cdw12f_','cdw12r_']:
        for suffix in ['q','op_aq','op_p']:
            key='v('+core+suffix+')';events=_events(V,key,threshold)
            times=[float(x) for x in events];before=[x for x in times if x<first]
            out['startup_events'][key]={'event_type':{'q':'NRC pulse','op_aq':'shaped activity','op_p':'canonical entry pulse'}[suffix],
                'before_stimulus_s':before,'all_rising_times_s':times}
            if before:early.append(key)
    hold=V['v(por_hold)']>threshold;indices=np.flatnonzero(hold)
    release=float(t[indices[-1]]) if len(indices) and indices[-1]<len(t)-1 else None
    out['POR']={'release_s':release,'result':'PASS' if release is not None and release<3. else 'FAIL','release_by_original_3s_engineering_boundary':True}
    out['startup_silence']={'result':'FAIL' if early else 'PASS','early_nodes':early,'first_stimulus_s':first}
    out['new_reference_KCL_and_energy']=ledger(V,plan['diagnostic_reference_plan'])
    # Keep every new terminal measured; report actual measured currents without inventing a new scalar limit.
    out['new_device_current_peaks_A']={name:{tag:float(np.max(np.abs(V['i(va_'+name+'_'+tag+')']))) for tag in 'dgsb'} for name in plan['new_or_changed_MOS']}
    states=[out[k]['result'] for k in ['model_domain','POR','startup_silence','new_reference_KCL_and_energy']]
    out['result']='UNMEASURED' if 'UNMEASURED' in states else ('FAIL' if 'FAIL' in states else 'PASS')
    return out
