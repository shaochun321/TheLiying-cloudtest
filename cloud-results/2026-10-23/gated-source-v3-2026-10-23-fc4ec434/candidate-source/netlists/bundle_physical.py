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


def gated_source(nl, name, diode_p, out, enable_b, W, L=None,
                 mult=1, scale=1.0):
    """Low-active enable, same build-time interface as the existing bundle.

    cp: source fixed to vdd; its gate cg selects diode_p (enabled) or vdd
    (disabled). bias: PMOS pass device, source=cg, drain=diode_p.
    off: PMOS gate pull-up. Physical inverter generates complementary enable.
    Device sizes are a single design proposal, not simulation-qualified values.
    """
    if not isinstance(mult, int) or mult < 1:
        raise ValueError("mult must be a positive integer")
    cg, enable_a = name + "cg", name + "ena"
    inverter(nl, name + "eni_", enable_b, enable_a)
    nl.M(name + "cp", out, cg, "vdd", WELL, "pch",
         W * scale, L or v("BIAS_L"), mult=mult)
    nl.M(name + "bias", diode_p, enable_b, cg, WELL, "pch",
         1.2e-6, 1e-6)
    nl.M(name + "off", cg, enable_a, "vdd", WELL, "pch",
         2.4e-6, 1e-6)

