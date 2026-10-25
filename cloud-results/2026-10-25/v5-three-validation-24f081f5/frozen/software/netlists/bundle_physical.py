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
                 mult=1, scale=1.0, *, reference_bias_n=None):
    """Low-active gate; explicit physical NMOS-reference wiring is required.

    diode_p is kept as a legacy provenance label, not connected to this bundle.
    Callers explicitly supply iref_n (irefp_n family) or ilim_n (ilimp_n family).
    The mapping is a construction-time wire, never selected by case/time/result.
    Design dimensions are proposed values, not simulation-qualified values.
    """
    if not isinstance(mult, int) or mult < 1:
        raise ValueError("mult must be a positive integer")
    if reference_bias_n is None or reference_bias_n == diode_p:
        raise ValueError("explicit NMOS bias gate node required")
    local_p = name + "local_p"
    cg, enable_a = name + "cg", name + "ena"

    # Clone the existing NMOS-to-PMOS bias conversion at each receiving branch.
    # Only the gate of refn touches the shared n-bias; shared p-bias is untouched.
    nl.M(name + "refn", local_p, reference_bias_n, "0", "0", "nch",
         v("BIAS_W"), v("BIAS_L"))
    nl.M(name + "refp", local_p, local_p, "vdd", WELL, "pch",
         v("BIAS_W"), v("BIAS_L"))

    inverter(nl, name + "eni_", enable_b, enable_a)
    nl.M(name + "cp", out, cg, "vdd", WELL, "pch",
         W * scale, L or v("BIAS_L"), mult=mult)
    nl.M(name + "bias", local_p, enable_b, cg, WELL, "pch",
         1.2e-6, 1e-6)
    nl.M(name + "off", cg, enable_a, "vdd", WELL, "pch",
         2.4e-6, 1e-6)
