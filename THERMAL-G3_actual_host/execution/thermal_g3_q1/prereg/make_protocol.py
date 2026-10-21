"""Q1-R mother-qualification protocol generator (INFRA, construction time).

Derives every segment duration of the two-qualification-run protocol from the registered
parameters and the offline candidate estimates in analysis/input_bounds.json (the estimates
are inputs to the schedule only; they qualify nothing). Writes prereg/protocol_q1r_joint.json.

Per role the sequence is: idle -> weak -> recover -> valid -> recover -> max (sustained) ->
withdraw/recover -> re-input -> recover. Roles are STAGGERED: each role's whole sequence runs
while the other two are idle, so every role has an own-idle window while others are active.
Segment lengths:
  POR settle     : POR_R*POR_C*ln(...) release + 5 tau_m of the slowest membrane
  weak           : >= 5 tau_m,max (steady membrane under the weak input is reached)
  valid          : T_entry,valid,max + q_max + 50 ms margin, rounded up to 10 ms
  max            : >= 3 estimated sustained periods + q_max
  recover        : activity exit (trace below shaping trip) + recovery hold + 5 tau_m,max
                   (state returns to baseline before the next segment)
  re-input       : same as valid
Edges are finite ramps EDGE_S; levels are plateaus.
"""
import json
import math
import os
import sys

Q1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, Q1)
from netlists.params import v  # noqa: E402

EDGE_S = 1e-3          # finite gate edge
ROUND_S = 0.01
ROLES = ("G0", "Sigma", "Theta_Cdir")
CM_KEY = {"G0": "NM_CM", "Sigma": "NM_CM", "Theta_Cdir": "NM_CM_THETA_CDIR"}


def up(x):
    return math.ceil(x / ROUND_S - 1e-9) * ROUND_S


def make(cert_path=os.path.join(Q1, "analysis", "input_bounds.json")):
    cert = json.load(open(cert_path, encoding="utf-8"))
    if cert["status"] in ("INCOMPATIBLE", "UNKNOWN"):
        raise SystemExit(f"certificate status {cert['status']}: protocol not generated")
    roles = cert["nom"]["roles"]
    t_por = v("POR_R") * v("POR_C") * math.log(2.0) * 1.5      # release ~ tau ln2, +50 %
    tau_slow = max(v("NM_RM") * v(CM_KEY[r]) * 1.1 for r in ROLES)
    t = up(t_por + 5 * tau_slow)
    segs, plan = [], {}
    for role in ROLES:
        rr = roles[role]
        tau_m = v("NM_RM") * v(CM_KEY[role]) * 1.1
        q_max = rr["q_width_max_s"]
        t_valid_entry = rr.get("T_entry_valid_max_s")
        if role == "Theta_Cdir":
            # bench drives the actual relation stack at the history level the chain reaches
            # at entry (certificate chain_entry); entry time from that level
            t_valid_entry = 5 * tau_m
        recover = up(rr["activity_window_s"] + rr["recovery"]["hold_s_after_full_charge"] + 5 * tau_m)
        d = {"weak": up(5 * tau_m), "valid": up(t_valid_entry + q_max + 0.05),
             "max": up(3 * rr["event_source_timing"]["period_max_s"] + q_max),
             "reinput": up(t_valid_entry + q_max + 0.05)}
        seq = [("weak", d["weak"]), ("recover_w", recover), ("valid", d["valid"]), ("recover_v", recover),
               ("max", d["max"]), ("withdraw", recover), ("reinput", d["reinput"]), ("recover_r", recover)]
        plan[role] = []
        for lab, dur in seq:
            plan[role].append({"label": lab, "t_start_s": round(t, 6), "t_end_s": round(t + dur, 6)})
            t += dur
        segs.append({"role": role, "t_start_s": plan[role][0]["t_start_s"], "t_end_s": round(t, 6)})
    total = up(t + 0.1)
    # own-idle windows: the other roles' active spans
    for role in ROLES:
        own = next(s for s in segs if s["role"] == role)
        plan[role].append({"label": "idle_others_active",
                           "spans": [[s["t_start_s"], s["t_end_s"]] for s in segs if s["role"] != role]})
        plan[role].append({"label": "idle_before", "t_start_s": round(up(t_por), 6),
                           "t_end_s": own["t_start_s"]})
    out = {"schema": "thermal_g3_q1r.protocol.2", "edge_s": EDGE_S, "total_s": total,
           "por_settle_s": up(t_por + 5 * tau_slow), "roles": plan, "role_spans": segs,
           "derivation": {"t_por_release_est_s": t_por, "tau_m_slow_s": tau_slow,
                          "certificate_sha_source": os.path.relpath(cert_path, Q1).replace("\\", "/"),
                          "rule": __doc__.split("Segment lengths:")[1].split("Edges")[0].strip()}}
    path = os.path.join(Q1, "prereg", "protocol_q1r_joint.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
    return out


def gate_pwl(plan_role, label_set, vdd, edge=EDGE_S):
    """PWL text for a low-active gate: low (0 V) during segments whose label is in label_set,
    high (vdd) otherwise; finite edges, plateaus between."""
    pts = [(0.0, vdd)]
    for s in plan_role:
        if s.get("label") in label_set:
            a, b = s["t_start_s"], s["t_end_s"]
            pts += [(a, vdd), (a + edge, 0.0), (b, 0.0), (b + edge, vdd)]
    return "PWL(" + " ".join(f"{t:.6g} {x:.6g}" for t, x in pts) + ")"


if __name__ == "__main__":
    p = make()
    print("total_s", p["total_s"])
    for r in ROLES:
        print(r, [(s["label"], s.get("t_start_s"), s.get("t_end_s")) for s in p["roles"][r][:8]])
