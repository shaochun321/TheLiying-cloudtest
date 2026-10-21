"""Independent unpack check of a THERMAL-G3-Q1-R run package (INFRA). Starts no solver.

Run from the unpacked run-package root (the directory holding RUN.md):
    python -B thermal_g3_q1/tools/check_cloud_package.py

Checks (results -> _unpack_check/unpack_check.json; exit 0 only if every item is PASS):
  inputs_manifest      every file listed in MANIFEST_inputs.json exists with its sha256, and no
                       unlisted file is present
  freeze_pins          every file pinned by thermal_g3_q1/FREEZE_Q1R.json matches
  v1_ledger_snapshot   the sealed v1 ledger snapshot hash equals the hash pinned in config.py
  task_table_copy      the in-package task table hash equals the one recorded in cases_q1r.json
  no_absolute_paths    absolute-path literals in package code are only the registered
                       workstation defaults, which the run-package layout does not use, or
                       self-check path fixtures marked "# path fixture (never opened)"; what is
                       actually opened is checked by files_opened_*
  deck_identity_33     all 33 decks rebuilt in this tree hash to the frozen deck identities
  production_dispatch  in a scratch copy, with a stand-in backend registered (the stand-in
                       executable tests/fake_ngspice.py writes synthetic raws, no solver):
                       Q1_MOTHER_PROTOCOL -> PASS, Q1_MOTHER_HALFSTEP -> PASS (judged against the
                       protocol raw), G0_W -> PASS (formal unblocked), G0_C counterexample -> FAIL
                       and round STOPPED; every verdict carries freeze / deck / raw hashes
  files_opened         every file the static and dispatch phases opened lies inside the run
                       package, the temporary directory or the Python installation
Synthetic raws test the package mechanics only; they say nothing about the circuit.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # thermal_g3_q1/
PACK = os.path.dirname(HERE)                                            # run-package root
OUT = os.path.join(PACK, "_unpack_check")

# Workstation defaults that exist as literals but are not used in the run-package layout:
# config falls back to them only when no backend registration / env / sibling layout applies;
# make_cases reads the in-package task table (origin is provenance); source_manifest and the
# v1 re-audit are construction-time tools that are not part of the run.
ALLOWED_ABS = {"config.py": "_CODEX", "prereg/make_cases.py": "TASK_TABLE_ORIGIN",
               "tools/source_manifest.py": "TOOLS", "audit/reaudit_v1_dev.py": "RAW_DIR"}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def allowed_roots():
    roots = {os.path.abspath(PACK), os.path.abspath(tempfile.gettempdir()), os.path.abspath(sys.prefix),
             os.path.abspath(sys.base_prefix)}
    for k in ("stdlib", "platstdlib", "purelib", "platlib"):
        p = sysconfig.get_paths().get(k)
        if p:
            roots.add(os.path.abspath(p))
    return [os.path.normcase(r) for r in roots]


def install_open_audit(log):
    def hook(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            p = os.fsdecode(args[0])
            if not p.startswith("<"):
                log.add(os.path.normcase(os.path.abspath(p)))
    sys.addaudithook(hook)


def outside(paths):
    roots = allowed_roots()
    return sorted(p for p in paths if not any(p == r or p.startswith(r + os.sep) for r in roots))


# ------------------------------------------------------------------ phase: static
def phase_static():
    opened = set()
    install_open_audit(opened)
    sys.path.insert(0, HERE)
    os.chdir(HERE)
    res = {}
    man = json.load(open(os.path.join(PACK, "MANIFEST_inputs.json"), encoding="utf-8"))
    bad = [r for r, h in man["files"].items() if not os.path.isfile(os.path.join(PACK, r)) or sha(os.path.join(PACK, r)) != h]
    present = set()
    for d, _, fs in os.walk(PACK):
        if os.path.abspath(d).startswith(os.path.abspath(OUT)) or "__pycache__" in d:
            continue
        for f in fs:
            present.add(os.path.relpath(os.path.join(d, f), PACK).replace("\\", "/"))
    extra = sorted(present - set(man["files"]) - {"MANIFEST_inputs.json"})
    res["inputs_manifest"] = {"pass": not bad and not extra, "n": len(man["files"]), "bad": bad[:10], "unlisted": extra[:10]}
    fr = json.load(open(os.path.join(HERE, "FREEZE_Q1R.json"), encoding="utf-8"))
    bad = [r for r, h in fr["pinned_sha256"].items() if not os.path.isfile(os.path.join(HERE, r)) or sha(os.path.join(HERE, r)) != h]
    res["freeze_pins"] = {"pass": not bad, "n": len(fr["pinned_sha256"]), "bad": bad[:10]}
    import config
    res["v1_ledger_snapshot"] = {"pass": os.path.isfile(config.V1_LEDGER) and sha(config.V1_LEDGER) == config.V1_LEDGER_SHA256
                                 and os.path.abspath(config.V1_LEDGER).startswith(os.path.abspath(PACK)),
                                 "path": os.path.relpath(config.V1_LEDGER, PACK).replace("\\", "/")}
    reg = json.load(open(os.path.join(HERE, "prereg", "cases_q1r.json"), encoding="utf-8"))
    tt = os.path.join(HERE, reg["task_table"]["path"])
    res["task_table_copy"] = {"pass": os.path.isfile(tt) and sha(tt) == reg["task_table"]["sha256"],
                              "path": reg["task_table"]["path"]}
    lit = re.compile(r"""["'](?:[A-Za-z]:[/\\]|/home/|/Users/|/mnt/)[^"']*["']""")
    found = []
    for d, _, fs in os.walk(HERE):
        if "__pycache__" in d:
            continue
        for f in fs:
            if not f.endswith(".py"):
                continue
            rp = os.path.relpath(os.path.join(d, f), HERE).replace("\\", "/")
            for i, line in enumerate(open(os.path.join(d, f), encoding="utf-8"), 1):
                if lit.search(line) and not line.lstrip().startswith("#"):
                    ok = rp in ALLOWED_ABS and ALLOWED_ABS[rp] in "".join(
                        open(os.path.join(d, f), encoding="utf-8").readlines()[max(0, i - 2):i])
                    fixture = line.rstrip().endswith("# path fixture (never opened)")
                    found.append({"file": rp, "line": i, "registered": "workstation default" if ok else
                                  ("test fixture" if fixture else None)})
    res["no_absolute_paths"] = {"pass": all(x["registered"] for x in found), "literals": found}
    from runtime.decks import deck_text
    mism = [cid for cid, d in fr["decks"].items()
            if hashlib.sha256(deck_text(cid)[0].encode()).hexdigest() != d["sha256"]]
    res["deck_identity_33"] = {"pass": not mism and len(fr["decks"]) == 33, "n": len(fr["decks"]), "mismatch": mism}
    res["files_opened_static"] = {"pass": not outside(opened), "outside": outside(opened)[:20], "n": len(opened)}
    return res


# ------------------------------------------------------------------ phase: dispatch
def phase_dispatch(scratch):
    """In a scratch copy (thermal_g3_q1 + thermal_g3_v1), stand-in backend, production run_case."""
    opened = set()
    install_open_audit(opened)
    pkg = os.path.join(scratch, "thermal_g3_q1")
    sys.path.insert(0, pkg)
    os.chdir(pkg)
    import numpy as np
    from tools.register_backend import main as register
    from tools.write_freeze import build_freeze, sha as fsha
    fake = os.path.join(pkg, "tests", "fake_ngspice.py")
    osdi = os.path.join(scratch, "standin.osdi")
    open(osdi, "wb").write(b"stand-in OSDI for the unpack check; never loaded")
    register(["--platform", "unpack-check-standin", "--ngspice", fake, "--osdi", osdi])
    fr = build_freeze(root=pkg, status="FROZEN_AWAITING_LAUNCH", why=[])
    with open(os.path.join(pkg, "FREEZE_Q1R.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(fr, f)
    with open(os.path.join(pkg, "prereg", "LAUNCH_PERMISSION.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"freeze_sha256": fsha(os.path.join(pkg, "FREEZE_Q1R.json")), "phases": ["qualification", "formal", "rerun"],
                   "granted_by": "unpack-check stand-in (scratch copy only)", "date": "-"}, f)
    from runtime.decks import case_assets, registry
    from tests.synth_raw import legal
    reg = {c["case_id"]: c for c in registry()["cases"]}
    npz = {}
    for cid in ("Q1_MOTHER_PROTOCOL", "G0_W", "G0_C"):
        V = legal(reg[cid], case_assets(cid))
        if cid == "G0_C":       # counterexample: no second step
            c = reg[cid]
            p = f"g{c['judge']['pol']}{c['judge']['site']}_"
            a2 = c["env"][str(c["judge"]["site"])][1][0]
            for n in ("and_g8", "col_q", "op_aq", "op_p"):
                V[f"v({p}{n})"][V["time"] >= a2] = 0.0
        npz[cid] = os.path.join(scratch, f"{cid}.npz")
        np.savez(npz[cid], **V)
    from runtime.coordinator import Coordinator, Refused
    C = Coordinator(root=pkg, raw_root=os.path.join(scratch, "raw"), solver=[sys.executable, "-B", fake])
    os.environ["FAKE_MODE"] = "npz"
    out = {}
    for cid, src in (("Q1_MOTHER_PROTOCOL", "Q1_MOTHER_PROTOCOL"), ("Q1_MOTHER_HALFSTEP", "Q1_MOTHER_PROTOCOL"),
                     ("G0_W", "G0_W"), ("G0_C", "G0_C")):
        os.environ["FAKE_NPZ"] = npz[src]
        try:
            aid, e = C.run_case(cid)
            out[cid] = {"aid": aid, "status": e["status"], "scientific": (e.get("verdict") or {}).get("scientific")}
        except Refused as x:
            out[cid] = {"refused": str(x)}
    try:
        C.run_case("CHAIN_12_W_F")
        out["after_fail"] = "RAN"
    except Refused as x:
        out["after_fail"] = str(x)
    vr = C.records(C.verdicts)
    bound = all(v.get("freeze_sha256") and v.get("deck_sha256") and v.get("raw_sha256") == fsha(v["raw_path"])
                and v["judge_output"]["sha256"] == fsha(v["judge_output"]["path"]) for v in vr)
    ok = ([out[c].get("scientific") for c in ("Q1_MOTHER_PROTOCOL", "Q1_MOTHER_HALFSTEP", "G0_W", "G0_C")]
          == ["PASS", "PASS", "PASS", "FAIL"] and "round stopped" in out["after_fail"] and bound and len(vr) == 4)
    return {"production_dispatch": {"pass": ok, "runs": out, "n_verdicts": len(vr), "verdicts_bound": bound},
            "files_opened_dispatch": {"pass": not outside(opened), "outside": outside(opened)[:20], "n": len(opened)}}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--phase-static":
        print("RES" + json.dumps(phase_static()))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--phase-dispatch":
        print("RES" + json.dumps(phase_dispatch(sys.argv[2])))
        return
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    env = {k: v for k, v in os.environ.items() if not k.startswith("THERMAL_G3")}
    env["PYTHONIOENCODING"] = "utf-8"
    res = {}

    def sub(args):
        r = subprocess.run([sys.executable, "-B", os.path.abspath(__file__)] + args, cwd=PACK, env=env,
                           capture_output=True, text=True, timeout=3600)
        line = [l for l in r.stdout.splitlines() if l.startswith("RES")]
        if not line:
            return {f"phase_{args[0]}_raised": {"pass": False, "error": (r.stdout + r.stderr)[-1500:]}}
        return json.loads(line[-1][3:])
    res.update(sub(["--phase-static"]))
    scratch = os.path.join(OUT, "scratch")
    os.makedirs(scratch)
    shutil.copytree(HERE, os.path.join(scratch, "thermal_g3_q1"), ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(PACK, "thermal_g3_v1"), os.path.join(scratch, "thermal_g3_v1"))
    res.update(sub(["--phase-dispatch", scratch]))
    out = {"schema": "thermal_g3_q1r.unpack_check.1", "pack_root": "<unpacked run package>", "solver_starts": 0,
           "python": sys.version.split()[0], "platform": sys.platform,
           "all_pass": all(x.get("pass") for x in res.values()), "items": res}
    with open(os.path.join(OUT, "unpack_check.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
    for k, x in res.items():
        print(("PASS " if x.get("pass") else "FAIL ") + k)
    print("all_pass", out["all_pass"])
    sys.exit(0 if out["all_pass"] else 1)


if __name__ == "__main__":
    main()
