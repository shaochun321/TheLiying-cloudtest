"""THERMAL-G3-v1 fixed bundles, traces and collective gate (construction time, INFRA).

and_tree     : 10 shaped traces -> 9 fixed AND2 (NAND2 + inverter) -> one logic node
gated_source : PMOS mirror copy of a reference diode, gated by a series PMOS switch
Nothing here counts spikes; the AND tree only sees real trace voltages.

v1.1: bundle_trace removed (inline in build_thermal_g3.g0 using neuron_nrc.trace).
"""
from .build import WELL, inverter, nand2
from .params import v


def and2(nl, p, a, b, y):
    nand2(nl, p + "n", a, b, p + "nb")
    inverter(nl, p + "i", p + "nb", y)


def and_tree(nl, p, ins):
    """Balanced fixed tree of AND2 cells over len(ins) inputs (10 -> 9 cells)."""
    lvl, k = list(ins), 0
    while len(lvl) > 1:
        nxt = []
        for i in range(0, len(lvl) - 1, 2):
            y = f"{p}g{k}"
            and2(nl, f"{p}a{k}_", lvl[i], lvl[i + 1], y)
            nxt.append(y)
            k += 1
        if len(lvl) % 2:
            nxt.append(lvl[-1])
        lvl = nxt
    assert k == len(ins) - 1
    return lvl[0]


def gated_source(nl, name, diode_p, out, enable_b, W, L=None, mult=1, scale=1.0):
    """Current copy of a PMOS diode reference into `out`, conducting only while enable_b is
    low (series PMOS switch). Both devices are real; no ideal current source.

    Args:
        scale: real multiplier (v1.1 corrected 2026-10-08); applied to W, NOT to mult
               (SPICE mult must be integer). Example: scale=0.3 sets W_eff = 0.3*W."""
    if not isinstance(mult, int) or mult < 1:
        raise ValueError(f"gated_source mult must be positive integer, got {mult}")
    W_eff = W * scale
    nl.M(name + "sw", name + "x", enable_b, "vdd", WELL, "pch", 4e-6, 1e-6)
    nl.M(name + "cp", out, diode_p, name + "x", WELL, "pch", W_eff, L or v("BIAS_L"), mult=mult)
