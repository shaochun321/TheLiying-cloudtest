"""Q1-R measured-value readback (INFRA, read-only). Before the qualification solve exists every
item is UNMEASURED; after it, values are read from the raw of Q1_MOTHER_PROTOCOL and placed
next to the offline candidate estimates (they never overwrite them). The production judge
attaches this readback to the Q1_MOTHER_PROTOCOL judge output (observers/judges.py).

measured per role (the certificate's declared readback items):
  q              every q in valid / max / reinput: width, rec and op_at at its falling edge
                 (vs certificate Vrec_req and z_req); shortest / longest width (vs q_width_min/max)
  entry delay    first q in the valid segment minus the segment start (vs T_entry_valid_max)
  activity       op_aq high time after the first q of the valid and reinput segments (vs the
                 certificate activity window)
  membrane       vm peak in the max segment; vm at the weak segment start and its signed extreme
                 (vs weak_expected_du)
  branches       per segment, for every terminal at the role's vm ledger node: charge into the
                 element and mean current (ammeters from the ledger plan)
Missing vectors -> that item UNMEASURED; nothing is defaulted.
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from observers.observers_q1r import UNM, check_axis, edges  # noqa: E402

PREFIX = {"G0": "g0_", "Sigma": "sg_", "Theta_Cdir": "tc_"}
SEGS = ("weak", "valid", "max", "withdraw", "reinput")


def _at(t, x, tt):
    return float(np.interp(tt, t, x))


def _estimate(rc):
    return {"q_width_min_s": rc.get("q_width_min_s"), "q_width_max_s": rc.get("q_width_max_s"),
            "T_entry_valid_max_s": rc.get("T_entry_valid_max_s"), "activity_window_s": rc.get("activity_window_s"),
            "Vrec_req_V": rc["recovery"]["Vrec_req_V"], "z_req_V": rc["trace"]["z_req_V"],
            "weak_expected_du_V": rc.get("weak_expected_du_V")}


def measured(V, plan=None, proto=None, cert=None):
    out = {"schema": "thermal_g3_q1r.measured.2"}
    e = check_axis(V)
    if e:
        return {**out, "status": "UNMEASURED", "why": e}
    proto = proto or json.load(open(os.path.join(ROOT, "prereg", "protocol_q1r_joint.json"), encoding="utf-8"))
    cert = cert or json.load(open(os.path.join(ROOT, "analysis", "input_bounds.json"), encoding="utf-8"))
    t = V["time"]
    thr = float(np.median(V["v(vdd)"])) / 2
    for role, pr in PREFIX.items():
        r = {"offline_estimate": _estimate(cert["nom"]["roles"][role])}
        segs = {s["label"]: s for s in proto["roles"][role] if "t_start_s" in s}
        q = V.get(f"v({pr}q)")
        if q is None:
            out[role] = UNM + "q missing"
            continue
        up, dn = edges(t, q, thr)
        pulses = []
        for lab in ("valid", "max", "reinput"):
            s = segs[lab]
            for u in up[(up >= s["t_start_s"]) & (up < s["t_end_s"])]:
                d = dn[dn > u]
                if not len(d):
                    pulses.append({"segment": lab, "t_up": float(u), "t_down": None})
                    continue
                d = float(d[0])
                p = {"segment": lab, "t_up": float(u), "t_down": d, "width_s": d - float(u)}
                for n, key in (("rec", "rec_at_end_V"), ("op_at", "op_at_at_end_V")):
                    x = V.get(f"v({pr}{n})")
                    p[key] = _at(t, x, d) if x is not None else UNM + f"{n} missing"
                pulses.append(p)
        r["q"] = pulses
        ws = [p["width_s"] for p in pulses if "width_s" in p]
        r["q_width_min_s"] = min(ws) if ws else None
        r["q_width_max_s"] = max(ws) if ws else None
        recs = [p["rec_at_end_V"] for p in pulses if isinstance(p.get("rec_at_end_V"), float)]
        r["rec_at_q_end_min_V"] = min(recs) if recs else UNM + "no closed q / rec"
        ats = [p["op_at_at_end_V"] for p in pulses if isinstance(p.get("op_at_at_end_V"), float)]
        r["op_at_at_q_end_min_V"] = min(ats) if ats else UNM + "no closed q / op_at"
        va = segs["valid"]
        ent = up[(up >= va["t_start_s"]) & (up < va["t_end_s"])]
        r["entry_delay_valid_s"] = float(ent[0] - va["t_start_s"]) if len(ent) else None
        aq = V.get(f"v({pr}op_aq)")
        act = {}
        for lab in ("valid", "reinput"):
            s = segs[lab]
            first = up[(up >= s["t_start_s"]) & (up < s["t_end_s"])]
            if aq is None:
                act[lab] = UNM + "op_aq missing"
            elif not len(first):
                act[lab] = None
            else:
                aup, adn = edges(t, aq, thr)
                a0 = aup[aup >= first[0] - 1e-3]
                a1 = adn[adn > a0[0]] if len(a0) else []
                act[lab] = float(a1[0] - a0[0]) if len(a0) and len(a1) else None
        r["activity_window_s"] = act
        mx = segs["max"]
        vm = V.get(f"v({pr}vm)")
        if vm is not None:
            r["vm_peak_max_seg_V"] = float(np.max(vm[(t >= mx["t_start_s"]) & (t <= mx["t_end_s"])]))
            w = segs["weak"]
            m = (t >= w["t_start_s"]) & (t <= w["t_end_s"])
            pre = vm[t < w["t_start_s"]]
            v0 = float(pre[-1]) if len(pre) else float(vm[0])      # last sample before the segment
            r["weak_vm_pre_V"] = v0
            r["weak_signed_extreme_du_V"] = float(vm[m].max() - v0) if (vm[m].max() - v0) >= (v0 - vm[m].min()) \
                else float(vm[m].min() - v0)
        # branch charges at the role's vm ledger node
        node = f"{pr}vm"
        terms = (plan or {}).get("terms", {}).get(node)
        if not terms:
            r["branches"] = UNM + "no ledger plan for " + node
        else:
            br = {}
            for it in terms:
                x = V.get(it["vec"].lower())
                if x is None:
                    br[it["element"]] = UNM + f"{it['vec']} missing"
                    continue
                i_in = it["sign"] * x
                per = {}
                for lab in SEGS:
                    s = segs[lab]
                    m = (t >= s["t_start_s"]) & (t <= s["t_end_s"])
                    qc = float(np.trapezoid(i_in[m], t[m])) if m.sum() > 1 else 0.0
                    per[lab] = {"charge_C": qc, "mean_A": qc / max(s["t_end_s"] - s["t_start_s"], 1e-12)}
                br[it["element"]] = {"kind": it["kind"], "per_segment": per}
            r["branches"] = br
        out[role] = r
    out["status"] = "MEASURED"
    return out


def readback(raw_path=None, plan=None):
    if raw_path is None or not os.path.exists(raw_path):
        return {"schema": "thermal_g3_q1r.measured.2", "status": "UNMEASURED",
                "why": "no Q1_MOTHER_PROTOCOL raw (no qualification solve yet)"}
    from solver_adapter.read_raw import read_raw
    if plan is None:
        from runtime.decks import case_assets
        plan = case_assets("Q1_MOTHER_PROTOCOL")["plan"]
    return measured(read_raw(raw_path)[-1], plan)


if __name__ == "__main__":
    print(json.dumps(readback(sys.argv[1] if len(sys.argv) > 1 else None), indent=1))
