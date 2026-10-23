"""Unintegrated netlist-builder prototype; NOT a device model or solver.

Gate-bias switching candidate for THERMAL-G3's gated_source. All functional
switching is performed by instantiated MOS devices. No behavioral sources.
Use in a candidate copy only after freezing the proposed validation contract.
Relative imports assume placement in the project's netlists package.
"""
from .build import WELL, inverter
from .params import v


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

