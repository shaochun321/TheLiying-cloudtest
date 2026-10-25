"""THERMAL-G3-v1 unified physical mother N-P1 and shared references (construction time, INFRA).

TYPE:HYBRID (BIO role: spiking membrane with leak, threshold, refractory recovery; SEMI
realisation: EKV MOS + R/C only). Every function is a device branch:
  membrane   : C_m to ground, R_m to the real rest reference vrest
  threshold  : symmetric 5T comparator (R1 non-Schmitt) + 2 inverters; resistive positive
               feedback from the inverted output o2 onto the threshold node (hysteresis)
  set        : rising edge of the comparator output (RC delay + inverter + NAND2) -> Sbar
  latch      : NAND2 (Q = p) / NAND3 (Qb = pb, third input = POR release), cross-coupled
               through R_L C_L (state held on capacitors)
  timer      : PMOS(gate pb) charges R_d C_d while p is high, NMOS(gate pb) empties it while
               p is low; resistive-hysteresis buffer(timer) = Rbar ends the pulse
  discharge  : NMOS(gate p) from membrane to vrest during the pulse
  recovery   : PMOS(gate pb) charges C_rec during the pulse; R_rec leaks it; NMOS(gate rec)
               shunts the membrane to vrest until rec decays (relative refractory)
  power-up   : common supply ramp; POR RC + inverters give por_hold (shunts every membrane to
               vrest and fast-settles transduction means) and por_ok (latch NAND3 input)
No behavioural source performs reset, discharge or timing. The only B/E sources in the whole
netlist are the NTC device equation, its Joule heat, and the environment boundary.
"""
from .build import WELL, inverter, nand2
from .params import v


def nand3(nl, p, a, b, c, y):
    wn, wp, l = 3 * v("INV_WN"), v("INV_WP"), v("INV_L")
    for k, g in enumerate((a, b, c)):
        nl.M(p + f"p{k}", y, g, "vdd", WELL, "pch", wp, l)
    nl.M(p + "na", y, a, p + "x1", "0", "nch", wn, l)
    nl.M(p + "nb", p + "x1", b, p + "x2", "0", "nch", wn, l)
    nl.M(p + "nc", p + "x2", c, "0", "0", "nch", wn, l)


def buffer(nl, p, a, y):
    inverter(nl, p + "a", a, p + "n")
    inverter(nl, p + "b", p + "n", y)


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
    # POR: RC from the rail; por_hold = inv(porc) high until porc crosses the trip
    nl.R("porr", "vdd", "porc", v("POR_R"))
    nl.C("porc", "porc", "0", v("POR_C"))
    # regenerative release (dev-002: the slow RC edge drove every latch through a long
    # linear transition): porc -> Ra -> x ; x -> inv -> por_hold -> inv -> por_ok ;
    # por_ok -> Rf -> x  (resistive positive feedback, two plain inverters, no cross-rail)
    nl.R("porra", "porc", "porx", v("POR_RA"))
    nl.R("porrf", "por_ok", "porx", v("POR_RF"))
    inverter(nl, "pori1", "porx", "por_hold")
    inverter(nl, "pori2", "por_hold", "por_ok")
    # bias references: diode-connected devices fed by resistors (real currents, measured)
    W, L = v("BIAS_W"), v("BIAS_L")
    nl.R("iref", "vdd", "iref_n", v("IREF_R"))
    nl.M("irefd", "iref_n", "iref_n", "0", "0", "nch", W, L)          # NMOS I_ref diode
    nl.R("istep", "vdd", "istep_n", v("ISTEP_R"))
    nl.M("istepd", "istep_n", "istep_n", "0", "0", "nch", W, L)       # NMOS I_step diode
    # PMOS I_ref diode (sources): NMOS copy of I_ref pulls from a PMOS diode
    nl.M("irefm", "irefp_n", "iref_n", "0", "0", "nch", W, L)
    nl.M("irefpd", "irefp_n", "irefp_n", "vdd", WELL, "pch", W, L)


def np1(nl, p, thr_ref, bias_k=0):
    """One N-P1 instance. Inputs are attached by the caller as currents into p+'vm'.
    thr_ref: reference node of the threshold divider (vthe for G0 ensembles/collector,
    vthr for relation receivers). bias_k: number of unit I_step sink devices (ensemble
    graded recruitment, physical multiplicity). Returns dict of port node names."""
    vm, thr = p + "vm", p + "thr"
    nl.C(p + "cm", vm, "0", v("NM_CM"))
    nl.R(p + "rm", vm, "vrest", v("NM_RM"))
    if bias_k:
        nl.M(p + "bias", vm, "istep_n", "0", "0", "nch", v("BIAS_W"), v("BIAS_L"),
             mult=bias_k)
    # threshold with resistive positive feedback from the inverted comparator output
    W, L = v("NM_CMP_W"), v("NM_CMP_L")
    kp = p + "k"
    nl.R(kp + "b", "vdd", kp + "nb", v("NM_CMP_RB"))
    nl.M(kp + "mb", kp + "nb", kp + "nb", "0", "0", "nch", 4e-6, L)
    nl.M(kp + "mt", kp + "tail", kp + "nb", "0", "0", "nch", 4e-6, L)
    nl.M(kp + "m1", kp + "d1", vm, kp + "tail", "0", "nch", W, L)
    nl.M(kp + "m2", kp + "o1", thr, kp + "tail", "0", "nch", W, L)
    nl.M(kp + "m3", kp + "d1", kp + "d1", "vdd", WELL, "pch", 4e-6, L)
    nl.M(kp + "m4", kp + "o1", kp + "d1", "vdd", WELL, "pch", 4e-6, L)
    inverter(nl, kp + "i1", kp + "o1", kp + "o2")       # o2 low when vm > thr
    inverter(nl, kp + "i2", kp + "o2", p + "c")          # c high when vm > thr
    nl.R(p + "hra", thr, thr_ref, v("HYS_RA"))
    nl.R(p + "hrf", thr, kp + "o2", v("HYS_RF"))
    # rising-edge set pulse: Sbar = NAND(c, not(delayed c))
    nl.R(p + "er", p + "c", p + "ce", v("NM_EDGE_R"))
    nl.C(p + "ec", p + "ce", "0", v("NM_EDGE_C"))
    inverter(nl, p + "ei", p + "ce", p + "ned")
    nand2(nl, p + "es", p + "c", p + "ned", p + "sb")
    # latch (low-active Sbar / Rbar), POR release as third input of the Qb gate
    # cross-coupling through RC (dev-006..009: a purely algebraic NAND latch has two roots;
    # the solver jumped idle latches of both polarities to the other root in one large step).
    # The latch state is now held on C_L (tau = R_L C_L = 1 ms << set pulse 20 ms, pulse 0.23 s),
    # so one step cannot move it more than h*VDD/(R_L C_L); a real flip still completes in ~ms.
    nand2(nl, p + "lq", p + "sb", p + "pbf", p + "p")
    nand3(nl, p + "lqb", p + "rb", p + "pf", "por_ok", p + "pb")
    nl.R(p + "lrp", p + "p", p + "pf", v("NM_LAT_R"))
    nl.C(p + "lcp", p + "pf", "0", v("NM_LAT_C"))
    nl.R(p + "lrn", p + "pb", p + "pbf", v("NM_LAT_R"))
    nl.C(p + "lcn", p + "pbf", "0", v("NM_LAT_C"))
    for n in (p + "p", p + "pb", p + "sb"):
        nl.C(p + "cw" + n[len(p):], n, "0", v("C_WIRE"))
    # pulse timer
    nl.M(p + "tp", p + "tt", p + "pb", "vdd", WELL, "pch", 2e-6, 1e-6)
    nl.R(p + "tr", p + "tt", p + "td", v("NM_TD_R"))
    nl.C(p + "tc", p + "td", "0", v("NM_TD_C"))
    # timer empties through R_dis (dev-006: an unresistored NMOS emptied the timer in ns, the
    # reset pulse was shorter than the latch flip and the latch re-set metastably on a rail
    # disturbance -> spurious pulses with vm far below threshold). R_dis C_d ~ 2.5 ms holds
    # Rbar low until the latch has resolved; re-arm is still << the 0.82 s recovery.
    nl.M(p + "tn", p + "tdd", p + "pb", "0", "0", "nch", 2e-6, 1e-6)
    nl.R(p + "tdr", p + "td", p + "tdd", v("NM_TD_RDIS"))
    # regenerative reset (dev-005: a plain inverter on td closed a negative loop through
    # pb -> timer, the latch parked at pb = 0.74 V / rb = 1.27 V): td -> Ra -> tx ;
    # tx -> inv -> rb -> inv -> rbq ; rbq -> Rf -> tx  (positive feedback, snap + hold)
    nl.R(p + "tra", p + "td", p + "tx", v("NM_TRA"))
    nl.R(p + "trf", p + "rbq", p + "tx", v("NM_TRF"))
    inverter(nl, p + "ti", p + "tx", p + "rb")
    inverter(nl, p + "tq", p + "rb", p + "rbq")
    # membrane discharge during the pulse, recovery shunt afterwards, POR shunt
    nl.M(p + "dis", vm, p + "p", "vrest", "0", "nch", v("NM_DIS_W"), v("NM_DIS_L"))
    nl.M(p + "rp", p + "rt", p + "pb", "vdd", WELL, "pch", 2e-6, 1e-6)
    nl.R(p + "rrc", p + "rt", p + "rec", v("NM_REC_RC"))
    nl.C(p + "rc", p + "rec", "0", v("NM_REC_C"))
    nl.R(p + "rr", p + "rec", "0", v("NM_REC_R"))
    nl.M(p + "sh", vm, p + "rec", "vrest", "0", "nch", v("NM_SH_W"), v("NM_SH_L"))
    nl.M(p + "por", vm, "por_hold", "vrest", "0", "nch", v("NM_SH_W"), v("NM_SH_L"))
    return {"vm": vm, "p": p + "p", "pb": p + "pb", "rec": p + "rec", "c": p + "c"}


def trace(nl, p, pb_drive, node, rc, c, rl):
    """RC activity trace charged through a PMOS switch while the driving pulse is high."""
    nl.M(p + "sw", p + "t", pb_drive, "vdd", WELL, "pch", 2e-6, 1e-6)
    nl.R(p + "rc", p + "t", node, rc)
    nl.C(p + "c", node, "0", c)
    nl.R(p + "rl", node, "0", rl)


def pmos_out(nl, name, gate_diode, out, W=None, L=None, mult=1):
    """PMOS mirror output device sourcing from vdd (gate = an existing PMOS diode node)."""
    nl.M(name, out, gate_diode, "vdd", WELL, "pch", W or v("BIAS_W"), L or v("BIAS_L"),
         mult=mult)


def nmos_out(nl, name, gate_diode, out, W=None, L=None, mult=1):
    nl.M(name, out, gate_diode, "0", "0", "nch", W or v("BIAS_W"), L or v("BIAS_L"), mult=mult)
