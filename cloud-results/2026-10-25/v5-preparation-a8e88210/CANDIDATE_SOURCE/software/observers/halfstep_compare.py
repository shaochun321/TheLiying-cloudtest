"""Q1-R half-step comparison (INFRA, read-only). Q1 proposal §4 / v1.1 NUM gate.

Baseline and half-step runs have the same netlist and stimulus; only the analysis max step
differs (checked by tools/static_check.py). Roles are given by an explicit map
[{"core": <core prefix>, "port": <occurrence-port prefix>, "rdis": <ohm>}, ...] because the formal
collector core (gw1_col_) and its port (gw1_op_) use different prefixes.
Gates:
  events  per role, nodes core q, port op_aq, port op_p: identical counts and order of rising
          edges; matching edge times within max(2 x larger max step, 1e-4 s)
  charge  reset-branch charge (Rdis carries (vmd - vrest)/Rdis) per role and every listed branch
          ammeter: |dQ| <= 1 % of max(|Q|, Q_floor)
  peaks   per role, core vm / h / rec and port op_at: |d peak| <= 1 % of max(|peak|, V_floor)
Near-zero floors fixed in advance: Q_floor = 1e-9 C, V_floor = 10 mV. Any missing vector ->
UNMEASURED (never an exception).
"""
import numpy as np

from .observers_q1r import check_axis, edges

Q_FLOOR = 1e-9
V_FLOOR = 0.010
REL = 0.01


def required_for(roles, ammeters=()):
    v = ["v(vrest)"]
    for r in roles:
        c, p = r["core"], r["port"]
        v += [f"v({c}{n})" for n in ("q", "vm", "h", "rec", "vmd")] + [f"v({p}{n})" for n in ("aq", "p", "at")]
    return v + [a.lower() for a in ammeters]


def compare(Va, Vb, roles, ammeters, max_step_a, max_step_b):
    for V in (Va, Vb):
        e = check_axis(V)
        if e:
            return {"result": "UNMEASURED", "why": e}
    need = required_for(roles, ammeters)
    for tag, V in (("baseline", Va), ("halfstep", Vb)):
        miss = [n for n in need if n not in V]
        if miss:
            return {"result": "UNMEASURED", "why": f"{tag} missing {miss[:3]}"}
    ta, tb = Va["time"], Vb["time"]
    tol_t = max(2 * max(max_step_a, max_step_b), 1e-4)
    out = {"events": {}, "charge": {}, "peaks": {}}
    fails = []
    for r in roles:
        c, p = r["core"], r["port"]
        for n in (f"v({c}q)", f"v({p}aq)", f"v({p}p)"):
            ua, _ = edges(ta, Va[n], 1.5)
            ub, _ = edges(tb, Vb[n], 1.5)
            same = len(ua) == len(ub) and (len(ua) == 0 or np.max(np.abs(ua - ub)) <= tol_t)
            out["events"][n] = {"a": len(ua), "b": len(ub), "same": bool(same),
                                "max_dt": float(np.max(np.abs(ua - ub))) if len(ua) == len(ub) and len(ua) else None}
            if not same:
                fails.append(f"events {n}")
        for n in (f"v({c}vm)", f"v({c}h)", f"v({c}rec)", f"v({p}at)"):
            pa, pb = float(np.max(Va[n])), float(np.max(Vb[n]))
            ok = abs(pa - pb) <= REL * max(abs(pa), abs(pb), V_FLOOR)
            out["peaks"][n] = {"a": pa, "b": pb, "ok": bool(ok)}
            if not ok:
                fails.append(f"peak {n}")
        qa = float(np.trapezoid((Va[f"v({c}vmd)"] - Va["v(vrest)"]) / r["rdis"], ta))
        qb = float(np.trapezoid((Vb[f"v({c}vmd)"] - Vb["v(vrest)"]) / r["rdis"], tb))
        ok = abs(qa - qb) <= REL * max(abs(qa), abs(qb), Q_FLOOR)
        out["charge"][f"{c}reset"] = {"a": qa, "b": qb, "ok": bool(ok)}
        if not ok:
            fails.append(f"charge {c}reset")
    for name in ammeters:
        n = name.lower()
        qa, qb = float(np.trapezoid(Va[n], ta)), float(np.trapezoid(Vb[n], tb))
        ok = abs(qa - qb) <= REL * max(abs(qa), abs(qb), Q_FLOOR)
        out["charge"][n] = {"a": qa, "b": qb, "ok": bool(ok)}
        if not ok:
            fails.append(f"charge {n}")
    out["fails"] = fails
    out["result"] = "PASS" if not fails else "FAIL"
    return out
