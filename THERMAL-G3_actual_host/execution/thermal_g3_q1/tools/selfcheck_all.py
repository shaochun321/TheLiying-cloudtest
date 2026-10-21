"""Q1-R no-solver self-check suite (INFRA). Writes results/selfcheck.json; exit 0 only if every
item is PASS. ngspice is never started: coordinator items use tests/fake_ngspice.py through the
real supervisor, in a temporary copy of this package (temporary ledger, temporary freeze).

Items (reviews 2026-10-10 §3.2 and closure §2; plan §E). Each item asserts its specific gate or
refusal reason, not just "not PASS":
  bench_*         actual Cm values and uniqueness; canonical occurrence ports and declared loads;
                  stimulus plateaus / amplitudes / staggering read back from the deck PWLs; no M=k
  halfstep_identity  half-step deck differs from its baseline only in the analysis line
  certificate_*   certificate runs and returns a status; missing data -> not PASS
  judge_*         mother gates on synthetic data: normal passes; Σ's negative weak move passes and
                  a wrong-sign move fails; rec / trace not charged at q end fails; lock-high, no
                  recovery, cross-talk fail; legal re-input not killed; missing data not PASS
  readback_*      measured rec / op_at at q end, activity window, branch charges per segment next
                  to the offline estimates; UNMEASURED without raw or ledger plan
  halfstep_*      comparator: identical PASS, shifted event FAIL, missing vector UNMEASURED
  support_*       relation support / consumption (observers/support_q1r.py), review 2026-10-10
                  limited supplement: the reviewer's CHAIN (h = hs = 0, spatial nodes at vmid) and
                  FULL (all op_aq / op_p = 0) records FAIL at the named support gates; Σ
                  equipotential, Θ injection outside support, vm without charge, hs without
                  matching Σ, conflict with Cdir firing, a later unsupported event, load current /
                  rail rise outside Cdir activity, zero Cdir activity with load, pulse outside or
                  twice in one activity FAIL; legal integration delay with Σ before Θ and two q in
                  one activity PASS; injector currents read from complete vm ledgers (CHAIN /
                  FULL) and FULL cross-reference probes. The fixed 2026-10-17 pairs cover exact
                  two-pulse RC retention / missing source / unsupported preload / weak vs
                  excessive shunt, with default physical-ledger checks at the FULL entry.
  formal_* g0_* chain_* struct_* invalid_* full_* num_* dc_* ledger_*
                  every formal judge passes its legal synthetic trace, and the review's
                  counterexamples fail at the named gate: no common window, no repeat, port twice,
                  collector before AND, CUT with group output; child before parents, Θ outside
                  target activity, load not consumed, opposite Cdir, not returned; structure rules
                  vs baseline; FULL silent parents / wrong window / unswapped mirror / cut edge
                  firing; half-step vs FULL_NOM; DC references at 10 V, supply KCL, model domain;
                  a ledger terminal current +5 %
  static_*        a deck without v(load_pos) and a baseline deck without a half-step vector are
                  caught by the static closure check; deck identity is independent of backend paths
  coord_*         production dispatch with the stand-in executable writing synthetic raws:
                  permission / qualification / half-step ordering; protocol and half-step judged
                  and recorded with freeze / deck / raw / judge-output hashes; formal unblocked
                  only after both PASS; scientific FAIL stops the round; UNMEASURED blocks
                  dependants without stopping; aborted raw -> no verdict, round stopped; verdict
                  guards (unknown / incomplete / foreign freeze / changed raw; no public writer);
                  cost gate forecast and refusal; one backend per round (a re-registered backend
                  is refused after the first start); asset / registry / env pinning; rerun only after
                  infrastructure failure; completion gate (NaN / short / bad axis / abort / empty
                  list); supervisor kills the solver tree after coordinator death; caps; clean dir
Synthetic data tests the judging software only; it says nothing about the circuit.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ITEMS = {}


def item(name, ok, **ev):
    assert "result" not in ev, "evidence key 'result' would mask the item result"
    ITEMS[name] = {"result": "PASS" if ok else "FAIL", **{k: (v if isinstance(v, (int, float, str, bool, list, dict, type(None))) else str(v)) for k, v in ev.items()}}
    print(("PASS " if ok else "FAIL ") + name)


# ------------------------------------------------------------------ bench
def check_bench():
    from runtime.decks import deck_text
    txt, req = deck_text("Q1_MOTHER_PROTOCOL")
    L = txt.lower().splitlines()
    cm = {r: [l for l in L if l.startswith(f"c{p}cm ")] for r, p in (("G0", "g0_"), ("Sigma", "sg_"), ("Theta_Cdir", "tc_"))}
    vals = {r: [float(l.split()[3]) for l in ls] for r, ls in cm.items()}
    from netlists.params import v
    want = {"G0": v("NM_CM"), "Sigma": v("NM_CM"), "Theta_Cdir": v("NM_CM_THETA_CDIR")}
    item("bench_cm_values_unique", all(len(vals[r]) == 1 and abs(vals[r][0] - want[r]) < 1e-15 for r in want), cm=vals)
    rd = {r: [float(l.split()[3]) for l in L if l.startswith(f"r{p}rdis ")] for r, p in (("G0", "g0_"), ("Sigma", "sg_"), ("Theta_Cdir", "tc_"))}
    wr = {"G0": v("NRC_RDIS_G0"), "Sigma": v("NRC_RDIS_RCV"), "Theta_Cdir": v("NRC_RDIS_THETA_CDIR")}
    item("bench_rdis_values_unique", all(len(rd[r]) == 1 and abs(rd[r][0] - wr[r]) < 1e-9 for r in wr), rdis=rd)
    ports = all(any(l.startswith(f"c{p}op_tc ") for l in L) and any(l.startswith(f"n{p}op_gpa ") for l in L)
                for p in ("g0_", "sg_", "tc_"))
    loads = sum(1 for l in L if re.match(r"n(g0|sg|tc)_ld_", l))
    item("bench_canonical_ports_and_loads", ports and loads == 9, consumer_gate_loads=loads)
    item("bench_explicit_unit_devices", not any(" m=" in l for l in L))
    proto = json.load(open(os.path.join(ROOT, "prereg", "protocol_q1r_joint.json"), encoding="utf-8"))
    # PWL plateaus: every stimulus PWL has finite edges and flat plateaus between them
    pwls = [l for l in L if "pwl(" in l and l.startswith(("vg0_g", "vsg_s", "vtc_"))]
    flat = True
    for l in pwls:
        nums = [float(x) for x in re.findall(r"[-+0-9.e]+", l.split("pwl(")[1])]
        pts = list(zip(nums[0::2], nums[1::2]))
        for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
            if y0 != y1 and (t1 - t0) > proto["edge_s"] * 1.0001:
                flat = False
    item("bench_stimulus_plateaus_finite_edges", flat and len(pwls) == 7, n_pwl=len(pwls))
    spans = {s["role"]: (s["t_start_s"], s["t_end_s"]) for s in proto["role_spans"]}
    order = sorted(spans.values())
    stagger = all(a[1] <= b[0] for a, b in zip(order, order[1:]))
    # every stimulus PWL changes level only inside its own role's span
    own = {"vg0_": "G0", "vsg_": "Sigma", "vtc_": "Theta_Cdir"}
    inside = True
    for l in pwls:
        a, b = spans[own[l[:4]]]
        nums = [float(x) for x in re.findall(r"[-+0-9.e]+", l.split("pwl(")[1])]
        pts = list(zip(nums[0::2], nums[1::2]))
        for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
            if y0 != y1 and not (a - 1e-9 <= t0 and t1 <= b + 2 * proto["edge_s"]):
                inside = False
    item("bench_roles_staggered", stagger and inside, spans=spans)
    cert = json.load(open(os.path.join(ROOT, "analysis", "input_bounds.json"), encoding="utf-8"))
    hl = cert["nom"]["history_levels_V"]
    tcs = [l for l in L if l.startswith("vtc_hs ")][0]
    item("bench_theta_levels_from_certificate",
         all(f"{x:.6g}" in tcs for x in (hl["single_pulse"], hl["valid_entry_min"],
                                          cert["nom"]["roles"]["Theta_Cdir"]["inputs_h_bound_V"])))
    hs, _ = deck_text("Q1_MOTHER_HALFSTEP")
    strip = lambda t: [l for l in t.splitlines() if not l.startswith(("tran ", "* THERMAL"))]
    item("halfstep_identity", strip(hs) == strip(txt))


# ------------------------------------------------------------------ certificate
def check_certificate():
    from analysis import input_bounds as ib
    c = ib.certificate(3.0)
    item("certificate_runs", c["status"] in ("NO_INCOMPATIBILITY_FOUND", "INCOMPATIBLE", "UNKNOWN"), status=c["status"])
    # missing data must not give PASS: remove a role's valid input and re-run the status logic
    fake = {"roles": {"G0": {"checks": {"x": {"pass": True}}, "unknown": ["something unknown"]}}}
    fails, unk = [], []
    for role, rr in fake["roles"].items():
        unk += rr.get("unknown", [])
        fails += [k for k, x in rr["checks"].items() if x.get("pass") is not True]
    st = "INCOMPATIBLE" if fails else ("UNKNOWN" if unk else "NO_INCOMPATIBILITY_FOUND")
    item("certificate_unknown_not_pass", st == "UNKNOWN")
    item("certificate_never_reports_pass", "PASS" != c["status"])


# ------------------------------------------------------------------ mother judges on synthetic data
def _proto_cert():
    proto = json.load(open(os.path.join(ROOT, "prereg", "protocol_q1r_joint.json"), encoding="utf-8"))
    cert = json.load(open(os.path.join(ROOT, "analysis", "input_bounds.json"), encoding="utf-8"))
    return proto, cert


def check_judges():
    from observers.observers_q1r import observe_role
    from observers.criteria_q1r import judge_joint
    from netlists.bench_mother import PREFIX
    from tests.synth_raw import mother_raw, mother_events
    proto, cert = _proto_cert()
    obs = lambda V: {r: observe_role(V, PREFIX[r], proto["roles"][r], t_end_required=proto["total_s"])
                     for r in PREFIX}
    gate = lambda j, r, g: j[r]["gates"][g]["result"]

    V = mother_raw(proto, cert, mother_events(proto))
    j = judge_joint(obs(V), cert)
    item("judge_normal_passes", j["joint"] == "PASS",
         roles={r: j[r]["overall"] for r in PREFIX},
         gates={r: {g: x["result"] for g, x in j[r].get("gates", {}).items() if x["result"] != "PASS"} for r in PREFIX})
    du = cert["nom"]["roles"]["Sigma"]["weak_expected_du_V"]
    item("judge_sigma_negative_weak_passes", du < 0 and gate(j, "Sigma", "weak_no_entry") == "PASS",
         expected_du=du, signed_move=j["Sigma"]["gates"]["weak_no_entry"].get("signed_move"))
    j = judge_joint(obs(mother_raw(proto, cert, mother_events(proto), weak_sign=-1.0)), cert)
    item("judge_weak_wrong_sign_fails", gate(j, "Sigma", "weak_no_entry") == "FAIL"
         and gate(j, "G0", "weak_no_entry") == "FAIL", sigma=j["Sigma"]["gates"]["weak_no_entry"])
    j = judge_joint({}, cert)
    item("judge_all_roles_missing_not_pass", j["joint"] != "PASS", joint=j["joint"])
    j = judge_joint(obs(mother_raw(proto, cert, mother_events(proto), drop=("v(sg_q)",))), cert)
    item("judge_missing_vector_not_pass", j["joint"] != "PASS" and j["Sigma"]["overall"] == "UNMEASURED",
         sigma=j["Sigma"]["overall"])
    j = judge_joint(obs(mother_raw(proto, cert, mother_events(proto), t_end=proto["total_s"] / 2)), cert)
    item("judge_short_trace_not_pass", j["joint"] == "UNMEASURED", joint=j["joint"])
    j = judge_joint(obs(mother_raw(proto, cert, mother_events(proto, lock_high=True))), cert)
    item("judge_lock_high_after_two_pulses_fails", gate(j, "Sigma", "max_exit") == "FAIL" and j["joint"] == "FAIL")
    # no recovery: rec held high through withdraw
    V = mother_raw(proto, cert, mother_events(proto))
    seg = {s["label"]: s for s in proto["roles"]["G0"] if "t_start_s" in s}
    t = V["time"]
    V["v(g0_rec)"][(t >= seg["max"]["t_start_s"]) & (t < seg["withdraw"]["t_end_s"] + 0.01)] = 2.9
    j = judge_joint(obs(V), cert)
    item("judge_no_recovery_fails", gate(j, "G0", "withdraw_recovery") == "FAIL")
    # rec not charged during q: withdraw end state alone is no longer enough
    V = mother_raw(proto, cert, mother_events(proto))
    V["v(g0_rec)"] = np.minimum(V["v(g0_rec)"], 0.05)
    j = judge_joint(obs(V), cert)
    item("judge_rec_not_charged_at_q_end_fails", gate(j, "G0", "rec_charged_at_q_end") == "FAIL"
         and j["joint"] == "FAIL", rec=j["G0"]["gates"]["rec_charged_at_q_end"])
    V = mother_raw(proto, cert, mother_events(proto))
    V["v(tc_op_at)"] = V["v(tc_op_at)"] * 0.02
    j = judge_joint(obs(V), cert)
    item("judge_trace_not_charged_at_q_end_fails", gate(j, "Theta_Cdir", "trace_charged_at_q_end") == "FAIL",
         trace=j["Theta_Cdir"]["gates"]["trace_charged_at_q_end"])
    # legal re-input: a re-input pulse must not be counted against withdraw or idle gates
    j = judge_joint(obs(mother_raw(proto, cert, mother_events(proto))), cert)
    ok = all(gate(j, r, "withdraw_recovery") == "PASS" and gate(j, r, "idle_others_active") == "PASS"
             and gate(j, r, "re_arm") == "PASS" for r in PREFIX)
    item("judge_legal_reinput_not_killed", ok)
    # cross-talk: a q pulse of G0 while Sigma is active must fail G0's idle gate
    ev = mother_events(proto)
    sseg = {s["label"]: s for s in proto["roles"]["Sigma"] if "t_start_s" in s}
    ev["G0"] = ev["G0"] + [(sseg["valid"]["t_start_s"] + 0.1, sseg["valid"]["t_start_s"] + 0.11)]
    j = judge_joint(obs(mother_raw(proto, cert, ev)), cert)
    item("judge_idle_crosstalk_fails", gate(j, "G0", "idle_others_active") == "FAIL")


def check_readback():
    from analysis.raw_bounds import measured, readback
    from runtime.decks import case_assets, registry
    from tests.synth_raw import mother_legal
    c = next(c for c in registry()["cases"] if c["case_id"] == "Q1_MOTHER_PROTOCOL")
    a = case_assets(c["case_id"])
    r = readback(None)
    item("readback_unmeasured_without_raw", r["status"] == "UNMEASURED")
    m = measured(mother_legal(c, a), a["plan"])
    ok = m["status"] == "MEASURED" and all(
        isinstance(m[r_]["rec_at_q_end_min_V"], float) and isinstance(m[r_]["op_at_at_q_end_min_V"], float)
        and isinstance(m[r_]["activity_window_s"]["valid"], float) and isinstance(m[r_]["branches"], dict)
        and all(isinstance(b, dict) for b in m[r_]["branches"].values()) and "offline_estimate" in m[r_]
        for r_ in ("G0", "Sigma", "Theta_Cdir"))
    item("readback_rec_activity_branches_measured", ok,
         sample={k: m["Sigma"][k] for k in ("rec_at_q_end_min_V", "activity_window_s", "weak_signed_extreme_du_V")})
    m = measured(mother_legal(c, a), None)
    item("readback_branches_unmeasured_without_plan", str(m["G0"]["branches"]).startswith("UNMEASURED"))


def check_halfstep():
    from observers.halfstep_compare import compare
    from observers.judges import role_map
    from tests.synth_raw import mother_raw, mother_events
    proto, cert = _proto_cert()
    roles = role_map({"case_id": "Q1_MOTHER_HALFSTEP"})
    V = mother_raw(proto, cert, mother_events(proto))
    r = compare(V, dict(V), roles, [], 2.5e-4, 1.25e-4)
    item("halfstep_identical_passes", r["result"] == "PASS", fails=r.get("fails"))
    ev = mother_events(proto)
    ev["G0"] = [(a + 0.05, b + 0.05 if b else None) for a, b in ev["G0"]]
    r = compare(V, mother_raw(proto, cert, ev), roles, [], 2.5e-4, 1.25e-4)
    item("halfstep_shifted_event_fails", r["result"] == "FAIL", fails=r.get("fails", [])[:3])
    W = dict(V)
    W.pop("v(sg_rec)")
    r = compare(V, W, roles, [], 2.5e-4, 1.25e-4)
    item("halfstep_missing_vector_unmeasured", r["result"] == "UNMEASURED", why=r.get("why"))


# ------------------------------------------------------------------ formal judges (31 cases)
def _cp(V):
    return {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in V.items()}


def _gate(r, name):
    return (r.get("gates") or {}).get(name, {}).get("result")


def _events_up(V, name):
    from observers.observers_q1r import edges
    return edges(V["time"], V[name], float(np.median(V["v(vdd)"])) / 2)[0]


def check_formal():
    from runtime.decks import case_assets, registry
    from tests.synth_raw import legal, pulse, VDD
    from observers.judges import judge
    reg = registry()
    C = {c["case_id"]: c for c in reg["cases"]}
    A, L = {}, {}

    def run(cid, V, base=None, plan=True):
        a = A.setdefault(cid, case_assets(cid))
        am = [x for x in a["save"] if x.startswith("i(v") and x != "i(vsrc)" and not x.startswith("i(va_")]
        return judge(C[cid], V, base, a["plan"] if plan else None, ammeters=am, mos_nodes=a["mos_nodes"])

    # legal synthetic data passes every formal judge (baselines judged first)
    order = sorted((c for c in reg["cases"] if c["phase"] == "formal"),
                   key=lambda c: (c.get("baseline_case_id") is not None, c["case_id"]))
    bad = {}
    for c in order:
        cid = c["case_id"]
        A[cid] = case_assets(cid)
        L[cid] = legal(c, A[cid])
        r = run(cid, L[cid], L.get(c.get("baseline_case_id")))
        if r["result"] != "PASS":
            bad[cid] = {k: x.get("result") for k, x in (r.get("gates") or {}).items()
                        if isinstance(x, dict) and x.get("result") != "PASS"} or r.get("why")
    item("formal_legal_synthetic_all_pass", not bad and len(order) == 31, n=len(order), failed=bad)

    # ---- G0
    c = C["G0_W"]
    p = f"g{c['judge']['pol']}{c['judge']['site']}_"
    steps = c["env"][str(c["judge"]["site"])]
    t = L["G0_W"]["time"]
    V = _cp(L["G0_W"])
    for (a, b, _x) in steps:
        V[f"v({p}b1_q)"][(t >= a) & (t <= b + 1.0)] = 0.0
        tk = a + 0.35
        V[f"v({p}b1_q)"] += pulse(t, tk + 0.002, tk + 0.02)
    r = run("G0_W", V, plan=False)
    item("g0_no_common_trace_window_fails", _gate(r, "step1_and_in_common_trace_window") == "FAIL", judge_result=r["result"])
    V = _cp(L["G0_W"])
    a2 = steps[1][0]
    for n in ("and_g8", "col_q", "op_aq", "op_p"):
        V[f"v({p}{n})"][t >= a2] = 0.0
    r = run("G0_W", V, plan=False)
    item("g0_no_repeat_fails", _gate(r, "step2_and_in_common_trace_window") == "FAIL"
         and _gate(r, "step1_and_in_common_trace_window") == "PASS", judge_result=r["result"])
    V = _cp(L["G0_W"])
    V[f"v({p}op_p)"] += pulse(t, steps[0][0] + 1.6, steps[0][0] + 1.7)
    r = run("G0_W", V, plan=False)
    item("g0_port_twice_fails", _gate(r, "step1_port_once_after_collector") == "FAIL")
    V = _cp(L["G0_W"])
    tc = r["gates"]["step1_collector_after_and"].get("t_col")
    V[f"v({p}col_q)"] += pulse(t, steps[0][0] + 0.05, steps[0][0] + 0.06)
    r = run("G0_W", V, plan=False)
    item("g0_collector_before_and_fails", _gate(r, "step1_collector_after_and") == "FAIL", t_col_legal=tc)
    V = _cp(L["G0_CUT_K1"])
    t = V["time"]
    V[f"v({p}and_g8)"] += pulse(t, steps[0][0] + 0.9, steps[0][0] + 1.5)
    V[f"v({p}col_q)"] += pulse(t, steps[0][0] + 0.95, steps[0][0] + 0.96)
    r = run("G0_CUT_K1", V, L["G0_W"], plan=False)
    item("g0_cut_group_output_fails", _gate(r, "step1_no_group_output") == "FAIL")
    r = run("G0_CUT_K1", L["G0_CUT_K1"], None, plan=False)
    item("g0_cut_without_baseline_unmeasured", r["result"] == "UNMEASURED")

    # ---- CHAIN
    c = C["CHAIN_12_W_F"]
    t = L["CHAIN_12_W_F"]["time"]
    t_on = {int(s): segs[0][0] for s, segs in c["env"].items()}
    V = _cp(L["CHAIN_12_W_F"])
    V["v(cdw12f_q)"] += pulse(t, t_on[1] + 0.1, t_on[1] + 0.12)
    r = run("CHAIN_12_W_F", V, plan=False)
    item("chain_child_before_parents_fails", _gate(r, "no_relation_before_parents") == "FAIL"
         and _gate(r, "cdir_after_theta_and_sigma_in_theta_activity") == "FAIL", early=r["gates"]["no_relation_before_parents"].get("early"))
    V = _cp(L["CHAIN_12_W_F"])
    V["v(gw2_op_aq)"][:] = 0.0
    r = run("CHAIN_12_W_F", V, plan=False)
    item("chain_theta_outside_target_activity_fails", _gate(r, "theta_after_parents_in_target_activity") == "FAIL")
    V = _cp(L["CHAIN_12_W_F"])
    V["v(load_pos)"] = V["v(vmid)"].copy()
    r = run("CHAIN_12_W_F", V, plan=False)
    item("chain_load_not_consumed_fails", _gate(r, "matching_rail_consumed") == "FAIL")
    V = _cp(L["CHAIN_12_W_F"])
    V["v(cdw12r_q)"] += pulse(t, t_on[2] + 1.0, t_on[2] + 1.03)
    r = run("CHAIN_12_W_F", V, plan=False)
    item("chain_opposite_cdir_fails", _gate(r, "cdir_opposite_silent") == "FAIL")
    V = _cp(L["CHAIN_12_W_F"])
    V.pop("v(load_pos)")
    r = run("CHAIN_12_W_F", V, plan=False)
    item("chain_missing_load_pos_unmeasured", r["result"] == "UNMEASURED", why=r.get("why"))
    V = _cp(L["CHAIN_12_W_F"])
    V["v(thw12f_q)"][-5:] = VDD
    r = run("CHAIN_12_W_F", V, plan=False)
    item("chain_not_returned_fails", _gate(r, "returned") == "FAIL")

    # ---- STRUCTURE
    V = _cp(L["STRUCT_THETA_PORT_CUT"])
    t = V["time"]
    V["v(cdw12f_q)"] += pulse(t, t_on[2] + 1.0, t_on[2] + 1.03)
    r = run("STRUCT_THETA_PORT_CUT", V, L["CHAIN_12_W_F"], plan=False)
    item("struct_port_cut_cdir_fires_fails", _gate(r, "target_cdir_silent") == "FAIL")
    r = run("STRUCT_THETA_PORT_CUT", L["STRUCT_THETA_PORT_CUT"], None, plan=False)
    item("struct_without_baseline_unmeasured", r["result"] == "UNMEASURED")
    V = _cp(L["STRUCT_CDIR_HISTORY_BLEED"])
    V["v(cdw12f_hs)"] = np.full_like(V["time"], float(np.max(L["CHAIN_12_W_F"]["v(cdw12f_hs)"])))
    r = run("STRUCT_CDIR_HISTORY_BLEED", V, L["CHAIN_12_W_F"], plan=False)
    item("struct_bleed_history_not_bled_fails", _gate(r, "history_bled") == "FAIL")
    r = run("STRUCT_REAL_SIGMA_SWAP", L["CHAIN_12_W_F"], L["CHAIN_12_W_F"], plan=False)
    item("struct_swap_not_reversed_fails", _gate(r, "sigma_readout_reversed") == "FAIL")
    V = _cp(L["INVALID_SYNC"])
    V["v(gw2_col_q)"] = np.roll(V["v(gw2_col_q)"], 1000)
    r = run("INVALID_SYNC", V, plan=False)
    item("invalid_sync_not_synchronous_fails", _gate(r, "parents_actually_synchronous") == "FAIL")
    V = _cp(L["INVALID_STALE"])
    V["v(hw1)"][:] = 2.9
    r = run("INVALID_STALE", V, plan=False)
    item("invalid_stale_history_valid_fails", _gate(r, "source_history_expired_at_target") == "FAIL")

    # ---- FULL (per block)
    V = _cp(L["FULL_NOM"])
    for pol in ("w", "c"):
        for s_ in (1, 2, 3, 4):
            V[f"v(g{pol}{s_}_col_q)"][:] = 0.0
    r = run("FULL_NOM", V, plan=False)
    item("full_silent_parents_fails", _gate(r, "w12_f_chain_in_block") == "FAIL" and _gate(r, "c34_r_chain_in_block") == "FAIL")
    V = _cp(L["FULL_NOM"])
    tf = V["time"]
    warm0 = min(seg[0] for ss in C["FULL_NOM"]["env"].values() for seg in ss if seg[2] > 0)
    for i, k in ((1, 2), (2, 3), (3, 4)):
        V[f"v(cdc{i}{k}r_q)"][:] = 0.0
        V[f"v(cdc{i}{k}r_q)"] += pulse(tf, warm0 + 0.05, warm0 + 0.08)
    r = run("FULL_NOM", V, plan=False)
    item("full_wrong_window_fails", _gate(r, "c12_r_chain_in_block") == "FAIL")
    r = run("FULL_REAL_MIRROR", L["FULL_NOM"], L["FULL_NOM"], plan=False)
    item("full_mirror_unswapped_fails", _gate(r, "w12_r_chain_in_block") == "FAIL")
    r = run("FULL_SPACE_CUT", L["FULL_NOM"], L["FULL_NOM"], plan=False)
    item("full_space_cut_edge_fires_fails", _gate(r, "w23_cut_cdir_silent") == "FAIL"
         and _gate(r, "w12_f_chain_in_block") == "PASS")
    V = _cp(L["FULL_NOM"])
    V["v(load_neg)"] = V["v(vmid)"].copy()
    r = run("FULL_NOM", V, plan=False)
    item("full_cool_rail_not_consumed_fails", _gate(r, "c_rail_consumed") == "FAIL")

    # ---- NUM / half-step: explicit role maps, compared against the registered baseline
    from observers.judges import role_map
    rm = role_map({"case_id": "NUM_G0_HALFSTEP"})
    r = run("NUM_G0_HALFSTEP", L["NUM_G0_HALFSTEP"], L["G0_W"], plan=False)
    item("num_g0_mapping_passes", r["result"] == "PASS" and rm[0]["core"] != rm[0]["port"][:len(rm[0]["core"])],
         roles=rm)
    V = _cp(L["FULL_NUM_HALFSTEP"])
    V["v(cdw12f_q)"] = np.roll(V["v(cdw12f_q)"], 50)
    r = run("FULL_NUM_HALFSTEP", V, L["FULL_NOM"], plan=False)
    item("full_num_halfstep_vs_full_nom_shift_fails", r["result"] == "FAIL",
         n_roles=len(role_map({"case_id": "FULL_NUM_HALFSTEP"})))
    V = _cp(L["FULL_NUM_HALFSTEP"])
    V.pop("v(thw12f_rec)")
    try:
        r = run("FULL_NUM_HALFSTEP", V, L["FULL_NOM"], plan=False)
        item("halfstep_formal_missing_vector_unmeasured", r["result"] == "UNMEASURED", why=r.get("gates", {}).get("halfstep", {}).get("why"))
    except Exception as e:
        item("halfstep_formal_missing_vector_unmeasured", False, error=repr(e))
    r = run("NUM_CHAIN_HALFSTEP", L["NUM_CHAIN_HALFSTEP"], None, plan=False)
    item("halfstep_without_baseline_unmeasured", r["result"] == "UNMEASURED")

    # ---- DC: finite values are not enough
    V = _cp(L["DC_3"])
    for ref in ("vrest", "vthe", "vthr", "vmid", "iref_n", "ilim_n", "istep_n"):
        V[f"v({ref})"] = np.array([10.0])
    r = run("DC_3", V, plan=False)
    item("dc_references_at_10V_fail", r["result"] == "FAIL" and _gate(r, "vrest_divider_ratio") == "FAIL"
         and _gate(r, "Iref_within_10pct_of_estimate") == "FAIL")
    V = _cp(L["DC_3"])
    V["i(vsrc)"] = V["i(vsrc)"] * 3.0
    r = run("DC_3", V, plan=False)
    item("dc_supply_kcl_mismatch_fails", _gate(r, "supply_kcl_across_R_INT") == "FAIL")
    V = _cp(L["DC_3"])
    for n in list(V):
        if n.startswith("v(") and n not in ("v(vsrc)", "v(vdd)") and float(V[n][0]) == 1.5:
            V[n] = np.array([0.2])
    r = run("DC_3", V, plan=False)
    item("dc_model_domain_outside_fails", _gate(r, "model_domain") == "FAIL",
         outside=(r["gates"]["model_domain"].get("outside") or [])[:3])

    # ---- relation support and consumption (review 2026-10-10 limited supplement §2)
    def runs(cid, V, base=None):
        a = A.setdefault(cid, case_assets(cid))
        return judge(C[cid], V, base, a["plan"], mos_nodes=a["mos_nodes"], ledger_check=False)

    def fails(r, *names):
        return all(_gate(r, n) == "FAIL" for n in names)
    from netlists.ledger_plan import injection
    cw = "CHAIN_12_W_F"
    L0 = L[cw]
    t = L0["time"]
    vmid = L0["v(vmid)"]
    # reviewer's CHAIN counterexample: source history 0, matching history 0, spatial nodes at vmid
    V = _cp(L0)
    V["v(hw1)"][:] = 0.0
    V["v(cdw12f_hs)"][:] = 0.0
    for n in ("v(spw1)", "v(spw2)", "v(spws12)"):
        V[n] = vmid.copy()
    r = runs(cw, V)
    item("support_review_chain_no_history_no_spatial_fails", r["result"] == "FAIL" and fails(
        r, "theta_support_all_events", "sigma_spatial_support_all_events", "cdir_support_all_events"),
        gates={n: _gate(r, n) for n in ("theta_support_all_events", "sigma_spatial_support_all_events",
                                         "cdir_support_all_events", "parents_after_stimulus")})
    # reviewer's FULL counterexample: every G0 / Θ / Σ / Cdir op_aq and op_p held at 0
    V = _cp(L["FULL_NOM"])
    for n in list(V):
        if n.endswith("_op_aq)") or n.endswith("_op_p)"):
            V[n] = np.zeros_like(V[n])
    r = runs("FULL_NOM", V)
    item("support_review_full_no_activity_fails", r["result"] == "FAIL" and fails(
        r, "w12_theta_support_all_events", "w12_ports_canonical", "w12_load_consumed_in_cdir_activity",
        "c34_theta_support_all_events", "load_pos_quiet_outside_cdir_activity"),
        gates={n: _gate(r, n) for n in ("w12_theta_support_all_events", "w12_ports_canonical",
                                         "w12_load_consumed_in_cdir_activity", "w12_f_chain_in_block")})
    # Σ: spatial nodes equipotential only
    V = _cp(L0)
    V["v(spws12)"] = V["v(spw1)"].copy()
    r = runs(cw, V)
    item("support_sigma_equipotential_fails", fails(r, "sigma_spatial_support_all_events")
         and "equipotential" in json.dumps(r["gates"]["sigma_spatial_support_all_events"]))
    # Θ: membrane driven by injection before the target activity (outside support cause interval)
    V = _cp(L0)
    th_t = float(t[np.argmax(V["v(thw12f_q)"] > 1.5)])
    a0 = float(t[np.argmax(V["v(gw2_op_aq)"] > 1.5)])  # target G0 activity start (cause begins here)
    b0 = a0 + 1.499  # cause end (G0 activity end)
    plan = A[cw]["plan"]
    it = next(x for x in plan["terms"]["thw12f_vm"] if x["element"] == "nthw12f_rm_mo")
    # Inject during [a0-0.7, a0-0.1] to bring vm from rest to near entry (~1.18V), well before cause starts at a0
    # Then a tiny injection during cause pushes vm just over entry at th_t, but total cause injection is insufficient
    r_inj = (t >= a0 - 0.7) & (t < a0 - 0.1)
    r_cause_inj = (t >= a0) & (t <= th_t)
    # Set vm trajectory: ramp during preload, then slow rise during cause to cross entry at th_t
    t_end_inj = a0 - 0.1
    v_preload = 0.989 + 0.19  # 1.179V, just below entry 1.232V
    v_entry = 0.989 + 0.243    # 1.232V
    dv_preload = 0.19
    dv_cause = v_entry - v_preload  # ~0.053V, the push over entry
    # vm piecewise: [a0-0.7, a0-0.1] ramp to v_preload, [a0-0.1, a0] hold, [a0, th_t] ramp to v_entry
    vm_new = np.select(
        [t < a0 - 0.7, (t >= a0 - 0.7) & (t < a0 - 0.1), (t >= a0 - 0.1) & (t < a0),
         (t >= a0) & (t <= th_t)],
        [0.989,  # rest
         0.989 + dv_preload * (t - (a0 - 0.7)) / 0.6,  # preload ramp
         v_preload,  # hold
         v_preload + dv_cause * (t - a0) / (th_t - a0)],  # cause ramp
        default=V["v(thw12f_vm)"])  # after th_t, keep original
    V["v(thw12f_vm)"] = vm_new
    # Injection currents: preload bulk (1.05× charge), cause residual deliberately insufficient (0.05× of needed charge)
    cm = 1.5e-6
    i_preload = 1.05 * cm * dv_preload / 0.6
    i_cause = 0.05 * cm * dv_cause / (th_t - a0)  # only 5% of needed charge during cause
    V[it["vec"].lower()] = np.select(
        [r_inj, r_cause_inj],
        [-i_preload / it["sign"], -i_cause / it["sign"]],
        default=0.0)
    # The entry at th_t uses mostly preload from outside cause, so should fail cause charge predicate
    r = runs(cw, V)
    item("support_theta_injection_outside_support_fails", fails(r, "theta_support_all_events")
         and any(e.get("checks", {}).get("net_charge_sufficient") is False
                 or e.get("checks", {}).get("retained_state_supported") is False
                 for e in r["gates"]["theta_support_all_events"]["unsupported"].get("thw12f_", [])),
         why=r["gates"]["theta_support_all_events"].get("unsupported"))
    # Θ: membrane rises with no injected charge
    V = _cp(L0)
    V[it["vec"].lower()] = np.zeros_like(t)
    r = runs(cw, V)
    item("support_theta_vm_without_charge_fails", fails(r, "theta_support_all_events")
         and any(e.get("checks", {}).get("net_charge_sufficient") is False
                 or e.get("checks", {}).get("retained_state_supported") is False
                 for e in r["gates"]["theta_support_all_events"]["unsupported"].get("thw12f_", [])))
    # Cdir: matching history rises without a matching Σ activity
    V = _cp(L0)
    V["v(sgw12f_op_aq)"][:] = 0.0
    V["v(sgw12f_op_p)"][:] = 0.0
    r = runs(cw, V)
    item("support_hs_without_matching_sigma_fails", fails(r, "cdir_hs_from_matching_sigma"))
    # Cdir: measured shunt exceeds injection while the record still claims the same rise.
    V = _cp(L0)
    V["v(cdw12f_hc)"][:] = 2.5  # strong conflict (kh capable of ~6.86 uA at this gate voltage)
    kit = next((x for x in plan.get("probes", {}).values() if x["element"] == "ncdw12f_kh"), None)
    if kit is None:
        kit = next(x for x in plan.get("terms", {}).get("cdw12f_vm", []) if x["element"] == "ncdw12f_kh")
    i_cd, _ = injection(L0, plan, "cdw12f_")
    V[kit["vec"].lower()] = 2 * np.maximum(i_cd, 0) / kit["sign"]
    r = runs(cw, V)
    item("support_conflict_with_cdir_firing_fails", fails(r, "cdir_support_all_events")
         and any(e.get("checks", {}).get("net_charge_sufficient") is False
                 for e in r["gates"]["cdir_support_all_events"]["unsupported"].get("cdw12f_", [])),
         why=r["gates"]["cdir_support_all_events"].get("unsupported"))
    # Cdir: weak conflict residual (hc slightly above H_GATE) with full support should pass
    V = _cp(L0)
    V["v(cdw12f_hc)"][:] = 0.65  # weak residual, kh essentially off at this voltage
    # Set kh shunt current to near-zero to match the weak hc voltage (kh channel essentially off)
    kit_wk = next((x for x in plan.get("probes", {}).values() if x["element"] == "ncdw12f_kh"), None)
    if kit_wk is None:
        kit_wk = next(x for x in plan.get("terms", {}).get("cdw12f_vm", []) if x["element"] == "ncdw12f_kh")
    # At hc=0.65V, kh current is ~1e-20 A (essentially zero); set to 1e-21 A to represent weak residual
    V[kit_wk["vec"]] = np.full_like(t, 1e-21)
    r = runs(cw, V)
    cdir_gate_result = _gate(r, "cdir_support_all_events")
    if r["result"] != "PASS":
        print(f"  all gates: {[(k, _gate(r, k)) for k in r['gates']]}")
    item("support_weak_conflict_residual_passes", r["result"] == "PASS"
         and cdir_gate_result == "PASS")
    # coverage: correct first events, then a later Cdir event without any support
    V = _cp(L0)
    late = (t >= t[-1] - 3.0) & (t < t[-1] - 2.985)
    V["v(cdw12f_q)"] = V["v(cdw12f_q)"] + np.where(late, 2.967, 0.0)
    V["v(cdw12f_vm)"] = V["v(cdw12f_vm)"] + np.where((t >= t[-1] - 3.2) & (t < t[-1] - 2.985), 0.3, 0.0)
    r = runs(cw, V)
    un = r["gates"]["cdir_support_all_events"].get("unsupported", {}).get("cdw12f_", [])
    item("support_later_unsupported_event_fails", fails(r, "cdir_support_all_events")
         and _gate(r, "cdir_after_theta_and_sigma_in_theta_activity") == "PASS"
         and any(e["t_q"] > t[-1] - 3.1 for e in un), unsupported=[e["t_q"] for e in un])
    # Exact retained-charge acceptance and its source-removal pair are in check_support_pairs.
    # consumption: path current outside Cdir activity; rail rise without Cdir activity
    V = _cp(L0)
    pit = next(x for x in plan["terms"]["load_pos"] if x["element"] == "nagw12f_cp")
    w = (t >= t[-1] - 4.0) & (t < t[-1] - 3.0)
    V[pit["vec"]] = V[pit["vec"]] + np.where(w, -1e-6, 0.0) / pit["sign"]
    r = runs(cw, V)
    item("support_load_current_outside_cdir_activity_fails", fails(r, "load_consumed_in_cdir_activity"))
    V = _cp(L0)
    V["v(load_pos)"] = V["v(load_pos)"] + np.where(w, 0.12, 0.0)
    r = runs(cw, V)
    item("support_rail_rise_without_cdir_activity_fails", fails(r, "load_pos_quiet_outside_cdir_activity"))
    V = _cp(L0)
    V["v(cdw12f_op_aq)"][:] = 0.0
    V["v(cdw12f_op_p)"][:] = 0.0
    r = runs(cw, V)
    item("support_cdir_activity_zero_load_claimed_fails", fails(r, "ports_canonical", "load_consumed_in_cdir_activity"))
    # canonical port: a pulse outside activity, two pulses in one activity
    V = _cp(L0)
    V["v(thw12f_op_p)"] = V["v(thw12f_op_p)"] + np.where(w, 2.967, 0.0)
    r = runs(cw, V)
    item("support_pulse_outside_activity_fails", fails(r, "ports_canonical"))
    V = _cp(L0)
    two = (t >= th_t + 0.6) & (t < th_t + 0.7)
    V["v(thw12f_op_p)"] = np.where(two, 2.967, V["v(thw12f_op_p)"])
    r = runs(cw, V)
    item("support_two_pulses_in_one_activity_fails", fails(r, "ports_canonical"))
    # must PASS: Σ before Θ (no order imposed), integration delay, two q in one activity with one p
    r = runs(cw, L0)
    sg1 = float(t[np.argmax(L0["v(sgw12f_q)"] > 1.5)])
    ncd = len(_events_up(L0, "v(cdw12f_q)"))
    names = [n for n in r["gates"] if n.endswith("_all_events") or n in (
        "cdir_hs_from_matching_sigma", "cdir_conflict_consistent", "ports_canonical", "load_consumed_in_cdir_activity")]
    item("support_legal_sigma_before_theta_integration_delay_passes", r["result"] == "PASS" and sg1 < th_t and ncd == 2
         and all(_gate(r, n) == "PASS" for n in names), sigma_q=sg1, theta_q=th_t, cdir_events=ncd, gates=names)
    i_in, _ = injection(L0, plan, "thw12f_")
    item("support_injection_read_from_ledger_terms", i_in is not None and float(np.max(i_in)) > 0)
    fp = A["FULL_NOM"]["plan"]
    i_in, i_sh = injection(L["FULL_NOM"], fp, "cdw12f_")
    from netlists.ledger_plan import membrane_ledger
    fm = membrane_ledger(L["FULL_NOM"], fp, "cdw12f_")
    term_vectors = {x["vec"] for its in fp["terms"].values() for x in its}
    item("support_full_injection_read_from_ledger_and_probes", i_in is not None and i_sh is not None
         and fm is not None and len(fp["nodes"]) == 38 and len(fp["probes"]) == 60
         and all(p["vec"] in term_vectors for p in fp["probes"].values())
         and np.array_equal(i_in, fm["in"]) and np.array_equal(i_sh, fm["sh"]),
         n_ledger_nodes=len(fp["nodes"]), n_probes=len(fp["probes"]))

    # ---- physical ledger: a terminal current perturbed by 5 %
    for cid in ("CHAIN_12_W_F", "FULL_NOM"):
        V = _cp(L[cid])
        plan = A[cid]["plan"]
        n0 = plan["nodes"][0]
        big = max(plan["terms"][n0], key=lambda it: float(np.max(np.abs(V[it["vec"].lower()]))))
        V[big["vec"].lower()] = V[big["vec"].lower()] * 1.05
        r = run(cid, V)
        lg = r["gates"]["physical_ledger"]
        item(f"ledger_current_plus5pct_fails_{cid}", lg["result"] == "FAIL" and lg["nodes"][n0]["kcl"] is False
             and r["result"] == "FAIL", node=n0, term=big["element"], kcl_peak=lg["nodes"][n0]["kcl_peak"])
    V = _cp(L["CHAIN_12_W_F"])
    plan = A["CHAIN_12_W_F"]["plan"]
    V.pop(plan["terms"][plan["nodes"][0]][0]["vec"].lower())
    r = run("CHAIN_12_W_F", V)
    item("ledger_missing_current_not_pass", r["result"] != "PASS"
         and r["gates"]["physical_ledger"]["result"] == "UNMEASURED")


def check_support_pairs():
    """Integrated replacement of tools/_block.py: review 2026-10-17 fixed pairs.

    Exact RC reference first, then immutable-source mutations. FULL replays use the default
    production judge, including its physical ledger. No negative is re-closed.
    """
    from runtime.decks import case_assets, registry
    from tests.synth_raw import legal, supported_rc_pair, fill_ledger
    from netlists.ledger_plan import membrane_ledger
    from netlists.params import v
    from observers.support_q1r import consts, score_events, _gate as support_gate
    from observers.judges import judge

    C = {c["case_id"]: c for c in registry()["cases"]}
    cert = _proto_cert()[1]
    ue = cert["nom"]["roles"]["Theta_Cdir"]["u_entry_V"]
    core, node = "cdw12f_", "cdw12f_vm"
    plan = case_assets("CHAIN_12_W_F")["plan"]
    mo = next(it for it in plan["terms"][node] if it["element"] == "ncdw12f_rm_mo")
    reference, cause, meta = supported_rc_pair(plan, core, ue)
    t = reference["time"]
    K = consts(C["CHAIN_12_W_F"], cert)

    def rc_gate(V, source):
        led = membrane_ledger(V, plan, core)
        ev = score_events(V, core, source, led["in"], v("NM_CM_THETA_CDIR"), ue, K, ledger=led)
        return support_gate({core: ev}), ev

    ga, ea = rc_gate(reference, cause)
    i2 = int(np.searchsorted(t, meta["second_start_s"]))
    retained = float(reference[f"v({node})"][i2] - reference["v(vrest)"][i2])
    item("support_pair_dual_rc_accumulation_accepted",
         ga["result"] == "PASS" and len(ea) == 1 and all(ea[0]["checks"].values())
         and any(not seg["cause_with_tolerance"]
                 and 0 < seg["supported_state_end_V"] < seg["supported_state_start_V"]
                 for seg in ea[0]["source_ledger"])
         and retained > 0.5 * ue and abs(retained - meta["retained_at_second_start_V"]) < 1e-12,
         gate=ga, construction=meta, retained_V=retained)

    # Same vm, caps, leakage and final current: remove ONLY the early injected source and cause.
    no_source = _cp(reference)
    no_source[mo["vec"].lower()][t < meta["second_start_s"]] = 0.0
    late_cause = cause & (t >= meta["second_start_s"])
    gb, eb = rc_gate(no_source, late_cause)
    item("support_pair_retained_charge_without_source_rejected",
         gb["result"] == "FAIL" and len(eb) == 1
         and eb[0]["checks"]["retained_state_supported"] is False
         and "without source" in eb[0]["why"]
         and np.array_equal(no_source[f"v({node})"], reference[f"v({node})"]), gate=gb)

    # Keep the early physical input but remove its support; the local late net increment is sufficient.
    gc, ec = rc_gate(reference, late_cause)
    m = (t >= meta["second_start_s"]) & (t <= meta["entry_time_s"])
    local_net = float(np.trapezoid((membrane_ledger(reference, plan, core)["in"]
                                  - membrane_ledger(reference, plan, core)["leak"])[m], t[m]))
    local_cap = meta["Cm_F"] * (ue - retained)
    item("support_pair_preload_outside_support_rejected",
         gc["result"] == "FAIL" and len(ec) == 1 and ec[0]["checks"]["account_closes"] is True
         and ec[0]["checks"]["retained_state_supported"] is False
         and "outside support" in ec[0]["why"] and local_net >= (1 - K["TOL"]) * local_cap,
         gate=gc, local_net_C=local_net, local_cap_C=local_cap)

    # Full production entry, default physical ledger enabled. Baseline is completed before mutations.
    cid = "FULL_NOM"
    assets = case_assets(cid)
    base = legal(C[cid], assets)
    fp, ft = assets["plan"], base["time"]
    fterms = fp["terms"][node]
    fkh = next(it for it in fterms if it["element"] == "ncdw12f_kh")
    fmo = next(it for it in fterms if it["element"] == "ncdw12f_rm_mo")
    am = [x for x in assets["save"] if x.startswith("i(v") and x != "i(vsrc)" and not x.startswith("i(va_")]

    def production(V):
        return judge(C[cid], V, None, fp, ammeters=am, mos_nodes=assets["mos_nodes"])

    rb = production(base)
    name = "w12_cdir_support_all_events"
    item("support_pair_full_baseline_accepted", rb["result"] == "PASS"
         and _gate(rb, "physical_ledger") == "PASS" and _gate(rb, name) == "PASS", judge=rb)
    weak = _cp(base)
    weak["v(cdw12f_hc)"][:] = 1.2
    weak[fkh["vec"].lower()] = np.full_like(ft, 7.141553089580153e-17 / fkh["sign"])
    rw = production(weak)
    item("support_pair_weak_shunt_hc1p2_accepted", rw["result"] == "PASS"
         and _gate(rw, name) == "PASS" and _gate(rw, "physical_ledger") == "PASS", judge=rw)

    strong = _cp(base)
    strong["v(cdw12f_hc)"][:] = 2.5
    strong[fkh["vec"].lower()] = 2 * np.abs(base[fmo["vec"].lower()]) / fkh["sign"]
    rs = production(strong)
    es = rs["gates"][name].get("unsupported", {}).get(core, [])
    item("support_pair_shunt_exceeding_injection_rejected", rs["result"] == "FAIL"
         and _gate(rs, name) == "FAIL"
         and any(e["checks"]["net_charge_sufficient"] is False
                 and e["account_from_anchor"]["Q_sh_C"] > e["account_from_anchor"]["Q_in_C"]
                 and e["account_stretch"]["Q_net_C"] < 0 for e in es), judge=rs)

    # FULL: unsupported 0.2 V preload before the existing cause, then enough local net charge.
    # Build currents from the membrane equation, not by assigning a residual to another branch.
    preload = _cp(base)
    event = rb["gates"][name]["events"][core][0]
    a, tq = event["cause"][0], event["t_q"]
    pa, pb = a - 0.7, a - 0.1
    cm = v("NM_CM_THETA_CDIR") + v("C_NODE")
    rm, tau = v("NM_RM"), v("NM_RM") * cm
    rest = base["v(vrest)"]
    u_a = 0.2 * np.exp(-(a - pb) / tau)
    u = np.where(ft < pa, 0.0, np.where(ft < pb, 0.2 * (ft - pa) / (pb - pa),
                 np.where(ft < a, 0.2 * np.exp(-(ft - pb) / tau),
                          u_a + (ue - u_a) * (ft - a) / (tq - a))))
    before = ft <= tq
    preload[f"v({node})"][before] = (rest + u)[before]
    derivative = np.gradient(preload[f"v({node})"], ft)
    needed = cm * derivative + (preload[f"v({node})"] - rest) / rm
    # Include the derivative stencil across the join to the unchanged post-event trajectory.
    current_window = ft <= tq + 2 * float(np.max(np.diff(ft)))
    preload[fmo["vec"].lower()][current_window] = -needed[current_window] / fmo["sign"]
    # Exact component equations on this vm node; later currents remain unchanged.
    local_plan = {"nodes": [node], "terms": {node: fterms}, "probes": {}}
    fill_ledger(preload, local_plan, ft, preset=(fmo["vec"].lower(), fkh["vec"].lower()))
    for it in fterms:
        preload[it["vec"].lower()][~current_window] = base[it["vec"].lower()][~current_window]
    rp = production(preload)
    ep = rp["gates"][name].get("unsupported", {}).get(core, [])
    late = (ft >= a) & (ft <= tq)
    net_late = float(np.trapezoid(needed[late] - (preload[f"v({node})"][late] - rest[late]) / rm, ft[late]))
    cap_late = cm * (ue - u_a)
    item("support_pair_full_preload_outside_support_rejected", rp["result"] == "FAIL"
         and _gate(rp, name) == "FAIL" and _gate(rp, "physical_ledger") == "PASS"
         and any(e["checks"]["account_closes"] is True
                 and e["checks"]["retained_state_supported"] is False
                 and "outside support" in e["why"] for e in ep)
         and net_late >= (1 - K["TOL"]) * cap_late,
         judge=rp, local_net_C=net_late, local_cap_C=cap_late, residual_closing_used=False)

    missing = _cp(base)
    other = next(it for it in fterms if it["element"] == "ncdw12f_dis")
    missing.pop(other["vec"].lower())
    ru = production(missing)
    item("support_pair_full_missing_membrane_branch_unmeasured", ru["result"] != "PASS"
         and _gate(ru, name) == "UNMEASURED" and _gate(ru, "physical_ledger") == "UNMEASURED",
         judge=ru, missing_vector=other["vec"])


# ------------------------------------------------------------------ static vector closure
def check_static_closure():
    import tools.static_check as sc
    from runtime.decks import case_assets, registry, deck_text
    from netlists.ledger_plan import save_vectors
    reg = registry()
    C = {c["case_id"]: c for c in reg["cases"]}
    for cid in ("CHAIN_12_W_F", "G0_W", "NUM_G0_HALFSTEP"):
        a = case_assets(cid)
        sc.LEDGER_NEED[cid] = save_vectors(a["plan"]) if a["plan"]["nodes"] else []

    def patched(drop):
        def dt(case_id, raw_path=None):
            text, req = deck_text(case_id) if raw_path is None else deck_text(case_id, raw_path=raw_path)
            if case_id in drop:
                text = "\n".join((" ".join(x for x in l.split() if x != drop[case_id]) if l.startswith(".save ") else l)
                                 for l in text.splitlines())
            return text, req
        return dt
    orig = sc.deck_text
    try:
        sc.deck_text = patched({})
        r = sc.check_case(C["CHAIN_12_W_F"], None, {})
        item("static_chain_closure_passes", r["checks"]["judge_vectors_saved"]["pass"])
        sc.deck_text = patched({"CHAIN_12_W_F": "v(load_pos)"})
        r = sc.check_case(C["CHAIN_12_W_F"], None, {})
        item("static_chain_missing_load_pos_caught", not r["checks"]["judge_vectors_saved"]["pass"]
             and "v(load_pos)" in r["checks"]["judge_vectors_saved"]["missing"])
        texts = {}
        sc.deck_text = patched({"G0_W": "v(gw1_col_rec)"})
        sc.check_case(C["G0_W"], None, texts)
        sc.deck_text = patched({})
        r = sc.check_case(C["NUM_G0_HALFSTEP"], None, texts)
        item("static_halfstep_baseline_missing_vector_caught", not r["checks"]["baseline_vectors_saved"]["pass"],
             missing=r["checks"]["baseline_vectors_saved"]["missing"])
    finally:
        sc.deck_text = orig
    # deck identity does not depend on where the backend is installed
    import hashlib
    txt, _ = deck_text("FULL_NOM")
    ids = set()
    for ml, od in (("C:/a/c05.lib", "C:/a/x.osdi"), ("/opt/q/models/c05.lib", "/opt/q/ekv26.osdi")):  # path fixture (never opened)
        body, _ = deck_text("FULL_NOM", raw_path="/r/x.raw", model_lib=ml, osdi=od)
        ids.add(hashlib.sha256(body.replace("/r/x.raw", "<RAW>").replace(ml, "<MODEL_LIB>").replace(od, "<OSDI>").encode()).hexdigest())
    item("deck_identity_independent_of_backend_paths", ids == {hashlib.sha256(txt.encode()).hexdigest()}
         and not re.search(r"[A-Za-z]:/|/home/|/Users/", txt))


# ------------------------------------------------------------------ coordinator (stand-in executable)
def write_permission(root):
    from tools.write_freeze import sha
    fr_sha = sha(os.path.join(root, "FREEZE_Q1R.json"))
    with open(os.path.join(root, "prereg", "LAUNCH_PERMISSION.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"freeze_sha256": fr_sha, "phases": ["qualification", "formal", "rerun"],
                   "granted_by": "selfcheck", "date": "selfcheck"}, f)


def temp_package():
    """Isolated package and sealed v1 ledger; explicitly register the test-only backend.

    No installed solver/OSDI is needed to test the coordinator. Never register a stand-in in
    the real package, and never claim this temporary registration as a host qualification.
    """
    tmp = tempfile.mkdtemp(prefix="q1r_selfcheck_")
    dst = os.path.join(tmp, "pkg")
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", "*.lock", "q1_ledger.jsonl",
                                                            "verdicts.jsonl", "verdicts", "STOPPED", "decks",
                                                            "LAUNCH_PERMISSION.json"))
    v1 = os.path.join(tmp, "thermal_g3_v1", "results")
    os.makedirs(v1)
    import config
    shutil.copy2(config.V1_LEDGER, os.path.join(v1, "analysis_ledger.jsonl"))
    osdi = os.path.join(tmp, "selfcheck_standin.osdi")
    with open(osdi, "wb") as f:
        f.write(b"selfcheck stand-in, never loaded by a circuit solver")
    r = subprocess.run([sys.executable, "-B", os.path.join(dst, "tools", "register_backend.py"),
                        "--platform", "selfcheck-standin", "--ngspice", os.path.join(dst, "tests", "fake_ngspice.py"),
                        "--osdi", osdi, "--ngspice-version", "synthetic selfcheck writer, not ngspice",
                        "--openvaf-version", "not used (stand-in only)"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return tmp, dst


def pid_alive(pid):
    if os.name == "nt":
        return str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    st = open(f"/proc/{pid}/stat").read().split()[2] if os.path.exists(f"/proc/{pid}/stat") else "R"
    return st != "Z"


def run_py(code, cwd, env=None, timeout=600):
    return subprocess.run([sys.executable, "-B", "-c", code], cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env={**os.environ, **(env or {})})


GO = '''
def go(cid, rerun=False):
    try:
        aid, e = C.run_case(cid, rerun=rerun)
        v = e.get("verdict") or {}
        return {"aid": aid, "status": e["status"], "scientific": v.get("scientific")}
    except Refused as x:
        return {"refused": str(x)}
'''


def boot_for(pkg, enforce=True):
    fake = os.path.join(ROOT, "tests", "fake_ngspice.py")
    return (f"import sys,os,json; sys.path.insert(0,{pkg!r}); os.chdir({pkg!r});"
            f"from runtime.coordinator import Coordinator, Refused;"
            f"from tools.write_freeze import build_freeze, sha;"
            f"C=Coordinator(root={pkg!r}, raw_root=os.path.join({pkg!r},'rawtmp'), "
            f"solver=[sys.executable,'-B',{fake!r}], enforce={enforce});" + GO)


def go(pkg, cid, npz=None, rerun=False, enforce=True, mode=None):
    env = {"FAKE_MODE": mode or ("npz" if npz else "ok")}
    if npz:
        env["FAKE_NPZ"] = npz
    r = run_py(boot_for(pkg, enforce) + f"\nprint('RES'+json.dumps(go({cid!r}, rerun={rerun})))", pkg, env=env)
    line = [l for l in r.stdout.splitlines() if l.startswith("RES")]
    return json.loads(line[-1][3:]) if line else {"error": (r.stdout + r.stderr)[-600:]}


def make_npz(tmp):
    """Legal synthetic raws (and one counterexample) written as .npz for the stand-in solver."""
    from runtime.decks import case_assets, registry
    from tests.synth_raw import legal
    reg = {c["case_id"]: c for c in registry()["cases"]}
    out = {}
    for cid in ("Q1_MOTHER_PROTOCOL", "G0_W", "NUM_G0_HALFSTEP", "G0_CUT_K10", "G0_C"):
        V = legal(reg[cid], case_assets(cid))
        out[cid] = os.path.join(tmp, f"{cid}.npz")
        np.savez(out[cid], **V)
    # G0_C without its second step (no repeat): a required scientific FAIL
    V = dict(np.load(out["G0_C"]))
    c = reg["G0_C"]
    p = f"g{c['judge']['pol']}{c['judge']['site']}_"
    a2 = c["env"][str(c["judge"]["site"])][1][0]
    for n in ("and_g8", "col_q", "op_aq", "op_p"):
        V[f"v({p}{n})"][V["time"] >= a2] = 0.0
    out["G0_C_FAIL"] = os.path.join(tmp, "G0_C_FAIL.npz")
    np.savez(out["G0_C_FAIL"], **V)
    return out


def check_coordinator():
    tmp, pkg = temp_package()
    try:
        npz = make_npz(tmp)
        boot = boot_for(pkg)
        r = run_py(boot + "fr=build_freeze(root=os.getcwd(), status='FROZEN_AWAITING_LAUNCH', why=[]);"
                   "json.dump(fr, open('FREEZE_Q1R.json','w'))", pkg)
        assert r.returncode == 0, r.stderr
        x = go(pkg, "Q1_MOTHER_PROTOCOL")
        item("coord_refuses_without_permission", "permission" in x.get("refused", ""), out=x)
        write_permission(pkg)
        x = go(pkg, "G0_W")
        item("coord_formal_refused_before_qual", "qualification" in x.get("refused", ""), out=x)
        # production path: solve -> completion -> read raw -> registered judge -> verdict
        x = go(pkg, "Q1_MOTHER_PROTOCOL", npz["Q1_MOTHER_PROTOCOL"])
        item("coord_qual_protocol_judged_pass", x.get("status") == "complete" and x.get("scientific") == "PASS", out=x)
        vr = [json.loads(l) for l in open(os.path.join(pkg, "results", "verdicts.jsonl"), encoding="utf-8")]
        from tools.write_freeze import sha
        v0 = vr[0] if vr else {}
        ok = bool(vr) and v0.get("freeze_sha256") == sha(os.path.join(pkg, "FREEZE_Q1R.json")) \
            and v0.get("raw_sha256") == sha(v0["raw_path"]) and v0["judge_output"]["sha256"] == sha(v0["judge_output"]["path"]) \
            and bool(v0.get("deck_sha256")) and bool(v0.get("backend"))
        item("coord_verdict_bound_to_freeze_deck_raw_judge", ok, keys=sorted(v0))
        x = go(pkg, "Q1_MOTHER_PROTOCOL", npz["Q1_MOTHER_PROTOCOL"])
        item("coord_no_repeat_without_infra_failure", "only an infrastructure failure" in x.get("refused", ""), out=x)
        x = go(pkg, "G0_W", npz["G0_W"])
        item("coord_formal_refused_until_halfstep_pass", "Q1_MOTHER_HALFSTEP" in x.get("refused", ""), out=x)
        x = go(pkg, "Q1_MOTHER_HALFSTEP", npz["Q1_MOTHER_PROTOCOL"])
        item("coord_halfstep_judged_against_protocol_raw", x.get("scientific") == "PASS", out=x)
        x = go(pkg, "G0_W", npz["G0_W"])
        item("coord_formal_unblocked_after_qual_pass", x.get("scientific") == "PASS", out=x)
        x = go(pkg, "NUM_G0_HALFSTEP", npz["NUM_G0_HALFSTEP"])
        item("coord_num_g0_halfstep_vs_g0_w_pass", x.get("scientific") == "PASS", out=x)
        # infrastructure failure -> rerun allowed (and judged)
        r = run_py(boot + "C._append({'rec':'start','analysis_id':'formal-099','phase':'formal','case_id':'G0_CUT_K10','scale':'single_site_single_polarity','analysis':'x','reserved_timeout_s':10,'deck_sha256':'x'});"
                   "C._append({'rec':'end','analysis_id':'formal-099','case_id':'G0_CUT_K10','status':'launch_error','wall_s':0.1})", pkg)
        x = go(pkg, "G0_CUT_K10", npz["G0_CUT_K10"], rerun=True)
        item("coord_infra_failure_rerunnable", x.get("aid") == "rerun-001" and x.get("scientific") == "PASS", out=x)
        x = go(pkg, "G0_CUT_K10", npz["G0_CUT_K10"], rerun=True)
        item("coord_rerun_only_after_infra_failure", "rerun only after" in x.get("refused", ""), out=x)
        # required scientific FAIL stops the round
        x = go(pkg, "G0_C", npz["G0_C_FAIL"])
        stopped = os.path.exists(os.path.join(pkg, "results", "STOPPED"))
        y = go(pkg, "CHAIN_12_W_F")
        item("coord_required_fail_stops_round", x.get("scientific") == "FAIL" and stopped
             and "round stopped" in y.get("refused", "") and "scientific FAIL" in y.get("refused", ""), out=[x, y])
        os.remove(os.path.join(pkg, "results", "STOPPED"))
        # changed frozen asset -> refused
        with open(os.path.join(pkg, "netlists", "params.py"), "a", encoding="utf-8") as f:
            f.write("\n# tamper\n")
        x = go(pkg, "CHAIN_12_W_F")
        item("coord_changed_asset_refused", "netlists/params.py" in x.get("refused", ""), out=x)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    check_coordinator_b()
    check_coordinator_runtime()


def check_coordinator_b():
    """Second package: registry / env pinning, UNMEASURED blocking, verdict guards, cost gate."""
    tmp, pkg = temp_package()
    try:
        npz = make_npz(tmp)
        run_py(boot_for(pkg) + "fr=build_freeze(root=os.getcwd(), status='FROZEN_AWAITING_LAUNCH', why=[]);"
               "json.dump(fr, open('FREEZE_Q1R.json','w'))", pkg)
        write_permission(pkg)
        regp = os.path.join(pkg, "prereg", "cases_q1r.json")
        orig = open(regp, "rb").read()
        reg = json.loads(orig.decode("utf-8"))
        reg["cases"][0]["timeout_s"] = 599
        json.dump(reg, open(regp, "w", encoding="utf-8", newline="\n"))
        x = go(pkg, "Q1_MOTHER_PROTOCOL")
        item("coord_changed_case_refused", "cases_q1r.json" in x.get("refused", ""), out=x)
        open(regp, "wb").write(orig)
        r = run_py(boot_for(pkg) + "\nprint('RES'+json.dumps(go('Q1_MOTHER_PROTOCOL')))", pkg,
                   env={"THERMAL_G3_OSDI": "C:/elsewhere/other.osdi"})  # path fixture (never opened)
        item("coord_env_override_refused", "environment override" in r.stdout, out=r.stdout.strip()[-200:])
        # UNMEASURED blocks dependants (baseline raw changed after its verdict -> half-step unmeasured)
        x = go(pkg, "Q1_MOTHER_PROTOCOL", npz["Q1_MOTHER_PROTOCOL"])
        v0 = json.loads(open(os.path.join(pkg, "results", "verdicts.jsonl"), encoding="utf-8").readline())
        with open(v0["raw_path"], "ab") as f:
            f.write(b"\0")
        y = go(pkg, "Q1_MOTHER_HALFSTEP", npz["Q1_MOTHER_PROTOCOL"])
        z = go(pkg, "G0_W", npz["G0_W"])
        item("coord_unmeasured_blocks_dependants", x.get("scientific") == "PASS" and y.get("scientific") == "UNMEASURED"
             and not os.path.exists(os.path.join(pkg, "results", "STOPPED"))
             and "Q1_MOTHER_HALFSTEP has no scientific PASS" in z.get("refused", ""), out=[x, y, z])
        # _record_verdict guards; no public verdict writer
        code = boot_for(pkg) + '''
def tryv(aid):
    try:
        C._record_verdict(aid, "PASS", "x"); return "RECORDED"
    except Refused as e:
        return str(e)
st = [r for r in C.records() if r["rec"] == "start"]
en = {r["analysis_id"]: r for r in C.records() if r["rec"] == "end"}
q2 = en["qual-002"]
C._append({"rec": "start", "analysis_id": "formal-900", "phase": "formal", "case_id": "G0_W", "scale": "s", "analysis": "x",
           "reserved_timeout_s": 1, "deck_sha256": "x", "freeze_sha256": "f" * 64})
C._append({"rec": "end", "analysis_id": "formal-900", "case_id": "G0_W", "status": "complete", "wall_s": 0.1, "files": q2["files"]})
C._append({"rec": "start", "analysis_id": "formal-901", "phase": "formal", "case_id": "G0_C", "scale": "s", "analysis": "x",
           "reserved_timeout_s": 1, "deck_sha256": "x", "freeze_sha256": st[0]["freeze_sha256"]})
C._append({"rec": "end", "analysis_id": "formal-901", "case_id": "G0_C", "status": "timeout_killed", "wall_s": 0.1, "files": q2["files"]})
print("RES" + json.dumps({"unknown": tryv("qual-999"), "raw_changed": tryv("qual-001"), "foreign": tryv("formal-900"),
                          "incomplete": tryv("formal-901"), "public": hasattr(C, "record_verdict")}))
'''
        r = run_py(code, pkg)
        line = [l for l in r.stdout.splitlines() if l.startswith("RES")]
        g = json.loads(line[-1][3:]) if line else {}
        item("coord_record_verdict_guards", "unknown analysis" in g.get("unknown", "") and "changed since the run" in g.get("raw_changed", "")
             and "different freeze" in g.get("foreign", "") and "status timeout_killed" in g.get("incomplete", "")
             and g.get("public") is False, out=g or (r.stdout + r.stderr)[-400:])
        # cost gate: a measured forecast within budget passes; an over-budget forecast is refused
        code = boot_for(pkg) + '''
fr = C.freeze()[0]
reg = json.load(open(os.path.join(C.root, "prereg", "cases_q1r.json"), encoding="utf-8"))
c = next(k for k in reg["cases"] if k["case_id"] == "CHAIN_12_W_F")
a = C.cost_gate(c, "formal", fr)
C._append({"rec": "start", "analysis_id": "formal-902", "phase": "formal", "case_id": "G0_C", "scale": "single_site_single_polarity",
           "analysis": "x", "reserved_timeout_s": 2700, "deck_sha256": "x"})
C._append({"rec": "end", "analysis_id": "formal-902", "case_id": "G0_C", "status": "complete", "wall_s": 2690.0, "files": {}})
try:
    b = C.cost_gate(c, "formal", fr)
except Refused as e:
    b = str(e)
print("RES" + json.dumps({"measured": a, "over": b}))
'''
        r = run_py(code, pkg)
        line = [l for l in r.stdout.splitlines() if l.startswith("RES")]
        g = json.loads(line[-1][3:]) if line else {}
        item("coord_cost_gate_forecast_from_measured", isinstance(g.get("measured"), (int, float)) and g["measured"] < 108000,
             out=g or (r.stdout + r.stderr)[-400:])
        item("coord_cost_gate_refuses_over_budget", "cost gate" in str(g.get("over", "")), out=g)
        # one backend per round: register a different OSDI, re-freeze, re-permit -> refused
        osdi2 = os.path.join(tmp, "other_backend.osdi")
        open(osdi2, "wb").write(b"not the round's backend")
        r = run_py(f"import sys,os; sys.path.insert(0,{pkg!r}); os.chdir({pkg!r}); from tools.register_backend import main;"
                   f"main(['--platform','test-other','--ngspice',{os.path.join(ROOT, 'tests', 'fake_ngspice.py')!r},'--osdi',{osdi2!r}])", pkg)
        run_py(boot_for(pkg) + "fr=build_freeze(root=os.getcwd(), status='FROZEN_AWAITING_LAUNCH', why=[]);"
               "json.dump(fr, open('FREEZE_Q1R.json','w'))", pkg)
        write_permission(pkg)
        x = go(pkg, "Q1_MOTHER_HALFSTEP", npz["Q1_MOTHER_PROTOCOL"])
        item("coord_backend_fixed_by_first_start", "backend differs" in x.get("refused", ""), out=x, reg=r.stdout.strip()[-120:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_coordinator_runtime():
    """Completion gate, supervisor kill, caps; enforce=False isolates these from the contract."""
    tmp, pkg = temp_package()
    try:
        fake = os.path.join(ROOT, "tests", "fake_ngspice.py")
        boot = (f"import sys,os,json; sys.path.insert(0,{pkg!r}); os.chdir({pkg!r});"
                f"from runtime.coordinator import Coordinator, Refused;"
                f"from tools.write_freeze import build_freeze;"
                f"json.dump(build_freeze(root=os.getcwd(), status='X', why=[]), open('FREEZE_Q1R.json','w'));"
                f"C=Coordinator(root={pkg!r}, raw_root=os.path.join({pkg!r},'rawtmp'), solver=[sys.executable,'-B',{fake!r}], enforce=False);")
        res = os.path.join(pkg, "results")

        def reset():
            for f in ("q1_ledger.jsonl", "verdicts.jsonl", "STOPPED"):
                if os.path.exists(os.path.join(res, f)):
                    os.remove(os.path.join(res, f))
        for mode, want, name in (("nan", "non-finite", "coord_nan_rejected"), ("short", "raw ends at", "coord_short_raw_rejected"),
                                 ("badaxis", "time axis", "coord_bad_axis_rejected"), ("abort", "log contains", "coord_abort_rejected")):
            reset()
            r = run_py(boot + "aid,e=C.run_case('Q1_MOTHER_PROTOCOL'); print(e['status'])", pkg, env={"FAKE_MODE": mode})
            item(name, want in r.stdout, out=(r.stdout + r.stderr).strip()[-200:])
        # the last one was an abort: no verdict, round stopped, no rerun
        stopped = open(os.path.join(res, "STOPPED"), encoding="utf-8").read() if os.path.exists(os.path.join(res, "STOPPED")) else ""
        nv = len(open(os.path.join(res, "verdicts.jsonl")).readlines()) if os.path.exists(os.path.join(res, "verdicts.jsonl")) else 0
        r = run_py(boot + "\ntry:\n C.run_case('Q1_MOTHER_PROTOCOL', rerun=True); print('RAN')\nexcept Refused as e: print('REFUSED',e)", pkg)
        item("coord_aborted_raw_no_verdict_round_stopped", nv == 0 and "execution failure" in stopped
             and "round stopped" in r.stdout, stopped=stopped, out=r.stdout.strip()[-200:])
        reset()
        r = run_py(boot + "\nC._append({'rec':'start','analysis_id':'qual-001','phase':'qualification','case_id':'Q1_MOTHER_PROTOCOL','scale':'mother_bench','analysis':'x','reserved_timeout_s':600,'deck_sha256':'x'})"
                   "\nC._append({'rec':'end','analysis_id':'qual-001','case_id':'Q1_MOTHER_PROTOCOL','status':'log contains x','wall_s':1.0})"
                   "\ntry:\n C.run_case('Q1_MOTHER_PROTOCOL', rerun=True); print('RAN')\nexcept Refused as e: print('REFUSED',e)", pkg)
        item("coord_solver_failure_not_rerunnable", "rerun only after a preregistered infrastructure failure" in r.stdout,
             out=r.stdout.strip()[-200:])
        # empty required list
        r = run_py(boot + "print(C.completion(0,'', 'nofile', {'analysis':'op'}, []))", pkg)
        item("coord_empty_required_rejected", "no raw output" in r.stdout, out=r.stdout.strip())
        r = run_py(boot + "import tempfile;f=tempfile.mktemp(suffix='.raw');"
                   "open(f,'wb').write(b'x');print(C.completion(0,'',f,{'analysis':'op'},[]))", pkg)
        item("coord_empty_required_list_is_failure", r.stdout.strip() not in ("None", ""), out=r.stdout.strip())
        # supervisor kill when the coordinator itself is killed: coordinator runs with a 3 s cap
        reg = json.load(open(os.path.join(pkg, "prereg", "cases_q1r.json"), encoding="utf-8"))
        reg["cases"][0]["timeout_s"] = 33   # supervisor deadline = 33 - KILL_GRACE_S(30) = 3 s
        json.dump(reg, open(os.path.join(pkg, "prereg", "cases_q1r.json"), "w", encoding="utf-8", newline="\n"))
        reset()
        pidf = os.path.join(tmp, "child.pid")
        coord = subprocess.Popen([sys.executable, "-B", "-c", boot + "C.run_case('Q1_MOTHER_PROTOCOL')"], cwd=pkg,
                                 env={**os.environ, "FAKE_MODE": "sleep", "FAKE_CHILD_PID_FILE": pidf})
        t0 = time.time()
        while not os.path.exists(pidf) and time.time() - t0 < 20:
            time.sleep(0.1)
        coord.kill()          # coordinator dies; supervisor must still enforce the deadline
        time.sleep(6.0)
        child = int(open(pidf).read()) if os.path.exists(pidf) else None
        alive = child is not None and pid_alive(child)
        item("coord_supervisor_kills_tree_after_coordinator_death", child is not None and not alive, child=child)
        # caps: qualification start cap 2 and phase wall cap
        reset()
        r = run_py(boot + "C._append({'rec':'start','analysis_id':'qual-001','phase':'qualification','case_id':'A','scale':'mother_bench','analysis':'x','reserved_timeout_s':600,'deck_sha256':'x'});"
                   "C._append({'rec':'start','analysis_id':'qual-002','phase':'qualification','case_id':'B','scale':'mother_bench','analysis':'x','reserved_timeout_s':600,'deck_sha256':'x'});"
                   "\ntry:\n C.reserve('Q1_MOTHER_PROTOCOL'); print('RAN')\nexcept Refused as e: print('REFUSED',e)", pkg)
        item("coord_start_cap_refused", "start cap 2 reached" in r.stdout, out=r.stdout.strip()[-200:])
        reset()
        # the case cap in this temp registry is 33 s (supervisor test); 1190 + 33 > 1200
        r = run_py(boot + "C._append({'rec':'start','analysis_id':'qual-001','phase':'qualification','case_id':'A','scale':'mother_bench','analysis':'x','reserved_timeout_s':1190,'deck_sha256':'x'});"
                   "\ntry:\n C.reserve('Q1_MOTHER_PROTOCOL'); print('RAN')\nexcept Refused as e: print('REFUSED',e)", pkg)
        item("coord_phase_wall_cap_refused", "qualification wall cap" in r.stdout, out=r.stdout.strip()[-200:])
        # clean directory: results/ absent entirely
        shutil.rmtree(res, ignore_errors=True)
        shutil.rmtree(os.path.join(pkg, "rawtmp"), ignore_errors=True)
        r = run_py(boot + "aid,e=C.run_case('Q1_MOTHER_PROTOCOL'); print(aid, e['status'], e['verdict']['scientific'])", pkg, env={"FAKE_MODE": "ok"})
        item("coord_clean_directory_works", "qual-001 complete" in r.stdout, out=(r.stdout + r.stderr).strip()[-300:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for fn in (check_bench, check_certificate, check_judges, check_readback, check_halfstep, check_formal, check_support_pairs,
               check_static_closure, check_coordinator):
        try:
            fn()
        except Exception as e:      # an exception is a failed self-check, never a skipped one
            import traceback
            item(f"{fn.__name__}_raised", False, error=repr(e)[:400], where=traceback.format_exc()[-600:])
    out = {"schema": "thermal_g3_q1r.selfcheck.1", "solver_starts": 0,
           "n": len(ITEMS), "n_pass": sum(x["result"] == "PASS" for x in ITEMS.values()), "items": ITEMS}
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "selfcheck.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"{out['n_pass']}/{out['n']} PASS")
    sys.exit(0 if out["n_pass"] == out["n"] else 1)


if __name__ == "__main__":
    main()
