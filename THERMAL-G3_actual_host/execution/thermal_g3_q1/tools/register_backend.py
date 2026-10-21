"""Register the solver backend of an execution host (INFRA). Runs no solver and no binary.

    python -B tools/register_backend.py --platform linux-x64 --ngspice /opt/ngspice-47/bin/ngspice \
        --osdi /work/ekv26.osdi [--openvaf /opt/openvaf/openvaf] [--ngspice-version "ngspice-47"]

Writes prereg/backend_registration.json: platform tag, absolute paths and sha256 of the ngspice
executable and the OSDI, how the OSDI was built (backend/ekv_src copy, OpenVAF 1.0.0,
-D__NGSPICE__; compiler hash when given) and the versions declared by the operator. After this,
config.get_ngspice_path / get_osdi_path resolve to the registered assets, and a new freeze must be
written (tools/write_freeze.py, after static check and selfcheck on that host). The user grants
the launch permission for THAT freeze; there is no cross-backend comparison gate and no separate
budget per backend: all starts of the round use the backend of its first start.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True)
    ap.add_argument("--ngspice", required=True)
    ap.add_argument("--osdi", required=True)
    ap.add_argument("--openvaf")
    ap.add_argument("--ngspice-version", default="declared: ngspice-47")
    ap.add_argument("--openvaf-version", default="declared: OpenVAF 1.0.0")
    a = ap.parse_args(argv)
    for p in (a.ngspice, a.osdi):
        if not os.path.isfile(p):
            raise SystemExit(f"not a file: {p}")
    src = {os.path.basename(p): sha(p) for p in sorted(glob.glob(os.path.join(ROOT, "backend", "ekv_src", "*")))}
    reg = {"schema": "thermal_g3_q1r.backend.1", "platform": a.platform,
           "assets": {"THERMAL_G3_NGSPICE": {"path": os.path.abspath(a.ngspice).replace("\\", "/"), "sha256": sha(a.ngspice),
                                             "version": a.ngspice_version},
                      "THERMAL_G3_OSDI": {"path": os.path.abspath(a.osdi).replace("\\", "/"), "sha256": sha(a.osdi)}},
           "osdi_build": {"sources": "backend/ekv_src", "source_sha256": src, "compiler_version": a.openvaf_version,
                          "compiler_sha256": sha(a.openvaf) if a.openvaf and os.path.isfile(a.openvaf) else None,
                          "defines": ["__NGSPICE__"],
                          "command": "openvaf -D__NGSPICE__ backend/ekv_src/ekv26.va -o <osdi>"},
           "registered": time.strftime("%Y-%m-%d %H:%M:%S"),
           "note": "registration only; the backend is usable after a new freeze and a user permission for it"}
    p = os.path.join(ROOT, "prereg", "backend_registration.json")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(reg, f, indent=1)
    print(p, sha(p))
    return reg


if __name__ == "__main__":
    main(sys.argv[1:])
