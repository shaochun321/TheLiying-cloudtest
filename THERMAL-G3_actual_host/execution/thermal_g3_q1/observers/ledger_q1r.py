"""Q1-R physical ledger observer (INFRA, read-only).

Scope (netlists/ledger_plan.py): complete KCL at the instrumented ledger nodes, using every
terminal current there (R, C including C_NODE, MOS d/g/s/b with displacement and gate currents,
sources). Gates, preregistered (v1 plan §9B numerical gates):
  kcl      binned residual charge (10 ms bins) per node, normalised by that bin's throughput
           sum|i|dt: 99th percentile <= 1e-3, peak <= 1e-2 (bins below Q_FLOOR excluded)
  energy   per node, sum over terminals of v*i integrated: |sum| <= 1 % of the total absorbed
           magnitude (KCL at a node with one voltage implies port-energy closure up to numerics)
  cap      every capacitor at the node: 0.5 C (vc_end^2 - vc_0^2) with vc its own terminal
           voltage equals the integrated terminal power within 1 % (or E_FLOOR absolute)
  supply   integrated supply energy from v(vsrc) and i(vsrc) reported (no gate)
Missing vectors -> UNMEASURED. No full-network energy closure is claimed.
"""
import numpy as np

BIN_S = 10e-3
Q_FLOOR = 1e-12       # C: bins with less throughput are not normalised
E_FLOOR = 1e-12       # J
KCL_P99, KCL_PEAK, E_REL = 1e-3, 1e-2, 1e-2


def _trap(y, t):
    return float(np.trapezoid(y, t))


def ledger(V, plan):
    t = V.get("time")
    if t is None:
        return {"result": "UNMEASURED", "why": "no time axis"}
    need = [f"v({n})" for n in plan["nodes"]] + [it["vec"] for its in plan["terms"].values() for it in its]
    miss = [x for x in need if x.lower() not in V]
    if miss:
        return {"result": "UNMEASURED", "why": f"missing {miss[:3]}"}
    out = {"nodes": {}, "scope": "KCL/charge/energy at ledger nodes only"}
    fails = []
    edges = np.arange(t[0], t[-1] + BIN_S, BIN_S)
    for n, items in plan["terms"].items():
        if not items:
            out["nodes"][n] = {"result": "UNMEASURED", "why": "no instrumented terminal"}
            fails.append(f"{n}:no terminals")
            continue
        I = np.array([it["sign"] * V[it["vec"].lower()] for it in items])     # into each element
        res = I.sum(axis=0)                                                    # KCL residual
        thr = np.abs(I).sum(axis=0)
        rel = []
        for a, b in zip(edges[:-1], edges[1:]):
            m = (t >= a) & (t <= b)
            if m.sum() < 2:
                continue
            q_thr = _trap(thr[m], t[m])
            if q_thr < Q_FLOOR:
                continue
            rel.append(abs(_trap(res[m], t[m])) / q_thr)
        rel = np.array(rel) if rel else np.array([0.0])
        vn = V[f"v({n})"]
        p_tot = np.abs(vn * I).sum(axis=0)
        e_net = _trap(vn * res, t)
        e_abs = _trap(p_tot, t)
        # each capacitor: integrated terminal power equals its stored-energy change, using the
        # capacitor's own voltage (far terminal may be another node, e.g. LOAD_C to vmid)
        cap_ok, cap_d = True, 0.0
        for it in items:
            if it["kind"] != "C" or not it["C"]:
                continue
            far = it.get("far")
            vf = 0.0 if far in (None, "0") else V.get(f"v({far})")
            if vf is None:
                cap_ok, cap_d = False, None
                break
            vc = vn - vf
            e_int = _trap(vc * it["sign"] * V[it["vec"].lower()], t)
            e_state = 0.5 * it["C"] * (vc[-1] ** 2 - vc[0] ** 2)
            d = abs(e_int - e_state)
            cap_d = max(cap_d, d)
            if d > max(E_REL * max(abs(e_state), abs(e_int)), E_FLOOR):
                cap_ok = False
        kcl_ok = float(np.percentile(rel, 99)) <= KCL_P99 and float(rel.max()) <= KCL_PEAK
        e_ok = abs(e_net) <= max(E_REL * e_abs, E_FLOOR)
        r = {"kcl_p99": float(np.percentile(rel, 99)), "kcl_peak": float(rel.max()), "kcl": bool(kcl_ok),
             "energy_net_J": e_net, "energy_abs_J": e_abs, "energy": bool(e_ok), "cap_mismatch_J": cap_d,
             "cap": bool(cap_ok),
             "n_terms": len(items)}
        r["result"] = "PASS" if (kcl_ok and e_ok and cap_ok) else "FAIL"
        if r["result"] != "PASS":
            fails.append(n)
        out["nodes"][n] = r
    if "v(vsrc)" in V and "i(vsrc)" in V:
        out["supply_energy_J"] = -_trap(V["v(vsrc)"] * V["i(vsrc)"], t)
    out["fails"] = fails
    out["result"] = "PASS" if not fails else "FAIL"
    return out


def model_domain(V, mos_nodes, vs_max=2.0, vgd_max=3.3):
    """|Vsb| < 2 V and |Vgb|, |Vdb| < 3.3 V (C05 card validity) for MOS whose four terminal
    node voltages are all saved; returns coverage."""
    bad, covered = [], 0
    for name, (d, g, s, b) in mos_nodes.items():
        keys = [f"v({x})" if x != "0" else None for x in (d, g, s, b)]
        vals = []
        for k in keys:
            if k is None:
                vals.append(0.0)
            elif k in V:
                vals.append(V[k])
            else:
                vals = None
                break
        if vals is None:
            continue
        covered += 1
        vd, vg, vs, vb = vals
        if np.max(np.abs(np.asarray(vs) - vb)) >= vs_max or np.max(np.abs(np.asarray(vg) - vb)) >= vgd_max \
                or np.max(np.abs(np.asarray(vd) - vb)) >= vgd_max:
            bad.append(name)
    return {"covered": covered, "total": len(mos_nodes), "outside": bad[:20],
            "result": "PASS" if covered and not bad else ("UNMEASURED" if not covered else "FAIL")}
