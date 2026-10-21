"""THERMAL-G3-v1 N-RC mother: dynamic hysteresis relaxation unit (v1.1 candidate).

TYPE:HYBRID (BIO role: spiking membrane with leak, threshold, refractory recovery; SEMI
realisation: EKV MOS + R/C only). v1.1 removes the cross-coupled NAND latch, independent
edge detector and independent timer. The pulse is formed by the membrane trajectory itself:
  membrane   : C_m to ground, R_m to the real rest reference vrest
  threshold  : symmetric 5T comparator + 2 inverters; resistive positive feedback from the
               inverted output o2 onto the threshold node h (explicit Ch capacitor, tau ~2 ms)
  discharge  : q high -> NMOS + Rdis series path pulls membrane toward vrest; when vm crosses
               the exit boundary q self-lowers (no external reset scheduler)
  recovery   : q high -> PMOS + R_ch charges C_rec; recovery shunt = two series NMOS (gates
               rec and qb): the shunt is disabled while q is high (avoiding premature cutoff
               of the pulse that establishes recovery itself), enabled after q lowers
  power-up   : common supply ramp; POR RC + regenerative inverter pair give por_hold (shunts
               every membrane and h to their prepare states) and por_ok

v1.1 §4.1: q/qb from the comparator output inverter chain (o1→qb→q); the h feedback resistor
connects to qb. This is REGENERATIVE (positive) hysteresis: q rises → qb falls → h falls →
vm−h grows → q held high. The negative path that ends the pulse is the real reset: q opens
the discharge NMOS → vm falls below the lowered h → q falls (errata 2026-10-09).
ΔV_h ~ R_a/(R_a+R_f) × swing, τ_h ~ (R_a || R_f) C_h. Rdis must be derived per role (§4.3):
G0 ensemble/collector 220 kΩ, Θ/Σ/Cdir receiver 75 kΩ — do not share one value. Activity
trace and occurrence port use real q pulse width (§4.4), not a fixed constant.

No behavioural source performs reset, discharge or timing. The only B/E sources in the whole
netlist are the NTC device equation, its Joule heat, and the environment boundary.
"""
from .build import WELL, inverter
from .params import v


def divider(nl, name, rt, rb):
    nl.R(name + "t", "vdd", name, rt)
    nl.R(name + "b", name, "0", rb)
    nl.C(name + "c", name, "0", v("REF_C"))


def supply_ramp(nl, vdd):
    """Common external energy boundary: source ramps 0 -> vdd in T_RAMP (identical for all)."""
    nl.V("src", "vsrc", "0", f"PWL(0 0 {v('T_RAMP')} {vdd})")
    nl.R("int", "vsrc", "vdd", v("R_INT"))
    nl.C("dec", "vdd", "0", v("C_DEC"))


def references(nl):
    """Shared physical references: rest / thresholds / mid dividers, POR, bias diodes."""
    divider(nl, "vrest", v("VREST_RT"), v("VREST_RB"))
    divider(nl, "vthe", v("VTHE_RT"), v("VTHE_RB"))
    divider(nl, "vthr", v("VTHR_RT"), v("VTHR_RB"))
    divider(nl, "vmid", v("VMID_RT"), v("VMID_RB"))
    # POR: RC from the rail; regenerative release with resistive positive feedback
    nl.R("porr", "vdd", "porc", v("POR_R"))
    nl.C("porc", "porc", "0", v("POR_C"))
    nl.R("porra", "porc", "porx", v("POR_RA"))
    nl.R("porrf", "por_ok", "porx", v("POR_RF"))
    inverter(nl, "pori1", "porx", "por_hold")
    inverter(nl, "pori2", "por_hold", "por_ok")
    # bias references: diode-connected devices fed by resistors (real currents, measured)
    W, L = v("BIAS_W"), v("BIAS_L")
    nl.R("iref", "vdd", "iref_n", v("IREF_R"))
    nl.M("irefd", "iref_n", "iref_n", "0", "0", "nch", W, L)
    nl.R("istep", "vdd", "istep_n", v("ISTEP_R"))
    nl.M("istepd", "istep_n", "istep_n", "0", "0", "nch", W, L)
    nl.M("irefm", "irefp_n", "iref_n", "0", "0", "nch", W, L)
    nl.M("irefpd", "irefp_n", "irefp_n", "vdd", WELL, "pch", W, L)


def nrc(nl, p, thr_ref, bias_k=0, rdis=None, cm=None):
    """One N-RC instance (v1.1). Inputs are attached by the caller as currents into p+'vm'.
    thr_ref: reference node of the threshold divider (vthe for G0 ensembles/collector,
    vthr for relation receivers). bias_k: number of unit I_step sink devices (ensemble
    graded recruitment, physical multiplicity). rdis: discharge resistor (role-dependent,
    v1.1 §4.3; defaults to NRC_RDIS_G0 if not given). cm: membrane capacitance (role-dependent,
    Q1-R §4; defaults to NM_CM). Returns dict of port node names."""
    vm, h = p + "vm", p + "h"
    if rdis is None:
        rdis = v("NRC_RDIS_G0")
    if cm is None:
        cm = v("NM_CM")
    nl.C(p + "cm", vm, "0", cm)
    nl.R(p + "rm", vm, "vrest", v("NM_RM"))
    if bias_k:
        # k explicit unit sink devices (M=1 each), not one M=k instance (Q1-R §2.4)
        for i in range(bias_k):
            nl.M(p + f"bias{i}", vm, "istep_n", "0", "0", "nch", v("BIAS_W"), v("BIAS_L"))
    # threshold with resistive positive feedback and explicit Ch (v1.1 §4.2, corrected 2026-10-08)
    # Comparator: NMOS m1 reads vm, m2 reads h; PMOS mirror loads; when vm > h, m1 current
    # increases, d1 falls, m4 pulls o1 up -> o1 RISES with vm−h (corrected polarity)
    W, L = v("NRC_CMP_W"), v("NRC_CMP_L")
    kp = p + "k"
    nl.R(kp + "b", "vdd", kp + "nb", v("NRC_CMP_RB"))
    nl.M(kp + "mb", kp + "nb", kp + "nb", "0", "0", "nch", 4e-6, L)
    nl.M(kp + "mt", kp + "tail", kp + "nb", "0", "0", "nch", 4e-6, L)
    nl.M(kp + "m1", kp + "d1", vm, kp + "tail", "0", "nch", W, L)
    nl.M(kp + "m2", kp + "o1", h, kp + "tail", "0", "nch", W, L)
    nl.M(kp + "m3", kp + "d1", kp + "d1", "vdd", WELL, "pch", 4e-6, L)
    nl.M(kp + "m4", kp + "o1", kp + "d1", "vdd", WELL, "pch", 4e-6, L)
    # Output inverters: o1 -> qb -> q (v1.1 §4.2 minimal chain)
    inverter(nl, kp + "i1", kp + "o1", p + "qb")         # qb = inv(o1)
    inverter(nl, kp + "i2", p + "qb", p + "q")           # q = inv(qb)
    # Resistive hysteresis (regenerative): h = (ref*Rf + qb*Ra)/(Ra+Rf); qb LOW during the pulse
    # pulls h DOWN, holding q high; exit comes from the real reset driving vm below the lowered h
    nl.R(p + "hra", h, thr_ref, v("NRC_HYS_RA"))
    nl.R(p + "hrf", h, p + "qb", v("NRC_HYS_RF"))
    nl.C(p + "hc", h, "0", v("NRC_H_C"))
    # membrane discharge: q high -> NMOS + Rdis series path to vrest (v1.1 §4.1, §4.3)
    nl.M(p + "dis", vm, p + "q", p + "vmd", "0", "nch", v("NRC_DIS_W"), v("NRC_DIS_L"))
    nl.R(p + "rdis", p + "vmd", "vrest", rdis)
    # recovery: q high -> PMOS + R_ch charges C_rec; shunt = two series NMOS (v1.1 §4.1)
    nl.M(p + "rp", p + "rt", p + "qb", "vdd", WELL, "pch", 2e-6, 1e-6)
    nl.R(p + "rrc", p + "rt", p + "rec", v("NRC_REC_RC"))
    nl.C(p + "rc", p + "rec", "0", v("NRC_REC_C"))
    nl.R(p + "rr", p + "rec", "0", v("NRC_REC_R"))
    # recovery shunt: rec AND qb (both gates must be high to conduct; q high -> qb low -> off)
    nl.M(p + "sh1", vm, p + "rec", p + "vms", "0", "nch", v("NRC_SH_W"), v("NRC_SH_L"))
    nl.M(p + "sh2", p + "vms", p + "qb", "vrest", "0", "nch", v("NRC_SH_W"), v("NRC_SH_L"))
    # POR shunt: por_hold high -> h to thr_ref, vm to vrest (prepare state)
    nl.M(p + "porh", h, "por_hold", thr_ref, "0", "nch", v("NRC_SH_W"), v("NRC_SH_L"))
    nl.M(p + "porm", vm, "por_hold", "vrest", "0", "nch", v("NRC_SH_W"), v("NRC_SH_L"))
    return {"vm": vm, "q": p + "q", "qb": p + "qb", "rec": p + "rec", "h": h}


def trace(nl, p, qb_drive, node, rc, c, rl):
    """RC activity trace charged through a PMOS switch while the driving pulse is high
    (v1.1: qb low during pulse, PMOS on; qb high after pulse, PMOS off). Returns the trace node."""
    nl.M(p + "sw", p + "t", qb_drive, "vdd", WELL, "pch", 2e-6, 1e-6)
    nl.R(p + "rc", p + "t", node, rc)
    nl.C(p + "c", node, "0", c)
    nl.R(p + "rl", node, "0", rl)
    return node


def pmos_out(nl, name, gate_diode, out, W=None, L=None, mult=1):
    """PMOS mirror output device sourcing from vdd (gate = an existing PMOS diode node)."""
    nl.M(name, out, gate_diode, "vdd", WELL, "pch", W or v("BIAS_W"), L or v("BIAS_L"),
         mult=mult)


def nmos_out(nl, name, gate_diode, out, W=None, L=None, mult=1):
    nl.M(name, out, gate_diode, "0", "0", "nch", W or v("BIAS_W"), L or v("BIAS_L"), mult=mult)
