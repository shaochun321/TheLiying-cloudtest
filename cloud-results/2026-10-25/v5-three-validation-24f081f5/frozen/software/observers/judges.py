"""Q1-R judge registry (INFRA, read-only): one entry point per case.

    required(case)                       -> list of vectors this case's judge reads (and, for
                                            baseline comparisons, the baseline's required list)
    judge(case, V, baseline_V, plan)     -> {"result": PASS|FAIL|UNMEASURED, "gates": {...}}

Every gate is an explicit PASS/FAIL/UNMEASURED; the case result is PASS only if every gate is
PASS. Missing vectors -> UNMEASURED, never an exception or a default. Events are VDD/2
crossings on logic nodes. Windows come from the case's registered stimulus (env) and the
offline certificate (analysis/input_bounds.json); Θ and Σ are not forced into an order.

Formal semantics (Q1-R closure review §2D):
  G0        per stimulus step: recruitment order by k; a common window where all ten shaped
            traces b_k_q are high; the AND rise inside it; collector q after the AND rise and
            before the common window ends; port p after collector q, once per step; return
            after the step; the second step repeats it. CUT_Kn: the cut ensemble still fires and
            its trace rises; AND / collector / port silent; uncut ensembles as the baseline.
  CHAIN     no relation q before the stimulus or before its parents; Θ_dir after both parents'
            collector q and while the target activity is high; Σ_dir after the first parent;
            Cdir_dir after Θ_dir and Σ_dir and while Θ_dir is active; Cdir_opposite silent;
            matching rail above vmid by the derived single-path minimum, opposite rail flat;
            everything returns.
            Support (observers/support_q1r.py, every event of every core of the edge): Θ from
            source history AND target activity with the injected charge accounting for entry;
            Σ from the signed spatial difference raised by G0 activity with the OTA charge; Cdir
            from the matching-Σ history AND Θ activity, conflict shunt consistent; canonical
            ports; load path current and rail rise inside Cdir activity only.
  STRUCTURE port CUT / BLEED / SWAP / SYNC / STALE against the baseline raw (see functions),
            plus the same support gates (SWAP with the declared inverted Σ readout)
  FULL      per warm / cool block; MIRROR swaps directions; SPACE_CUT kills edge 23 only; the
            support gates per polarity and edge, and both rails quiet outside Cdir activity
  NUM       half-step comparison against the baseline (observers/halfstep_compare.py)
  DC        static ledger: supply KCL, reference ratios, bias currents, model domain
  MOTHER    criteria_q1r.judge_joint (+ ledger, + analysis/raw_bounds readback attached to the
            output); HALFSTEP: halfstep_compare vs PROTOCOL
"""
import json
import math
import os

import numpy as np

from .observers_q1r import check_axis, edges, observe_role
from .criteria_q1r import judge_joint
from .halfstep_compare import compare
from .ledger_q1r import ledger, model_domain
from .support_q1r import edge_support, rail_quiet_check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P, F, U = "PASS", "FAIL", "UNMEASURED"
MIRROR_TOL = 0.10
FLAT_FRAC = 0.10
EDGE_TOL_S = 1e-3


def _cert():
    return json.load(open(os.path.join(ROOT, "analysis", "input_bounds.json"), encoding="utf-8"))


def _proto():
    return json.load(open(os.path.join(ROOT, "prereg", "protocol_q1r_joint.json"), encoding="utf-8"))


def _g(ok, **kw):
    return {"result": P if ok else F, **{k: (float(v) if isinstance(v, (np.floating,)) else v) for k, v in kw.items()}}


def _fold(gates):
    res = [g["result"] for g in gates.values()]
    return P if res and all(r == P for r in res) else (F if F in res else U)


def _ups(V, name, thr):
    up, dn = edges(V["time"], V[name], thr)
    return up, dn


def _first_in(arr, a, b):
    x = arr[(arr >= a) & (arr <= b)]
    return float(x[0]) if len(x) else None


def _high_at(V, name, t, thr):
    return float(np.interp(t, V["time"], V[name])) > thr


# ------------------------------------------------------------------ required vectors
def g0_vectors(pol, s):
    p = f"g{pol}{s}_"
    v = ["v(vdd)", "v(vrest)", "v(vthe)", "v(vthr)", "v(por_ok)", f"v(s{s}_s)", f"v(s{s}_m)"]
    v += [f"v({p}e{k}_q)" for k in range(1, 11)] + [f"v({p}b{k}_q)" for k in range(1, 11)]
    v += [f"v({p}and_g8)", f"v({p}gb)", f"v({p}col_q)", f"v({p}col_qb)", f"v({p}col_vm)", f"v({p}col_h)",
          f"v({p}col_rec)", f"v({p}col_vmd)", f"v({p}op_at)", f"v({p}op_aq)", f"v({p}op_p)"]
    return v


def chain_vectors(pol, i, j):
    v = ["v(vdd)", "v(vrest)", "v(vmid)", "v(load_pos)", "v(load_neg)"]
    for s in (i, j):
        v += [f"v(g{pol}{s}_col_q)", f"v(g{pol}{s}_op_aq)", f"v(g{pol}{s}_op_p)", f"v(h{pol}{s})"]
    for d in ("f", "r"):
        for kind in ("th", "sg", "cd"):
            rp = f"{kind}{pol}{i}{j}{d}_"
            v += [f"v({rp}{n})" for n in ("vm", "q", "qb", "h", "rec", "vmd", "op_at", "op_aq", "op_p")]
        v += [f"v(cd{pol}{i}{j}{d}_hs)", f"v(cd{pol}{i}{j}{d}_hc)"]
    v += [f"v(sp{pol}{i})", f"v(sp{pol}{j})", f"v(sp{pol}s{i}{j})"]
    return v


def full_vectors():
    v = ["v(vdd)", "v(vrest)", "v(vmid)", "v(load_pos)", "v(load_neg)"]
    for pol in ("w", "c"):
        for s in (1, 2, 3, 4):
            v += [f"v(g{pol}{s}_col_q)", f"v(g{pol}{s}_op_p)", f"v(g{pol}{s}_op_aq)", f"v(h{pol}{s})"]
        v += [f"v(sp{pol}{s})" for s in (1, 2, 3, 4)]
        for i, j in ((1, 2), (2, 3), (3, 4)):
            v += [f"v(sp{pol}s{i}{j})"]
            for d in ("f", "r"):
                for kind in ("th", "sg", "cd"):
                    rp = f"{kind}{pol}{i}{j}{d}_"
                    v += [f"v({rp}{n})" for n in ("vm", "q", "h", "rec", "vmd", "op_at", "op_aq", "op_p")]
                v += [f"v(cd{pol}{i}{j}{d}_hs)", f"v(cd{pol}{i}{j}{d}_hc)"]
    return v


DC_VECTORS = ["v(vsrc)", "v(vdd)", "v(vrest)", "v(vthe)", "v(vthr)", "v(vmid)", "v(iref_n)", "v(irefp_n)",
              "v(ilim_n)", "v(ilimp_n)", "v(istep_n)", "i(vsrc)"]


HALFSTEP_CASES = ("Q1_MOTHER_HALFSTEP", "NUM_G0_HALFSTEP", "NUM_CHAIN_HALFSTEP", "FULL_NUM_HALFSTEP")
HALFSTEP_BASE = {"Q1_MOTHER_HALFSTEP": "Q1_MOTHER_PROTOCOL", "NUM_G0_HALFSTEP": "G0_W",
                 "NUM_CHAIN_HALFSTEP": "CHAIN_12_W_F", "FULL_NUM_HALFSTEP": "FULL_NOM"}


def required(case):
    """Vectors this case's judge reads. A half-step case and its baseline share one list (the
    baseline case's save list is generated from the same function), so the comparison is closed."""
    from .halfstep_compare import required_for
    j, cid, grp = case.get("judge") or {}, case["case_id"], case["group"]
    if grp == "MOTHER":
        return required_for(role_map({"case_id": "Q1_MOTHER_HALFSTEP"}))
    if grp == "G0" or cid == "NUM_G0_HALFSTEP":
        return g0_vectors(j.get("pol", "w"), j.get("site", 1)) + (
            required_for(role_map({"case_id": "NUM_G0_HALFSTEP"})) if cid in ("G0_W", "NUM_G0_HALFSTEP") else [])
    if grp in ("CHAIN", "STRUCTURE") or cid == "NUM_CHAIN_HALFSTEP":
        return chain_vectors(j["pol"], *j["pair"]) + (
            required_for(role_map({"case_id": "NUM_CHAIN_HALFSTEP"})) if cid in ("CHAIN_12_W_F", "NUM_CHAIN_HALFSTEP") else [])
    if grp == "FULL":
        return full_vectors() + (
            required_for(role_map({"case_id": "FULL_NUM_HALFSTEP"})) if cid in ("FULL_NOM", "FULL_NUM_HALFSTEP") else [])
    if grp == "DC":
        return list(DC_VECTORS)
    raise KeyError(cid)


def _missing(V, names):
    return [n for n in names if n.lower() not in V]


# ------------------------------------------------------------------ G0
def g0_step(V, p, a, b, thr, after_s):
    """One stimulus step [a, b]; scored until b + after_s."""
    t1 = b + after_s
    first = {}
    for k in range(1, 11):
        up, _ = _ups(V, f"v({p}e{k}_q)", thr)
        first[k] = _first_in(up, a, t1)
    order = [first[k] for k in range(1, 11)]
    ok_order = all(x is not None for x in order) and all(order[i] <= order[i + 1] + EDGE_TOL_S for i in range(9))
    t = V["time"]
    m = (t >= a) & (t <= t1)
    allhi = np.all(np.vstack([V[f"v({p}b{k}_q)"][m] > thr for k in range(1, 11)]), axis=0)
    common = t[m][allhi]
    win = (float(common[0]), float(common[-1])) if len(common) else None
    and_up, _ = _ups(V, f"v({p}and_g8)", thr)
    col_up, _ = _ups(V, f"v({p}col_q)", thr)
    p_up, _ = _ups(V, f"v({p}op_p)", thr)
    t_and = _first_in(and_up, a, t1)
    t_col = _first_in(col_up, a, t1)
    p_in = p_up[(p_up >= a) & (p_up <= t1)]
    ok_and = win is not None and t_and is not None and win[0] - EDGE_TOL_S <= t_and <= win[1] + EDGE_TOL_S
    ok_col = t_and is not None and t_col is not None and t_col >= t_and - EDGE_TOL_S
    ok_p = len(p_in) == 1 and t_col is not None and p_in[0] >= t_col - EDGE_TOL_S
    end_ok = all(float(np.interp(t1, t, V[f"v({p}{n})"])) < thr for n in ("col_q", "op_aq", "op_p"))
    return {"first_q_s": first, "order": ok_order, "common_window_s": win, "and_in_window": ok_and,
            "collector_after_and": ok_col, "port_once_after_collector": ok_p, "returned": end_ok,
            "t_and": t_and, "t_col": t_col, "n_p": int(len(p_in))}


def judge_g0(case, V, base=None):
    e = check_axis(V)
    if e:
        return {"result": U, "why": e}
    j = case["judge"]
    p = f"g{j['pol']}{j['site']}_"
    miss = _missing(V, g0_vectors(j["pol"], j["site"]))
    if miss:
        return {"result": U, "why": f"missing {miss[:3]}"}
    thr = float(np.median(V["v(vdd)"])) / 2
    steps = case["env"][str(j["site"])] if str(j["site"]) in case["env"] else case["env"][j["site"]]
    after = _cert()["nom"]["roles"]["G0"]["activity_window_s"] + 0.5
    gates = {}
    cut = j.get("cut_k")
    for n, (a, b, _amp) in enumerate(steps, 1):
        s = g0_step(V, p, a, b, thr, after)
        if cut:
            up, _ = _ups(V, f"v({p}e{cut}_q)", thr)
            bup, _ = _ups(V, f"v({p}b{cut}_q)", thr)
            src_ok = _first_in(up, a, b + after) is not None and _first_in(bup, a, b + after) is not None
            silent = s["t_and"] is None and s["t_col"] is None and s["n_p"] == 0
            gates[f"step{n}_cut_source_still_fires"] = _g(src_ok)
            gates[f"step{n}_no_group_output"] = _g(silent, t_and=s["t_and"], t_col=s["t_col"], n_p=s["n_p"])
        else:
            gates[f"step{n}_recruitment_order"] = _g(s["order"], first_q_s=s["first_q_s"])
            gates[f"step{n}_and_in_common_trace_window"] = _g(s["and_in_window"], window=s["common_window_s"], t_and=s["t_and"])
            gates[f"step{n}_collector_after_and"] = _g(s["collector_after_and"], t_col=s["t_col"])
            gates[f"step{n}_port_once_after_collector"] = _g(s["port_once_after_collector"], n_p=s["n_p"])
            gates[f"step{n}_returned"] = _g(s["returned"])
    if cut and base is not None:
        same = True
        for k in range(1, 11):
            if k == cut:
                continue
            a_up, _ = _ups(V, f"v({p}e{k}_q)", thr)
            b_up, _ = _ups(base, f"v({p}e{k}_q)", thr)
            same = same and len(a_up) == len(b_up)
        gates["uncut_ensembles_as_baseline"] = _g(same)
    elif cut:
        gates["uncut_ensembles_as_baseline"] = {"result": U, "why": "baseline raw not available"}
    return {"result": _fold(gates), "gates": gates}


# ------------------------------------------------------------------ CHAIN / STRUCTURE
def _events(V, name, thr):
    up, _ = _ups(V, name, thr)
    return up


def rail_min_rise():
    """Derived minimum rail rise for one active Cdir path: (1-tol) Iref LOAD_R (1 - exp(-T/tau))
    with T = the shortest Cdir activity (certificate activity window)."""
    import sys
    sys.path.insert(0, ROOT)
    from netlists.params import v
    c = _cert()["nom"]
    tau = v("LOAD_R") * v("LOAD_C")
    T = c["roles"]["Theta_Cdir"]["activity_window_s"]
    return (1 - MIRROR_TOL) * c["refs"]["Iref"] * v("LOAD_R") * (1 - math.exp(-T / tau))


def chain_core(V, pol, i, k, dirn, t_stim):
    thr = float(np.median(V["v(vdd)"])) / 2
    fwd, rev = ("f", "r") if dirn == "f" else ("r", "f")
    src, tgt = (i, k) if dirn == "f" else (k, i)
    ev = {n: _events(V, n, thr) for n in (
        f"v(g{pol}{i}_col_q)", f"v(g{pol}{k}_col_q)", f"v(th{pol}{i}{k}{fwd}_q)", f"v(sg{pol}{i}{k}{fwd}_q)",
        f"v(cd{pol}{i}{k}{fwd}_q)", f"v(cd{pol}{i}{k}{rev}_q)", f"v(th{pol}{i}{k}{rev}_q)")}
    first = {n: (float(x[0]) if len(x) else None) for n, x in ev.items()}
    t_src, t_tgt = first[f"v(g{pol}{src}_col_q)"], first[f"v(g{pol}{tgt}_col_q)"]
    th, sg = first[f"v(th{pol}{i}{k}{fwd}_q)"], first[f"v(sg{pol}{i}{k}{fwd}_q)"]
    cd, cdo = first[f"v(cd{pol}{i}{k}{fwd}_q)"], first[f"v(cd{pol}{i}{k}{rev}_q)"]
    parents = t_src is not None and t_tgt is not None and min(t_src, t_tgt) >= t_stim - EDGE_TOL_S
    rel_all = [x for n, arr in ev.items() if "_col_q" not in n for x in arr]
    early = [x for x in rel_all if x < t_stim or (t_src is not None and x < min(t_src, t_tgt or t_src))]
    th_ok = th is not None and parents and th >= max(t_src, t_tgt) - EDGE_TOL_S and \
        _high_at(V, f"v(g{pol}{tgt}_op_aq)", th, thr)
    sg_ok = sg is not None and parents and sg >= min(t_src, t_tgt) - EDGE_TOL_S
    cd_ok = cd is not None and th is not None and sg is not None and cd >= max(th, sg) - EDGE_TOL_S and \
        _high_at(V, f"v(th{pol}{i}{k}{fwd}_op_aq)", cd, thr)
    return {"parents": parents, "no_early_relation": not early, "theta": th_ok, "sigma": sg_ok,
            "cdir": cd_ok, "cdir_opposite_silent": cdo is None, "first": first, "early": early[:5]}


def returned(V, names, thr):
    return all(float(V[n][-1]) < thr for n in names)


def judge_chain(case, V, base=None, plan=None):
    e = check_axis(V)
    if e:
        return {"result": U, "why": e}
    j = case["judge"]
    pol, (i, k) = j["pol"], j["pair"]
    miss = _missing(V, chain_vectors(pol, i, k))
    if miss:
        return {"result": U, "why": f"missing {miss[:3]}"}
    thr = float(np.median(V["v(vdd)"])) / 2
    t_stim = min(seg[0] for segs in case["env"].values() for seg in segs)
    dirn = j.get("dir", "f")
    c = chain_core(V, pol, i, k, dirn, t_stim)
    cid = case["case_id"]
    rr = rail_min_rise()
    vm = V["v(vmid)"]
    rail, orail = ("v(load_pos)", "v(load_neg)") if dirn == "f" else ("v(load_neg)", "v(load_pos)")
    rise = float(np.max(V[rail] - vm))
    orise = float(np.max(V[orail] - vm))
    names_ret = [f"v({kd}{pol}{i}{k}{d}_{n})" for kd in ("th", "sg", "cd") for d in ("f", "r") for n in ("q", "op_aq")]
    gates = {}
    if j["kind"] == "chain":
        gates["parents_after_stimulus"] = _g(c["parents"], first=c["first"])
        gates["no_relation_before_parents"] = _g(c["no_early_relation"], early=c["early"])
        gates["theta_after_parents_in_target_activity"] = _g(c["theta"])
        gates["sigma_after_first_parent"] = _g(c["sigma"])
        gates["cdir_after_theta_and_sigma_in_theta_activity"] = _g(c["cdir"])
        gates["cdir_opposite_silent"] = _g(c["cdir_opposite_silent"])
        gates["matching_rail_consumed"] = _g(rise >= rr, rise_V=rise, min_V=rr)
        gates["opposite_rail_flat"] = _g(orise <= FLAT_FRAC * rr, rise_V=orise, max_V=FLAT_FRAC * rr)
        gates["returned"] = _g(returned(V, names_ret, thr) and abs(float(V[rail][-1] - vm[-1])) <= FLAT_FRAC * rr)
        gates.update(support_gates(case, V, plan, pol, i, k, rr))
        return {"result": _fold(gates), "gates": gates}
    # ---------------- structure: comparisons against the baseline raw
    if base is None and cid not in ("INVALID_SYNC", "INVALID_STALE"):
        return {"result": U, "why": "baseline raw not available"}
    fwd = "f"
    cnt = lambda VV, n: len(_events(VV, n, thr))
    first_t = lambda VV, n: (lambda x: float(x[0]) if len(x) else None)(_events(VV, n, thr))
    parents = [f"v(g{pol}{i}_col_q)", f"v(g{pol}{k}_col_q)"]

    def as_baseline(names):
        tol = 2 * case["max_step_s"] + EDGE_TOL_S
        ok = True
        for n in names:
            if cnt(V, n) != cnt(base, n):
                return False
            a, b = first_t(V, n), first_t(base, n)
            if (a is None) != (b is None) or (a is not None and abs(a - b) > tol):
                ok = False
        return ok
    cd = f"v(cd{pol}{i}{k}{fwd}_q)"
    if cid == "STRUCT_THETA_PORT_CUT":
        gates["parents_and_theta_as_baseline"] = _g(as_baseline(parents + [f"v(th{pol}{i}{k}{fwd}_q)"]))
        gates["target_cdir_silent"] = _g(cnt(V, cd) == 0)
        gates["rail_flat"] = _g(rise <= FLAT_FRAC * rr, rise_V=rise)
    elif cid == "STRUCT_SIGMA_PORT_CUT":
        gates["parents_and_sigma_as_baseline"] = _g(as_baseline(parents + [f"v(sg{pol}{i}{k}{fwd}_q)"]))
        gates["target_cdir_silent"] = _g(cnt(V, cd) == 0)
        gates["rail_flat"] = _g(rise <= FLAT_FRAC * rr, rise_V=rise)
    elif cid == "STRUCT_CDIR_HISTORY_BLEED":
        import re
        m = re.findall(r"[-+0-9.e]+", case["build_args"]["bleed"]["pwl"])
        tb0, tb1 = float(m[4]), float(m[6])
        hs = f"v(cd{pol}{i}{k}{fwd}_hs)"
        h_b = float(np.interp(tb1, V["time"], V[hs]))
        h_0 = float(np.interp(tb1, base["time"], base[hs]))
        in_win = lambda VV: int(np.sum((_events(VV, cd, thr) >= tb0) & (_events(VV, cd, thr) <= tb1 + 2.0)))
        gates["parents_as_baseline"] = _g(as_baseline(parents))
        gates["history_bled"] = _g(h_b <= 0.5 * h_0, h_bleed=h_b, h_base=h_0)
        gates["cdir_reduced_in_bleed_window"] = _g(in_win(V) < in_win(base), n=in_win(V), n_base=in_win(base))
    elif cid == "STRUCT_REAL_SIGMA_SWAP":
        sf, sr = f"v(sg{pol}{i}{k}f_q)", f"v(sg{pol}{i}{k}r_q)"
        gates["sigma_readout_reversed"] = _g(cnt(V, sf) == cnt(base, sr) and cnt(V, sr) == cnt(base, sf),
                                             swap=[cnt(V, sf), cnt(V, sr)], base=[cnt(base, sf), cnt(base, sr)])
        gates["matching_cdir_silent"] = _g(cnt(V, cd) == 0)
    elif cid == "INVALID_SYNC":
        qmax = _cert()["nom"]["roles"]["G0"]["q_width_max_s"]
        a, b = first_t(V, parents[0]), first_t(V, parents[1])
        gates["parents_actually_synchronous"] = _g(a is not None and b is not None and abs(a - b) <= 2 * qmax,
                                                   dt=None if a is None or b is None else abs(a - b))
        gates["no_cdir_either_direction"] = _g(cnt(V, cd) == 0 and cnt(V, f"v(cd{pol}{i}{k}r_q)") == 0)
        gates["rails_flat"] = _g(rise <= FLAT_FRAC * rr and orise <= FLAT_FRAC * rr)
    elif cid == "INVALID_STALE":
        hv = _cert()["nom"]["history_levels_V"]["valid_entry_min"]
        tt = first_t(V, parents[1])
        h_at = None if tt is None else float(np.interp(tt, V["time"], V[f"v(h{pol}{i})"]))
        gates["source_history_expired_at_target"] = _g(h_at is not None and h_at < hv, h=h_at, valid_min=hv)
        gates["no_theta_no_cdir"] = _g(cnt(V, f"v(th{pol}{i}{k}f_q)") == 0 and cnt(V, cd) == 0)
    else:
        return {"result": U, "why": "no structure rule"}
    gates["returned"] = _g(returned(V, names_ret, thr))
    gates.update(support_gates(case, V, plan, pol, i, k, rr, swap=cid == "STRUCT_REAL_SIGMA_SWAP"))
    return {"result": _fold(gates), "gates": gates}


def support_gates(case, V, plan, pol, i, k, rr, swap=False):
    """Relation support of edge (i, k) plus both rails quiet outside its Cdir activity."""
    if plan is None:
        return {"relation_support": {"result": U, "why": "no ledger / probe plan"}}
    g = edge_support(V, plan, case, _cert(), pol, i, k, swap=swap)
    for d, rail in (("f", "load_pos"), ("r", "load_neg")):
        ok, mx = rail_quiet_check(V, rail, [f"v(cd{pol}{i}{k}{d}_op_aq)"], _consts(case), rr, FLAT_FRAC)
        g[f"{rail}_quiet_outside_cdir_activity"] = _g(ok, max_rise_V=mx)
    return g


def _consts(case):
    from .support_q1r import consts
    return consts(case, _cert())


# ------------------------------------------------------------------ FULL
def judge_full(case, V, base=None, plan=None):
    e = check_axis(V)
    if e:
        return {"result": U, "why": e}
    miss = _missing(V, full_vectors())
    if miss:
        return {"result": U, "why": f"missing {miss[:3]}"}
    thr = float(np.median(V["v(vdd)"])) / 2
    env = case["env"]
    segs = sorted((s, seg) for s, ss in env.items() for seg in ss)
    warm = [(int(s), seg) for s, seg in segs if seg[2] > 0]
    cool = [(int(s), seg) for s, seg in segs if seg[2] < 0]
    blocks = {"w": (min(x[1][0] for x in warm), max(x[1][1] for x in warm)),
              "c": (min(x[1][0] for x in cool), max(x[1][1] for x in cool))}
    after = _cert()["nom"]["roles"]["G0"]["activity_window_s"] * 3
    cid = case["case_id"]
    want = {"w": "f", "c": "r"} if cid != "FULL_REAL_MIRROR" else {"w": "r", "c": "f"}
    rr = rail_min_rise()
    gates = {}
    t = V["time"]
    for pol, (a, b) in blocks.items():
        lo, hi = a, b + after
        d = want[pol]
        o = "r" if d == "f" else "f"
        for i, k in ((1, 2), (2, 3), (3, 4)):
            edge = f"{i}{k}"
            cut = cid == "FULL_SPACE_CUT" and edge == "23"
            par = [_first_in(_events(V, f"v(g{pol}{s}_col_q)", thr), lo, hi) for s in (i, k)]
            th = _first_in(_events(V, f"v(th{pol}{edge}{d}_q)", thr), lo, hi)
            sg = _first_in(_events(V, f"v(sg{pol}{edge}{d}_q)", thr), lo, hi)
            cd = _first_in(_events(V, f"v(cd{pol}{edge}{d}_q)", thr), lo, hi)
            cdo = _first_in(_events(V, f"v(cd{pol}{edge}{o}_q)", thr), lo, hi)
            if cut:
                gates[f"{pol}{edge}_cut_cdir_silent"] = _g(cd is None and cdo is None)
                continue
            ok = (all(x is not None for x in par) and th is not None and sg is not None and cd is not None
                  and th >= max(par) - EDGE_TOL_S and sg >= min(par) - EDGE_TOL_S and cd >= max(th, sg) - EDGE_TOL_S)
            gates[f"{pol}{edge}_{d}_chain_in_block"] = _g(ok, parents=par, theta=th, sigma=sg, cdir=cd)
            gates[f"{pol}{edge}_{o}_cdir_silent"] = _g(cdo is None)
        rail = "v(load_pos)" if d == "f" else "v(load_neg)"
        m = (t >= lo) & (t <= hi)
        gates[f"{pol}_rail_consumed"] = _g(float(np.max(V[rail][m] - V["v(vmid)"][m])) >= rr)
    # no Cdir outside both blocks
    outside = 0
    for pol in ("w", "c"):
        for i, k in ((1, 2), (2, 3), (3, 4)):
            for d in ("f", "r"):
                ev = _events(V, f"v(cd{pol}{i}{k}{d}_q)", thr)
                for x in ev:
                    if not any(a <= x <= b + after for a, b in blocks.values()):
                        outside += 1
    gates["no_cdir_outside_blocks"] = _g(outside == 0, n=outside)
    names_ret = [f"v({kd}{pol}{i}{k}{d}_q)" for kd in ("th", "sg", "cd") for pol in ("w", "c")
                 for i, k in ((1, 2), (2, 3), (3, 4)) for d in ("f", "r")]
    gates["returned"] = _g(returned(V, names_ret, thr))
    # relation support per polarity and edge, every event; rails quiet outside Cdir activity
    if plan is None:
        gates["relation_support"] = {"result": U, "why": "no ledger / probe plan"}
    else:
        cert = _cert()
        for pol in ("w", "c"):
            for i, k in ((1, 2), (2, 3), (3, 4)):
                for gname, gv in edge_support(V, plan, case, cert, pol, i, k).items():
                    gates[f"{pol}{i}{k}_{gname}"] = gv
        for d, rail in (("f", "load_pos"), ("r", "load_neg")):
            names = [f"v(cd{pol}{i}{k}{d}_op_aq)" for pol in ("w", "c") for i, k in ((1, 2), (2, 3), (3, 4))]
            ok, mx = rail_quiet_check(V, rail, names, _consts(case), rr, FLAT_FRAC)
            gates[f"{rail}_quiet_outside_cdir_activity"] = _g(ok, max_rise_V=mx)
    return {"result": _fold(gates), "gates": gates}


# ------------------------------------------------------------------ NUM / half-step
def role_map(case):
    """Explicit core / port prefixes, Rdis and ammeters for the half-step comparator."""
    import sys
    sys.path.insert(0, ROOT)
    from netlists.params import v
    cid = case["case_id"]
    if cid == "Q1_MOTHER_HALFSTEP":
        from netlists.bench_mother import PREFIX
        rd = {"g0_": v("NRC_RDIS_G0"), "sg_": v("NRC_RDIS_RCV"), "tc_": v("NRC_RDIS_THETA_CDIR")}
        return [{"core": p, "port": p + "op_", "rdis": rd[p]} for p in PREFIX.values()]
    if cid == "NUM_G0_HALFSTEP":
        return [{"core": "gw1_col_", "port": "gw1_op_", "rdis": v("NRC_RDIS_G0")}]
    if cid == "NUM_CHAIN_HALFSTEP":
        out = []
        for d in ("f", "r"):
            out += [{"core": f"thw12{d}_", "port": f"thw12{d}_op_", "rdis": v("NRC_RDIS_THETA_CDIR")},
                    {"core": f"sgw12{d}_", "port": f"sgw12{d}_op_", "rdis": v("NRC_RDIS_RCV")},
                    {"core": f"cdw12{d}_", "port": f"cdw12{d}_op_", "rdis": v("NRC_RDIS_THETA_CDIR")}]
        return out
    if cid == "FULL_NUM_HALFSTEP":
        out = []
        for pol in ("w", "c"):
            for i, k in ((1, 2), (2, 3), (3, 4)):
                for d in ("f", "r"):
                    out += [{"core": f"{kd}{pol}{i}{k}{d}_", "port": f"{kd}{pol}{i}{k}{d}_op_",
                             "rdis": v("NRC_RDIS_RCV") if kd == "sg" else v("NRC_RDIS_THETA_CDIR")}
                            for kd in ("th", "sg", "cd")]
        return out
    raise KeyError(cid)


def judge_halfstep(case, V, base, ammeters=()):
    if base is None:
        return {"result": U, "why": "baseline raw not available"}
    r = compare(base, V, role_map(case), list(ammeters), case_max_step(case, base=True), case["max_step_s"])
    return {"result": r["result"], "gates": {"halfstep": r}}


def case_max_step(case, base=False):
    return case["max_step_s"] * (2 if base else 1)


# ------------------------------------------------------------------ DC
def judge_dc(case, V, base=None, mos_nodes=None):
    import sys
    sys.path.insert(0, ROOT)
    from netlists.params import v
    from analysis import input_bounds as ib
    miss = _missing(V, DC_VECTORS)
    if miss:
        return {"result": U, "why": f"missing {miss[:3]}"}
    x = {n: float(np.ravel(V[n.lower()])[0]) for n in DC_VECTORS}
    vdd_set = case["judge"]["vdd"]
    est = ib.supply_and_refs(vdd_set)
    gates = {}
    i_supply = -x["i(vsrc)"]
    gates["supply_kcl_across_R_INT"] = _g(abs((x["v(vsrc)"] - x["v(vdd)"]) / v("R_INT") - i_supply)
                                          <= 0.01 * max(abs(i_supply), 1e-9),
                                          drop_current=(x["v(vsrc)"] - x["v(vdd)"]) / v("R_INT"), i_vsrc=i_supply)
    for ref, (rt, rb) in (("vrest", ("VREST_RT", "VREST_RB")), ("vthe", ("VTHE_RT", "VTHE_RB")),
                          ("vthr", ("VTHR_RT", "VTHR_RB")), ("vmid", ("VMID_RT", "VMID_RB"))):
        want = x["v(vdd)"] * v(rb) / (v(rt) + v(rb))
        gates[f"{ref}_divider_ratio"] = _g(abs(x[f"v({ref})"] - want) <= 0.01 * want, value=x[f"v({ref})"], want=want)
    for name, node, R, key in (("Iref", "v(iref_n)", "IREF_R", "Iref"), ("Ilim", "v(ilim_n)", "ILIM_R", "Ilim"),
                               ("Istep", "v(istep_n)", "ISTEP_R", "Istep")):
        i = (x["v(vdd)"] - x[node]) / v(R)
        gates[f"{name}_within_10pct_of_estimate"] = _g(abs(i - est[key]) <= 0.10 * est[key], value=i, estimate=est[key])
    gates["vdd_at_setpoint"] = _g(abs(x["v(vsrc)"] - vdd_set) <= 1e-3, vsrc=x["v(vsrc)"])
    md = model_domain(V, mos_nodes or {})
    gates["model_domain"] = {"result": md["result"], **md}
    return {"result": _fold(gates), "gates": gates, "scope": "static ledger at the op point"}


# ------------------------------------------------------------------ dispatch
def judge(case, V, base=None, plan=None, ammeters=(), mos_nodes=None, ledger_check=True):
    cid, grp = case["case_id"], case["group"]
    if cid == "Q1_MOTHER_PROTOCOL":
        proto, cert = _proto(), _cert()
        from netlists.bench_mother import PREFIX
        obs = {r: observe_role(V, PREFIX[r], proto["roles"][r], t_end_required=proto["total_s"]) for r in PREFIX}
        out = judge_joint(obs, cert)
        res = {"result": out["joint"], "gates": out}
        # measured readback next to the offline estimates (reported, not a gate)
        from analysis.raw_bounds import measured
        res["measured_readback"] = measured(V, plan, proto, cert)
    elif cid in ("Q1_MOTHER_HALFSTEP", "NUM_G0_HALFSTEP", "NUM_CHAIN_HALFSTEP", "FULL_NUM_HALFSTEP"):
        res = judge_halfstep(case, V, base, ammeters)
    elif grp == "G0":
        res = judge_g0(case, V, base)
    elif grp in ("CHAIN", "STRUCTURE"):
        res = judge_chain(case, V, base, plan)
    elif grp == "FULL":
        res = judge_full(case, V, base, plan)
    elif grp == "DC":
        res = judge_dc(case, V, base, mos_nodes or {})
    else:
        return {"result": U, "why": f"no judge for {cid}"}
    if ledger_check and plan and plan.get("nodes") and grp != "DC":
        lg = ledger(V, plan)
        res.setdefault("gates", {})
        if isinstance(res["gates"], dict):
            res["gates"]["physical_ledger"] = lg
        if lg["result"] != P:
            res["result"] = F if lg["result"] == F else (U if res["result"] == P else res["result"])
    return res
