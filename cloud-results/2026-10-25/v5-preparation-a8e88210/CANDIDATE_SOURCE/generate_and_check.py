"""Generate only three selected cases and audit actual flat connectivity, no solver."""
import argparse
import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
IDS=('Q1_MOTHER_PROTOCOL','CHAIN_12_W_F','G0_W')


def write(p,d):p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')


def analysis_preflight(text,expected):
    lines=[x.strip().lower() for x in text.splitlines()]
    analyses=[x for x in lines if re.match(r'^\.?(op|dc|tran)\b',x)]
    return (analyses==[expected.lower()] and 'uic' not in expected.lower().split()
            and lines.count('.control')==1 and lines.count('.endc')==1
            and '.options sparse method=gear reltol=1e-5 abstol=1e-16' in lines)


def isolate_ok(block,shared_p,shared_n):
    return (not any(shared_p in e['nodes'] for e in block)
            and all(shared_n not in [e['nodes'][i] for i in (0,2,3)] for e in block)
            and any(e['model']=='nch' and e['nodes'][1]==shared_n for e in block))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--static-helper',type=Path,required=True);ap.add_argument('--baseline-artifacts',type=Path)
    args=ap.parse_args();args.out.mkdir(exist_ok=False);sys.path.insert(0,str(args.source))
    # No process execution allowed from any imported builder, including accidental calls.
    def guard(event,values):
        if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):raise RuntimeError('Process execution forbidden in zero-solver preparation')
    sys.addaudithook(guard)
    from runtime.decks import case_assets,netlist_for,registry
    from netlists.ledger_plan import ledger_nodes,ledger_terminals,plan_from_netlist
    from netlists.params import v
    spec=importlib.util.spec_from_file_location('static_helpers',args.static_helper);helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
    candidate=args.baseline_artifacts is not None;summary=[]
    for cid in IDS:
        asset=case_assets(cid);case=copy.deepcopy(asset['case']);plain,_=netlist_for(case)
        mos={e[0]:dict(name=e[0],**e[3]) for e in plain.elements if e[1]=='M'}
        for e in mos.values():e['nodes']=list(e['nodes'])
        cdir=[name for name in mos if re.fullmatch(r'ncd[wc]\d\d[fr]_(st_mh|st_mp|rm_mo|kh|kp)',name)]
        groups=[];new_names=set();local_nodes=[];old=None
        if candidate:
            old=json.loads((args.baseline_artifacts/(cid+'.json')).read_text())
            for name,e in mos.items():
                if not name.endswith('_refn'):continue
                pre=name[:-4];cp=pre+'cp';old_cp=old['mos'][cp]
                shared_p=old_cp['nodes'][1];shared_n={'irefp_n':'iref_n','ilimp_n':'ilim_n'}[shared_p]
                block=[mos[pre+s] for s in ('refn','refp','eni_p','eni_n','cp','bias','off')]
                assert isolate_ok(block,shared_p,shared_n)
                assert mos[pre+'refn']['nodes']==[e['nodes'][0],shared_n,'0','0']
                assert mos[pre+'refp']['nodes']==[e['nodes'][0],e['nodes'][0],'vdd','vsrc']
                assert mos[cp]['nodes'][2:]==['vdd','vsrc']
                for suffix in ('refn','refp'):assert mos[pre+suffix]['W']==v('BIAS_W') and mos[pre+suffix]['L']==v('BIAS_L')
                assert mos[cp]['W']==old_cp['W'] and mos[cp]['L']==old_cp['L'] and mos[cp]['mult']==old_cp['mult']
                bad=copy.deepcopy(block);next(x for x in bad if x['name']==pre+'bias')['nodes'][0]=shared_p
                assert not isolate_ok(bad,shared_p,shared_n)
                bad=copy.deepcopy(block);next(x for x in bad if x['name']==pre+'refn')['nodes'][2]=shared_n
                assert not isolate_ok(bad,shared_p,shared_n)
                new_names.update(x['name'] for x in block);local_nodes.append(e['nodes'][0])
                groups.append(dict(prefix=pre,legacy_p_label=shared_p,reference_bias_n=shared_n,local_p=e['nodes'][0],
                    devices=block,isolation='PASS_STATIC',reconnection_mutants_rejected=2))
            clamps=[n for n in mos if n.endswith('kporclamp')]
            expected=[n[:-4]+'kporclamp' for n in old['mos'] if n.endswith('porm')]
            assert set(clamps)==set(expected)
            for name in clamps:
                e=mos[name];assert e['nodes']==[name[1:-8]+'o1','por_hold','0','0']
                assert e['W']==4e-6 and e['L']==1e-6;new_names.add(name)
            # Added complete terminal instrumentation on every new/changed bundle device,
            # reference devices, POR clamps and direction support/conflict paths.
            refs={'nirefd','nirefm','nirefpd','nilimd','nilimm','nilimpd'} & set(mos)
            observed=sorted(new_names|refs|set(cdir))
            terminals=list(ledger_terminals(case))+[(re.escape(name),tag) for name in observed for tag in 'dgsb']
            extra_nodes=['vrest','iref_n','irefp_n','ilim_n','ilimp_n','por_hold','por_ok','porc','porx']
            extra_nodes=[n for n in extra_nodes if n in plain.domain]+local_nodes
            nl,_=netlist_for(case,sorted(set(ledger_nodes(case)+extra_nodes)),terminals)
        else:
            nl=asset['netlist'];observed=[];clamps=[]
        # The original numerical registry remains unchanged. This explicit candidate preview
        # applies the approved current 125 us path; output interval and stop remain original.
        original_analysis=case['analysis'];tokens=original_analysis.split();assert tokens[:1]==['tran'] and len(tokens)==5
        assert tokens[1]=='0.001' and tokens[3]=='0';tokens[4]='0.000125';analysis=' '.join(tokens)
        saved=list(asset['save'])
        if candidate:
            saved += ['v('+n+')' for n in sorted(nl.domain)]
            saved += ['i('+line.split()[0]+')' for line in nl.lines if line.lower().startswith('v')]
        saved=list(dict.fromkeys(x.lower() for x in saved))
        text='\n'.join(['* THERMAL-G3-v5 static preview '+cid,'.include ../software/models/c05_ekv26_typ.lib',
            nl.text(),'.options sparse method=gear reltol=1e-5 abstol=1e-16','.save '+' '.join(saved),'.control',
            'pre_osdi <OSDI>', 'set filetype=binary',analysis,'write <RAW>','quit','.endc','.end',''])
        assert analysis_preflight(text,analysis)
        assert not analysis_preflight(text.replace(analysis,analysis+' uic'),analysis)
        assert not analysis_preflight(text.replace(analysis,analysis.replace('0.001','0.000125',1)),analysis)
        assert not analysis_preflight(text.replace(analysis,analysis.replace('0.000125','0.00025')),analysis)
        assert not analysis_preflight(text.replace(analysis,analysis+'\nop'),analysis)
        els=helpers.elements(text);names=[x[0].lower() for x in els]
        assert len(names)==len(set(names))
        fl=helpers.floating(els);geom=helpers.domain(els);assert not fl,fl[:10];assert not geom,geom[:10]
        # Actual terminal nodes in instrumented decks include the ammeter inner nodes.
        actual_nodes={n.lower() for e in els for n in e[1:5 if e[0].startswith('n') else 3]}
        voltage_sources={e[0].lower() for e in els if e[0].startswith('v')}
        for vec in saved:
            if vec.startswith('v('):assert vec[2:-1] in actual_nodes,vec
            elif vec.startswith('i('):assert vec[2:-1] in voltage_sources,vec
        assert set(asset['required'])<=set(saved)
        if candidate:
            # All new devices have measured four-terminal currents and voltage observability.
            for name in observed:
                for tag in 'dgsb':assert f'i(va_{name}_{tag})' in saved
                for n in mos[name]['nodes']:assert n=='0' or 'v('+n+')' in saved
            # Every new logical electrical node receives one uniform registered C_NODE.
            new_nodes=set(plain.domain)-set(old['logical_nodes'])
            for n in new_nodes:
                par=[e for e in plain.elements if e[0]=='cpar_'+n]
                assert len(par)==1 and par[0][3]['C']==v('C_NODE'),n
            # Verify stimuli and every unchanged original primitive survive verbatim.
            normalized={' '.join(e).split()[0]:' '.join(e) for e in helpers.normalise(els)}
            changed_old=[n for n in old['normalized'] if n not in normalized or old['normalized'][n]!=normalized[n]]
            allowed=set()
            for g in groups:allowed|={g['prefix']+'sw',g['prefix']+'cp','cpar_'+g['prefix'][1:]+'x'}
            allowed|={'rvrestt','rvrestb'}
            assert set(changed_old)<=allowed,sorted(set(changed_old)-allowed)
            added=sorted(set(normalized)-set(old['normalized']));removed=sorted(set(old['normalized'])-set(normalized))
            changed=sorted(set(changed_old)-set(removed))
            write(args.out/(cid+'_DEVICE_CHANGES.json'),dict(added=added,removed=removed,changed=changed,
                baseline_MOS=len(old['mos']),candidate_MOS=len(mos),delta_MOS=len(mos)-len(old['mos']),
                original_stimuli_and_remaining_primitives_unchanged=True,original_scoring_vectors=old['original_scoring_vectors']))
        else:
            normalized={e[0]:' '.join(e) for e in helpers.normalise(els)}
            new_nodes=[]
        report=dict(case_id=cid,mos=mos,logical_nodes=sorted(plain.domain),normalized=normalized,
            original_scoring_vectors=asset['save'] if not candidate else old['original_scoring_vectors'],
            original_analysis=original_analysis,preview_analysis=analysis,save_vectors=saved,
            gated_sources=groups,clamps=clamps,observed_four_terminal_devices=observed,
            new_nodes=sorted(new_nodes),ledger_plan=plan_from_netlist(nl,ledger_nodes(case)),
            diagnostic_reference_plan=plan_from_netlist(nl,['vrest']+local_nodes) if candidate else None,
            checks=dict(no_duplicate_names=True,no_floating_nodes_in_topology_graph=True,geometry_within_card=True,
                saved_vectors_exist=True,required_vectors_saved=True,one_analysis_and_command_mutants=True),
            source_anchor_policy='Original scoring view retained separately; do not feed added por_hold into support scoring',
            dynamic_model_domain='UNMEASURED',physical_function='UNMEASURED',solver_starts=0)
        (args.out/(cid+'.cir')).write_text(text);write(args.out/(cid+'.json'),report)
        with (args.out/(cid+'_MOS.csv')).open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['name','d','g','s','b','model','W_m','L_m','mult'])
            for name,e in sorted(mos.items()):w.writerow([name,*e['nodes'],e['model'],e['W'],e['L'],e['mult']])
        summary.append(dict(case_id=cid,n_mos=len(mos),gated_source_instances=len(groups),POR_clamps=len(clamps),
            saved_vectors=len(saved),observed_four_terminal_devices=len(observed),new_electrical_nodes=len(new_nodes),static='PASS',dynamic='UNMEASURED'))
    write(args.out/'STATIC_ACCEPTANCE.json',dict(scope='Three selected decks only',cases=summary,
          no_solver_subprocess_allowed=True,new_solver_starts=0,dynamic_qualification_inherited=False))
    print(json.dumps(summary))


if __name__=='__main__':main()
