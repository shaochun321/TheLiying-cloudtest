"""Build the THERMAL-G3-Q1-R run package (INFRA). Starts no solver.

    python -B tools/make_cloud_package.py [--out DIR]

Requires a current FREEZE_Q1R.json whose pinned files all match. Writes
<DIR>/thermal_g3_q1r_runpack_<freeze8>.zip (default DIR: a sibling of the raw root, outside git)
with this layout under thermal_g3_q1r_runpack_<freeze8>/:
  thermal_g3_q1/            every file pinned by the freeze + FREEZE_Q1R.json (+ superseded
                            freezes as provenance): code, 2+31 case registry, protocol, node /
                            vector maps (ledger plan + judges), observers, production judging
                            entry, params, model card, VA sources + includes, provenance,
                            in-package task table copy
  thermal_g3_v1/results/analysis_ledger.jsonl   sealed v1 ledger snapshot (24 dev starts)
  backend/windows-x64/      registered workstation binaries (OSDI, ngspice archive + file list)
  RUN.md  tasks.json  budget_contract.json  MANIFEST_runtime.json  MANIFEST_inputs.json
Then unpacks the zip into a fresh temporary directory outside the project and runs
thermal_g3_q1/tools/check_cloud_package.py there; its report is copied to
results/cloud_unpack_check.json (not pinned).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config  # noqa: E402


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def topo(cases):
    done, order = set(), []
    pending = list(cases)
    while pending:
        nxt = [c for c in pending if all(d in done for d in c["depends_on"])
               and (not c["baseline_case_id"] or c["baseline_case_id"] in done)]
        if not nxt:
            raise SystemExit("dependency cycle")
        for c in nxt:
            order.append(c["case_id"])
            done.add(c["case_id"])
        pending = [c for c in pending if c["case_id"] not in done]
    return order


NOT_READY = [
    {"item": "linux_ngspice_47", "why": "ngspice-47 on the cloud host is not installed / verified here"},
    {"item": "linux_osdi_build", "why": "ekv26 OSDI not yet built from backend/ekv_src with OpenVAF 1.0.0 -D__NGSPICE__ on the host"},
    {"item": "backend_registration_and_freeze", "why": "tools/register_backend.py, static check, selfcheck and write_freeze "
                                                       "not yet run on the host; the shipped freeze authorises the workstation backend only"},
    {"item": "launch_permission_for_host_freeze", "why": "the user grants permission for the host freeze; none exists"},
    {"item": "linux_supervisor_deadline", "why": "the process-group SIGKILL path of runtime/supervisor.py is not exercised on Linux "
                                                 "(selfcheck item coord_supervisor_kills_tree_after_coordinator_death must pass on the host)"},
    {"item": "python_stack", "why": "Python / numpy (>= 2.0, trapezoid) / scipy on the host not verified; see MANIFEST_runtime.json"},
    {"item": "storage_and_retrieval", "why": "raw output volume (FULL cases: 345 saved vectors) and retrieval channel not verified"},
]


RUN_MD = """# THERMAL-G3-Q1-R run package {freeze8}

Freeze `thermal_g3_q1/FREEZE_Q1R.json` sha256 `{freeze}` (status {status}).
This freeze authorises the **workstation** backend only. Cloud environment items are
**NOT_READY** (`tasks.json` → `environment.NOT_READY`). Nothing in this package has been run on
a cloud host. Synthetic stand-in runs (unpack check) say nothing about the circuit.

## Budget and backend (single contract)
- There is one budget: dev 24 (sealed, `thermal_g3_v1/results/analysis_ledger.jsonl`) /
  qualification 2 / formal 31 / rerun 4 = 61 starts; 48 h cumulative wall (v1 used {v1_wall_h:.3f} h);
  phase caps 1200 / 108000 / 14400 s. Q1 starts so far: {q1_starts}.
- One backend per round, fixed by the first start (Q1_MOTHER_PROTOCOL). If the cloud is used,
  use it from Q1_MOTHER_PROTOCOL onwards. No cross-platform comparison gate; no separate budget
  per backend; rerun slots are only for registered infrastructure failures, not a platform quota.
- Ledger custody: once execution starts on a host, that host's `thermal_g3_q1/results/q1_ledger.jsonl`
  is the only live Q1 ledger. Do not start cases on two hosts.

## Steps on the execution host
1. Unpack. From the package root: `python -B thermal_g3_q1/tools/check_cloud_package.py` (no solver).
2. Backend (Linux): install ngspice-47; build the OSDI:
   `openvaf -D__NGSPICE__ thermal_g3_q1/backend/ekv_src/ekv26.va -o ekv26.osdi` (OpenVAF 1.0.0).
   (Windows host: `backend/windows-x64/` holds the registered OSDI and the ngspice-47 archive.)
3. `cd thermal_g3_q1` and run `python -B tools/register_backend.py --platform <tag> --ngspice <exe> --osdi <osdi> [--openvaf <exe>]`.
4. `python -B tools/static_check.py`, `python -B tools/selfcheck_all.py`, then `python -B tools/write_freeze.py`;
   the new `FREEZE_Q1R.json` must be FROZEN_AWAITING_LAUNCH (the old one is kept as superseded).
   `prereg/source_manifest.json` stays as workstation provenance (do not re-run source_manifest.py).
5. The user writes `prereg/LAUNCH_PERMISSION.json` for that freeze (`README.md`).
6. Run cases one at a time in `tasks.json` → `order`: `python -B runtime/coordinator.py <case_id>`.
   Qualification first (Q1_MOTHER_PROTOCOL, then Q1_MOTHER_HALFSTEP, 600 s cap each); the
   coordinator refuses anything out of order, over a cap, after a required FAIL (STOPPED), or on a
   different backend. Raw output goes to `$THERMAL_G3_Q1_RAW_ROOT` (default `../thermal_g3_q1_raw`).

## Bring back
- `thermal_g3_q1/results/q1_ledger.jsonl` (start / end records with cir / log / raw sha256)
- `thermal_g3_q1/results/verdicts.jsonl` (per case: freeze / deck / raw / backend / judge-output sha256)
- `thermal_g3_q1/results/verdicts/<aid>_<case>.json` (per-gate judge output, incl. ledger and readback)
- `thermal_g3_q1/results/STOPPED` if present
- raw root: `<aid>/<aid>_<case>.{{cir,raw,log,sup.json}}` (raw files are large; their sha256 is in the ledger)
- `thermal_g3_q1/FREEZE_Q1R.json`, `prereg/backend_registration.json`, `prereg/LAUNCH_PERMISSION.json`
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(config.get_raw_root()), "thermal_g3_q1_dist"))
    a = ap.parse_args(argv)
    frp = os.path.join(ROOT, "FREEZE_Q1R.json")
    fr, fr_sha = json.load(open(frp, encoding="utf-8")), sha(frp)
    bad = [r for r, h in fr["pinned_sha256"].items() if sha(os.path.join(ROOT, r)) != h]
    if bad:
        raise SystemExit(f"package differs from its freeze: {bad[:5]}")
    name = f"thermal_g3_q1r_runpack_{fr_sha[:8]}"
    stage = tempfile.mkdtemp(prefix="q1r_pack_")
    top = os.path.join(stage, name)
    pkg = os.path.join(top, "thermal_g3_q1")
    for r in list(fr["pinned_sha256"]) + [f for f in os.listdir(ROOT) if f.startswith("FREEZE_Q1")]:
        d = os.path.join(pkg, r)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, r), d)
    v1 = os.path.join(top, "thermal_g3_v1", "results")
    os.makedirs(v1)
    if sha(config.V1_LEDGER) != config.V1_LEDGER_SHA256:
        raise SystemExit("v1 ledger hash changed")
    shutil.copy2(config.V1_LEDGER, os.path.join(v1, "analysis_ledger.jsonl"))
    # registered workstation binaries
    tools = os.path.dirname(config.get_osdi_path())
    win = os.path.join(top, "backend", "windows-x64")
    os.makedirs(win)
    shutil.copy2(config.get_osdi_path(), os.path.join(win, os.path.basename(config.get_osdi_path())))
    for f in ("ngspice-47_64.7z", "ngspice47_files.sha256", "tools.sha256"):
        shutil.copy2(os.path.join(tools, f), os.path.join(win, f))
    ext = fr["external_sha256"]
    backends = {"windows-x64": {"status": "REGISTERED (this freeze)",
                                "ngspice_exe_sha256": ext["THERMAL_G3_NGSPICE"]["sha256"],
                                "ngspice_archive": "backend/windows-x64/ngspice-47_64.7z",
                                "ngspice_archive_sha256": sha(os.path.join(win, "ngspice-47_64.7z")),
                                "osdi": f"backend/windows-x64/{os.path.basename(config.get_osdi_path())}",
                                "osdi_sha256": ext["THERMAL_G3_OSDI"]["sha256"],
                                "note": "on another Windows host the install paths differ: register + re-freeze as in RUN.md"},
                "linux-x64": {"status": "NOT_READY", "build": "OpenVAF 1.0.0 -D__NGSPICE__ from thermal_g3_q1/backend/ekv_src; ngspice-47"}}
    # ledger state and budget contract
    recs = [json.loads(l) for l in open(config.V1_LEDGER, encoding="utf-8") if l.strip()]
    v1_wall = sum(r.get("wall_s") or 0.0 for r in recs if r["rec"] == "end")
    q1l = os.path.join(ROOT, "results", "q1_ledger.jsonl")
    q1 = [json.loads(l) for l in open(q1l, encoding="utf-8")] if os.path.exists(q1l) else []
    started = {r["case_id"] for r in q1 if r["rec"] == "start"}
    budget = {"dev_closed": config.DEV_CLOSED, **config.CAPS, "total": config.GLOBAL_START_CAP,
              "global_wall_cap_s": config.GLOBAL_WALL_CAP_S, "phase_wall_caps_s": config.PHASE_WALL_CAP_S,
              "v1_wall_used_s": v1_wall, "q1_starts_so_far": len([r for r in q1 if r["rec"] == "start"]),
              "per_backend_budget": None, "cross_platform_gate": None,
              "rerun_policy": "registered infrastructure failures only (runtime/coordinator.py INFRA_FAILURES)"}
    reg = json.load(open(os.path.join(ROOT, "prereg", "cases_q1r.json"), encoding="utf-8"))
    cases = reg["cases"]
    order = topo(sorted(cases, key=lambda c: (c["phase"] != "qualification", c["case_id"])))
    groups = {}
    for c in cases:
        if c["baseline_case_id"]:
            groups.setdefault(c["baseline_case_id"], []).append(c["case_id"])
    tasks = {"schema": "thermal_g3_q1r.tasks.1", "freeze_sha256": fr_sha, "freeze_status": fr["status"],
             "backend_policy": "one backend per round, fixed by the first start; cloud -> from Q1_MOTHER_PROTOCOL onwards",
             "backends": backends, "budget": budget,
             "not_started": [c["case_id"] for c in cases if c["case_id"] not in started],
             "order": order,
             "cases": [{k: c[k] for k in ("case_id", "phase", "group", "scale", "analysis", "timeout_s", "depends_on",
                                          "baseline_case_id")} for c in cases],
             "baseline_groups": groups,
             "outputs": {"ledger": "thermal_g3_q1/results/q1_ledger.jsonl", "verdicts": "thermal_g3_q1/results/verdicts.jsonl",
                         "per_gate": "thermal_g3_q1/results/verdicts/<aid>_<case>.json", "stop_marker": "thermal_g3_q1/results/STOPPED",
                         "raw_root": "$THERMAL_G3_Q1_RAW_ROOT or ../thermal_g3_q1_raw (relative to thermal_g3_q1)",
                         "per_run": "<raw_root>/<aid>/<aid>_<case>.{cir,raw,log,sup.json}"},
             "environment": {"NOT_READY": NOT_READY}}
    import numpy
    import scipy
    runtime = {"schema": "thermal_g3_q1r.runtime.1", "built": time.strftime("%Y-%m-%d %H:%M:%S"),
               "built_on": {"python": sys.version.split()[0], "numpy": numpy.__version__, "scipy": scipy.__version__,
                            "platform": sys.platform},
               "requires": {"python": ">=3.10", "numpy": ">=2.0 (numpy.trapezoid)", "scipy": "any with optimize.brentq"},
               "solver_backend_frozen": {k: {"sha256": x["sha256"]} for k, x in ext.items()},
               "freeze_sha256": fr_sha, "deck_identity_sha256": {k: d["sha256"] for k, d in fr["decks"].items()}}
    for fn, obj in (("tasks.json", tasks), ("budget_contract.json", budget), ("MANIFEST_runtime.json", runtime)):
        with open(os.path.join(top, fn), "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=1, ensure_ascii=False)
    with open(os.path.join(top, "RUN.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(RUN_MD.format(freeze8=fr_sha[:8], freeze=fr_sha, status=fr["status"], v1_wall_h=v1_wall / 3600,
                              q1_starts=budget["q1_starts_so_far"]))
    files = {}
    for d, _, fs in os.walk(top):
        for f in fs:
            p = os.path.join(d, f)
            files[os.path.relpath(p, top).replace("\\", "/")] = sha(p)
    with open(os.path.join(top, "MANIFEST_inputs.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"schema": "thermal_g3_q1r.inputs.1", "freeze_sha256": fr_sha, "files": dict(sorted(files.items()))}, f, indent=1)
    os.makedirs(a.out, exist_ok=True)
    zp = os.path.join(a.out, name + ".zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in os.walk(top):
            for f in fs:
                p = os.path.join(d, f)
                z.write(p, os.path.relpath(p, stage).replace("\\", "/"))
    shutil.rmtree(stage, ignore_errors=True)
    print(zp, sha(zp), len(files) + 1, "files")
    # ---------------- independent unpack check, outside the project, no solver
    chk = tempfile.mkdtemp(prefix="q1r_unpack_")
    with zipfile.ZipFile(zp) as z:
        z.extractall(chk)
    root = os.path.join(chk, name)
    env = {k: v for k, v in os.environ.items() if not k.startswith("THERMAL_G3")}
    r = subprocess.run([sys.executable, "-B", os.path.join(root, "thermal_g3_q1", "tools", "check_cloud_package.py")],
                       cwd=root, env={**env, "PYTHONIOENCODING": "utf-8"}, capture_output=True, text=True, timeout=7200)
    print(r.stdout[-3000:], r.stderr[-2000:])
    rep = os.path.join(root, "_unpack_check", "unpack_check.json")
    out = json.load(open(rep, encoding="utf-8")) if os.path.exists(rep) else {"all_pass": False, "error": r.stderr[-2000:]}
    out["zip"] = {"name": os.path.basename(zp), "sha256": sha(zp), "dir": "outside git (raw-root sibling)"}
    out["unpacked_in"] = "fresh temporary directory outside the project"
    with open(os.path.join(ROOT, "results", "cloud_unpack_check.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
    shutil.rmtree(chk, ignore_errors=True)
    print("unpack check all_pass", out["all_pass"])
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
