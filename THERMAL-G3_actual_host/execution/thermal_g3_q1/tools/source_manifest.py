"""THERMAL-G3-Q1 source + toolchain manifest (INFRA, construction time only).

Records sha256 of every Q1 source file (and, for files copied from thermal_g3_v1, the v1
original so identity/difference is explicit), plus the solver toolchain actually used:
ngspice executable, OSDI binary, Verilog-A sources, OpenVAF compiler and the compile branch.
Output: prereg/source_manifest.json. Re-run before freezing; FREEZE_Q1.json pins its hash.
"""
import glob
import hashlib
import json
import os
import sys

Q1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1 = os.path.join(os.path.dirname(Q1), "thermal_g3_v1")
sys.path.insert(0, Q1)
import config  # noqa: E402

TOOLS = ("C:/Users/shaoc/Documents/Codex/2026-09-24/files-mentioned-by-the-user-2026/"
         "work/mfs0_r1/tools")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def rel(p):
    return os.path.relpath(p, Q1).replace("\\", "/")


def main():
    src = {}
    for p in sorted(glob.glob(os.path.join(Q1, "**", "*.py"), recursive=True)
                    + glob.glob(os.path.join(Q1, "models", "*.lib"))):
        if "__pycache__" in p or os.sep + "results" + os.sep in p:
            continue
        r = rel(p)
        ent = {"sha256": sha(p)}
        v1p = os.path.join(V1, r)
        if os.path.exists(v1p):
            ent["v1_sha256"] = sha(v1p)
            ent["identical_to_v1"] = ent["v1_sha256"] == ent["sha256"]
        src[r] = ent
    tool = {
        "ngspice": {"path": config.get_ngspice_path(), "sha256": sha(config.get_ngspice_path())},
        "osdi": {"path": config.get_osdi_path(), "sha256": sha(config.get_osdi_path()),
                 "identical_to": "ekv_src/ekv26_rebuilt_ngspice.osdi"
                 if sha(config.get_osdi_path()) == sha(f"{TOOLS}/ekv_src/ekv26_rebuilt_ngspice.osdi")
                 else None},
        "verilog_a": {os.path.basename(p): sha(p) for p in
                      sorted(glob.glob(f"{TOOLS}/ekv_src/*.va") + glob.glob(f"{TOOLS}/ekv_src/*.vams"))},
        "compiler": {"path": f"{TOOLS}/openvaf1/openvaf.exe", "sha256": sha(f"{TOOLS}/openvaf1/openvaf.exe"),
                     "version": "OpenVAF 1.0.0 (dwarning release)",
                     "defines": ["__NGSPICE__"],
                     "source_of_define": "work/mfs0_r1/research/r1/model_provenance.md:13"},
        "model_card": {"path": rel(config.get_model_lib_path()), "sha256": sha(config.get_model_lib_path()),
                       "validity_note": "source states |Vg|<3.3V, |Vd|<3.3V, |Vs|<2V; W 0.8-10um, L 0.5-10um"},
    }
    out = {"schema": "thermal_g3_q1.source_manifest.1", "sources": src, "toolchain": tool}
    path = os.path.join(Q1, "prereg", "source_manifest.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    diff = [k for k, e in src.items() if e.get("identical_to_v1") is False]
    print(path, sha(path), "differs_from_v1:", diff)


if __name__ == "__main__":
    main()
