"""DC channel-current estimates only, no SPICE/OSDI invocation.

Uses the existing project EKV static approximation (no junction currents or
dynamic charges). Solves only the old ON-state internal node by scalar root
finding; compares against the proposed steady gate bias. Does not simulate
the new gate selector, startup, OFF leakage, or reference loading.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
SOURCE = Path("J:/LiYing-test/THERMAL-G3_actual_host/execution/thermal_g3_q1/analysis/ekv26_static.py")
spec = importlib.util.spec_from_file_location("existing_ekv_static", SOURCE)
ekv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ekv)


def bisect(f, lo, hi):
    fl, fh = f(lo), f(hi)
    if fl * fh > 0:
        raise ValueError("root not bracketed")
    for _ in range(90):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm * fl > 0:
            lo, fl = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def ip(w, l, d, g, s, b):
    return -ekv.ids("pch", w, l, d, g, s, b)


rows = []
for vb, vs in ((2.7, 2.6652897827525255),
               (3.0, 2.960971126511531),
               (3.2, 3.158100525537112)):
    for iref, scale, role in ((1.2e-6, 1.0, "collector"),
                             (1.0e-6, 0.5, "spatial"),
                             (1.0e-6, 1.0, "load")):
        vg = bisect(lambda g: ip(4e-6, 4e-6, g, g, vs, vb) - iref, 0, vs)
        for frac in (0.0, 1/3, 0.5, 0.7, 0.9):
            vo = vs * frac
            w, l = 4e-6 * scale, 4e-6
            x = bisect(lambda x: ip(4e-6, 1e-6, x, 0, vs, vb)
                       - ip(w, l, vo, vg, x, vb), vo, vs)
            old_i = ip(w, l, vo, vg, x, vb)
            new_i = ip(w, l, vo, vg, vs, vb)
            rows.append(dict(vsrc_V=vb, vdd_V=vs, role=role,
                             output_V=vo, reference_gate_V=vg,
                             old_source_V=x, old_ON_channel_A=old_i,
                             new_steady_ON_channel_A=new_i,
                             relative_change=(new_i-old_i)/old_i,
                             selector_source_bulk_if_cg_equals_ref_V=abs(vg-vb)))

out = dict(scope="OFFLINE_CHANNEL_ESTIMATE_ONLY", new_solver_starts=0,
           approximation_source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
           assumptions=["Steady ON gate equals reference diode voltage",
                        "Reference current is assumed 1uA or 1.2uA, not a new measurement",
                        "Original measured DC rail values used as conditional inputs",
                        "No claim about selector transients, junction leakage or compliance qualification"],
           row_count=len(rows),
           relative_change_min=min(x["relative_change"] for x in rows),
           relative_change_max=max(x["relative_change"] for x in rows),
           selector_source_bulk_max_at_assumed_bias_V=max(x["selector_source_bulk_if_cg_equals_ref_V"] for x in rows),
           rows=rows)
(ROOT/"offline_channel_comparison.json").write_text(json.dumps(out, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({k:v for k,v in out.items() if k not in ("rows", "assumptions")}, indent=2))
