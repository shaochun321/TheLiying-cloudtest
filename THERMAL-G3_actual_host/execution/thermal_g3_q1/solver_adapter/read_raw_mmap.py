"""Memory-efficient ngspice binary raw reader (CLOUD-B1 §3.2).

Replaces the MFS0-R3 read_raw() whole-file approach with mmap + zero-copy views.
Peak memory ~= file size (not 3×), enabling multi-GB waveform parsing on cloud workers.
"""
import mmap
import numpy as np


def read_raw_mmap(path):
    """Parse ngspice binary raw file using memory mapping.

    Returns list of plot dicts (same structure as original read_raw), but uses numpy views
    into the mmap buffer instead of creating copies. The mmap stays open as long as the
    returned arrays are alive.

    IMPORTANT: Caller must not modify the returned arrays (they are read-only views).
    If modification is needed, call .copy() explicitly on the specific arrays.
    """
    with open(path, "rb") as f:
        # Memory-map the entire file (read-only, private mapping)
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    plots, pos = [], 0
    size = len(mm)

    while pos < size:
        hdr, names = {}, []

        # Parse ASCII header
        while True:
            end = mm.find(b"\n", pos)
            if end == -1:
                break
            line = mm[pos:end].decode("latin-1")
            pos = end + 1

            if line.startswith("Binary:") or line.startswith("Values:"):
                binary = line.startswith("Binary:")
                break

            if line.startswith("Variables:"):
                nvar = hdr.get("nvar", 0)
                for _ in range(nvar):
                    end = mm.find(b"\n", pos)
                    if end == -1:
                        break
                    parts = mm[pos:end].decode("latin-1").split()
                    if len(parts) >= 2:
                        names.append(parts[1])
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

        nvar = hdr.get("nvar", 0)
        npts = hdr.get("npts", 0)
        if nvar == 0 or npts == 0:
            break

        cplx = "complex" in hdr.get("flags", "")
        nb = nvar * npts * (16 if cplx else 8)

        if pos + nb > size:
            raise ValueError(f"truncated binary data: expected {nb} bytes, got {size - pos}")

        # Zero-copy view: frombuffer on the mmap slice (read-only)
        # IMPORTANT: This creates a view, not a copy. The mmap must stay alive.
        arr = np.frombuffer(mm, dtype="<f8", count=nvar * npts * (2 if cplx else 1), offset=pos)
        arr = arr.reshape(npts, nvar * (2 if cplx else 1))

        # Build dict with column views (still zero-copy)
        plot = {}
        for i, n in enumerate(names):
            plot[n.lower()] = arr[:, i]  # view, not copy

        plots.append(plot)
        pos += nb

        # Skip trailing newlines
        while pos < size and mm[pos:pos + 1] in (b"\n", b"\r"):
            pos += 1

    # NOTE: We do not close mm here. It stays alive as long as the returned arrays are alive.
    # Python's gc will close it when all views are garbage-collected.
    return plots


def read_raw_mmap_safe(path):
    """Safe wrapper: same as read_raw_mmap but copies all arrays so mmap can be closed.

    Use this if the caller needs to modify arrays or keep them alive for a long time.
    Peak memory = 2× file size (mmap + copies), still better than 3× of the original.
    """
    plots_view = read_raw_mmap(path)
    # Explicitly copy all arrays so we can close the mmap
    plots_copy = []
    for plot in plots_view:
        plots_copy.append({k: v.copy() for k, v in plot.items()})
    return plots_copy


# Backward compatibility: drop-in replacement for the original read_raw
def read_raw(path, safe=True):
    """Drop-in replacement for solver_adapter.ngspice.read_raw().

    Args:
        path: Path to ngspice binary .raw file.
        safe: If True (default), copy arrays so mmap can be closed immediately.
              If False, return zero-copy views (caller must not modify, mmap stays open).

    Returns:
        List of plot dicts, each mapping variable name (lowercase) to numpy array.
    """
    if safe:
        return read_raw_mmap_safe(path)
    else:
        return read_raw_mmap(path)
