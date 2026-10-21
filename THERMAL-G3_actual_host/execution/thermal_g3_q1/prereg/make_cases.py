"""Q1-R case generator (INFRA): the original 2 qualification + 31 formal cases.

The 31 formal case_ids, groups, scales, protocols and baselines are those of
outputs/THERMAL-G3-v1.1修订任务表_2026-10-08.json (G0 4 / CHAIN 12 / STRUCTURE 6 / FULL 4 /
NUM 2 / DC 3); its sha256 is pinned in the output. Each case records the builder and its
construction-time arguments, the environment stimulus, the analysis (and its stop / max step),
judge configuration, baseline, dependencies and the scale hard cap. Required / saved vectors
are derived per case by runtime/decks.case_assets from the judge registry and the ledger plan.

Stimulus: inherited from the dev-006/007 decks: +-3 K steps of STEP_S = 7 s on a 43.5 C
background; the G0 occurrence interval targets 1.5 s (forward) / 3 s (reverse) as in the table.
Waits: POR settle + 5 tau_m of the slowest membrane before the first event; after the last
event: Θ/Cdir history expiry (certificate) + activity exit + 5 tau_m, so the run returns.
Max step: 0.5 ms (half of the 1 ms trace charge time constant); half-step cases 0.25 ms.
"""
import hashlib
import json
import math
import os
import sys

Q1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, Q1)
from netlists.params import v  # noqa: E402

# The task table is read from the in-package copy; the workstation original is provenance only
# (checked for identity when it exists, never required).
TASK_TABLE = os.path.join(Q1, "prereg", "inputs", "thermal_g3_v1.1_task_table_2026-10-08.json")
TASK_TABLE_ORIGIN = ("C:/Users/shaoc/Documents/Codex/2026-09-24/files-mentioned-by-the-user-2026/outputs/"
                     "THERMAL-G3-v1.1修订任务表_2026-10-08.json")
STEP_S, AMP_K = 7.0, 3.0
MAX_STEP = 0.5e-3
TSTEP_PRINT = 1e-3
TIMEOUT = {"single_site_single_polarity": 2700, "two_actual_G0_parent_chain": 5400,
           "four_sites_both_polarities_124_cores": 14400, "mother_bench": 600}
STATIC_TIMEOUT = 900
INTERVAL = {"F": 1.5, "R": 3.0}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def up(x, q=0.1):
    return math.ceil(x / q - 1e-9) * q


def schedule():
    cert = json.load(open(os.path.join(Q1, "analysis", "input_bounds.json"), encoding="utf-8"))
    proto = json.load(open(os.path.join(Q1, "prereg", "protocol_q1r_joint.json"), encoding="utf-8"))
    t0 = proto["por_settle_s"]
    tail = cert["nom"]["history_expiry_s"] + cert["nom"]["roles"]["G0"]["activity_window_s"] + \
        5 * v("NM_RM") * v("NM_CM_THETA_CDIR") * 1.1
    return cert, proto, up(t0), up(tail)


def g0_env(site, t0, amp):
    return {site: [[t0, t0 + STEP_S, amp]]}


def chain_env(i, j, d, pol, t0):
    """Adjacent pair (i, j): warm(+)/cool(-) steps; F: i then j after 1.5 s; R: j then i after 3 s."""
    amp = AMP_K if pol == "W" else -AMP_K
    a, b = (i, j) if d == "F" else (j, i)
    dt = INTERVAL[d]
    return {a: [[t0, t0 + STEP_S, amp]], b: [[t0 + dt, t0 + dt + STEP_S, amp]]}


def full_env(t0, mirror=False):
    """Four sites: warm events forward 1->4 at 1.5 s spacing, then cool events reverse 4->1."""
    env = {s: [] for s in (1, 2, 3, 4)}
    order_w = [1, 2, 3, 4]
    tw = t0
    for k, s in enumerate(order_w):
        env[s].append([tw + 1.5 * k, tw + 1.5 * k + STEP_S, AMP_K])
    tc = tw + 1.5 * 3 + STEP_S + 25.0      # cool block after warm block has returned
    for k, s in enumerate(reversed(order_w)):
        env[s].append([tc + 3.0 * k, tc + 3.0 * k + STEP_S, -AMP_K])
    return env, tc + 3.0 * 3 + STEP_S




def make():
    cert, proto, t0, tail = schedule()
    if os.path.exists(TASK_TABLE_ORIGIN) and sha(TASK_TABLE_ORIGIN) != sha(TASK_TABLE):
        raise SystemExit("in-package task table differs from its origin")
    table = json.load(open(TASK_TABLE, encoding="utf-8"))
    cases = []
    # ---------------- qualification (mother bench)
    tq = proto["total_s"]
    for cid, ms in (("Q1_MOTHER_PROTOCOL", 0.25e-3), ("Q1_MOTHER_HALFSTEP", 0.125e-3)):
        cases.append({"case_id": cid, "phase": "qualification", "group": "MOTHER", "scale": "mother_bench",
                      "builder": "bench_mother", "build_args": {}, "env": None,
                      "analysis": f"tran {TSTEP_PRINT:g} {tq:g} 0 {ms:g}", "x_stop": tq, "max_step_s": ms,
                      "timeout_s": TIMEOUT["mother_bench"],
                      "baseline_case_id": None if cid.endswith("PROTOCOL") else "Q1_MOTHER_PROTOCOL",
                      "depends_on": [] if cid.endswith("PROTOCOL") else ["Q1_MOTHER_PROTOCOL"],
                      "judge": "criteria_q1r.judge_joint" if cid.endswith("PROTOCOL") else "halfstep_compare.compare"})
    # ---------------- formal (original table order and ids)
    for c in table["formal_cases"]:
        cid, grp, scale = c["case_id"], c["group"], c["scale"]
        rec = {"case_id": cid, "phase": "formal", "group": grp, "scale": scale,
               "protocol_text": c["protocol"], "expected_text": c["expected"],
               "baseline_case_id": c["baseline_case_id"], "builder": "build_thermal_g3.build",
               "timeout_s": TIMEOUT.get(scale, STATIC_TIMEOUT), "depends_on": ["Q1_MOTHER_PROTOCOL", "Q1_MOTHER_HALFSTEP"]}
        ms = MAX_STEP
        if grp == "G0":
            pol = "w" if cid != "G0_C" else "c"
            amp = AMP_K if pol == "w" else -AMP_K
            args = {"sites": [1, 2, 3, 4], "g0_sites": [1], "pols": [pol], "layers": ["g0"]}
            if cid == "G0_CUT_K1":
                args["g0_cut"] = ["w", 1, 1]
            if cid == "G0_CUT_K10":
                args["g0_cut"] = ["w", 1, 10]
            # stimulus, withdraw, recover, repeat (table: 完整刺激、撤回、恢复后重复)
            env = {1: [[t0, t0 + STEP_S, amp], [t0 + STEP_S + tail, t0 + 2 * STEP_S + tail, amp]]}
            stop = up(t0 + 2 * STEP_S + 2 * tail)
            rec.update(build_args=args, env=env,
                       judge={"kind": "g0", "pol": pol, "site": 1, "cut_k": args.get("g0_cut", [None] * 3)[2]})
            if cid.startswith("G0_CUT"):
                rec["depends_on"] = rec["depends_on"] + ["G0_W"]
            elif cid == "G0_C":
                rec["depends_on"] = rec["depends_on"] + ["G0_W"]
        elif grp in ("CHAIN", "STRUCTURE", "NUM") and scale == "two_actual_G0_parent_chain":
            if grp == "CHAIN":
                _, pair, pol, d = cid.split("_")
                i, j = int(pair[0]), int(pair[1])
            else:
                i, j, pol, d = 1, 2, "W", "F"
            env = chain_env(i, j, d, pol, t0)
            args = {"sites": [1, 2, 3, 4], "g0_sites": [i, j], "pols": [pol.lower()],
                    "layers": ["g0", "theta", "sigma", "cdir", "load"]}
            p = pol.lower()
            if cid == "STRUCT_THETA_PORT_CUT":
                args["theta_port_cut"] = [[p, i, j, "f"]]
            if cid == "STRUCT_SIGMA_PORT_CUT":
                args["sigma_port_cut"] = [[p, i, j, "f"]]
            if cid == "STRUCT_CDIR_HISTORY_BLEED":
                tb = t0 + INTERVAL["F"] + 0.5          # after the second G0 event starts
                args["bleed"] = {"which": [p, i, j, "f"],
                                 "pwl": f"PWL(0 0 {tb:g} 0 {tb + 1e-3:g} {v('VDD'):g} {tb + 0.5:g} {v('VDD'):g} {tb + 0.501:g} 0)"}
            if cid == "STRUCT_REAL_SIGMA_SWAP":
                args["sigma_readout_swap"] = True
            if cid == "INVALID_SYNC":
                env = {i: [[t0, t0 + STEP_S, AMP_K]], j: [[t0, t0 + STEP_S, AMP_K]]}
            if cid == "INVALID_STALE":
                exp = cert["nom"]["history_expiry_s"]
                gap = up(exp + cert["nom"]["roles"]["G0"]["activity_window_s"] + STEP_S)
                env = {i: [[t0, t0 + STEP_S, AMP_K]], j: [[t0 + gap, t0 + gap + STEP_S, AMP_K]]}
                rec["stale_gap_s"] = gap
            last = max(seg[1] for segs in env.values() for seg in segs)
            stop = up(last + tail)
            if grp == "NUM":
                ms = MAX_STEP / 2
            rec.update(build_args=args, env=env,
                       judge={"kind": grp.lower(), "pol": p, "pair": [i, j], "dir": d.lower()})
            if grp != "CHAIN" or cid != "CHAIN_12_W_F":
                rec["depends_on"] = rec["depends_on"] + ["CHAIN_12_W_F"]
        elif grp == "NUM" and scale == "single_site_single_polarity":
            args = {"sites": [1, 2, 3, 4], "g0_sites": [1], "pols": ["w"], "layers": ["g0"]}
            env = {1: [[t0, t0 + STEP_S, AMP_K], [t0 + STEP_S + tail, t0 + 2 * STEP_S + tail, AMP_K]]}
            stop = up(t0 + 2 * STEP_S + 2 * tail)
            ms = MAX_STEP / 2
            rec.update(build_args=args, env=env, judge={"kind": "num", "pol": "w", "site": 1, "baseline": "G0_W"})
            rec["depends_on"] = rec["depends_on"] + ["G0_W"]
        elif grp == "FULL":
            env, last = full_env(t0)
            args = {}
            if cid == "FULL_REAL_MIRROR":
                args["mirror_sites"] = True
            if cid == "FULL_SPACE_CUT":
                args["cut_edges"] = [["w", "23"], ["c", "23"]]
            if cid == "FULL_NUM_HALFSTEP":
                ms = MAX_STEP / 2
            stop = up(last + tail)
            rec.update(build_args=args, env=env, judge={"kind": "full"})
            rec["depends_on"] = rec["depends_on"] + (["FULL_NOM"] if cid != "FULL_NOM" else
                                                     ["CHAIN_12_W_F", "STRUCT_THETA_PORT_CUT"])
        elif grp == "DC":
            vdd = {"DC_2P7": 2.7, "DC_3": 3.0, "DC_3P2": 3.2}[cid]
            rec.update(build_args={"dc_supply": True, "vdd": vdd}, env={},
                       judge={"kind": "dc", "vdd": vdd}, timeout_s=STATIC_TIMEOUT)
            rec.update(analysis="op", x_stop=None, max_step_s=None)
            cases.append(rec)
            continue
        rec.update(analysis=f"tran {TSTEP_PRINT:g} {stop:g} 0 {ms:g}", x_stop=stop, max_step_s=ms)
        cases.append(rec)
    # dependency sanity
    ids = [c["case_id"] for c in cases]
    for c in cases:
        for d in c["depends_on"]:
            assert d in ids, (c["case_id"], d)
        assert c["baseline_case_id"] is None or c["baseline_case_id"] in ids
    counts = {}
    for c in cases:
        counts[c["group"]] = counts.get(c["group"], 0) + 1
    out = {"schema": "thermal_g3_q1r.cases.2", "task_table": {"path": os.path.relpath(TASK_TABLE, Q1).replace("\\", "/"), "sha256": sha(TASK_TABLE),
                                                          "origin": TASK_TABLE_ORIGIN},
           "stimulus_rule": {"step_s": STEP_S, "amp_K": AMP_K, "interval_s": INTERVAL, "t0_s": t0,
                             "tail_s": tail, "max_step_s": MAX_STEP},
           "counts": counts, "n_qualification": sum(c["phase"] == "qualification" for c in cases),
           "n_formal": sum(c["phase"] == "formal" for c in cases), "cases": cases}
    path = os.path.join(Q1, "prereg", "cases_q1r.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    return out


if __name__ == "__main__":
    o = make()
    print(o["counts"], o["n_qualification"], o["n_formal"])
    for c in o["cases"]:
        print(c["case_id"], c["scale"], c.get("analysis"), c["timeout_s"], c["depends_on"][-1:] if c["depends_on"] else [])
