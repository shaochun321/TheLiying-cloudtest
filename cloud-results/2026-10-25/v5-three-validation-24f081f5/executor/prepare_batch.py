"""Bind the authorized three cases; all preparation is zero-solver."""
from pathlib import Path
import ast, copy, hashlib, importlib.util, json, re, shutil, sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent.parent
INPUT=ROOT.parent/'v5-three-validation-input-2026-10-25-24f081f5/thermal_g3_v5_launch_20261025'
PREP=ROOT.parent/'v5-preparation-2026-10-25-a8e88210'
SOURCE=ROOT/'frozen/software'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def check(text,analysis):
    lines=[x.strip() for x in text.splitlines()]
    return (not re.search(r'<(RAW|OSDI|MODEL_LIB)>',text) and lines.count('.control')==1 and lines.count('.endc')==1
      and [x for x in lines if re.match(r'^\.?(op|dc|tran)\b',x)]==[analysis] and 'uic' not in analysis.split()
      and '.options sparse method=gear reltol=1e-5 abstol=1e-16' in lines)

def main():
    identity=json.loads((PREP/'CANDIDATE_SOURCE/SOURCE_IDENTITY.json').read_text())
    original=PREP/'CANDIDATE_SOURCE/software'
    assert all(sha(original/rel)==h for rel,h in identity['candidate_sha256'].items())
    shutil.copytree(original,SOURCE)
    shutil.copytree(INPUT,ROOT/'frozen/input-package')
    shutil.copyfile(INPUT/'reference/original_engineering_v3.py',ROOT/'executor/original_engineering_v3.py')
    shutil.copyfile(PREP/'CANDIDATE_SOURCE/original_static_helpers.py',ROOT/'executor/original_static_helpers.py')
    sys.path.insert(0,str(SOURCE))
    from runtime.decks import registry,case_assets,netlist_for
    from netlists.ledger_plan import plan_from_netlist
    import original_static_helpers as helpers
    assets=json.loads((INPUT/'reference/ASSET_IDENTITY.json').read_text())
    for name,row in assets.items():assert sha(Path(row['path']))==row['sha256'],name
    model=SOURCE/'models/c05_ekv26_typ.lib';assert sha(model)==assets['model_card']['sha256']
    osdi=assets['OSDI']['path'];ng=assets['ngspice']['path']
    t0=ROOT/'frozen/t0-reproduced';p=json.loads((t0/'T0_PREVIEW_PLAN.json').read_text())
    assert (t0/'T0_PREVIEW.cir').read_text()==(INPUT/'t0-preview/T0_PREVIEW.cir').read_text()
    assert p==json.loads((INPUT/'t0-preview/T0_PREVIEW_PLAN.json').read_text())
    limits=json.loads((ROOT/'frozen/NMOS_BIAS_LIMITS_REPRODUCED.json').read_text())
    assert limits==json.loads((INPUT/'PROPOSED_NMOS_BIAS_LIMITS.json').read_text())
    def pwls(text):return sorted(' '.join(x.split()).lower() for x in text.splitlines() if x.startswith('v') and 'pwl(' in x.lower())
    assert pwls((t0/'T0_PREVIEW.cir').read_text())==pwls((INPUT/'reference/ORIGINAL_T0.cir').read_text())
    def bind(cid,text,plan,analysis,cap):
        directory=ROOT/cid;raw=directory/(cid+'.raw');deck=directory/(cid+'.cir')
        text=text.replace('.include <MODEL_LIB>','.include '+str(model)).replace('.include ../software/models/c05_ekv26_typ.lib','.include '+str(model))
        text=text.replace('<OSDI>',osdi).replace('<RAW>',str(raw))
        assert check(text,analysis)
        assert not check(text.replace(analysis,analysis+'\nop'),analysis)
        if analysis.startswith('tran'):
            assert not check(text.replace(analysis,analysis+' uic'),analysis)
            assert not check(text.replace(analysis,analysis.replace('0.001','0.000125',1)),analysis)
            assert not check(text.replace(analysis,analysis.replace('0.000125','0.00025')),analysis)
        els=helpers.elements(text);assert not helpers.floating(els);assert not helpers.domain(els)
        names=[x[0].lower() for x in els];assert len(names)==len(set(names))
        deck.write_text(text)
        plan.update(case_id=cid,status='FROZEN_AUTHORIZED_ONCE',deck=str(deck),deck_sha256=sha(deck),raw=str(raw),
                    analysis=analysis,command=[ng,'-n','-b',str(deck)],wall_cap_s=cap,maximum_actual_starts=1,
                    required_end_s=None if analysis=='op' else float(analysis.split()[2]),max_step_s=None if analysis=='op' else .000125)
        save(directory/'plan.json',plan)
        return {'case_id':cid,'analysis':analysis,'wall_cap_s':cap,'MOS':len(plan['mos_nodes']),'vectors':len(plan['required_vectors']),'deck_sha256':sha(deck)}
    plans=[bind('T0_GATED_SOURCE_BENCH',(t0/'T0_PREVIEW.cir').read_text(),p,'tran 0.001 0.06 0 0.000125',600)]
    c=copy.deepcopy(next(c for c in registry()['cases'] if c['case_id']=='DC_3'))
    plain,_=netlist_for(c);nl,_=netlist_for(c,sorted(set(plain.domain)|{'0'}))
    mos={e[0]:e[3]['nodes'] for e in nl.elements if e[1]=='M'}
    saves=['v('+n+')' for n in sorted(nl.domain)]+[term[1] for term in nl.terms]
    saves=list(dict.fromkeys(x.lower() for x in saves));a=case_assets('DC_3');assert set(a['required'])<=set(saves)
    text='\n'.join(['* v5 full-network DC_3','.include <MODEL_LIB>',nl.text(),'.options sparse method=gear reltol=1e-5 abstol=1e-16',
       '.save '+' '.join(saves),'.control','pre_osdi <OSDI>','set filetype=binary','op','write <RAW>','quit','.endc','.end',''])
    new=[name for name in mos if name.endswith(('kporclamp','_refn','_refp','_eni_p','_eni_n','_bias','_off')) or (name.endswith('_cp') and ('cin_' in name or name.startswith(('nsp','nag'))))]
    dp={'case':c,'mos_nodes':mos,'expected_mos_count':len(mos),'required_vectors':saves,'science_view':'All DC vectors; no transient support anchor',
        'diagnostic_reference_plan':plan_from_netlist(nl,['vrest']),'new_or_changed_MOS':new,'physical_ledger_plan':None}
    for name in new:
        for tag in 'dgsb':assert 'i(va_'+name+'_'+tag+')' in saves
    plans.append(bind('DC_3',text,dp,'op',1800))
    gd=PREP/'CANDIDATE_SOURCE/generated-verified';p=json.loads((gd/'CHAIN_12_W_F.json').read_text());c=copy.deepcopy(next(c for c in registry()['cases'] if c['case_id']=='CHAIN_12_W_F'))
    c.update(analysis='tran 0.001 39.2 0 0.000125',max_step_s=.000125)
    original_views=p['original_scoring_vectors'];assert 'v(por_hold)' not in original_views
    plan={'case':c,'mos_nodes':{name:e['nodes'] for name,e in p['mos'].items()},'expected_mos_count':len(p['mos']),'required_vectors':p['save_vectors'],
        'science_view_vectors':['time']+original_views,'anchor_policy':'Original science whitelist excludes v(por_hold); actual record-start anchor retained',
        'first_stimulus_s':min(seg[0] for segs in c['env'].values() for seg in segs),
        'physical_ledger_plan':p['ledger_plan'],'diagnostic_reference_plan':p['diagnostic_reference_plan'],
        'new_or_changed_MOS':[name for name in p['observed_four_terminal_devices'] if name.endswith(('kporclamp','_refn','_refp','_eni_p','_eni_n','_cp','_bias','_off'))]}
    plans.append(bind('CHAIN_12_W_F',(gd/'CHAIN_12_W_F.cir').read_text(),plan,c['analysis'],28800))
    # Meaningful regressions for the added monitoring gates, no circuit solver.
    import numpy as np
    from engineering_v5 import current_band,full_domain
    tt=np.array([.022,.024,.03,.04,.06]);ref=np.ones(5)*1e-6;mask=tt>=.024
    assert current_band(tt,ref,ref,mask)['result']=='PASS'
    droop=ref.copy();droop[3]=0;assert current_band(tt,droop,ref,mask)['result']=='FAIL'
    assert full_domain({'v(d)':np.zeros(1)}, {'n':['d','g','0','0']})['result']=='UNMEASURED'
    preflight={'result':'PASS','cases':plans,'same_candidate_source_sha256':identity['candidate_sha256'],
      'T0_original_PWLs_preserved':True,'T0_preview_reproduced':True,'bias_limits_reproduced':True,
      'original_gate_observer_preserved':sha(ROOT/'executor/original_engineering_v3.py')==sha(INPUT/'reference/original_engineering_v3.py'),
      'monitor_droop_mutant_rejected':True,'partial_domain_coverage_rejected':True,'command_mutants_rejected':True,
      'solver_execution_performed':False,'old_state':'54/84'}
    save(ROOT/'frozen/PREFLIGHT.json',preflight)
    save(ROOT/'frozen/ENGINEERING_POLICY.json',{'T0':'All original gates + continuous monitor +/-10%, continuous working current after 254us, NMOS 3.8/4.1mV, design-box coverage, full 75/75 domain',
      'DC':'Original ten gates + full coverage; complete vrest KCL with original ledger 1e-3 relative floor1pA; report full new device currents and supply',
      'CHAIN':'Original eighteen gates and twenty-node ledger on original scoring whitelist; separate full domain, original 3s POR-release engineering boundary, no pre-stimulus q/aq/p, original ledger criteria at new reference nodes',
      'all_original_energy_gates_unchanged':True,'fixed_BDF_explanation_cannot_replace_FAIL':True})
    save(ROOT/'frozen/AUTHORIZATION.json',{'user':'Explicit current message: same v5, T0 then DC_3 then CHAIN_12_W_F; predecessor all-pass; max3 starts; upload each case small files and lossless RAW fragments, verify remote retrieval',
      'starts_before':54,'max_new_starts':3,'cap':84,'maximum_after':57,'per_case_wall_cap_s':{'T0':600,'DC_3':1800,'CHAIN':28800},'batch_wall_cap_s':31200,'chain_8h_is_not_forecast':True,
      'retry':False,'scan':False,'retune':False,'automatic_matrix':False,'old_v4_qualification_inherited':False,'main_modified':False})
    save(ROOT/'frozen/ASSET_IDENTITY.json',assets)
    save(ROOT/'frozen/RESOURCE_CHECK.json',{'disk_free_bytes':shutil.disk_usage(ROOT).free,'memory_max_bytes':int(Path('/sys/fs/cgroup/memory.max').read_text()),
      'chain_minimum_grid_payload_bytes':int(39.2/.000125)*1396*8,'delivery_strategy':'Stream compression to <=40MiB parts; Git upload; independent API part download and streamed RAW restoration without a second large clone or restored RAW disk copy',
      'original_RAW_retained':True,'minimum_free_disk_before_CHAIN_bytes':12_000_000_000,'runtime_disk_abort_below_bytes':1_000_000_000})
    for p in (ROOT/'executor').glob('*.py'):ast.parse(p.read_text())
    print(json.dumps(preflight['cases']))

if __name__=='__main__':main()
