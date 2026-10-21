"""Stand-in executable for coordinator self-checks (INFRA). It is NOT a solver. It reads the deck
for the analysis line and the `write` path and emits a synthetic binary raw containing every
saved vector (finite values on the analysis axis), or misbehaves on purpose (env FAKE_MODE):
  ok       complete raw to the analysis stop
  short    raw ends at half the stop
  nan      one NaN in the first saved vector
  badaxis  time axis not strictly increasing
  abort    prints an ngspice abort message, writes nothing
  sleep    spawns a grandchild and sleeps (supervisor kill test; child pid -> FAKE_CHILD_PID_FILE)
  npz      writes the vectors of the .npz named by FAKE_NPZ, in the deck's save order (tran:
           "time" first); a saved vector absent from the .npz is an error (rc 1, nothing written)
"""
import os
import re
import subprocess
import sys
import time

import numpy as np


def write_raw(path, names, data):
    hdr = ["Title: fake", "Date: -", "Plotname: Transient Analysis", "Flags: real",
           f"No. Variables: {len(names)}", f"No. Points: {data.shape[0]}", "Variables:"]
    hdr += [f"\t{i}\t{n}\tvoltage" for i, n in enumerate(names)]
    hdr += ["Binary:"]
    with open(path, "wb") as f:
        f.write(("\n".join(hdr) + "\n").encode("latin-1"))
        f.write(data.astype("<f8").tobytes())


def main():
    cir = sys.argv[-1]
    lines = open(cir, encoding="ascii").read().splitlines()
    raw = [l.split(None, 1)[1] for l in lines if l.startswith("write ")][0]
    an = [l for l in lines if l.startswith(("tran ", "op"))][0].split()
    save = []
    for l in lines:
        if l.lower().startswith(".save "):
            save += l.split()[1:]
    mode = os.environ.get("FAKE_MODE", "ok")
    if mode == "sleep":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        open(os.environ["FAKE_CHILD_PID_FILE"], "w").write(str(child.pid))
        time.sleep(120)
        return
    if mode == "npz":
        src = np.load(os.environ["FAKE_NPZ"])
        names = (["time"] if an[0] != "op" else []) + save
        miss = [n for n in names if n not in src.files]
        if miss:
            print(f"fake: npz lacks {miss[:3]}", file=sys.stderr)
            sys.exit(1)
        write_raw(raw, names, np.column_stack([np.ravel(src[n]).astype(float) for n in names]))
        print("done")
        return
    if mode == "abort":
        print("doAnalyses: TRAN:  Timestep too small\nsimulation(s) aborted")
        return
    if an[0] == "op":
        names = ["v(vdd)"] + [n for n in save if n != "v(vdd)"]
        write_raw(raw, names, np.full((1, len(names)), 1.0))
        print("done")
        return
    stop = float(an[2])
    t = np.linspace(0.0, stop * (0.5 if mode == "short" else 1.0), 501)
    if mode == "badaxis":
        t[10] = t[9]
    names = ["time"] + save
    data = np.column_stack([t] + [np.sin(t + k) for k in range(len(save))])
    if mode == "nan":
        data[50, 1] = np.nan
    write_raw(raw, names, data)
    print("done")


if __name__ == "__main__":
    main()
