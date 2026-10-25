"""Connection invariants only. No solver, no physical performance claim.

Uses the existing inverter/parameter definitions read-only; records MOS instances
and verifies the proposed module cannot conduct directly into either shared
reference through its channel wiring. Gate/displacement coupling is not removed.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
PROJECT = Path("J:/LiYing-test/THERMAL-G3_actual_host/execution/thermal_g3_q1")
sys.path.insert(0, str(PROJECT))
from netlists.build import inverter, WELL
from netlists.params import v

prototype = ROOT / "gated_source_local_bias_prototype.py"
tree = ast.parse(prototype.read_text(encoding="utf-8"))
function = next(x for x in tree.body if isinstance(x, ast.FunctionDef))
env = dict(inverter=inverter, WELL=WELL, v=v)
exec(compile(ast.Module(body=[function], type_ignores=[]), str(prototype), "exec"), env)


class Recorder:
    def __init__(self):
        self.devices = []

    def M(self, name, d, g, s, b, model, w, l, **kwargs):
        self.devices.append(dict(name=name, d=d, g=g, s=s, b=b,
                                 model=model, W=w, L=l, parameters=kwargs))


def invariant(devices, shared_p, shared_n):
    if any(shared_p in [d[k] for k in ("d", "g", "s", "b")] for d in devices):
        return False
    for d in devices:
        if shared_n in (d["d"], d["s"], d["b"]):
            return False
    return any(d["g"] == shared_n and d["model"] == "nch" for d in devices)


results = []
for role, shared_p, shared_n, scale in (
    ("collector", "ilimp_n", "ilim_n", 1.0),
    ("spatial", "irefp_n", "iref_n", 0.5),
    ("load", "irefp_n", "iref_n", 1.0),
):
    rec = Recorder()
    env["gated_source"](rec, role + "_", shared_p, "out", "enable_b",
                        4e-6, scale=scale, reference_bias_n=shared_n)
    assert len(rec.devices) == 7
    assert invariant(rec.devices, shared_p, shared_n)
    assert all(.8e-6 <= d["W"] <= 10e-6 and .5e-6 <= d["L"] <= 10e-6
               for d in rec.devices)
    # Deliberately reconnect the selector to the old public p-bias.
    mutant = [dict(d) for d in rec.devices]
    next(d for d in mutant if d["name"] == role + "_bias")["d"] = shared_p
    assert not invariant(mutant, shared_p, shared_n)
    # Deliberately make the copied n-bias a channel terminal.
    mutant_n = [dict(d) for d in rec.devices]
    next(d for d in mutant_n if d["name"] == role + "_refn")["s"] = shared_n
    assert not invariant(mutant_n, shared_p, shared_n)
    results.append(dict(role=role, connection_invariant="PASS",
                        shared_p_reconnection_mutant_rejected=True,
                        shared_n_channel_mutant_rejected=True,
                        devices=rec.devices))

out = dict(scope="CONSTRUCTION_INVARIANTS_ONLY", new_solver_starts=0,
           prototype_sha256=hashlib.sha256(prototype.read_bytes()).hexdigest(),
           dimensions_within_declared_card_ranges=True,
           limitations=["No model-domain transient proof",
                        "MOS gate charge and supply coupling remain",
                        "No guarantee of OFF leakage, pulse charge or reference stability"],
           roles=results)
(ROOT/"construction_invariants.json").write_text(json.dumps(out, indent=2)+"\n", encoding="utf-8")
print("3 roles verified; 6 deliberate reconnection mutants rejected; solver starts: 0")
