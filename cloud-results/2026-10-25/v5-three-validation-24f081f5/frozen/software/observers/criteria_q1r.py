"""Q1-R qualification criteria (INFRA, read-only judging of observer output).

All gates are evaluated per role on that role's own protocol segments (prereg/protocol_q1r_joint.json).
A gate result is PASS / FAIL / UNMEASURED. The joint verdict is PASS only if all three roles are
present and every required gate of every role is an explicit PASS; anything missing is not PASS.

Gates (Q1 proposal §4; Q1-R review 2026-10-10 §2B):
  idle_before        no q / p while the role has had no input yet
  weak_no_entry      weak segment: no q and no p; membrane moved in the registered direction by at
                     least half of the certificate's expected signed move (Σ: reverse input moves
                     it DOWN); if |expected| < 10 mV, vm stays below vrest + u_entry - delta
  trace_charged_at_q_end / rec_charged_at_q_end   at the end of every closed q in valid/max/reinput:
                     op_at >= certificate z_req and rec >= certificate Vrec_req
  valid_entry        valid segment: q rises; all q pulses close; p fires once
  max_exit           max segment: >= 1 q; EVERY q pulse closes inside the segment window
                     (a pulse still high at segment end, or with no fall, is FAIL)
  withdraw_recovery  withdraw segment (ends before re-input): no new q after the first
                     closure window; at segment end q, aq, p low; rec fell from its max to below
                     the shunt-release level of the certificate; vm back below u_entry (this
                     proves the end state only; charging during q is the rec_charged gate)
  re_arm             reinput segment: q rises again and closes; p fires again
  idle_others_active spans where the other roles are active: no q and no p of this role
Thresholds come from the certificate (u_entry, Vrec_req) and the protocol; no fixed
50 ms / 2.0 V / 10 s constants.
"""
from .observers_q1r import is_unmeasured

P, F, U = "PASS", "FAIL", "UNMEASURED"
V_FLOOR = 0.010          # preregistered near-zero movement scale (10 mV)
WEAK_MOVE_FRAC = 0.5     # the weak segment must move at least half of the registered expected move
DELTA_V = 0.020          # same allowance as the certificate


def _g(ok, **kw):
    return {"result": P if ok else F, **kw}


def _u(why):
    return {"result": U, "why": why}


def judge_role(obs, role_cert, refs):
    if is_unmeasured(obs) or obs is None:
        return {"overall": U, "why": obs if obs else "no observation"}
    S = obs["segments"]
    need = ("weak", "valid", "max", "withdraw", "reinput")
    miss = [k for k in need if k not in S]
    if miss:
        return {"overall": U, "why": "missing segments " + ",".join(miss)}
    vrest = refs["vrest"]
    u_entry = role_cert["u_entry_V"]
    vrec_req = role_cert["recovery"]["Vrec_req_V"]
    g = {}
    ib = S.get("idle_before")
    g["idle_before"] = (_g(not ib["q"] and not ib["p"], q=len(ib["q"]), p=len(ib["p"]))
                        if ib else _u("no idle_before segment"))
    w = S["weak"]
    du = role_cert["weak_expected_du_V"]
    if abs(du) >= V_FLOOR:
        moved = (w["vm_max"] - w["vm_pre"]) if du > 0 else (w["vm_pre"] - w["vm_min"])
        move_ok = moved >= WEAK_MOVE_FRAC * abs(du)
    else:
        moved = w["vm_max"] - w["vm_pre"]
        move_ok = w["vm_max"] < vrest + u_entry - DELTA_V
    g["weak_no_entry"] = _g(not w["q"] and not w["p"] and move_ok, q=len(w["q"]), p=len(w["p"]),
                            expected_du=du, signed_move=moved)
    # charge reached at the end of every core pulse (certificate targets)
    z_req = role_cert["trace"]["z_req_V"]
    pulses_all = [e for k in ("valid", "max", "reinput") for e in S[k]["q"] if e["t_down"] is not None]
    if not pulses_all:
        g["trace_charged_at_q_end"] = _u("no closed q pulse")
        g["rec_charged_at_q_end"] = _u("no closed q pulse")
    else:
        lo_at = min(e["op_at_at_end"] for e in pulses_all)
        lo_rec = min(e["rec_at_end"] for e in pulses_all)
        g["trace_charged_at_q_end"] = _g(lo_at >= z_req, min_V=lo_at, req_V=z_req, n=len(pulses_all))
        g["rec_charged_at_q_end"] = _g(lo_rec >= vrec_req, min_V=lo_rec, req_V=vrec_req, n=len(pulses_all))
    va = S["valid"]
    closed = [x for x in va["q"] if x["t_down"] is not None and x["t_down"] <= va["t1"]]
    g["valid_entry"] = _g(len(va["q"]) >= 1 and len(closed) == len(va["q"]) and len(va["p"]) == 1,
                          q=len(va["q"]), closed=len(closed), p=len(va["p"]))
    mx = S["max"]
    open_ = [x for x in mx["q"] if x["t_down"] is None or x["t_down"] > mx["t1"] or x["high_at_start"]]
    g["max_exit"] = _g(len(mx["q"]) >= 1 and not open_ and mx["q_end"] < refs["vdd"] / 2,
                       q=len(mx["q"]), open=len(open_), q_end=mx["q_end"])
    wd = S["withdraw"]
    ok = (wd["q_end"] < refs["vdd"] / 2 and wd["op_aq_end"] < refs["vdd"] / 2 and wd["op_p_end"] < refs["vdd"] / 2
          and wd["rec_end"] < vrec_req and wd["rec_max"] is not None and wd["rec_end"] < wd["rec_max"]
          and wd["vm_end"] < vrest + u_entry
          and not [x for x in wd["q"] if not x["high_at_start"]])
    g["withdraw_recovery"] = _g(ok, q_end=wd["q_end"], aq_end=wd["op_aq_end"], p_end=wd["op_p_end"],
                                rec_end=wd["rec_end"], rec_max=wd["rec_max"], vrec_req=vrec_req,
                                vm_end=wd["vm_end"], new_q=len([x for x in wd["q"] if not x["high_at_start"]]))
    ri = S["reinput"]
    rclosed = [x for x in ri["q"] if x["t_down"] is not None and x["t_down"] <= ri["t1"]]
    g["re_arm"] = _g(len(ri["q"]) >= 1 and len(rclosed) == len(ri["q"]) and len(ri["p"]) >= 1
                     and not any(x["high_at_start"] for x in ri["q"]),
                     q=len(ri["q"]), closed=len(rclosed), p=len(ri["p"]))
    spans = obs.get("idle_others_active")
    if spans is None:
        g["idle_others_active"] = _u("no idle span in protocol")
    else:
        nq = sum(len(s["q"]) for s in spans)
        npp = sum(len(s["p"]) for s in spans)
        g["idle_others_active"] = _g(nq == 0 and npp == 0, q=nq, p=npp)
    res = [x["result"] for x in g.values()]
    overall = P if res and all(r == P for r in res) else (F if F in res else U)
    return {"gates": g, "overall": overall}


def judge_joint(obs_by_role, cert, roles=("G0", "Sigma", "Theta_Cdir")):
    """Joint verdict: every required role present, every gate an explicit PASS."""
    out = {}
    for r in roles:
        o = obs_by_role.get(r)
        out[r] = judge_role(o, cert["nom"]["roles"][r], cert["nom"]["refs"]) if o is not None else \
            {"overall": U, "why": "role not observed"}
    res = [out[r]["overall"] for r in roles]
    out["joint"] = P if len(res) == len(roles) and all(x == P for x in res) else (F if F in res else U)
    return out
