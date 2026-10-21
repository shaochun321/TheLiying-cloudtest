"""Synthetic waveform generators for judge self-checks (INFRA, tests only).

They produce raw-like dicts with every vector a case's judge and ledger read, shaped as a LEGAL
response under the case's registered stimulus timing, plus mutation helpers that reproduce the
independent review's counterexamples. Synthetic data tests the judging software only; it says
nothing about whether the circuit behaves this way.

Ledger currents are generated KCL-consistently: at each ledger node every terminal current but
one is a smooth function and the last one closes the sum exactly (with the C terminal carrying
C dv/dt), so a legal trace passes the KCL/energy gates and a perturbed one does not.
Relation fixtures (CHAIN / FULL) carry their causes: G0 activity, source / matching histories,
the spatial difference at the certificate's levels, injector currents that account for each
membrane ramp, canonical pulses per activity entry and the load path current per Cdir activity.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from netlists.params import v  # noqa: E402

VDD = 2.967
DT = 1e-3


def axis(t_end):
    return np.linspace(0.0, t_end, int(round(t_end / DT)) + 1)


def pulse(t, a, b, hi=VDD):
    return np.where((t >= a) & (t < b), hi, 0.0)


def fill_ledger(V, plan, t, preset=()):
    """KCL-consistent synthetic terminal currents at every ledger node.

    Physical branch semantics (review 2026-10-17 §4.1): injector/path currents in `preset` are
    kept; resistive branches carry their ohmic current; capacitors carry C dv/dt of their own
    terminal voltage; every other branch (reset / recovery / POR / comparator gate) carries zero
    in this synthetic record. This function does not close a residual; the ordinary reference
    builders may subsequently call the explicitly synthetic _close_ledger helper."""
    for n, items in plan["terms"].items():
        vn = V.get(f"v({n})")
        if vn is None:
            vn = 0.99 + 0.01 * np.sin(t)
            V[f"v({n})"] = vn
        for it in items:
            vec = it["vec"].lower()
            if vec in preset:
                continue
            if it["kind"] == "C" and it["C"]:
                far = it.get("far")
                vf = 0.0 if far in (None, "0") else V.get(f"v({far})", np.zeros_like(t))
                cur = it["C"] * np.gradient(vn - vf, t)      # into element == out of the node
            elif it["kind"] == "R" and it.get("R"):
                far = it.get("far")
                vf = 0.0 if far in (None, "0") else V.get(f"v({far})", np.zeros_like(t))
                cur = (vn - vf) / it["R"]                     # ohmic, into element
            else:
                cur = np.zeros_like(t)
            V[vec] = it["sign"] * cur      # judges read sign * vec as "into element"
    if "v(vsrc)" not in V:
        V["v(vsrc)"] = np.full_like(t, 3.0)
    if "i(vsrc)" not in V:
        V["i(vsrc)"] = np.full_like(t, -1e-4)


def _close_ledger(V, plan, t):
    """SYNTHETIC FIXTURE ONLY: assign the remaining sum to a reset / discharge branch
    (n<prefix>dis on vm, r<prefix>rdis on vmd, n<prefix>sh on vms). The synthetic records force
    membrane voltages; this assignment is test data, not a measured or predicted device
    current. Never call after mutating a negative test, or from a production observer.
    A node without such a branch keeps its own unclosed record."""
    for n, items in plan["terms"].items():
        if not n.endswith(("vm", "vmd", "vms")):
            continue
        prefix = n.rsplit("_", 1)[0] + "_"
        suf = n.rsplit("_", 1)[1]
        if suf not in ("vm", "vmd", "vms"):
            continue
        cand = {"vm": f"n{prefix}dis", "vmd": f"r{prefix}rdis", "vms": f"n{prefix}sh1"}[suf]
        closer = next((it for it in items if it["element"] == cand), None)
        if closer is None:
            continue
        acc = np.zeros_like(t)
        for it in items:
            if it is closer:
                continue
            acc = acc + it["sign"] * V[it["vec"].lower()]
        V[closer["vec"].lower()] = closer["sign"] * (-acc)


def supported_rc_pair(plan, core, u_entry):
    """Review 2026-10-17's exact two-pulse passive RC record, NOT a circuit solve.

    I=0.5 uA on [0,.6), zero on [.6,.65), then I=0.5 uA. The first pulse stays
    below entry; the second reaches entry using the surviving first-pulse charge.
    All vm currents follow Cm du/dt=I-u/Rm; no residual-closing branch is assigned.
    Callers make negatives AFTER this reference is complete, without re-closing it.
    """
    node = core + "vm"
    terms = plan["terms"][node]
    cm = sum(it["C"] for it in terms if it["kind"] == "C")
    rm, current = v("NM_RM"), 0.5e-6
    tau = rm * cm
    u_first = rm * current * (1 - np.exp(-0.6 / tau))
    u_second = u_first * np.exp(-0.05 / tau)
    tq = 0.65 + tau * np.log((rm * current - u_second) / (rm * current - u_entry))
    t = np.unique(np.r_[np.arange(0, tq + 0.05, 0.5e-3), 0.6, 0.65, tq, tq + 0.02])
    u = np.where(t < 0.6, rm * current * (1 - np.exp(-t / tau)),
                 np.where(t < 0.65, u_first * np.exp(-(t - 0.6) / tau),
                          rm * current + (u_second - rm * current) * np.exp(-(t - 0.65) / tau)))
    cause = (t < 0.6) | (t >= 0.65)
    injected = np.where(cause, current, 0.0)
    derivative = (injected - u / rm) / cm
    V = {"time": t, "v(vdd)": np.full_like(t, VDD), "v(vrest)": np.full_like(t, VREST),
         f"v({node})": VREST + u, f"v({core}hs)": np.full_like(t, 1.3),
         f"v({core}q)": pulse(t, tq, tq + 0.02)}
    for it in terms:
        if it["element"] == f"n{core}rm_mo":
            out = -injected
        elif it["element"] == f"r{core}rm":
            out = u / rm
        elif it["kind"] == "C":
            assert it.get("far") in (None, "0"), "this fixture requires grounded membrane capacitors"
            out = it["C"] * derivative
        else:
            out = np.zeros_like(t)
        V[it["vec"].lower()] = out / it["sign"]
    return V, cause, {"equation": "Cm du/dt=I-u/Rm; piecewise exact exponential solution",
                      "Cm_F": cm, "Rm_ohm": rm, "I_A": current, "entry_time_s": float(tq),
                      "retained_at_second_start_V": float(u_second), "early_end_s": 0.6,
                      "second_start_s": 0.65, "residual_closing_used": False}


def defaults(V, names, t):
    for n in names:
        if n.lower() not in V:
            V[n.lower()] = np.zeros_like(t)


# ------------------------------------------------------------------ mother bench
def mother_events(proto, lock_high=False):
    """One q in valid, two in max, one in reinput, per role (a legal joint response)."""
    ev = {}
    for role in ("G0", "Sigma", "Theta_Cdir"):
        seg = {s["label"]: s for s in proto["roles"][role] if "t_start_s" in s}
        a = seg["valid"]["t_start_s"] + 0.05
        e = [(a, a + 0.01)]
        m0 = seg["max"]["t_start_s"] + 0.05
        e += [(m0, m0 + 0.01), (m0 + 0.3, m0 + 0.31)]
        if lock_high and role == "Sigma":
            e += [(m0 + 0.6, None)]
        r0 = seg["reinput"]["t_start_s"] + 0.05
        e += [(r0, r0 + 0.01)]
        ev[role] = e
    return ev


def mother_raw(proto, cert, role_events, t_end=None, missing_roles=(), drop=(), weak_sign=1.0):
    """Synthetic mother-bench raw: q pulses per role given as (t_up, t_down|None); a/p follow q
    with the real-port shape; rec charged by each pulse and decaying; in the weak segment the
    membrane moves by the certificate's signed expectation (weak_sign=-1 flips it)."""
    from netlists.bench_mother import PREFIX
    t_end = t_end or proto["total_s"]
    t = axis(t_end)
    V = {"time": t, "v(vdd)": np.full_like(t, VDD), "v(vrest)": np.full_like(t, 0.989)}
    for role, pr in PREFIX.items():
        if role in missing_roles:
            continue
        q, rec, aq, p = (np.zeros_like(t) for _ in range(4))
        for (u, d) in role_events.get(role, []):
            hi = (t >= u) & ((t < d) if d is not None else True)
            q[hi] = VDD
            rec[t >= u] = np.maximum(rec[t >= u], 2.9 * np.exp(-(t[t >= u] - (d or u)) / 0.82))
            aq[(t >= u) & (t < (d or t_end) + 1.5)] = VDD
        up = np.where((aq[1:] > 1.5) & (aq[:-1] <= 1.5))[0]
        for i in up:
            p[i + 1:i + 1 + 230] = VDD
        V[f"v({pr}q)"] = q
        V[f"v({pr}qb)"] = VDD - q
        V[f"v({pr}vm)"] = 0.989 + 0.1 * (q > 0)
        V[f"v({pr}h)"] = np.full_like(t, 1.2)
        V[f"v({pr}rec)"] = rec
        V[f"v({pr}op_at)"] = aq * 0.9
        V[f"v({pr}op_aq)"] = aq
        V[f"v({pr}op_p)"] = p
        V[f"v({pr}vmd)"] = np.full_like(t, 0.989)
        seg = {s["label"]: s for s in proto["roles"][role] if "t_start_s" in s}
        w = (t >= seg["weak"]["t_start_s"]) & (t < seg["weak"]["t_end_s"])
        V[f"v({pr}vm)"][w] += weak_sign * cert["nom"]["roles"][role]["weak_expected_du_V"]
    for k in drop:
        V.pop(k, None)
    return V


def mother_legal(case, assets, **kw):
    import json
    proto = json.load(open(os.path.join(ROOT, "prereg", "protocol_q1r_joint.json"), encoding="utf-8"))
    cert = json.load(open(os.path.join(ROOT, "analysis", "input_bounds.json"), encoding="utf-8"))
    V = mother_raw(proto, cert, mother_events(proto), **kw)
    defaults(V, assets["save"], V["time"])
    fill_ledger(V, assets["plan"], V["time"])
    _close_ledger(V, assets["plan"], V["time"])  # positive synthetic baseline only
    return V


# ------------------------------------------------------------------ G0
def g0_legal(case, assets):
    j = case["judge"]
    p = f"g{j['pol']}{j['site']}_"
    steps = case["env"][str(j["site"])]
    t = axis(case["x_stop"])
    V = {"time": t, "v(vdd)": np.full_like(t, VDD), "v(vrest)": np.full_like(t, 0.989)}
    for k in range(1, 11):
        V[f"v({p}e{k}_q)"] = np.zeros_like(t)
        V[f"v({p}b{k}_q)"] = np.zeros_like(t)
    for x in ("and_g8", "col_q", "op_aq", "op_p", "op_at", "col_rec"):
        V[f"v({p}{x})"] = np.zeros_like(t)
    cut = j.get("cut_k")
    for (a, b, _amp) in steps:
        for k in range(1, 11):
            tk = a + 0.3 + 0.05 * k
            V[f"v({p}e{k}_q)"] += pulse(t, tk, tk + 0.01)
            V[f"v({p}b{k}_q)"] += pulse(t, tk + 0.002, b + 1.0)
        if not cut:
            ta = a + 0.3 + 0.05 * 10 + 0.01
            V[f"v({p}and_g8)"] += pulse(t, ta, b + 1.0)
            V[f"v({p}col_q)"] += pulse(t, ta + 0.02, ta + 0.035)
            V[f"v({p}op_aq)"] += pulse(t, ta + 0.022, b + 1.2)
            V[f"v({p}op_p)"] += pulse(t, ta + 0.023, ta + 0.25)
    if cut:
        # the cut path keeps firing at its source; the AND input is open, so no group output
        pass
    defaults(V, assets["save"], t)
    if assets["plan"]["nodes"]:
        fill_ledger(V, assets["plan"], t)
        _close_ledger(V, assets["plan"], t)  # positive synthetic baseline only
    return V


# ------------------------------------------------------------------ relation support fixtures
VREST = 0.989
VMID = 1.4836
H_PLATEAU = 1.4          # synthetic history plateau (above the certificate valid level)
ACT_S = 1.5              # synthetic activity length after a q
QW = 0.015


def _cert():
    import json
    return json.load(open(os.path.join(ROOT, "analysis", "input_bounds.json"), encoding="utf-8"))


def _lp(t, x, tau):
    """First-order low-pass of a 0/1 activity (synthetic node smoothing)."""
    y = np.zeros_like(t, dtype=float)
    dt = t[1] - t[0]
    a = dt / tau
    for n in range(1, len(t)):
        y[n] = y[n - 1] + (x[n] - y[n - 1]) * a
    return y


def _hist(t, t0, decay_after=5.0, tau=8.4, ramp=0.3):
    """History node charged by an event at t0: ramp to the plateau, slow decay later."""
    h = H_PLATEAU * np.clip((t - t0) / ramp, 0, 1)
    return h * np.exp(-np.clip(t - t0 - decay_after, 0, None) / tau)


def _inj_items(plan, core):
    """Injector / shunt items of a core from the plan (ledger terms or probes)."""
    vm = core + "vm"
    items = list(plan.get("terms", {}).get(vm, [])) + [p for p in plan.get("probes", {}).values() if p["node"] == vm]
    find = lambda suf: next((it for it in items if it["element"] == f"n{core}{suf}"), None)
    return {"rm_mo": find("rm_mo"), "m4": find("ota_m4"), "m2": find("ota_m2"), "kh": find("kh")}


def _set_current(V, item, t, i_into_node, P):
    """Add a current delivered INTO the node by the element (sign convention of the plan)."""
    if item is None:
        return
    k = item["vec"].lower()
    V[k] = V.get(k, np.zeros_like(t)) + (-i_into_node / item["sign"])
    P.add(k)


def _event(V, t, plan, core, a, tq, cm, u_entry, P, injector="rm_mo"):
    """One supported event: vm ramps from its present level at a to entry (vrest + u_entry) at tq,
    holds through the q pulse, then decays passively (tau = Rm Cm) until a later call overwrites
    it; q pulse. The injector supplies exactly the node equation of the written trajectory
    (Cm dvm/dt + leak) with a 5 % margin on the capacitive part (review 2026-10-17 §4.1), so the
    ordinary synthetic builder records its residual with _close_ledger. The exact fixed RC
    acceptance pairs use supported_rc_pair instead, without that helper."""
    vmk, qk = f"v({core}vm)", f"v({core}q)"
    if vmk not in V or not np.any(V[vmk]):
        V[vmk] = np.full_like(t, VREST)
    V.setdefault(qk, np.zeros_like(t))
    vrest = float(np.median(V["v(vrest)"]))
    Rm, tau = v("NM_RM"), v("NM_RM") * cm
    r = (t >= a) & (t < tq)
    v_at_a = float(np.interp(a, t, V[vmk]))
    V[vmk][r] = v_at_a + (vrest + u_entry - v_at_a) * (t[r] - a) / (tq - a)
    V[vmk][(t >= tq) & (t < tq + QW)] = vrest + u_entry
    decay = t >= tq + QW
    V[vmk][decay] = vrest + u_entry * np.exp(-(t[decay] - (tq + QW)) / tau)
    V[qk] = V[qk] + pulse(t, tq, tq + QW)
    dvdt = np.gradient(V[vmk], t)
    i = np.where(r, 1.05 * cm * dvdt + (V[vmk] - vrest) / Rm, 0.0)
    _set_current(V, _inj_items(plan, core)[injector], t, i, P)
    if core.startswith("cd") and injector == "rm_mo":
        # conflict shunt record of this core (kh): the support account needs it measured. No
        # conflict source here: zeros, marked as measured so the ledger is complete.
        kk = _inj_items(plan, core)["kh"]
        if kk is not None:
            V.setdefault(kk["vec"].lower(), np.zeros_like(t))
            P.add(kk["vec"].lower())


def _activity(V, t, aqk, tq):
    V.setdefault(aqk, np.zeros_like(t))
    V[aqk] = np.maximum(V[aqk], pulse(t, tq + 0.002, tq + 0.002 + ACT_S))


def _pulses_from_activity(V, t, aqk, pk):
    """One canonical pulse per activity entry (0.23 s, inside the activity)."""
    aq = V.get(aqk, np.zeros_like(t))
    p = np.zeros_like(t)
    up = np.where((aq[1:] > VDD / 2) & (aq[:-1] <= VDD / 2))[0] + 1
    for n in up:
        p[n:n + 230] = np.where(aq[n:n + 230] > VDD / 2, VDD, 0.0)
    V[pk] = p


def _g0_fire(V, t, pol, s, ts):
    V[f"v(g{pol}{s}_col_q)"] = V.get(f"v(g{pol}{s}_col_q)", np.zeros_like(t)) + pulse(t, ts, ts + QW)
    _activity(V, t, f"v(g{pol}{s}_op_aq)", ts)
    V[f"v(h{pol}{s})"] = np.maximum(V.get(f"v(h{pol}{s})", np.zeros_like(t)), _hist(t, ts))


def _spatial(V, t, pol, sites, edges_):
    """sp_s at vmid + 0.3 x smoothed G0 activity; edge sense node below sp_i by the signed
    difference of the certificate's levels (forward single +40 mV, reverse single -25 mV,
    synchronous +15 mV), zero on a cut edge."""
    act = {s: (V.get(f"v(g{pol}{s}_op_aq)", np.zeros_like(t)) > VDD / 2).astype(float) for s in sites}
    for s in sites:
        V[f"v(sp{pol}{s})"] = VMID + 0.3 * _lp(t, act[s], 0.02)
    for (i, k), cut in edges_:
        if cut:
            V[f"v(sp{pol}s{i}{k})"] = V[f"v(sp{pol}{i})"].copy()
            continue
        ai, ak = act.get(i, 0 * t), act.get(k, 0 * t)
        diff = 0.040 * _lp(t, ai * (1 - ak), 0.004) - 0.025 * _lp(t, ak * (1 - ai), 0.004) \
            + 0.015 * _lp(t, ai * ak, 0.004)
        V[f"v(sp{pol}s{i}{k})"] = V[f"v(sp{pol}{i})"] - diff


def _first_at_least(t, x, lvl, after):
    m = (t >= after) & (x >= lvl)
    return float(t[m][0]) if m.any() else None


def relation_edge(V, t, plan, pol, i, k, d, ts, P, cert, sig_core_d=None, theta=True, sigma=True, cdir=True,
                  hs_override=None, cdir_extra=(), conflict=False):
    """Supported Θ_d / Σ_d / Cdir_d events of edge (i, k) given the G0 times ts[site].
    sig_core_d: which Σ core fires (the declared swap variant fires the opposite one)."""
    from netlists.params import v as pv
    roles = cert["nom"]["roles"]
    u_t, u_s = roles["Theta_Cdir"]["u_entry_V"], roles["Sigma"]["u_entry_V"]
    cm_t, cm_s = pv("NM_CM_THETA_CDIR"), pv("NM_CM")
    e = f"{i}{k}"
    src, tgt = (i, k) if d == "f" else (k, i)
    out = {}
    sd = sig_core_d or d
    sgc = f"sg{pol}{e}{sd}_"
    if sigma:
        diff = V[f"v(sp{pol}{i})"] - V[f"v(sp{pol}s{e})"]
        sdiff = diff if d == "f" else -diff
        a = _first_at_least(t, sdiff, 0.010, ts[src])
        tq = ts[src] + 0.1
        _event(V, t, plan, sgc, a, tq, cm_s, u_s, P, injector="m4")
        _activity(V, t, f"v({sgc}op_aq)", tq)
        out["sg"] = tq
    th_t = None
    if theta:
        thc = f"th{pol}{e}{d}_"
        th_t = max(ts[tgt] + 0.2, ts[src] + 0.35)
        # Synchronous-parent fixture: do not invent Theta injection before its source history
        # has formed. Ordinary staggered fixtures already have the history when the target fires.
        hg = 0.5 * cert["nom"]["history_levels_V"]["valid_entry_min"]
        th_a = _first_at_least(t, V[f"v(h{pol}{src})"], hg, ts[tgt] + 0.002)
        assert th_a is not None and th_a < th_t, "synthetic Theta needs a supported charging stretch"
        _event(V, t, plan, thc, th_a, th_t, cm_t, u_t, P)
        _activity(V, t, f"v({thc}op_aq)", th_t)
        out["th"] = th_t
    cdc = f"cd{pol}{e}{d}_"
    if sigma:
        hs = _hist(t, out["sg"] + 0.002) if hs_override is None else hs_override
        V[f"v(cd{pol}{e}{sd}_hs)"] = np.maximum(V.get(f"v(cd{pol}{e}{sd}_hs)", 0 * t), hs)
        if conflict:   # the swapped Σ feeds the opposite Cdir's conflict history
            other = "r" if sd == "f" else "f"
            V[f"v(cd{pol}{e}{other}_hc)"] = np.maximum(V.get(f"v(cd{pol}{e}{other}_hc)", 0 * t), hs)
    if cdir and th_t is not None:
        cd_t = th_t + 0.05
        _event(V, t, plan, cdc, th_t + 0.002, cd_t, cm_t, u_t, P)
        for x in cdir_extra:          # later events in the same activity (still supported)
            _event(V, t, plan, cdc, cd_t + QW + 0.02, cd_t + x, cm_t, u_t, P)
        _activity(V, t, f"v({cdc}op_aq)", cd_t)
        out["cd"] = cd_t
    return out


def load_paths(V, t, plan, cores, P):
    """Synthetic Iref paths and passive R || C rails, including C_NODE.

    Trapezoidal RC integration handles sampled current edges consistently. Capacitor currents
    come from the same RC equation, not a residual assigned to an unrelated branch.
    """
    from netlists.params import v as pv
    iref = _cert()["nom"]["refs"]["Iref"]
    R = pv("LOAD_R")
    drive = {"load_pos": np.zeros_like(t), "load_neg": np.zeros_like(t)}
    for pol, e, d in cores:
        rail = "load_pos" if d == "f" else "load_neg"
        act = (V.get(f"v(cd{pol}{e}{d}_op_aq)", np.zeros_like(t)) > VDD / 2).astype(float)
        it = next((x for x in plan.get("terms", {}).get(rail, []) if x["element"] == f"nag{pol}{e}{d}_cp"), None)
        _set_current(V, it, t, iref * act, P)
        drive[rail] += iref * act
    for rail, i in drive.items():
        caps = [x for x in plan.get("terms", {}).get(rail, []) if x["kind"] == "C"]
        cm = sum(x["C"] for x in caps) if caps else pv("LOAD_C") + pv("C_NODE")
        tau = R * cm
        u = np.zeros_like(t)
        for n in range(1, len(t)):
            h = (t[n] - t[n - 1]) / (2 * tau)
            u[n] = ((1 - h) * u[n - 1] + h * R * (i[n] + i[n - 1])) / (1 + h)
        V[f"v({rail})"] = VMID + u
        for it in caps:
            V[it["vec"].lower()] = (it["C"] / cm) * (i - u / R) / it["sign"]
            P.add(it["vec"].lower())
    for rail in ("load_pos", "load_neg"):
        for x in plan.get("terms", {}).get(rail, []):
            if x["element"].startswith("nag"):
                V.setdefault(x["vec"].lower(), np.zeros_like(t))
                P.add(x["vec"].lower())


def _base(case):
    t = axis(case["x_stop"])
    V = {"time": t, "v(vdd)": np.full_like(t, VDD), "v(vrest)": np.full_like(t, VREST),
         "v(vmid)": np.full_like(t, VMID)}
    return t, V, set()


def _finish(V, t, assets, P, cores_ports, g0_ports):
    for c in cores_ports:
        _pulses_from_activity(V, t, f"v({c}op_aq)", f"v({c}op_p)")
    for pol, s in g0_ports:
        _pulses_from_activity(V, t, f"v(g{pol}{s}_op_aq)", f"v(g{pol}{s}_op_p)")
    # every injector / shunt current of the plan that no event set is zero (measured as such)
    plan = assets["plan"]
    for it in list(plan.get("probes", {}).values()) + [x for its in plan.get("terms", {}).values() for x in its]:
        if any(it["element"].endswith(s) for s in ("_rm_mo", "_ota_m4", "_ota_m2", "_kh")):
            V.setdefault(it["vec"].lower(), np.zeros_like(t))
            P.add(it["vec"].lower())
    defaults(V, assets["save"], t)
    if plan["nodes"]:
        fill_ledger(V, plan, t, preset=P)
        _close_ledger(V, plan, t)
    return V


# ------------------------------------------------------------------ CHAIN family
def chain_legal(case, assets, which="nominal"):
    j = case["judge"]
    pol, (i, k) = j["pol"], j["pair"]
    dirn = j.get("dir", "f")
    cid = case["case_id"]
    t, V, P = _base(case)
    plan, cert = assets["plan"], _cert()
    t_on = {int(s): segs[0][0] for s, segs in case["env"].items()}
    src, tgt = (i, k) if dirn == "f" else (k, i)
    ts = {src: t_on[src] + 0.4, tgt: t_on.get(tgt, t_on[src]) + 0.4}
    for s in (i, k):
        _g0_fire(V, t, pol, s, ts[s])
    if cid == "INVALID_STALE":
        V[f"v(h{pol}{src})"] = H_PLATEAU * np.clip((t - ts[src]) / 0.3, 0, 1) * \
            np.exp(-np.clip(t - ts[src] - 0.3, 0, None) / 1.0)
    _spatial(V, t, pol, (i, k), [((i, k), False)])
    hs_override = None
    if cid == "STRUCT_SIGMA_PORT_CUT":
        hs_override = np.zeros_like(t)
    if cid == "STRUCT_CDIR_HISTORY_BLEED":
        import re
        m = re.findall(r"[-+0-9.e]+", case["build_args"]["bleed"]["pwl"])
        tb0 = float(m[4])
        hb = _hist(t, ts[src] + 0.1 + 0.002)
        hs_override = np.where(t < tb0, hb, 0.2 + (np.interp(tb0, t, hb) - 0.2) * np.exp(-np.clip(t - tb0, 0, None) / 0.02))
    silent_cd = cid in ("STRUCT_THETA_PORT_CUT", "STRUCT_SIGMA_PORT_CUT", "STRUCT_REAL_SIGMA_SWAP",
                        "INVALID_SYNC", "INVALID_STALE", "STRUCT_CDIR_HISTORY_BLEED")
    swap = cid == "STRUCT_REAL_SIGMA_SWAP"
    rev = "r" if dirn == "f" else "f"
    relation_edge(V, t, plan, pol, i, k, dirn, ts, P, cert, sig_core_d=rev if swap else None,
                  theta=cid != "INVALID_STALE", cdir=not silent_cd, hs_override=hs_override,
                  cdir_extra=(1.0,) if cid in ("CHAIN_12_W_F", "NUM_CHAIN_HALFSTEP") else (), conflict=swap)
    if swap:
        # conflict: the swapped Σ charged Cdir_dir's hc; with Θ_dir active the shunt conducts
        region = (V[f"v(cd{pol}{i}{k}{dirn}_hc)"] >= 0.5 * cert["nom"]["history_levels_V"]["valid_entry_min"]) & \
                 (V[f"v(th{pol}{i}{k}{dirn}_op_aq)"] > VDD / 2)
        _set_current(V, _inj_items(plan, f"cd{pol}{i}{k}{dirn}_")["kh"], t, -5e-8 * region, P)
    cores = [f"{kd}{pol}{i}{k}{d}_" for kd in ("th", "sg", "cd") for d in ("f", "r")]
    load_paths(V, t, plan, [(pol, f"{i}{k}", d) for d in ("f", "r")], P)
    return _finish(V, t, assets, P, cores, [(pol, i), (pol, k)])


# ------------------------------------------------------------------ FULL
def full_legal(case, assets):
    t, V, P = _base(case)
    plan, cert = assets["plan"], _cert()
    env = case["env"]
    mirror = case["case_id"] == "FULL_REAL_MIRROR"
    cores, paths = [], []
    for pol, sign in (("w", 1), ("c", -1)):
        on = {int(s): seg[0] for s, segs in env.items() for seg in segs if np.sign(seg[2]) == sign}
        if mirror:      # real mirror wiring: the G0 of site s sees the front of site 5 - s
            on = {s: on[5 - s] for s in on}
        d = ("f" if pol == "w" else "r") if not mirror else ("r" if pol == "w" else "f")
        ts = {s: on[s] + 0.4 for s in on}
        for s in on:
            _g0_fire(V, t, pol, s, ts[s])
        edges_ = [((i, k), case["case_id"] == "FULL_SPACE_CUT" and (i, k) == (2, 3)) for i, k in ((1, 2), (2, 3), (3, 4))]
        _spatial(V, t, pol, (1, 2, 3, 4), edges_)
        for (i, k), cut in edges_:
            if cut:
                continue
            src, tgt = (i, k) if d == "f" else (k, i)
            assert ts[src] < ts[tgt], "synthetic FULL: source must activate first"
            relation_edge(V, t, plan, pol, i, k, d, ts, P, cert)
        cores += [f"{kd}{pol}{i}{k}{dd}_" for kd in ("th", "sg", "cd") for i, k in ((1, 2), (2, 3), (3, 4)) for dd in ("f", "r")]
        paths += [(pol, f"{i}{k}", dd) for i, k in ((1, 2), (2, 3), (3, 4)) for dd in ("f", "r")]
    load_paths(V, t, plan, paths, P)
    return _finish(V, t, assets, P, cores, [(pol, s) for pol in ("w", "c") for s in (1, 2, 3, 4)])


# ------------------------------------------------------------------ DC
def dc_legal(case, assets):
    sys.path.insert(0, ROOT)
    from netlists.params import v
    from analysis import input_bounds as ib
    vdd_set = case["judge"]["vdd"]
    R = ib.supply_and_refs(vdd_set)
    vdd = R["vdd"]
    V = {}
    V["v(vsrc)"] = np.array([vdd_set])
    V["v(vdd)"] = np.array([vdd])
    V["i(vsrc)"] = np.array([-(vdd_set - vdd) / v("R_INT")])
    for ref in ("vrest", "vthe", "vthr", "vmid"):
        V[f"v({ref})"] = np.array([R[ref]])
    V["v(iref_n)"] = np.array([vdd - R["Iref"] * v("IREF_R")])
    V["v(ilim_n)"] = np.array([vdd - R["Ilim"] * v("ILIM_R")])
    V["v(istep_n)"] = np.array([vdd - R["Istep"] * v("ISTEP_R")])
    V["v(irefp_n)"] = np.array([R["irefp_n"]])
    V["v(ilimp_n)"] = np.array([R["ilimp_n"]])
    # synthetic only: every other node at 1.5 V, which satisfies |Vsb| < 2 V for both NMOS
    # (bulk 0) and PMOS (bulk vsrc); this tests the judge, not the circuit
    for n in assets["save"]:
        if n not in V:
            V[n] = np.array([1.5])
    return V


def legal(case, assets):
    g = case["group"]
    if g == "MOTHER":
        return mother_legal(case, assets)
    if g == "G0" or case["case_id"] == "NUM_G0_HALFSTEP":
        return g0_legal(case, assets)
    if g in ("CHAIN", "STRUCTURE") or case["case_id"] == "NUM_CHAIN_HALFSTEP":
        return chain_legal(case, assets)
    if g == "FULL":
        return full_legal(case, assets)
    if g == "DC":
        return dc_legal(case, assets)
    raise KeyError(case["case_id"])
