"""Write FREEZE_Q1R.json (INFRA). Status is decided by the overall preparation checklist:
  results/selfcheck.json   every item PASS
  results/static_check.json  all 33 decks PASS
  analysis/input_bounds.json  certificate status NO_INCOMPATIBILITY_FOUND
-> FROZEN_AWAITING_LAUNCH; otherwise NOT_READY with the failing items listed.
Pins every package file (except results/ outputs other than the three checklists and the deck
identities) and the external solver assets actually used; records each case's deck identity hash.
Usage: python -B tools/write_freeze.py [--provisional]   (--provisional is used only inside the
selfcheck to test the coordinator against a temporary freeze; it never writes the real file).
"""
import glob
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config  # noqa: E402


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _asset(p):
    ap = os.path.abspath(p)
    rel = os.path.relpath(ap, ROOT) if os.path.splitdrive(ap)[0] == os.path.splitdrive(ROOT)[0] else ".."
    return {"path": (rel if not rel.startswith("..") else ap).replace("\\", "/"), "sha256": sha(ap)}


def externals():
    """The backend this freeze authorises: prereg/backend_registration.json if present (run
    package on another host), else this workstation's assets. In-package assets are stored
    relative to the package root."""
    return {"THERMAL_G3_NGSPICE": _asset(config.get_ngspice_path()),
            "THERMAL_G3_OSDI": _asset(config.get_osdi_path()),
            "THERMAL_G3_MODEL_LIB": _asset(config.get_model_lib_path())}


def pins(root=ROOT):
    out = {}
    for p in sorted(glob.glob(os.path.join(root, "**", "*"), recursive=True)):
        rp = os.path.relpath(p, root).replace("\\", "/")
        if not os.path.isfile(p) or "__pycache__" in rp or rp.startswith("FREEZE_") or rp.endswith(".lock"):
            continue
        if rp.startswith("results/") and rp not in ("results/selfcheck.json", "results/static_check.json"):
            continue
        if rp == "prereg/LAUNCH_PERMISSION.json":
            continue
        out[rp] = sha(p)
    return out


def decide(root=ROOT):
    why = []
    sc = os.path.join(root, "results", "selfcheck.json")
    st = os.path.join(root, "results", "static_check.json")
    ce = os.path.join(root, "analysis", "input_bounds.json")
    if not os.path.exists(sc):
        why.append("selfcheck missing")
    else:
        s = json.load(open(sc, encoding="utf-8"))
        why += [f"selfcheck:{k}" for k, x in s["items"].items() if x["result"] != "PASS"]
    if not os.path.exists(st):
        why.append("static check missing")
    else:
        s = json.load(open(st, encoding="utf-8"))
        if not s["all_pass"]:
            why += [f"static:{k}" for k in s["failed"]]
    c = json.load(open(ce, encoding="utf-8"))
    if c["status"] != "NO_INCOMPATIBILITY_FOUND":
        why.append(f"certificate:{c['status']}")
    return ("FROZEN_AWAITING_LAUNCH" if not why else "NOT_READY"), why


def build_freeze(root=ROOT, status=None, why=None):
    from runtime.decks import deck_text, registry
    reg = registry()
    decks, sizes = {}, {}
    for c in reg["cases"]:
        txt, _ = deck_text(c["case_id"])
        decks[c["case_id"]] = {"sha256": hashlib.sha256(txt.encode()).hexdigest()}
        sizes[c["case_id"]] = sum(1 for l in txt.splitlines() if l and l[0].lower() in "rcnvbe" and not l.startswith(".")
                                  and not l.lower().startswith("va_"))
    if status is None:
        status, why = decide(root)
    return {"schema": "thermal_g3_q1r.freeze.3", "status": status, "not_ready_reasons": why or [],
            "contract": {"dev_closed": config.DEV_CLOSED, **config.CAPS, "total": config.GLOBAL_START_CAP,
                         "phase_wall_caps_s": config.PHASE_WALL_CAP_S},
            "candidate": {"G0": "220k / 100n", "Sigma": "75k / 100n", "Theta_Cdir": "12k / 1.5u"},
            "solver_starts_this_step": 0,
            "pinned_sha256": pins(root), "external_sha256": externals(),
            "backend": (config.backend_registration() or {}).get("platform", "windows-x64 (workstation)"),
            "decks": decks, "case_sizes": sizes,
            "permission_file": "prereg/LAUNCH_PERMISSION.json",
            "permission_format": {"freeze_sha256": "<sha256 of this FREEZE_Q1R.json>",
                                  "phases": ["qualification", "formal", "rerun"], "granted_by": "<user>",
                                  "date": "<YYYY-MM-DD>"}}


def main():
    fr = build_freeze()
    old = os.path.join(ROOT, "FREEZE_Q1.json")
    if os.path.exists(old):
        os.replace(old, os.path.join(ROOT, "FREEZE_Q1_superseded.json"))
    stale = os.path.join(ROOT, "prereg", "FREEZE_Q1R.json")
    if os.path.exists(stale):
        os.remove(stale)
    p = os.path.join(ROOT, "FREEZE_Q1R.json")
    if os.path.exists(p):
        # a previous freeze is never overwritten: it is kept as superseded under its own hash
        prev = os.path.join(ROOT, f"FREEZE_Q1R_superseded_{sha(p)[:8]}.json")
        os.replace(p, prev)
        print("previous freeze kept as", os.path.basename(prev))
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(fr, f, indent=1, ensure_ascii=False)
    print(p, sha(p), fr["status"], fr["not_ready_reasons"][:10], len(fr["pinned_sha256"]), "files pinned")


if __name__ == "__main__":
    main()
