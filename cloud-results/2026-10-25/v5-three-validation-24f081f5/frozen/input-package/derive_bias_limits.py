"""Offline, sampled NMOS gate sensitivity. Never invokes a circuit solver."""
from pathlib import Path
import argparse, hashlib, json, math, sys

p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
sys.dont_write_bytecode=True;sys.path.insert(0,str(a.source.resolve()))
from analysis.ekv26_static import ids
from netlists.params import v

cfg=json.loads(a.contract.read_text(encoding='utf-8'))['T0']
vdd=cfg['conditional_design_refs']['vdd']
def bisect(f,lo,hi,n=60):
    flo=f(lo)
    if flo*f(hi)>0:raise ValueError('Root not bracketed')
    for _ in range(n):
        mid=(lo+hi)/2;fm=f(mid)
        if fm*flo>0:lo=mid;flo=fm
        else:hi=mid
    return (lo+hi)/2
def current(d,g):return ids('nch',v('BIAS_W'),v('BIAS_L'),d,g,0.,0.,temp_c=27.)
records={}
for name,resistor in [('iref_n','IREF_R'),('ilim_n','ILIM_R')]:
    nominal=bisect(lambda x:(vdd-x)/v(resistor)-current(x,x),.05,vdd-1e-6)
    # Predefined design grid, independent of any v5 waveform. This is not a continuum bound.
    gates=[nominal-.020+.040*k/16 for k in range(17)]
    drains=[.05+(3.2-.05)*k/32 for k in range(33)]
    points=[(d,g,current(d,g)) for g in gates for d in drains]
    if min(x[2] for x in points)<=0:raise ValueError('Nonpositive nominal current')
    def errors(delta):
        ratios=[(current(d,g-delta)/i,current(d,g+delta)/i) for d,g,i in points]
        return min(x[0] for x in ratios),max(x[1] for x in ratios)
    # Reserve half the logarithmic +/-10% current allowance for gate-bias motion.
    # Other effects remain independently tested against the full original band.
    lower,upper=math.sqrt(.9),math.sqrt(1.1)
    lo,hi=0.,.02
    for _ in range(34):
        mid=(lo+hi)/2;mn,mx=errors(mid)
        if mn>=lower and mx<=upper:lo=mid
        else:hi=mid
    frozen=math.floor(lo/.0001)*.0001
    mn,mx=errors(frozen)
    records[name]={'nominal_gate_V':nominal,'gate_baseline_grid_V':[gates[0],gates[-1]],'gate_grid_count':17,'drain_grid_V':[.05,3.2],'drain_grid_count':33,'raw_sampled_limit_V':lo,'engineering_limit_V':frozen,'rounding_V':.0001,'min_current_ratio_on_grid':mn,'max_current_ratio_on_grid':mx}
out={'status':'PROPOSED_PRE_RUN_ENGINEERING_LIMITS','method':'Finite current ratio on a fixed offline EKV grid; reserve half the logarithmic +/-10% allowance and round down to 0.1mV','temperature_C':27.,'current_tolerance':.10,'bias_motion_current_ratio_band':[math.sqrt(.9),math.sqrt(1.1)],'records':records,'assumptions':['Same original static EKV implementation and 4um/4um geometry','This samples a design box; it is not a rigorous continuous or manufacturing bound','At fixed drain only: drain motion, gate charge, selector loss and process mismatch are not covered','Actual independent monitor and all working-output current gates remain mandatory','After24ms baseline and observed drain voltages must lie in the registered design box; outside is UNMEASURED/stop, never an automatic limit change'],'source_sha256':hashlib.sha256((a.source/'analysis/ekv26_static.py').read_bytes()).hexdigest(),'new_solver_starts':0}
a.out.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(json.dumps(out))
