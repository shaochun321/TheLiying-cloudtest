"""ngspice binary raw reader (INFRA). Logic copied unchanged from thermal_g3_v1
solver_adapter/ngspice.py read_raw (itself copied from the MFS0-R3 adapter)."""
import numpy as np


def read_raw(path):
    with open(path, "rb") as f:
        data = f.read()
    plots, pos = [], 0
    while pos < len(data):
        hdr, names = {}, []
        while True:
            end = data.index(b"\n", pos)
            line = data[pos:end].decode("latin-1")
            pos = end + 1
            if line.startswith("Binary:") or line.startswith("Values:"):
                binary = line.startswith("Binary:")
                break
            if line.startswith("Variables:"):
                for _ in range(hdr["nvar"]):
                    end = data.index(b"\n", pos)
                    names.append(data[pos:end].decode("latin-1").split()[1])
                    pos = end + 1
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                if k == "No. Variables":
                    hdr["nvar"] = int(v)
                elif k == "No. Points":
                    hdr["npts"] = int(v)
                elif k == "Flags":
                    hdr["flags"] = v.strip()
        if not binary:
            raise ValueError("ascii raw not supported")
        nvar, npts = hdr["nvar"], hdr["npts"]
        cplx = "complex" in hdr.get("flags", "")
        nb = nvar * npts * (16 if cplx else 8)
        arr = np.frombuffer(data[pos:pos + nb], dtype="<f8").reshape(npts, nvar * (2 if cplx else 1))
        pos += nb
        plots.append({n.lower(): arr[:, i].copy() for i, n in enumerate(names)})
        while pos < len(data) and data[pos:pos + 1] in (b"\n", b"\r"):
            pos += 1
    return plots
