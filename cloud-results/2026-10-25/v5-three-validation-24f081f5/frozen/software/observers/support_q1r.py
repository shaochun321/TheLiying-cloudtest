"""Q1-R relation support and consumption semantics (INFRA, read-only observer).

Review 2026-10-10 (limited supplement §2): every relation event must be supported by the
circuit quantities that physically cause it; first-event ordering is not enough. Scored for
EVERY q event of every relation core of an edge (Θ / Σ / Cdir, both directions), from saved
node voltages, the injector branch currents (ledger terms or targeted probes, see
netlists/ledger_plan.py injection()) and the certificate. No order between Θ and Σ is imposed;
an event may follow its support with the finite comparator delay D_CMP; one canonical pulse per
activity entry, not per q.

Support of one event at t_q of core X (membrane Cm + C_NODE to ground, Rm to vrest; review
2026-10-17 §4.1-4.2, see score_events for the exact account):
  cause interval   a maximal interval where X's cause predicate holds (below); the event uses
                   the latest cause interval starting before t_q, and t_q <= its end + D_CMP
  account          ONE continuous signed charge account on the vm node from the physical anchor
                   (POR release if por_hold is saved, else the record start), never reset at cause
                   gaps, q falls or local minima; every vm terminal current is measured (CHAIN and
                   FULL both instrument the relation vm nodes); I_in injectors, I_sh kh (out of
                   vm), I_leak Rm, I_other reset / recovery / POR / comparator gate
  supported state  X: the same capacitor equation with the injection gated by the dilated cause;
                   shunt / discharge / leak act on the supported charge first; vm - vrest - X/Cm
                   is charge without a supported source (preload outside support, no-source state)
  event            supported iff the membrane rose since the last q fall (or anchor); the account
                   closes (|residual| <= TOL x throughput); the stretch is net-charged (Q_in -
                   Q_sh - Q_leak - Q_other >= (1-TOL) Cm dvm); and X(t_q) >= (1-TOL) Cm (vm - vrest)
                   at entry. Missing ledger -> UNMEASURED (never zero-filled). No hc voltage label,
                   no fixed shunt ratio: the measured shunt simply enters the account.
Cause predicates (all from saved vectors; thresholds below):
  Θ_d    source history h_src >= H_GATE and target G0 op_aq high (the stack: history gate AND
         activity gate); the event additionally needs h_src >= H_VALID within [a, t_q], and the
         last rise of h_src through H_VALID after a source collector q
  Σ_d    signed spatial difference (f: sp_i - sp_s_ik, r: sp_s_ik - sp_i; inverted for the
         declared sigma_readout_swap variant) >= V_FLOOR, starting inside a G0 activity of
         either site (the spatial injection is gated by G0 op_aqb); I_in = OTA m4 + m2 net
  Cdir_d matching history hs >= H_GATE and Θ_d op_aq high; the event needs hs >= H_VALID in
         [a, t_q]; every rise of hs through H_GATE lies inside a matching Σ_d activity
         (extended by the history RC time HIST_TAU)
Conflict (Cdir_d): the measured kh shunt enters every event's account (above), whatever hc is.
  Source consistency: every rise of hc through H_GATE lies in an opposite-Σ activity (history RC
  time), and outward shunt charge drawn outside its gate sources (hc >= H_GATE AND Θ_d op_aq) is
  <= TOL x injected charge + I_LEAK x run time.
Canonical port (each relation core and each G0 of the edge): every op_aq rise follows a q
  rise within D_PORT; every q rise lies in an op_aq interval or is followed by an op_aq rise
  within D_PORT; each op_aq interval holds exactly one op_p rise; no op_p outside op_aq.
Consumption (Cdir_d -> rail, pos for f, neg for r): inside each Cdir_d op_aq interval the path
  current (aggregation source nag..._cp into the rail) has median >= (1 - TOL) Iref and the
  rail reaches >= (1 - TOL) Iref LOAD_R (1 - exp(-T/tau_L)) above vmid (other paths on the same
  rail may hold it higher; each path's own current is checked separately); outside the path's activity the
  path charge is <= TOL x inside charge + I_LEAK x run time.
Thresholds (preregistered here): H_VALID = certificate history_levels_V.valid_entry_min;
H_GATE = H_VALID / 2 (history clearly charged); V_FLOOR = 10 mV (criteria_q1r); TOL = 0.10
(MIRROR_TOL of the original contract); D_CMP = 2 max_step + 1 ms (contract edge tolerance);
D_PORT = 5 OP_RC OP_C + D_CMP; HIST_TAU = HIST_RR HIST_C1 + HIST_R2 HIST_C2; I_LEAK = 10 pA.
Missing vectors -> UNMEASURED; nothing is defaulted.
"""
import json
import math
import os
import sys

import numpy as np

from .observers_q1r import edges
from .criteria_q1r import V_FLOOR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P, F, U = "PASS", "FAIL", "UNMEASURED"
TOL = 0.10
EDGE_TOL_S = 1e-3
I_LEAK = 10e-12


def _v(name):
    sys.path.insert(0, ROOT)
    from netlists.params import v
    return v(name)


def consts(case, cert):
    max_step = case.get("max_step_s", 0.5e-3)
    d_cmp = 2 * max_step + EDGE_TOL_S
    hv = cert["nom"]["history_levels_V"]["valid_entry_min"]
    return {"H_VALID": hv, "H_GATE": 0.5 * hv, "V_FLOOR": V_FLOOR, "TOL": TOL, "D_CMP": d_cmp,
            "D_PORT": 5 * _v("OP_RC") * _v("OP_C") + d_cmp,
            "HIST_TAU": _v("HIST_RR") * _v("HIST_C1") + _v("HIST_R2") * _v("HIST_C2"),
            "TAU_L": _v("LOAD_R") * _v("LOAD_C"), "Iref": cert["nom"]["refs"]["Iref"]}


# ------------------------------------------------------------------ interval helpers
def intervals(t, mask):
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    d = np.diff(m.astype(int))
    starts = list(np.where(d == 1)[0] + 1)
    ends = list(np.where(d == -1)[0])
    if m[0]:
        starts = [0] + starts
    if m[-1]:
        ends = ends + [len(m) - 1]
    return [(float(t[a]), float(t[b])) for a, b in zip(starts, ends)]


def dilate(t, ivs, pre, post):
    m = np.zeros_like(t, dtype=bool)
    for a, b in ivs:
        m |= (t >= a - pre) & (t <= b + post)
    return m


def in_any(x, ivs, pre=0.0, post=0.0):
    return any(a - pre <= x <= b + post for a, b in ivs)


def _trap(y, t, a, b):
    m = (t >= a) & (t <= b)
    return float(np.trapezoid(y[m], t[m])) if m.sum() > 1 else 0.0


def _high(V, name, thr):
    return V[name] > thr


# ------------------------------------------------------------------ one event
def _cumtrap(y, t):
    out = np.zeros_like(t, dtype=float)
    out[1:] = np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))
    return out


def anchor_time(V, t, vm, vrest, k):
    """Physical initial state: the end of POR hold (every membrane shunted to vrest by the
    POR NMOS while por_hold is high), if por_hold was saved; else the record start (an initial
    membrane state that is not at vrest is then charged against support, never assumed)."""
    if "v(por_hold)" in V:
        thr = float(np.median(V["v(vdd)"])) / 2
        hi = np.where(V["v(por_hold)"] > thr)[0]
        if len(hi):
            return float(t[hi[-1]]), "por_hold release"
    return float(t[0]), "record start"


def score_events(V, core, cause, i_in, cm, u_entry, k, extra=None, ledger=None, i_sh=None):
    """All q events of `core` scored by ONE continuous signed charge account on the vm node.

    cause   boolean mask of the core's cause predicate; i_in injected current INTO vm (A);
    ledger  membrane_ledger() groups (complete terminal set of the vm node); i_sh (shunt, positive
            OUT of vm) is used only when no ledger is given; extra(t_q, a) -> (ok, why) adds
            the role-specific history condition.

    Charge account (review 2026-10-17 §4.1-4.2). From the physical anchor A (POR release, or
    record start) the net external current into vm is
        I_ext = I_in - I_sh - I_leak - I_other      (I_leak = (vm - vrest)/Rm through Rm)
    and the capacitor equation Cm dvm = I_ext dt (Cm incl. C_NODE) is integrated, never reset at
    cause gaps, q falls or local minima. The supported part of the state evolves by the same
    linear equation with the injection gated by the dilated cause:
        Cm dX/dt = I_in*cause - I_sh - I_other - X/Rm,   X(A) = Cm (vm(A) - vrest) if A is the POR
    release (an established reset), else 0 (unproven preload counts as unsupported).
    Discharge, shunt and leak act on the supported charge first (X >= 0; a branch cannot remove
    charge that is not there); vm(t) - vrest - X(t)/Cm is the unsupported state.
    Per event at t_q: Q_in, Q_sh, Q_leak, Q_other, Q_cap = Cm (vm(t_q) - vm(A)) over [A, t_q] and
    over the latest stretch [a', t_q] (a' = last q fall or A); residual = Q_in - Q_sh - Q_leak -
    Q_other - Q_cap (ledger: measured; no ledger: I_other UNMEASURED -> the event is UNMEASURED,
    never zero-filled). The event is supported iff
        the membrane rose over [a', t_q];
        |residual| <= TOL x throughput (sum |I| over [A, t_q]) -- the account closes;
        X(t_q)/Cm >= (1 - TOL)(vm(t_q) - vrest) -- the entry state is supported charge;
        the stretch is net-charged: Q_in - Q_sh - Q_leak - Q_other over [a', t_q] >= (1-TOL) Q_cap there.
    """
    t = V["time"]
    thr = float(np.median(V["v(vdd)"])) / 2
    vrest_t = V["v(vrest)"]
    vm = V[f"v({core}vm)"]
    up, dn = edges(t, V[f"v({core}q)"], thr)
    civ = intervals(t, cause)
    cdil = dilate(t, civ, k["D_CMP"], k["D_CMP"])
    Rm = _v("NM_RM")
    if ledger is not None:
        g = ledger
        I_in, I_sh, I_leak, I_other = g["in"], g["sh"], g["leak"], g["other"]
        cm_tot = cm + _v("C_NODE")
        scope = "complete vm ledger node"
    else:
        I_in = i_in
        I_sh = i_sh if i_sh is not None else np.zeros_like(t)
        I_leak = (vm - vrest_t) / Rm
        I_other = None
        cm_tot = cm
        scope = "injector probes only"
    A, why_A = anchor_time(V, t, vm, vrest_t, k)
    iA = int(np.searchsorted(t, A))
    out = []
    if I_other is None:
        for tq in up:
            out.append({"t_q": float(tq), "ok": None, "unmeasured": True,
                        "why": "membrane branches other than injector / shunt not measured at vm"})
        return out
    # supported state X (charge above vrest that is attributable to supported injection)
    drive = I_in * cdil - I_sh - I_other
    X = np.zeros_like(t, dtype=float)
    X[iA] = cm_tot * (vm[iA] - vrest_t[iA]) if why_A == "por_hold release" else 0.0
    for n in range(iA + 1, len(t)):
        dt = t[n] - t[n - 1]
        x = X[n - 1] + (0.5 * (drive[n] + drive[n - 1]) - X[n - 1] / (Rm * cm_tot)) * dt
        X[n] = min(max(x, 0.0), cm_tot * max(vm[n] - vrest_t[n], 0.0))
    c_in, c_sh, c_lk, c_ot = (_cumtrap(y, t) for y in (I_in, I_sh, I_leak, I_other))
    c_supported = _cumtrap(I_in * cdil, t)
    c_abs = _cumtrap(np.abs(I_in) + np.abs(I_sh) + np.abs(I_leak) + np.abs(I_other), t)

    def acc(a, b):
        ia, ib = int(np.searchsorted(t, a)), int(np.searchsorted(t, b))
        ib = min(ib, len(t) - 1)
        q = {"Q_in_C": c_in[ib] - c_in[ia], "Q_sh_C": c_sh[ib] - c_sh[ia], "Q_leak_C": c_lk[ib] - c_lk[ia],
             "Q_other_C": c_ot[ib] - c_ot[ia], "Q_cap_C": cm_tot * (vm[ib] - vm[ia])}
        q["Q_net_C"] = q["Q_in_C"] - q["Q_sh_C"] - q["Q_leak_C"] - q["Q_other_C"]
        q["residual_C"] = q["Q_net_C"] - q["Q_cap_C"]
        q["throughput_C"] = c_abs[ib] - c_abs[ia]
        q["Q_in_supported_C"] = c_supported[ib] - c_supported[ia]
        q["Q_in_outside_support_C"] = q["Q_in_C"] - q["Q_in_supported_C"]
        return {kk: float(v) for kk, v in q.items()}, ib

    def source_ledger(iq):
        """Trace every supported stretch AND intervening gap; X is never reinitialised here."""
        changes = np.where(cdil[1:] != cdil[:-1])[0] + 1
        cuts = [iA] + [int(n) for n in changes if iA < n < iq] + [iq]
        segments = []
        for ia, ib in zip(cuts[:-1], cuts[1:]):
            if ib <= ia:
                continue
            q, _ = acc(float(t[ia]), float(t[ib]))
            segments.append({"start_s": float(t[ia]), "end_s": float(t[ib]),
                             "cause_with_tolerance": bool(cdil[ia]), "account": q,
                             "supported_state_start_V": float(X[ia] / cm_tot),
                             "supported_state_end_V": float(X[ib] / cm_tot)})
        return segments

    for tq in up:
        ev = {"t_q": float(tq), "scope": scope, "anchor_s": A, "anchor": why_A}
        prev_fall = max([d for d in dn if d < tq], default=None)
        a_str = max(prev_fall, A) if prev_fall is not None else A
        cands = [(a, b) for a, b in civ if a <= tq and b >= a_str - k["D_CMP"]]
        if not cands:
            ev.update(ok=False, why="no cause interval before the event")
            out.append(ev)
            continue
        a, b = cands[-1]
        if tq > b + k["D_CMP"]:
            ev.update(ok=False, why=f"entry {tq - b:.4f} s after the cause interval ended")
            out.append(ev)
            continue
        tot, iq = acc(A, tq)
        st, _ = acc(a_str, tq)
        u_q = float(vm[iq] - vrest_t[iq])
        sup_V = float(X[iq] / cm_tot)
        rose = st["Q_cap_C"] > 0
        closes = abs(tot["residual_C"]) <= k["TOL"] * max(tot["throughput_C"], 1e-30)
        supported_state = sup_V >= (1 - k["TOL"]) * u_q
        net_charged = st["Q_net_C"] >= (1 - k["TOL"]) * st["Q_cap_C"]
        ok_x, why_x = extra(tq, a) if extra else (True, "")
        why = []
        if not rose:
            why.append("membrane did not rise")
        if not closes:
            why.append(f"charge account does not close (residual {tot['residual_C']:.3e} C of throughput "
                       f"{tot['throughput_C']:.3e} C)")
        if not net_charged:
            why.append(f"net charge {st['Q_net_C']:.3e} C does not account for the rise {st['Q_cap_C']:.3e} C "
                       f"(Q_in {st['Q_in_C']:.3e}, Q_sh {st['Q_sh_C']:.3e})")
        if not supported_state:
            why.append(f"entry state not supported: supported {sup_V:.4f} V of {u_q:.4f} V above vrest "
                       f"(charge outside support / without source)")
        if why_x:
            why.append(why_x)
        ev.update(ok=bool(rose and closes and net_charged and supported_state and ok_x), cause=[a, b],
                  stretch_start_s=a_str, u_entry_state_V=u_q, supported_state_V=sup_V,
                  checks={"membrane_rose": bool(rose), "account_closes": bool(closes),
                          "net_charge_sufficient": bool(net_charged),
                          "retained_state_supported": bool(supported_state), "source_history_valid": bool(ok_x)},
                  account_from_anchor=tot, account_stretch=st, source_ledger=source_ledger(iq),
                  account_sample_s=float(t[iq]), why="; ".join(why))
        out.append(ev)
    return out


def _gate(evs_by_core, unmeasured=None):
    if unmeasured:
        return {"result": U, "why": unmeasured}
    bad = {c: [e for e in evs if e["ok"] is False] for c, evs in evs_by_core.items()}
    bad = {c: e for c, e in bad.items() if e}
    unm = {c: [e for e in evs if e["ok"] is None] for c, evs in evs_by_core.items()}
    unm = {c: e for c, e in unm.items() if e}
    n = sum(len(e) for e in evs_by_core.values())
    res = F if bad else (U if unm else P)
    return {"result": res, "n_events": n,
            "unsupported": {c: e[:3] for c, e in bad.items()},
            "unmeasured": {c: e[:3] for c, e in unm.items()},
            "events": evs_by_core}


# ------------------------------------------------------------------ ports and load
def port_check(V, qn, aqn, pn, k):
    t = V["time"]
    thr = float(np.median(V["v(vdd)"])) / 2
    qu, _ = edges(t, V[qn], thr)
    au, ad = edges(t, V[aqn], thr)
    pu, _ = edges(t, V[pn], thr)
    aiv = intervals(t, V[aqn] > thr)
    why = []
    for x in au:
        if not any(x - k["D_PORT"] <= q <= x + EDGE_TOL_S for q in qu):
            why.append(f"activity rise {x:.4f} s without a q before it")
    for q in qu:
        if not (in_any(q, aiv, EDGE_TOL_S, EDGE_TOL_S) or any(q <= x <= q + k["D_PORT"] for x in au)):
            why.append(f"q {q:.4f} s without activity")
    for a, b in aiv:
        n = sum(1 for p in pu if a - EDGE_TOL_S <= p <= b + EDGE_TOL_S)
        if n != 1:
            why.append(f"activity [{a:.3f}, {b:.3f}] holds {n} canonical pulses")
    for p in pu:
        if not in_any(p, aiv, EDGE_TOL_S, EDGE_TOL_S):
            why.append(f"pulse {p:.4f} s outside activity")
    return why


def load_check(V, plan, rail, path_elem, aq_name, k):
    t = V["time"]
    thr = float(np.median(V["v(vdd)"])) / 2
    it = next((x for x in plan.get("terms", {}).get(rail, []) if x["element"] == path_elem), None)
    if it is None or it["vec"].lower() not in V:
        return None, f"path current {path_elem} not measured"
    i_path = -it["sign"] * V[it["vec"].lower()]             # out of the source into the rail
    aiv = intervals(t, V[aq_name] > thr)
    why = []
    vmid = V["v(vmid)"]
    for a, b in aiv:
        m = (t >= a + k["D_CMP"]) & (t <= b - k["D_CMP"])
        med = float(np.median(i_path[m])) if m.sum() else 0.0
        if med < (1 - k["TOL"]) * k["Iref"]:
            why.append(f"path current {med:.3e} A in activity [{a:.3f}, {b:.3f}] below (1-TOL) Iref")
        need = (1 - k["TOL"]) * k["Iref"] * _v("LOAD_R") * (1 - math.exp(-(b - a) / k["TAU_L"]))
        r1 = float(np.max((V[f"v({rail})"] - vmid)[(t >= a) & (t <= b + k["D_CMP"])]))
        if r1 < need:
            why.append(f"rail above vmid {r1:.4f} V in [{a:.3f}, {b:.3f}] below {need:.4f} V")
    inside = dilate(t, aiv, k["D_CMP"], k["D_CMP"])
    q_in = float(np.trapezoid(np.abs(i_path) * inside, t))
    q_out = float(np.trapezoid(np.abs(i_path) * ~inside, t))
    if q_out > k["TOL"] * q_in + I_LEAK * float(t[-1] - t[0]):
        why.append(f"path charge outside Cdir activity {q_out:.3e} C (inside {q_in:.3e} C)")
    return why, None


def rail_quiet_check(V, rail, aq_names, k, rr, flat_frac):
    """The rail does not rise outside every Cdir activity feeding it (plus 5 tau_L decay)."""
    t = V["time"]
    thr = float(np.median(V["v(vdd)"])) / 2
    ivs = [iv for n in aq_names for iv in intervals(t, V[n] > thr)]
    allowed = dilate(t, ivs, k["D_CMP"], 5 * k["TAU_L"])
    rise = (V[f"v({rail})"] - V["v(vmid)"])[~allowed]
    mx = float(np.max(rise)) if len(rise) else 0.0
    return mx <= flat_frac * rr, mx


# ------------------------------------------------------------------ one edge (6 cores)
def edge_support(V, plan, case, cert, pol, i, k_, swap=False, rr=None, flat_frac=0.1):
    """Support / conflict / port / consumption gates for edge (i, k_) of polarity pol."""
    sys.path.insert(0, ROOT)
    from netlists.ledger_plan import injection, membrane_ledger
    K = consts(case, cert)
    t = V["time"]
    thr = float(np.median(V["v(vdd)"])) / 2
    roles = cert["nom"]["roles"]
    e = f"{i}{k_}"
    need = ["v(vdd)", "v(vrest)", "v(vmid)", f"v(h{pol}{i})", f"v(h{pol}{k_})", f"v(sp{pol}{i})", f"v(sp{pol}s{e})"]
    for s in (i, k_):
        need += [f"v(g{pol}{s}_col_q)", f"v(g{pol}{s}_op_aq)", f"v(g{pol}{s}_op_p)"]
    for d in ("f", "r"):
        for kd in ("th", "sg", "cd"):
            need += [f"v({kd}{pol}{e}{d}_{n})" for n in ("vm", "q", "op_aq", "op_p")]
        need += [f"v(cd{pol}{e}{d}_hs)", f"v(cd{pol}{e}{d}_hc)"]
    miss = [n for n in need if n not in V]
    gates = {}
    names = ("theta_support_all_events", "sigma_spatial_support_all_events", "cdir_hs_from_matching_sigma",
             "cdir_support_all_events", "cdir_conflict_consistent", "ports_canonical", "load_consumed_in_cdir_activity")
    if miss:
        return {g: {"result": U, "why": f"missing {miss[:3]}"} for g in names}
    hv, hg = K["H_VALID"], K["H_GATE"]
    g0aq = {s: _high(V, f"v(g{pol}{s}_op_aq)", thr) for s in (i, k_)}
    g0aq_iv = [iv for s in (i, k_) for iv in intervals(t, g0aq[s])]
    col_up = {s: edges(t, V[f"v(g{pol}{s}_col_q)"], thr)[0] for s in (i, k_)}

    # ---------------- Θ
    th_ev, unm = {}, None
    for d in ("f", "r"):
        src, tgt = (i, k_) if d == "f" else (k_, i)
        core = f"th{pol}{e}{d}_"
        h = V[f"v(h{pol}{src})"]
        i_in, _ = injection(V, plan, core)
        if i_in is None:
            unm = f"injection of {core} not measured"
            break
        cause = (h >= hg) & g0aq[tgt]

        def x_th(tq, a, h=h, src=src):
            m = (t >= a) & (t <= tq)
            if not m.any() or float(np.max(h[m])) < hv:
                return False, "source history below the valid level"
            hu, _ = edges(t, h, hv)
            last = [x for x in hu if x <= tq]
            if (float(h[0]) < hv and not last) or (last and not any(c <= last[-1] + EDGE_TOL_S for c in col_up[src])):
                return False, "source history not formed by a source collector event"
            return True, ""
        th_ev[core] = score_events(V, core, cause, i_in, _v("NM_CM_THETA_CDIR"), roles["Theta_Cdir"]["u_entry_V"], K, x_th,
                                   ledger=membrane_ledger(V, plan, core))
    gates["theta_support_all_events"] = _gate(th_ev, unm)

    # ---------------- Σ
    sg_ev, unm = {}, None
    diff_f = V[f"v(sp{pol}{i})"] - V[f"v(sp{pol}s{e})"]
    for d in ("f", "r"):
        core = f"sg{pol}{e}{d}_"
        sd = diff_f if (d == "f") != swap else -diff_f
        i_in, _ = injection(V, plan, core)
        if i_in is None:
            unm = f"injection of {core} not measured"
            break
        cause = sd >= K["V_FLOOR"]

        def x_sg(tq, a):
            if not in_any(a, g0aq_iv, K["D_CMP"], K["D_CMP"]):
                return False, "spatial difference not raised by a G0 activity"
            return True, ""
        sg_ev[core] = score_events(V, core, cause, i_in, _v("NM_CM"), roles["Sigma"]["u_entry_V"], K, x_sg,
                                   ledger=membrane_ledger(V, plan, core))
        if not np.any(cause):
            for ev in sg_ev[core]:
                ev.update(ok=False, why="spatial nodes equipotential (|difference| < V_FLOOR throughout)")
    gates["sigma_spatial_support_all_events"] = _gate(sg_ev, unm)

    # ---------------- Cdir
    cd_ev, hs_ev, conf_why, unm = {}, {}, [], None
    for d in ("f", "r"):
        core = f"cd{pol}{e}{d}_"
        hs, hc = V[f"v({core}hs)"], V[f"v({core}hc)"]
        th_aq = _high(V, f"v(th{pol}{e}{d}_op_aq)", thr)
        sig_aq_iv = intervals(t, _high(V, f"v(sg{pol}{e}{d}_op_aq)", thr))
        hu, _ = edges(t, hs, hg)
        hs_ev[core] = [{"t_q": float(x), "ok": in_any(x, sig_aq_iv, K["D_CMP"], K["HIST_TAU"]),
                        "why": "hs rose without a matching Σ activity"} for x in hu]
        i_in, i_sh = injection(V, plan, core)
        if i_in is None or i_sh is None:
            unm = f"injection / shunt of {core} not measured"
            break
        cause = (hs >= hg) & th_aq

        def x_cd(tq, a, hs=hs):
            m = (t >= a) & (t <= tq)
            if not m.any() or float(np.max(hs[m])) < hv:
                return False, "matching history below the valid level"
            return True, ""
        led = membrane_ledger(V, plan, core)
        if led is not None:
            i_sh = led["sh"]          # the complete vm ledger is the authoritative shunt measurement
        # the measured shunt enters every event's charge account (score_events); no hc label gate
        cd_ev[core] = score_events(V, core, cause, i_in, _v("NM_CM_THETA_CDIR"), roles["Theta_Cdir"]["u_entry_V"], K, x_cd,
                                   ledger=led, i_sh=i_sh)
        # conflict source consistency: the shunt kh is gated by the conflicting-Σ history hc AND Θ
        # (kp); outward shunt charge drawn while either gate source is absent has no conflict
        # source. Gate sources from saved vectors: hc rose through H_GATE inside an opposite-Σ
        # activity (history RC) and Θ_d op_aq high.
        dn_ = "r" if d == "f" else "f"
        opp_iv = intervals(t, _high(V, f"v(sg{pol}{e}{dn_}_op_aq)", thr))
        hcu, _ = edges(t, hc, hg)
        bad_hc = [float(x) for x in hcu if not in_any(x, opp_iv, K["D_CMP"], K["HIST_TAU"])]
        if bad_hc:
            conf_why.append(f"{core}: conflict history hc rose at {bad_hc[:3]} s without an opposite Σ activity")
        src_on = dilate(t, intervals(t, th_aq & (hc >= hg)), K["D_CMP"], K["D_CMP"])
        q_out = _trap(np.clip(i_sh, 0, None) * ~src_on, t, float(t[0]), float(t[-1]))
        q_ref = _trap(np.abs(i_in) * th_aq, t, float(t[0]), float(t[-1]))
        if q_out > K["TOL"] * q_ref + I_LEAK * float(t[-1] - t[0]):
            conf_why.append(f"{core}: shunt charge {q_out:.3e} C outside its gate sources (hc history AND Θ)")
    gates["cdir_hs_from_matching_sigma"] = _gate(hs_ev, unm)
    gates["cdir_support_all_events"] = _gate(cd_ev, unm)
    gates["cdir_conflict_consistent"] = {"result": U, "why": unm} if unm else \
        {"result": P if not conf_why else F, "why": conf_why[:5]}

    # ---------------- ports
    pw = []
    for d in ("f", "r"):
        for kd in ("th", "sg", "cd"):
            c = f"{kd}{pol}{e}{d}_"
            pw += [f"{c}: {w}" for w in port_check(V, f"v({c}q)", f"v({c}op_aq)", f"v({c}op_p)", K)]
    for s in (i, k_):
        pw += [f"g{pol}{s}: {w}" for w in port_check(V, f"v(g{pol}{s}_col_q)", f"v(g{pol}{s}_op_aq)",
                                                     f"v(g{pol}{s}_op_p)", K)]
    gates["ports_canonical"] = {"result": P if not pw else F, "why": pw[:6], "n": len(pw)}

    # ---------------- consumption
    lw, unm = [], None
    for d, rail in (("f", "load_pos"), ("r", "load_neg")):
        if f"v({rail})" not in V:
            unm = f"v({rail}) missing"
            break
        w, u = load_check(V, plan, rail, f"nag{pol}{e}{d}_cp", f"v(cd{pol}{e}{d}_op_aq)", K)
        if u:
            unm = u
            break
        lw += [f"{d}: {x}" for x in w]
    gates["load_consumed_in_cdir_activity"] = {"result": U, "why": unm} if unm else \
        {"result": P if not lw else F, "why": lw[:5]}
    return gates
