"""Copy a readable baseline and integrate cited v2 + unqualified local-bias proposal.

No solver invocation; no freeze, authorization or prior qualification is inherited.
"""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True)
    ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();base=args.baseline;ref=args.reference;out=args.out
    out.mkdir(exist_ok=False)
    names=[]
    for folder in ['netlists','observers','solver_adapter','analysis']:
        names += [p.relative_to(base) for p in (base/folder).glob('*') if p.suffix in ['.py','.json']]
    names += [Path(p) for p in ['runtime/__init__.py','runtime/decks.py','config.py','models/c05_ekv26_typ.lib',
                               'prereg/cases_q1r.json','prereg/protocol_q1r_joint.json']]
    before={str(p):sha(base/p) for p in sorted(names)}
    for name in names:
        dst=out/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/name,dst)
    # These two actual historical source files were independently recovered by Git blob ID.
    for name in ['neuron_nrc.py','params.py']:
        shutil.copyfile(ref/'v2-targeted-reference/candidate-source/netlists'/name,out/'netlists'/name)
    prototype=ref/'design_reference/gated_source_local_bias_prototype.py'
    text=prototype.read_text();node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef))
    function='\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])+'\n'
    p=out/'netlists/bundle_physical.py';old=p.read_text();idx=old.index('def gated_source(')
    p.write_text(old[:idx]+function)
    def edit(name,old,new):
        p=out/name;s=p.read_text();assert s.count(old)==1,(name,old);p.write_text(s.replace(old,new))
    edit('netlists/build_thermal_g3.py',
         'gated_source(nl, p + "cin_", "ilimp_n", col["vm"], p + "gb", W=v("BIAS_W"))',
         'gated_source(nl, p + "cin_", "ilimp_n", col["vm"], p + "gb", W=v("BIAS_W"), reference_bias_n="ilim_n")')
    edit('netlists/build_thermal_g3.py','W=v("BIAS_W"))\n    # element-name collision guard',
         'W=v("BIAS_W"), reference_bias_n="iref_n")\n    # element-name collision guard')
    edit('netlists/spatial_graph.py','W=v("BIAS_W"), scale=v("SP_INJ_N"))',
         'W=v("BIAS_W"), scale=v("SP_INJ_N"), reference_bias_n="iref_n")')
    edit('netlists/bench_mother.py',
         'for lab, diode, Wc, Lc in (("weak", "irefp_n", 1.2e-6, 4e-6), ("valid", "irefp_n", 4e-6, 4e-6),\n                               ("max", "ilimp_n", 4e-6, 4e-6)):',
         'for lab, diode, bias_n, Wc, Lc in (("weak", "irefp_n", "iref_n", 1.2e-6, 4e-6), ("valid", "irefp_n", "iref_n", 4e-6, 4e-6),\n                               ("max", "ilimp_n", "ilim_n", 4e-6, 4e-6)):')
    edit('netlists/bench_mother.py','f"{p}g{lab}", W=Wc, L=Lc)',
         'f"{p}g{lab}", W=Wc, L=Lc, reference_bias_n=bias_n)')
    edit('runtime/decks.py','OPTIONS = "klu method=gear reltol=1e-5 abstol=1e-16"',
         'OPTIONS = "sparse method=gear reltol=1e-5 abstol=1e-16"')
    # All construction callsites must explicitly declare the n-bias wiring.
    callsites=[]
    for p in sorted((out/'netlists').glob('*.py')):
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='gated_source':
                assert any(k.arg=='reference_bias_n' for k in n.keywords)
                callsites.append(dict(file=str(p.relative_to(out)),line=n.lineno,source=ast.get_source_segment(p.read_text(),n)))
    assert len(callsites)==4
    diffs=[];changes=[]
    for rel in sorted(names):
        p=out/rel
        if sha(p)!=before[str(rel)]:
            changes.append(str(rel));diffs+=list(difflib.unified_diff((base/rel).read_text().splitlines(True),p.read_text().splitlines(True),fromfile='baseline/'+str(rel),tofile='candidate/'+str(rel)))
    for rel in names:assert sha(base/rel)==before[str(rel)],'Baseline changed'
    (out.parent/'baseline-to-v5.diff').write_text(''.join(diffs))
    (out.parent/'SOURCE_IDENTITY.json').write_text(json.dumps(dict(candidate='THERMAL-G3-v5',status='PREPARED_UNQUALIFIED',
        baseline_path=str(base),baseline_sha256=before,candidate_sha256={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},
        changed_files=changes,explicit_call_sites=callsites,baseline_unchanged=True,
        v2_actual_source_retrieval=json.loads((ref/'v2-targeted-reference/RETRIEVAL.json').read_text()),
        local_bias_prototype_sha256=sha(prototype),new_solver_starts=0,global_count='54/84',
        old_v4_source_recovered=False,old_qualification_inherited=False,solver_execution_entrypoints_copied=False),indent=2)+'\n')
    print(json.dumps({'changed_files':changes,'explicit_reference_call_sites':len(callsites),'status':'PREPARED_UNQUALIFIED'}))


if __name__=='__main__':main()
