"""THERMAL-G3-Q1 audit: read-only re-audit of the 24 sealed v1 dev analyses (INFRA).

Reads the v1 ledger and every existing cir/log/raw under the v1 raw root; never calls ngspice.
Per analysis: file hashes, raw point count and end time, h feedback wiring (from the deck),
and q crossings of VDD/2 (upward and downward; a missing downward edge is null).
Output: audit/v1_dev_raw_audit.json. Errata tables are generated from this file only.
"""
import glob
import hashlib
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
Q1 = os.path.dirname(HERE)
sys.path.insert(0, Q1)
from solver_adapter.read_raw import read_raw  # noqa: E402

V1 = os.path.join(os.path.dirname(Q1), "thermal_g3_v1")
V1_LEDGER = os.path.join(V1, "results", "analysis_ledger.jsonl")
RAW_DIR = ("C:/Users/shaoc/Documents/Codex/2026-09-24/files-mentioned-by-the-user-2026/"
           "work/thermal_g3_v1_raw/dev")
Q_THR = 1.5   # VDD/2 at VDD = 3.0 V (observation threshold on a rail-to-rail logic node)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def crossings(t, x, thr):
    up = np.where((x[1:] > thr) & (x[:-1] <= thr))[0] + 1
    dn = np.where((x[1:] <= thr) & (x[:-1] > thr))[0] + 1
    ev = []
    for i in up:
        j = dn[dn > i]
        ev.append({"up_s": float(t[i]), "down_s": float(t[j[0]]) if len(j) else None,
                   "width_s": float(t[j[0]] - t[i]) if len(j) else None})
    return ev


def deck_facts(cir):
    txt = open(cir, encoding="ascii", errors="replace").read().lower().splitlines()
    hrf = sorted({" ".join(l.split()[1:3]) for l in txt if re.match(r"^r\S*_hrf ", l)})
    analysis = [l.strip() for l in txt if l.strip().startswith(("tran", "dc ", "op"))]
    return {"hrf_nodes": hrf, "analysis_lines": analysis}


def main():
    recs = [json.loads(l) for l in open(V1_LEDGER, encoding="utf-8") if l.strip()]
    starts = {r["analysis_id"]: r for r in recs if r["rec"] == "start"}
    ends = {r["analysis_id"]: r for r in recs if r["rec"] == "end"}
    out = {"schema": "thermal_g3_q1.v1_dev_raw_audit.1", "mode": "read_only_no_solver",
           "ledger": {"path": V1_LEDGER, "sha256": sha(V1_LEDGER),
                      "starts": len(starts), "ends": len(ends),
                      "solver_wall_s_sum": sum((e.get("wall_s") or 0.0) for e in ends.values())},
           "q_threshold_V": Q_THR, "runs": {}}
    for aid in sorted(starts):
        s, e = starts[aid], ends.get(aid, {})
        files = {}
        for ext in ("cir", "log", "raw"):
            m = glob.glob(os.path.join(RAW_DIR, f"{aid}_*.{ext}"))
            files[ext] = ({"path": m[0].replace("\\", "/"), "size": os.path.getsize(m[0]),
                           "sha256": sha(m[0])} if m else None)
        run = {"tag": s.get("tag"), "purpose": s.get("purpose"), "analysis": s.get("analysis"),
               "start_t": s.get("t"), "end_t": e.get("t"), "wall_s": e.get("wall_s"),
               "ledger_error": e.get("error"), "files": files}
        if files["cir"]:
            run["deck"] = deck_facts(files["cir"]["path"])
        if files["raw"]:
            try:
                V = read_raw(files["raw"]["path"])[-1]
                xk = "time" if "time" in V else next(iter(V))
                x = V[xk]
                run["raw"] = {"x_var": xk, "points": int(len(x)), "x_end": float(x[-1]),
                              "vars": sorted(V)}
                if xk == "time":
                    run["q_events"] = {k: crossings(x, V[k], Q_THR)
                                       for k in sorted(V) if re.fullmatch(r"v\(\w*_q\)", k)}
            except Exception as ex:   # record, do not hide
                run["raw"] = {"parse_error": repr(ex)}
        out["runs"][aid] = run
    path = os.path.join(HERE, "v1_dev_raw_audit.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(path, sha(path))


if __name__ == "__main__":
    main()
