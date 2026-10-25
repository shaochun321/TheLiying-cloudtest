"""Q1-R read-only observers (INFRA). Run after the solver exits; never feed back.

Explicit node map per role (bench_mother.PREFIX): core q / qb, membrane vm, threshold h,
recovery rec, activity trace op_at and shaped activity op_aq / op_aqb, canonical occurrence
op_p / op_pb, branch ammeters. Event thresholds are VDD/2 on rail-to-rail logic nodes.

Every function returns UNMEASURED (a string starting with "UNMEASURED:") when a required vector,
the time axis or the needed time span is missing; nothing is filled with defaults.
"""
import numpy as np

UNM = "UNMEASURED:"
NODES = ("vm", "h", "q", "qb", "rec", "op_at", "op_aq", "op_p")


def is_unmeasured(x):
    return isinstance(x, str) and x.startswith(UNM)


def node_map(prefix):
    return {n: f"v({prefix}{n})" for n in NODES}


def check_axis(V):
    t = V.get("time")
    if t is None or len(t) < 2:
        return UNM + "no time axis"
    if not np.all(np.isfinite(t)) or not np.all(np.diff(t) > 0):
        return UNM + "time axis not finite/strictly increasing"
    return None


def edges(t, x, thr):
    """Rising/falling crossings (linear interpolation). Returns two arrays of times."""
    up = np.where((x[1:] > thr) & (x[:-1] <= thr))[0]
    dn = np.where((x[1:] <= thr) & (x[:-1] > thr))[0]
    ip = lambda i: t[i] + (thr - x[i]) * (t[i + 1] - t[i]) / (x[i + 1] - x[i])
    return np.array([ip(i) for i in up]), np.array([ip(i) for i in dn])


def pulses(t, x, thr, t0, t1):
    """High intervals of x that START inside [t0, t1): list of (t_up, t_down or None).
    A pulse already high at t0 is reported with t_up = t0 and flag 'high_at_start'."""
    up, dn = edges(t, x, thr)
    out = []
    if np.interp(t0, t, x) > thr:
        d = dn[dn > t0]
        out.append({"t_up": float(t0), "t_down": float(d[0]) if len(d) else None, "high_at_start": True})
    for u in up[(up >= t0) & (up < t1)]:
        d = dn[dn > u]
        out.append({"t_up": float(u), "t_down": float(d[0]) if len(d) else None, "high_at_start": False})
    return out


def window(t, x, t0, t1):
    m = (t >= t0) & (t <= t1)
    return x[m] if m.any() else None


def observe_role(V, prefix, plan_role, vdd_nom=3.0, t_end_required=None):
    """Per-role events cut by the role's own protocol segments."""
    err = check_axis(V)
    if err:
        return err
    t = V["time"]
    if t_end_required is not None and t[-1] < t_end_required * (1 - 1e-9):
        return UNM + f"trace ends at {t[-1]:.6g} s < protocol {t_end_required} s"
    nm = node_map(prefix)
    missing = [k for k, n in nm.items() if n not in V]
    if missing:
        return UNM + "missing vectors " + ",".join(missing)
    x = {k: V[n] for k, n in nm.items()}
    bad = [k for k, a in x.items() if len(a) != len(t) or not np.all(np.isfinite(a))]
    if bad:
        return UNM + "non-finite or short vectors " + ",".join(bad)
    vdd = float(np.median(V["v(vdd)"])) if "v(vdd)" in V else vdd_nom
    thr = vdd / 2
    segs = {s["label"]: s for s in plan_role if "t_start_s" in s}
    obs = {"vdd": vdd, "segments": {}}
    for lab, s in segs.items():
        a, b = s["t_start_s"], s["t_end_s"]
        if b <= a:
            continue
        qp = pulses(t, x["q"], thr, a, b)
        for e in qp:   # state reached at the end of each core pulse (trace / recovery charge)
            if e["t_down"] is not None:
                e["op_at_at_end"] = float(np.interp(e["t_down"], t, x["op_at"]))
                e["rec_at_end"] = float(np.interp(e["t_down"], t, x["rec"]))
        seg = {"t0": a, "t1": b,
               "q": qp,
               "aq": pulses(t, x["op_aq"], thr, a, b),
               "p": pulses(t, x["op_p"], thr, a, b)}
        vm = window(t, x["vm"], a, b)
        seg["vm_max"] = float(vm.max()) if vm is not None else None
        seg["vm_min"] = float(vm.min()) if vm is not None else None
        seg["vm_pre"] = float(np.interp(max(a - 1e-3, t[0]), t, x["vm"]))   # level just before the segment
        for k in ("q", "op_aq", "op_p", "rec", "vm", "op_at"):
            seg[f"{k}_end"] = float(np.interp(b, t, x[k]))
            seg[f"{k}_start"] = float(np.interp(a, t, x[k]))
        r = window(t, x["rec"], a, b)
        seg["rec_max"] = float(r.max()) if r is not None else None
        obs["segments"][lab] = seg
    idle = next((s for s in plan_role if s.get("label") == "idle_others_active"), None)
    if idle:
        spans = []
        for a, b in idle["spans"]:
            spans.append({"t0": a, "t1": b, "q": pulses(t, x["q"], thr, a, b),
                          "p": pulses(t, x["op_p"], thr, a, b),
                          "vm_max": float(window(t, x["vm"], a, b).max())})
        obs["idle_others_active"] = spans
    return obs


def charge(t, i, t0, t1):
    m = (t >= t0) & (t <= t1)
    return float(np.trapezoid(i[m], t[m])) if m.sum() > 1 else 0.0
