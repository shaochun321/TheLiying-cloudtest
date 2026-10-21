"""THERMAL-G3-Q1-R offline candidate certificate (INFRA, preparation only; not a qualification).

Every number here is a CANDIDATE ESTIMATE computed from the frozen params and the EKV2.6 static
channel current ported line by line from the compiled VA (analysis/ekv26_static.py, restored from
ae41504 where it was cross-checked against the dev-017 raw). It never runs during a solve and
never replaces a device. Dynamic behaviour is measured only by the two qualification analyses
(analysis/raw_bounds.py fills those values after a solve; before one they are UNMEASURED).

Per role (G0 collector, Sigma receiver, Theta/Cdir receiver) it reports:
  input domain      weak-max / valid-min / max currents from the actual input branch
  entry             I_valid_min(1-tol) Rm > u_entry + delta;  I_weak_max(1+tol) Rm < u_entry - delta
  exit              u_inf(I_max(1+tol), Rdis(1+5%)) < u_exit_low - delta (nonlinear reset branch)
  shortest q        u(t) and the relaxing threshold h(t) integrated together (tau_h from Ra||Rf, Ch)
  charge targets    trace and recovery: T_ch = tau ln((z_eq-z0)/(z_eq-z_req)) <= T_q,min
  parent window     entry time of the weakest valid relation input within the parent's activity

Status: INCOMPATIBLE if any required estimate fails; UNKNOWN if any required item cannot be
computed; otherwise NO_INCOMPATIBILITY_FOUND (never PASS: an estimate cannot qualify). Items that
are dynamic by nature (Cdir third-level timing, moving references) are listed as unmeasured.
Unsourced assumptions are listed (mirror tolerance, delta, temperature, comparator delay).
Output: analysis/input_bounds.json.
"""
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import brentq

Q1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, Q1)
from analysis.ekv26_static import ids  # noqa: E402
from netlists.params import v  # noqa: E402

TEMP_C = 27.0
MIRROR_TOL = 0.10   # UNSOURCED: no mismatch statistics in the C05 typical card
DELTA_V = 0.020     # UNSOURCED: comparator offset + reference ripple allowance
TOL_RDIS = 0.05     # design tolerance (Q1-R §4)
TOL_CM = 0.10       # design tolerance (Q1-R §4)
VSRC = 3.0          # NOM source; vdd is after R_INT, PMOS wells sit on vsrc (netlists/build.py WELL)

ROLES = {
    "G0": {"ref": "vthe", "Rdis": "NRC_RDIS_G0", "Cm": "NM_CM"},
    "Sigma": {"ref": "vthr", "Rdis": "NRC_RDIS_RCV", "Cm": "NM_CM"},
    "Theta_Cdir": {"ref": "vthr", "Rdis": "NRC_RDIS_THETA_CDIR", "Cm": "NM_CM_THETA_CDIR"},
}


def n_id(W, L, d, g, s, b=0.0):
    return ids("nch", W, L, d, g, s, b, temp_c=TEMP_C)


def p_id(W, L, d, g, s, b=VSRC):
    """PMOS current out of the drain; bulk on the well tap vsrc."""
    return -ids("pch", W, L, d, g, s, b, temp_c=TEMP_C)


# ------------------------------------------------------------------ references
def diode_n(R, vdd, W, L):
    Vg = brentq(lambda x: (vdd - x) / R - n_id(W, L, x, x, 0.0), 0.05, vdd - 1e-6)
    return Vg, (vdd - Vg) / R


def copy_into_pmos_diode(vgn, vdd, Wn, Ln, Wp, Lp):
    """NMOS copy (gate vgn) drawn from a PMOS diode at node x: solved jointly (no fixed drain)."""
    x = brentq(lambda x: p_id(Wp, Lp, x, x, vdd) - n_id(Wn, Ln, x, vgn, 0.0), 0.05, vdd - 1e-6)
    return x, n_id(Wn, Ln, x, vgn, 0.0)


def supply_and_refs(vsrc=VSRC):
    vdd = vsrc
    for _ in range(60):
        div = sum(vdd / (v(a) + v(b)) for a, b in (("VREST_RT", "VREST_RB"), ("VTHE_RT", "VTHE_RB"),
                                                     ("VTHR_RT", "VTHR_RB"), ("VMID_RT", "VMID_RB")))
        vref, iref = diode_n(v("IREF_R"), vdd, v("BIAS_W"), v("BIAS_L"))
        _, istep = diode_n(v("ISTEP_R"), vdd, v("BIAS_W"), v("BIAS_L"))
        vlim, ilim = diode_n(v("ILIM_R"), vdd, v("BIAS_W"), v("BIAS_L"))
        new = vsrc - v("R_INT") * (div + 2 * iref + istep + 2 * ilim + vdd / v("POR_R"))
        if abs(new - vdd) < 1e-10:
            break
        vdd = new
    r = lambda a, b: vdd * v(b) / (v(a) + v(b))
    irefp, _ = copy_into_pmos_diode(vref, vdd, v("BIAS_W"), v("BIAS_L"), v("BIAS_W"), v("BIAS_L"))
    ilimp, _ = copy_into_pmos_diode(vlim, vdd, v("BIAS_W"), v("BIAS_L"), v("BIAS_W"), v("BIAS_L"))
    return {"vsrc": vsrc, "vdd": vdd, "vrest": r("VREST_RT", "VREST_RB"), "vthe": r("VTHE_RT", "VTHE_RB"),
            "vthr": r("VTHR_RT", "VTHR_RB"), "vmid": r("VMID_RT", "VMID_RB"), "Iref": iref,
            "Istep": istep, "Ilim": ilim, "iref_n": vref, "irefp_n": irefp, "ilimp_n": ilimp}


def gated_copy(vdd, vgp, Wc, Lc, vout, Wsw=4e-6, Lsw=1e-6):
    """gated_source: PMOS switch (gate low) in series with a PMOS copy (gate vgp) into vout."""
    x = brentq(lambda x: p_id(Wsw, Lsw, x, 0.0, vdd) - p_id(Wc, Lc, vout, vgp, x), vout + 1e-9, vdd - 1e-12)
    return p_id(Wc, Lc, vout, vgp, x)


def thresholds(ref, vdd):
    ra, rf = v("NRC_HYS_RA"), v("NRC_HYS_RF")
    return (ref * rf + vdd * ra) / (ra + rf), (ref * rf) / (ra + rf)


# ------------------------------------------------------------------ membrane with reset
def i_reset(vm, vrest, vdd, rdis):
    if vm <= vrest:
        return 0.0
    W, L = v("NRC_DIS_W"), v("NRC_DIS_L")
    x = brentq(lambda s: n_id(W, L, vm, vdd, s) - (s - vrest) / rdis, vrest, vm)
    return (x - vrest) / rdis


def u_inf_reset(I, vrest, vdd, rdis):
    return brentq(lambda vm: I - (vm - vrest) / v("NM_RM") - i_reset(vm, vrest, vdd, rdis), vrest, vdd) - vrest


def q_width(I, u_e, u_x, vrest, vdd, rdis, cm, t_max=2.0, dt=2e-5):
    """q high from u = u_e; threshold relaxes u_e -> u_x with tau_h; q exits when u < h(t).
    Returns (width_s, exited); exited False if u never drops below h within t_max."""
    tau_h = v("NRC_H_C") * v("NRC_HYS_RA") * v("NRC_HYS_RF") / (v("NRC_HYS_RA") + v("NRC_HYS_RF"))
    u, t = u_e, 0.0
    while t < t_max:
        h = u_x + (u_e - u_x) * math.exp(-t / tau_h)
        if t > 0 and u < h - 1e-6:
            return t, True
        du = (I - u / v("NM_RM") - i_reset(vrest + u, vrest, vdd, rdis)) / cm
        u += du * dt
        t += dt
    return t_max, False


def switch_ron_max(W, L, vdd, v_lo, v_hi):
    """Upper bound of a PMOS switch (gate 0, source vdd) resistance over drain range."""
    r = []
    for vd in np.linspace(v_lo, v_hi, 25):
        i = p_id(W, L, vd, 0.0, vdd)
        if i > 0:
            r.append((vdd - vd) / i)
    return max(r)


def charge_time(R, C, Rleak, vdd, z_req, z0=0.0):
    z_eq = vdd * Rleak / (R + Rleak)
    if z_eq <= z_req:
        return None
    tau = C * R * Rleak / (R + Rleak)
    return tau * math.log((z_eq - z0) / (z_eq - z_req))


def shunt_hold_rec(I, u_hold, vrest, vdd):
    """Recovery shunt: two series NMOS (gate rec, gate qb=vdd) from vm to vrest. Required rec
    voltage so the shunt sinks I with vm held at vrest + u_hold (NaN if impossible)."""
    W, L = v("NRC_SH_W"), v("NRC_SH_L")
    vm = vrest + u_hold

    def sink(vrec):
        x = brentq(lambda x: n_id(W, L, vm, vrec, x) - n_id(W, L, x, vdd, vrest), vrest, vm)
        return n_id(W, L, x, vdd, vrest)
    if sink(vdd) < I:
        return None
    return brentq(lambda g: sink(g) - I, 0.0, vdd)


# ------------------------------------------------------------------ actual input branches
def history_after_pulses(vdd, width, period, n):
    """Two-stage history (build.history) charged through the PMOS switch 4/0.5 while its gate
    is low for `width` each `period`, n times; returns h after the n-th pulse."""
    h1 = h = 0.0
    dt = min(width / 50, 2e-4)
    for _ in range(n):
        t = 0.0
        while t < period:
            on = t < width
            if on:
                sd = brentq(lambda sd: p_id(4e-6, 0.5e-6, sd, 0.0, vdd) - (sd - h1) / v("HIST_RR"), h1, vdd)
                iin = (sd - h1) / v("HIST_RR")
            else:
                iin = 0.0
            i12 = (h1 - h) / v("HIST_R2")
            h1 += dt * (iin - i12) / v("HIST_C1")
            h += dt * (i12 - h / v("HIST_RL")) / v("HIST_C2")
            t += dt
            if on and t >= width:
                h_after = h
    return h


def history_decay_time(h0, h_target):
    """Time for the two-stage history (switch off, h1 starting at h0) to fall below h_target."""
    h1 = h = h0
    t, dt = 0.0, 1e-3
    while h > h_target and t < 120:
        i12 = (h1 - h) / v("HIST_R2")
        h1 += dt * (-i12) / v("HIST_C1")
        h += dt * (i12 - h / v("HIST_RL")) / v("HIST_C2")
        t += dt
    return t if h <= h_target else None


def history_bound(vdd):
    return vdd * v("HIST_RL") / (v("HIST_RR") + v("HIST_R2") + v("HIST_RL"))


def relation_input(vdd, h, vout):
    """relation_stack (mh gate h over mp gate vdd) loading the MIR diode, mirrored by RM_OUT into vout."""
    def resid(vmi):
        x = brentq(lambda x: n_id(v("REL_WH"), v("REL_LH"), vmi, h, x)
                   - n_id(v("REL_WP"), v("REL_LP"), x, vdd, 0.0), 0.0, vmi)
        return p_id(v("MIR_W"), v("MIR_L"), vmi, vmi, vdd) - n_id(v("REL_WP"), v("REL_LP"), x, vdd, 0.0)
    vmi = brentq(resid, 0.01, vdd - 1e-6)
    return p_id(v("RM_OUT_W"), v("RM_OUT_L"), vout, vmi, vdd)


def ota_out(vdd, inp, inn, vout):
    """ota5n static output current into vout (sourcing positive). Nested 1-D solves:
    tail node vt balances the tail sink against both input devices; d1 is the PMOS diode."""
    W, L = v("SP_W"), v("SP_L")
    vnb, _ = diode_n(v("SP_RB"), vdd, 4e-6, 4e-6)
    tail = lambda vt: n_id(4e-6, 4e-6, vt, vnb, 0.0)

    def vd1_of(i1):
        return brentq(lambda x: p_id(W, L, x, x, vdd) - i1, 0.0, vdd - 1e-9)

    def i2_of(vt):
        return n_id(W, L, vout, inn, vt)

    def i1_of(vt):
        # m1 drain is d1 (PMOS diode): find d1 where the diode current equals the m1 current
        f = lambda x: p_id(W, L, x, x, vdd) - n_id(W, L, x, inp, vt)
        if f(vdd) >= 0.0:      # m1 fully off: diode carries nothing
            return 0.0, vdd
        x = brentq(f, vt, vdd)
        return n_id(W, L, x, inp, vt), x
    vt = brentq(lambda vt: tail(vt) - i1_of(vt)[0] - i2_of(vt), 1e-6, min(inp, inn) - 1e-6)
    i1, vd1 = i1_of(vt)
    return p_id(W, L, vout, vd1, vdd) - i2_of(vt)


def spatial_drop(vdd, vmid, inj, active):
    """Linear DC solution of one polarity's 4-node graph; returns {edge: (node_i, s_e)}."""
    sites = [1, 2, 3, 4]
    names = [f"n{s}" for s in sites] + [f"s{i}{j}" for i, j in zip(sites[:-1], sites[1:])]
    idx = {n: k for k, n in enumerate(names)}
    G = np.zeros((len(names), len(names)))
    b = np.zeros(len(names))

    def cond(a, c, g):
        G[idx[a], idx[a]] += g
        G[idx[c], idx[c]] += g
        G[idx[a], idx[c]] -= g
        G[idx[c], idx[a]] -= g
    for s in sites:
        G[idx[f"n{s}"], idx[f"n{s}"]] += 1 / v("SP_RL")
        b[idx[f"n{s}"]] += vmid / v("SP_RL") + (inj if s in active else 0.0)
    for i, j in zip(sites[:-1], sites[1:]):
        cond(f"n{i}", f"s{i}{j}", 1 / v("SP_RS"))
        cond(f"s{i}{j}", f"n{j}", 1 / v("SP_RT"))
    x = np.linalg.solve(G, b)
    return {f"{i}{j}": (x[idx[f"n{i}"]], x[idx[f"s{i}{j}"]]) for i, j in zip(sites[:-1], sites[1:])}


# ------------------------------------------------------------------ certificate
U_GRID = np.linspace(0.0, 0.6, 61)   # membrane excursion u = vm - vrest over which inputs are bounded


def tab(fn, vrest):
    """Tabulate a branch current I(u) on U_GRID (the membrane is the branch's load)."""
    return np.array([fn(vrest + u) for u in U_GRID])


def u_steady(Iu, scale, Rm, u_cap=0.6):
    """Steady membrane excursion without reset: smallest u with Rm*scale*I(u) = u."""
    g = Rm * scale * Iu - U_GRID
    k = np.where(g <= 0)[0]
    if len(k) == 0:
        return u_cap          # input keeps the membrane above the bounded range
    k = k[0]
    if k == 0:
        return 0.0
    return float(U_GRID[k - 1] + (U_GRID[k] - U_GRID[k - 1]) * g[k - 1] / (g[k - 1] - g[k]))


def u_steady_reset(Iu, scale, vrest, vdd, rdis):
    """Steady excursion with q high (reset branch on), input I(u) scaled."""
    f = lambda u: scale * np.interp(u, U_GRID, Iu) - u / v("NM_RM") - i_reset(vrest + u, vrest, vdd, rdis)
    if f(0.0) <= 0:
        return 0.0
    return brentq(f, 0.0, U_GRID[-1]) if f(U_GRID[-1]) < 0 else float(U_GRID[-1])


def u_signed(I_of_vm, vrest, Rm, span=0.6):
    """Signed steady excursion (no reset, q low) under a branch that may source or sink:
    root of I(vrest+u) * Rm - u on [-span, span]. Used for the expected weak-segment move."""
    f = lambda u: I_of_vm(vrest + u) * Rm - u
    lo, hi = -span, span
    if f(lo) < 0:
        return lo
    if f(hi) > 0:
        return hi
    return brentq(f, lo, hi)


def role_inputs(R):
    """Input branches of each role as tabulated I(u) (actual branch, membrane as load)."""
    vdd, vrest = R["vdd"], R["vrest"]
    out = {}
    # G0 collector: actual input is the AND-gated ilimp copy; bench weak/valid are gated
    # irefp copies with legal geometry (registered in ae41504)
    out["G0"] = {"weak": tab(lambda x: gated_copy(vdd, R["irefp_n"], 1.2e-6, 4e-6, x), vrest),
                 "valid": tab(lambda x: gated_copy(vdd, R["irefp_n"], 4e-6, 4e-6, x), vrest),
                 "max": tab(lambda x: gated_copy(vdd, R["ilimp_n"], v("BIAS_W"), v("BIAS_L"), x), vrest),
                 "branches": {"weak": "gated irefp copy W/L 1.2/4 um", "valid": "gated irefp copy 4/4 um",
                              "max": "gated ilimp copy 4/4 um (actual collector input)"}}
    # Sigma: OTA reading the R_sense drop of the 4-node graph (edge 1-2)
    inj = gated_copy(vdd, R["irefp_n"], v("BIAS_W") * v("SP_INJ_N"), v("BIAS_L"), R["vmid"])
    g = {k: spatial_drop(vdd, R["vmid"], inj, active=a)["12"]
         for k, a in (("idle", set()), ("single", {1}), ("reverse", {2}), ("sync", {1, 2}))}
    ota = lambda pair: tab(lambda x: ota_out(vdd, pair[0], pair[1], x), vrest)
    idle, rev = ota(g["idle"]), ota(g["reverse"])
    out["Sigma"] = {"weak": np.maximum(idle, rev), "valid": ota(g["single"]),
                    "max": tab(lambda x: ota_out(vdd, R["vmid"] + 0.3, R["vmid"] - 0.3, x), vrest),
                    "sync_info": ota(g["sync"]),
                    "graph": {"inj_A": inj, **{f"{k}_drop_V": p[0] - p[1] for k, p in g.items()}},
                    "graph_nodes": {**{k: [float(p[0]), float(p[1])] for k, p in g.items()},
                                    "vmid": float(R["vmid"])},
                    "branches": {"weak": "OTA at idle graph and at a reverse-direction single event",
                                 "valid": "OTA at a forward single-site event", "max": "OTA fully steered (+-0.3 V)",
                                 "sync_info": "OTA at a synchronous two-site event (reported, judged by INVALID_SYNC)"}}
    # Theta/Cdir: relation stack + 1/16 mirror; max with h at the continuous-conduction bound
    hb = history_bound(vdd)
    out["Theta_Cdir"] = {"max": tab(lambda x: relation_input(vdd, hb, x), vrest), "h_bound_V": hb,
                         "branches": {"max": f"stack with h at continuous-conduction bound {hb:.3f} V"}}
    return out


# Inherited chain stimulus (dev-006/007 decks: +-3 K steps of 7 s); intervals from the v1.1 table
STEP_S = 7.0
INTERVALS_S = (1.5, 3.0)


def theta_chain_entry(R, g0, interval, cm, scale, dt=1e-3):
    """Θ receiver entry time after the target G0 starts: the source collector fires with its
    shortest q and estimated period for STEP_S; the source history charges through the real
    switch; the target activity gates the stack from `interval` on. Returns (t_entry, h)."""
    vdd, vrest = R["vdd"], R["vrest"]
    ue = thresholds(R["vthr"], vdd)[0] - vrest
    hs = np.linspace(0.0, 2.45, 50)
    Ih = np.array([relation_input(vdd, h, vrest) for h in hs])
    w, P = g0["event_source_timing"]["q_width_min_s"], g0["event_source_timing"]["period_max_s"]
    h1 = h = u = 0.0
    t = 0.0
    while t < interval + STEP_S:
        on = t < STEP_S and (t % P) < w
        if on:
            sd = brentq(lambda sd: p_id(4e-6, 0.5e-6, sd, 0.0, vdd) - (sd - h1) / v("HIST_RR"), h1, vdd)
            iin = (sd - h1) / v("HIST_RR")
        else:
            iin = 0.0
        i12 = (h1 - h) / v("HIST_R2")
        h1 += dt * (iin - i12) / v("HIST_C1")
        h += dt * (i12 - h / v("HIST_RL")) / v("HIST_C2")
        I = scale * np.interp(h, hs, Ih) if t >= interval else 0.0
        u += dt * (I - u / v("NM_RM")) / cm
        if u >= ue + DELTA_V:
            return t - interval, h
        t += dt
    return None, h


def certificate(vsrc=VSRC):
    R = supply_and_refs(vsrc)
    vdd, vrest = R["vdd"], R["vrest"]
    I = role_inputs(R)
    Rm = v("NM_RM")
    res = {"refs": R, "roles": {}, "stimulus": {"step_s": STEP_S, "intervals_s": INTERVALS_S,
                                                "source": "dev-006/007 decks (+-3 K, 7 s steps)"}}
    for role, spec in ROLES.items():
        ue_abs, ux_abs = thresholds(R[spec["ref"]], vdd)
        ue, ux = ue_abs - vrest, ux_abs - vrest
        rdis, cm = v(spec["Rdis"]), v(spec["Cm"])
        rr = {"u_entry_V": ue, "u_exit_low_V": ux, "Rdis": rdis, "Cm": cm, "checks": {}, "unknown": [],
              "branches": I[role].get("branches")}
        if "graph_nodes" in I[role]:
            rr["inputs_graph"] = I[role]["graph_nodes"]
            rr["inputs_graph_info"] = I[role]["graph"]
        if "h_bound_V" in I[role]:
            rr["inputs_h_bound_V"] = I[role]["h_bound_V"]
        inp = I[role]
        # ---- exit under the strongest actual input (Ron upper bound via the nonlinear branch)
        uinf = u_steady_reset(inp["max"], 1 + MIRROR_TOL, vrest, vdd, rdis * (1 + TOL_RDIS))
        rr["checks"]["max_exit"] = {"u_inf_V": uinf, "margin_V": ux - DELTA_V - uinf,
                                    "pass": bool(uinf < ux - DELTA_V)}
        # ---- q forms and exits; shortest (no input, fast reset) and longest (max input, slow)
        imax_u = lambda u: float(np.interp(u, U_GRID, inp["max"]))
        tmin, ok_min = q_width(0.0, ue, ux, vrest, vdd, rdis * (1 - TOL_RDIS), cm * (1 - TOL_CM))
        tmax, ok_max = q_width(imax_u(ue) * (1 + MIRROR_TOL), ue, ux, vrest, vdd,
                               rdis * (1 + TOL_RDIS), cm * (1 + TOL_CM))
        rr["q_width_min_s"] = tmin if ok_min else None
        rr["q_width_max_s"] = tmax if ok_max else None
        rr["checks"]["q_forms_and_exits"] = {"pass": bool(ok_min and ok_max and tmin > 1e-4),
                                             "q_min_s": tmin, "q_max_s": tmax}
        # ---- trace charge to the shaping trip within the shortest q
        trip = vdd / 2
        ron_t = switch_ron_max(2e-6, 1e-6, vdd, 0.0, trip + DELTA_V)
        tch = charge_time(v("OP_RC") + ron_t, v("OP_C"), v("OP_RL"), vdd, trip + DELTA_V)
        rr["trace"] = {"Ron_sw_max": ron_t, "T_ch_s": tch, "z_req_V": trip + DELTA_V}
        rr["checks"]["trace_charges_in_q"] = {"pass": bool(tch is not None and ok_min and tch <= tmin),
                                              "T_ch_s": tch, "q_min_s": tmin}
        # ---- recovery: rec level that lets the shunt hold vm below entry at the max input
        Im_entry = imax_u(ue) * (1 + MIRROR_TOL)
        vrec_req = shunt_hold_rec(Im_entry, ue - DELTA_V, vrest, vdd)
        ron_r = switch_ron_max(2e-6, 1e-6, vdd, 0.0, (vrec_req or vdd) + DELTA_V)
        tch_r = (charge_time(v("NRC_REC_RC") + ron_r, v("NRC_REC_C"), v("NRC_REC_R"), vdd, vrec_req + DELTA_V)
                 if vrec_req is not None else None)
        rr["recovery"] = {"Vrec_req_V": vrec_req, "Ron_sw_max": ron_r, "T_ch_s": tch_r}
        rr["checks"]["recovery_charges_in_q"] = {"pass": bool(tch_r is not None and ok_min and tch_r <= tmin),
                                                 "T_ch_s": tch_r, "q_min_s": tmin, "Vrec_req_V": vrec_req}
        tau_m_max = Rm * cm * (1 + TOL_CM)
        if vrec_req is not None:
            z_eq = vdd * v("NRC_REC_R") / (v("NRC_REC_RC") + v("NRC_REC_R"))
            hold = v("NRC_REC_R") * v("NRC_REC_C") * math.log(z_eq / vrec_req)
            rr["recovery"]["hold_s_after_full_charge"] = hold
            # sustained-input period estimate (report only): hold + re-entry from the held level + q
            ImRm = Im_entry * Rm
            rr["period_est_s"] = hold + (tau_m_max * math.log((ImRm - (ue - DELTA_V)) / (ImRm - ue))
                                         if ImRm > ue else float("nan")) + tmax
        z_pk = vdd * v("OP_RL") / (v("OP_RC") + v("OP_RL"))
        rr["activity_window_s"] = v("OP_RL") * v("OP_C") * math.log(z_pk / trip)
        # ---- source timing during an event (input on): least charge per pulse for a history it
        #      feeds = shortest q at the smallest on-event current, fastest reset; longest period
        #      = recovery hold at that current + re-entry from the shunt-held level + q
        I_on_min = (1 - MIRROR_TOL) * imax_u(ue)
        w_ev, ok_ev = q_width(I_on_min, ue, ux, vrest, vdd, rdis * (1 - TOL_RDIS), cm * (1 - TOL_CM))
        vrec_min = shunt_hold_rec(I_on_min, ue - DELTA_V, vrest, vdd)
        if ok_ev and vrec_min is not None and I_on_min * Rm > ue:
            z_eq = vdd * v("NRC_REC_R") / (v("NRC_REC_RC") + v("NRC_REC_R"))
            hold_ev = v("NRC_REC_R") * v("NRC_REC_C") * (1 + TOL_CM) * math.log(z_eq / vrec_min)
            reent = tau_m_max * math.log((I_on_min * Rm - (ue - DELTA_V)) / (I_on_min * Rm - ue))
            rr["event_source_timing"] = {"I_on_min_A": I_on_min, "q_width_min_s": w_ev,
                                         "period_max_s": hold_ev + reent + w_ev}
        else:
            rr["event_source_timing"] = None
        # ---- weak / valid (bench and actual-branch inputs)
        if "weak" in inp:
            uw = u_steady(inp["weak"], 1 + MIRROR_TOL, Rm)
            uv = u_steady(inp["valid"], 1 - MIRROR_TOL, Rm)
            rr["checks"]["weak_no_entry"] = {"u_inf_V": uw, "margin_V": ue - DELTA_V - uw,
                                             "pass": bool(uw < ue - DELTA_V)}
            rr["checks"]["valid_entry"] = {"u_inf_V": uv, "margin_V": uv - ue - DELTA_V,
                                           "pass": bool(uv > ue + DELTA_V)}
            Iv = (1 - MIRROR_TOL) * float(np.interp(ue, U_GRID, inp["valid"]))
            rr["T_entry_valid_max_s"] = (tau_m_max * math.log(Iv * Rm / (Iv * Rm - ue))
                                         if Iv * Rm > ue else None)
        if "sync_info" in inp:
            rr["sync_info_u_inf_V"] = u_steady(inp["sync_info"], 1 + MIRROR_TOL, Rm)
        res["roles"][role] = rr
    # ---- Theta/Cdir: valid entry is a chain property (source history x target activity)
    g0, tc, sg = res["roles"]["G0"], res["roles"]["Theta_Cdir"], res["roles"]["Sigma"]
    chain = {}
    for iv in INTERVALS_S:
        te, h = theta_chain_entry(R, g0, iv, tc["Cm"] * (1 + TOL_CM), 1 - MIRROR_TOL)
        chain[f"{iv}s"] = {"t_entry_after_target_s": te, "h_at_entry_V": h,
                           "overlap_window_s": STEP_S + g0["activity_window_s"] - 0.0}
    tc["chain_entry"] = chain
    tc["checks"]["chain_entry_within_target_activity"] = {
        "pass": bool(all(c["t_entry_after_target_s"] is not None and
                         c["t_entry_after_target_s"] <= STEP_S for c in chain.values())), **chain}
    # one shortest source pulse alone must not enter (weak relation input)
    # one source pulse alone must not enter: largest charge per pulse = longest q
    h1p = history_after_pulses(vdd, g0["q_width_max_s"], 1.0, 1)
    Iw1 = (1 + MIRROR_TOL) * relation_input(vdd, h1p, vrest)
    tc["checks"]["single_source_pulse_no_entry"] = {"h_V": h1p, "u_inf_V": Iw1 * Rm,
                                                    "pass": bool(Iw1 * Rm < tc["u_entry_V"] - DELTA_V)}
    # Cdir: input needs Sigma history (written while Sigma activity is high) and Θ activity.
    # Bound: Sigma under a valid event fires within T_entry and its activity is continuous while
    # the event lasts (period < activity window); history then charges continuously.
    sig_cont = sg.get("period_est_s") is not None and sg["period_est_s"] < sg["activity_window_s"]
    sg["checks"]["entry_within_parent_window"] = {
        "pass": bool(sg.get("T_entry_valid_max_s") is not None and sg["T_entry_valid_max_s"] <= STEP_S),
        "T_entry_s": sg.get("T_entry_valid_max_s"), "event_s": STEP_S}
    sg["activity_continuous_during_event"] = bool(sig_cont)
    # Cdir third-level entry depends on Σ history x Θ activity overlap; no offline bound is
    # claimed here -- it is a dynamic quantity measured and judged in the CHAIN/STRUCTURE cases
    res["dynamic_unmeasured"] = ["Cdir third-level entry timing (Σ history x Θ activity overlap)",
                                 "moving references during activity", "comparator delay"]
    # ---- history expiry for INVALID_STALE (valid-entry level -> single-pulse level)
    h_valid = min(c["h_at_entry_V"] for c in chain.values())
    res["history_expiry_s"] = history_decay_time(h_valid, h1p)
    res["history_levels_V"] = {"valid_entry_min": h_valid, "single_pulse": h1p}
    # ---- expected signed weak-segment move of each bench role (the bench's own weak branch):
    #      used by the mother weak gate; registered before any solve
    gn = sg["inputs_graph"]
    idle_I = lambda x: ota_out(vdd, gn["idle"][0], gn["idle"][1], x)
    weak_I = {"G0": lambda x: gated_copy(vdd, R["irefp_n"], 1.2e-6, 4e-6, x),
              "Sigma": lambda x: ota_out(vdd, gn["reverse"][0], gn["reverse"][1], x),
              "Theta_Cdir": lambda x: relation_input(vdd, h1p, x)}
    base_I = {"G0": lambda x: 0.0, "Sigma": idle_I, "Theta_Cdir": lambda x: 0.0}
    for role, rr in res["roles"].items():
        u_base = u_signed(base_I[role], vrest, Rm)
        u_weak = u_signed(weak_I[role], vrest, Rm)
        rr["weak_expected_du_V"] = u_weak - u_base
        rr["weak_baseline_u_V"] = u_base
    # ---- overall
    fails, unknown = [], []
    for role, rr in res["roles"].items():
        unknown += rr.get("unknown", [])
        for k, c in rr["checks"].items():
            if c.get("pass") is not True:
                fails.append(f"{role}:{k}")
    res["failed"] = fails
    res["unknown"] = unknown
    # never "PASS": an offline estimate cannot qualify; it can only find or not find an
    # incompatible constraint. Dynamic items stay listed as unmeasured.
    if fails:
        res["status"] = "INCOMPATIBLE"
    elif unknown:
        res["status"] = "UNKNOWN"
    else:
        res["status"] = "NO_INCOMPATIBILITY_FOUND"
    return res


def main():
    out = {"schema": "thermal_g3_q1r.certificate.2", "kind": "CANDIDATE_ESTIMATE_NOT_QUALIFICATION",
           "model": "analysis/ekv26_static.py (line-by-line VA port, ae41504)",
           "assumptions_unsourced": [
               f"mirror/branch tolerance +-{MIRROR_TOL:.0%} (no mismatch statistics in the card)",
               f"delta = {DELTA_V*1e3:.0f} mV comparator offset + reference ripple",
               "comparator delay and finite inverter edges ignored in q width",
               "references static at their divider values (moving vrest not covered)",
               "junction leakage, substrate and gate charge not ported",
               f"temperature {TEMP_C} C"],
           "nom": certificate(3.0)}
    out["status"] = out["nom"]["status"]
    path = os.path.join(Q1, "analysis", "input_bounds.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, default=float)
    n = out["nom"]
    for role, rr in n["roles"].items():
        print(role, {k: c.get("pass") for k, c in rr["checks"].items()})
    print("history_expiry_s", n["history_expiry_s"])
    print("status", out["status"], n["failed"], n["unknown"])


if __name__ == "__main__":
    main()
