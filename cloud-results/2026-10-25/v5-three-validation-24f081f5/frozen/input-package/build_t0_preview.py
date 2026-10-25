"""Rebuild the original nine-channel fixture around v5; no process execution."""
from pathlib import Path
import argparse, hashlib, json, sys

p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--channels',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
sys.dont_write_bytecode=True
def guard(event,args):
    if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):raise RuntimeError('No solver/process in preview')
sys.addaudithook(guard);sys.path.insert(0,str(a.source.resolve()))
from netlists.build import Netlist,WELL
from netlists.neuron_nrc import supply_ramp,references
from netlists.bundle_physical import gated_source
from netlists.params import v

channels=json.loads(a.channels.read_text(encoding='utf-8'));assert len(channels)==9
nl=Netlist(instrument=True);supply_ramp(nl,3.2);references(nl)
nl.R('ilim','vdd','ilim_n',v('ILIM_R'))
nl.M('ilimd','ilim_n','ilim_n','0','0','nch',v('BIAS_W'),v('BIAS_L'))
nl.M('ilimm','ilimp_n','ilim_n','0','0','nch',v('BIAS_W'),v('BIAS_L'))
nl.M('ilimpd','ilimp_n','ilimp_n','vdd',WELL,'pch',v('BIAS_W'),v('BIAS_L'))
nl.V('enable','enable_b','0','PWL(0 0 0.02 3.2 0.025 3.2 0.026 0 0.035 0 0.036 3.2 0.045 3.2 0.046 0 0.06 0)')
for ch in channels:
    prefix=ch['prefix'];out=ch['output_node'];voltage=ch['output_boundary_V']
    nl.V(prefix+'boundary',out,'0',f'PWL(0 0 0.02 {voltage:.12g})')
    bias={'ilimp_n':'ilim_n','irefp_n':'iref_n'}[ch['diode']]
    gated_source(nl,prefix,ch['diode'],out,'enable_b',W=v('BIAS_W'),L=v('BIAS_L'),scale=ch['scale'],reference_bias_n=bias)
    ch.update(reference_bias_n=bias,local_reference_node=prefix+'local_p')
mid=next(ch['output_boundary_V'] for ch in channels if ch['role']=='load' and ch['boundary_class']=='work_low')
nl.V('monitor_boundary','monitor_out','0',f'PWL(0 0 0.02 {mid:.12g})')
nl.M('monitor_cp','monitor_out','irefp_n','vdd',WELL,'pch',v('BIAS_W'),v('BIAS_L'))
for n in sorted(n for n,d in list(nl.domain.items()) if d=='elec' and n!='vsrc'):nl.C('par_'+n,n,'0',v('C_NODE'))
mos={name:extra['nodes'] for name,kind,terms,extra in nl.elements if kind=='M'}
assert len(mos)==75,len(mos)
saves=['v('+n+')' for n,d in sorted(nl.domain.items()) if d=='elec']+[term[1] for term in nl.terms]
saves=list(dict.fromkeys(saves));assert len(saves)==len(set(saves))
text='\n'.join(['* v5 T0 preview; original boundaries; no runtime permission','.include <MODEL_LIB>',nl.text(),'.options sparse method=gear reltol=1e-5 abstol=1e-16','.save '+' '.join(saves),'.control','pre_osdi <OSDI>','set filetype=binary','tran 0.001 0.06 0 0.000125','write <RAW>','quit','.endc','.end',''])
a.out.mkdir(exist_ok=False);(a.out/'T0_PREVIEW.cir').write_text(text,encoding='utf-8')
plan={'status':'STATIC_PREVIEW_ONLY','analysis':'tran 0.001 0.06 0 0.000125','mos_nodes':mos,'expected_mos_count':75,'channels':channels,'required_vectors':saves,'all_MOS_terminal_measurements':{name:terms for name,kind,terms,extra in nl.elements if kind=='M'},'new_solver_starts':0,'deck_sha256':hashlib.sha256(text.encode()).hexdigest()}
(a.out/'T0_PREVIEW_PLAN.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'mos':len(mos),'channels':len(channels),'vectors':len(saves),'new_solver_starts':0}))
