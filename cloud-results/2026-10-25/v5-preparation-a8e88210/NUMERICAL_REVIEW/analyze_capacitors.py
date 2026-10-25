"""Offline audit only: reads RAW; never imports a solver or changes scientific gates."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def metrics(t, voltage, current, capacitance):
    h = np.diff(t)
    dv, di = np.diff(voltage), np.diff(current)
    power_integrals = h * (voltage[:-1]*current[:-1] + voltage[1:]*current[1:]) / 2
    state_segments = capacitance * (voltage[1:]**2-voltage[:-1]**2) / 2
    charge_segments = h * (current[:-1]+current[1:]) / 2
    term_a = (voltage[:-1]+voltage[1:]) / 2 * (charge_segments-capacitance*dv)
    term_b = h*dv*di/4
    energy = float(power_integrals.sum())
    state = float(capacitance*(voltage[-1]**2-voltage[0]**2)/2)
    gap = energy-state
    limit = max(.01*max(abs(energy),abs(state)),1e-12)
    return dict(E_trap_J=energy, delta_E_J=state, signed_mismatch_J=gap,
                Q_trap_C=float(charge_segments.sum()), C_delta_v_C=float(capacitance*(voltage[-1]-voltage[0])),
                original_limit_J=limit, original_cap_gate_pass=abs(gap)<=limit,
                A_charge_consistency_J=float(term_a.sum()), B_product_quadrature_J=float(term_b.sum()),
                decomposition_roundoff_J=gap-float(term_a.sum()+term_b.sum()),
                max_interval_identity_error_J=float(np.max(np.abs(power_integrals-state_segments-term_a-term_b)))), (power_integrals-state_segments,term_a,term_b)


def derivative(t, voltage, order):
    h = np.diff(t)
    result = np.empty_like(voltage)
    result[0] = np.nan
    result[1:] = np.diff(voltage)/h
    if order == 2:
        r = h[1:]/h[:-1]
        result[2:] = ((1+2*r)/(1+r)*np.diff(voltage)[1:] - r*r/(1+r)*np.diff(voltage)[:-1])/h[1:]
        result[1] = np.nan
    return result


def validate_algorithms():
    # Known continuous passive RC, evaluated analytically at genuinely nonuniform times.
    rc = []
    C, tau, v0, vinf = 1e-7, .2, 1.2, .2
    for intervals in (40,80,160,320):
        u=np.linspace(0,1,intervals+1); t=.8*(.75*u+.25*u**1.7)
        vc=vinf+(v0-vinf)*np.exp(-t/tau); ic=-C*(v0-vinf)/tau*np.exp(-t/tau)
        m,_=metrics(t,vc,ic,C)
        rc.append(dict(intervals=intervals,max_step_s=float(np.diff(t).max()),error_J=abs(m['signed_mismatch_J'])))
    assert all(a['error_J']>b['error_J'] for a,b in zip(rc,rc[1:]))
    ratios=[a['error_J']/b['error_J'] for a,b in zip(rc,rc[1:])]
    assert all(3.8<r<4.2 for r in ratios)
    # Independent derivative weights from polynomial interpolation, not the same formula.
    t=np.array([0.,.07,.22,.31,.6,1.]); y=t*t+2*t+3
    checks=[]
    for order in (1,2):
        d=derivative(t,y,order)
        independent=[]
        for k in range(order,len(t)):
            dx=t[k-order:k+1]-t[k]
            matrix=np.array([dx**power for power in range(order+1)])
            rhs=np.zeros(order+1);rhs[1]=1.
            weights=np.linalg.solve(matrix,rhs)
            independent.append(float(weights@y[k-order:k+1]))
        err=float(np.max(np.abs(d[order:]-independent)))
        assert err<1e-12
        if order==2: assert np.max(np.abs(d[2:]-(2*t[2:]+2)))<1e-12
        checks.append(dict(order=order,independent_weight_max_error=err,result='PASS'))
    u=np.linspace(0,1,321);t=.8*(.75*u+.25*u**1.7)
    vc=vinf+(v0-vinf)*np.exp(-t/tau);ic=-C*(v0-vinf)/tau*np.exp(-t/tau)
    far=.3+.2*np.sin(3*t);near=vc+far
    positive,_=metrics(t,near-far,ic,C);assert positive['original_cap_gate_pass']
    mutants={
        'current_sign_reversed':metrics(t,vc,-ic,C)[0],
        'current_unit_A_vs_mA':metrics(t,vc,ic*1000,C)[0],
        'wrong_capacitance':metrics(t,vc,ic,C*2)[0],
        'non_ground_far_voltage_omitted':metrics(t,near,ic,C)[0],
    }
    assert all(not m['original_cap_gate_pass'] for m in mutants.values())
    return dict(result='PASS',scope='Algorithm validation only; no circuit qualification',
                passive_RC_refinements=rc,error_reduction_ratios=ratios,
                independent_BDF_checks=checks,non_ground_positive=positive,
                rejected_mutants={k:v['signed_mismatch_J'] for k,v in mutants.items()})


def read_selected(raw):
    meta={};names=[]
    with raw.open('rb') as f:
        while True:
            line=f.readline()
            if not line: raise ValueError('No binary payload')
            s=line.decode('latin1').strip()
            if s.startswith('No. Variables:'):meta['variables']=int(s.split(':',1)[1])
            elif s.startswith('No. Points:'):meta['points']=int(s.split(':',1)[1])
            elif s.startswith('Flags:'):meta['flags']=s.split(':',1)[1].strip()
            elif s=='Variables:':
                for k in range(meta['variables']):
                    columns=f.readline().decode('latin1').split();assert int(columns[0])==k
                    names.append(columns[1].lower())
            elif s=='Binary:':offset=f.tell();break
    assert meta['flags']=='real' and len(names)==meta['variables']
    assert raw.stat().st_size==offset+8*meta['points']*meta['variables']
    # Copy selected vectors once into contiguous memory; avoid repeated strided disk scans.
    data=np.memmap(raw,mode='r',dtype='<f8',offset=offset,shape=(meta['points'],meta['variables']))
    def get(name):return np.array(data[:,names.index(name.lower())],copy=True)
    return meta,get


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--expected-sha256',required=True);args=p.parse_args()
    args.out.mkdir(exist_ok=False)
    validation=validate_algorithms()
    (args.out/'ALGORITHM_VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
    # Exactly one original RAW checksum for this task.
    with args.raw.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    assert digest==args.expected_sha256,'RAW checksum mismatch'
    plan=json.loads(args.plan.read_text())['physical_ledger_plan'];meta,get=read_selected(args.raw)
    t=get('time');h=np.diff(t);assert np.all(np.isfinite(t)) and np.all(h>0)
    caps=[];intervals=[];bins=[];seen=set()
    for node,items in plan['terms'].items():
        for item in items:
            if item['kind']!='C' or item['element'] in seen:continue
            seen.add(item['element']);C=item['C'];far=item['far']
            voltage=get('v('+node+')')-(0. if far in (None,'0') else get('v('+far+')'))
            current=item['sign']*get(item['vec']);assert np.all(np.isfinite(voltage)) and np.all(np.isfinite(current))
            m,parts=metrics(t,voltage,current,C)
            assert abs(m['decomposition_roundoff_J'])<max(1e-22,abs(m['E_trap_J'])*1e-12)
            methods=[]
            for order in (1,2):
                model_current=C*derivative(t,voltage,order)
                model_current[:order]=current[:order]  # explicit measured boundary, not invented zero
                mm,_=metrics(t,voltage,model_current,C)
                diff=model_current[2:]-current[2:]
                rms=float(np.sqrt(np.mean(diff**2)));scale=float(np.sqrt(np.mean(current[2:]**2)))
                methods.append(dict(method='fixed_BDF'+str(order),boundary_samples_retained=order,
                    comparison_domain='k>=2 for both methods',current_residual_RMS_A=rms,
                    relative_current_RMS=rms/scale if scale else None,
                    max_abs_current_difference_A=float(np.max(np.abs(diff))),
                    reconstructed_energy_gap_J=mm['signed_mismatch_J'],
                    measured_minus_reconstructed_gap_J=m['signed_mismatch_J']-mm['signed_mismatch_J'],
                    scientific_pass_granted=False))
            errors,a,b=parts;order_idx=np.argsort(np.abs(errors),kind='stable')[::-1][:10]
            binids=np.floor((t[:-1]+h*.5)/.01).astype(int)
            binned=np.bincount(binids,weights=errors);ba=np.bincount(binids,weights=a);bb=np.bincount(binids,weights=b)
            bindices=np.argsort(np.abs(binned),kind='stable')[::-1][:10]
            for rank,k in enumerate(order_idx,1):
                intervals.append(dict(capacitor=item['element'],rank=rank,start_s=float(t[k]),end_s=float(t[k+1]),
                    residual_J=float(errors[k]),A_J=float(a[k]),B_J=float(b[k])))
            for rank,k in enumerate(bindices,1):
                bins.append(dict(capacitor=item['element'],rank=rank,start_s=float(k*.01),end_s=min(float((k+1)*.01),float(t[-1])),
                    residual_J=float(binned[k]),A_J=float(ba[k]),B_J=float(bb[k])))
            caps.append(dict(capacitor=item['element'],node=node,far=far,C_F=C,current_vector=item['vec'],sign=item['sign'],
                             **m,discrete_hypotheses=methods,first_three_error_windows=[row for row in bins if row['capacitor']==item['element']][:3]))
    result=dict(scope='G0_W existing measured capacitor branches only',raw_sha256=digest,raw_bytes=args.raw.stat().st_size,
        **meta,time_end_s=float(t[-1]),new_solver_starts=0,conservative_count='54/84',
        actual_solver_order_and_coefficients='UNMEASURED',original_formal_verdict='FAIL_UNCHANGED',
        capacitors=caps,algorithm_validation='PASS',new_physical_qualification='UNMEASURED')
    (args.out/'CAPACITOR_REVIEW.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for filename,rows in [('top_intervals.csv',intervals),('top_10ms_windows.csv',bins)]:
        with (args.out/filename).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({'caps':len(caps),'algorithm_validation':'PASS','raw_sha256':digest,
        'main_cap':{k:caps[0][k] for k in ['E_trap_J','delta_E_J','signed_mismatch_J','original_cap_gate_pass']},
        'new_solver_starts':0}))


if __name__=='__main__':main()
