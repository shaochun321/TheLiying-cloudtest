"""THERMAL-G3-v1 top-level netlist (construction time, INFRA).

Per site (1..4): environment boundary -> bidirectional thermal net -> NTC divider s
  -> mean m (RC 2 s; POR switch equalises m to s while por_hold)
  -> R2/R3 resistively loaded NMOS preamp (da, db)
  -> transduction pair (tail = 1.2 I_ref limit) with PMOS diode loads A (warm side), B
  -> per ensemble k: PMOS copy of A + NMOS copy of B  (warm: I_A - I_B, cool: I_B - I_A)
Per site and polarity: 10 N-P1 ensembles (bias k * I_step) -> bundle traces -> AND2 tree
  -> limited input (PMOS copy of the 1.2 I_ref diode, gated) -> N-P1 collector
  -> occurrence port (a0, p0).
Per polarity: Theta (3 pairs x 2 dir), Sigma_flow (3 edges x 2 dir), Cdir (3 edges x 2 dir),
each an N-P1 receiver (threshold vthr) + occurrence port; Cdir also has the conflict shunt.
Cdir N2 port currents -> fixed 1:1 aggregation per sign -> two real RC rails to vmid.

Construction-time options (fixed netlist variants, never switched during a solve):
  sites, polarities, layers ('g0' | 'theta' | 'sigma' | 'cdir' | 'load'), cut_edges,
  theta_port_cut, sigma_port_cut, sigma_readout_swap (real wiring swap), bleed (fixture).
"""
import math

from .build import Netlist, WELL, inverter, history, relation_stack
from .neuron_mother import np1 as np1_legacy  # dev-001~010, deprecated
from .neuron_nrc import (nrc, supply_ramp, references, pmos_out, nmos_out, trace)
from .bundle_physical import and_tree, gated_source
from .occurrence_port import occurrence_port
from .spatial_graph import spatial_graph
from .params import v

POLS = ("w", "c")
N_ENS = 10


# ------------------------------------------------------------------ environment
def env_expr(segments, t0):
    """segments: list of (t_on, t_off, amp_K). Smooth ramps (0.2 s logistic) -> boundary.
    Pure function of time; it does not read any circuit node."""
    if not segments:
        return f"{t0:.9g}"
    terms = []
    for ton, toff, a in segments:
        terms.append(f"{a:.6g}*(1/(1+exp(-(time-{ton:.6g})/0.05))-1/(1+exp(-(time-{toff:.6g})/0.05)))")
    return f"({t0:.9g}+" + "+".join(terms) + ")"


def sensor(nl, p, te_expr):
    """R3 bidirectional thermal network + NTC (device equation) + 100 kohm pull-down."""
    tag = p.rstrip("_")
    nl.BV(p + "te", p + "te", "0", te_expr, dom="therm")
    nl.V("qe" + tag, p + "te", p + "tea", "DC 0", dom="therm")
    nl.R(p + "ge", p + "tea", p + "tp", 1.0 / v("TH_GE"), dom="therm")
    nl.C(p + "cp", p + "tp", "0", v("TH_CP"), dom="therm")
    nl.R(p + "gm", p + "tp", p + "tn", 1.0 / v("TH_GM"), dom="therm")
    nl.C(p + "cn", p + "tn", "0", v("TH_CN"), dom="therm")
    r25, bb = v("NTC_R25"), v("NTC_B")
    rexpr = f"({r25:.9g}*exp({bb:.9g}*(1/(298.15+V({p}tn))-1/298.15)))"
    nl.B(p + "ntc", "vdd", p + "s", f"V(vdd,{p}s)/{rexpr}")
    nl.B(p + "heat", "0", p + "th", f"V(vdd,{p}s)*V(vdd,{p}s)/{rexpr}", dom="therm")
    nl.V("qh" + tag, p + "th", p + "tn", "DC 0", dom="therm")
    nl.R(p + "rs", p + "s", "0", v("R_S"))


def transduction(nl, p, s):
    """mean, preamp, limited differential pair; returns (A pmos diode, B pmos diode,
    NA nmos diode, NB nmos diode) for ensemble current copies."""
    m = p + "m"
    nl.R(p + "ravg", s, m, v("TR_RAVG"))
    nl.C(p + "cavg", m, "0", v("TR_CAVG"))
    nl.M(p + "mpor", m, "por_ok", s, WELL, "pch", v("TR_POR_W"), 1e-6)
    # R2/R3 preamp (resistive loads): da falls when s rises
    nl.R(p + "ab", "vdd", p + "anb", v("PRE_RB"))
    nl.M(p + "amb", p + "anb", p + "anb", "0", "0", "nch", 4e-6, 4e-6)
    nl.M(p + "amt", p + "atl", p + "anb", "0", "0", "nch", 4e-6, 4e-6)
    nl.M(p + "am1", p + "da", s, p + "atl", "0", "nch", v("PRE_W"), v("PRE_L"))
    nl.M(p + "am2", p + "db", m, p + "atl", "0", "nch", v("PRE_W"), v("PRE_L"))
    nl.R(p + "ara", "vdd", p + "da", v("PRE_RD"))
    nl.R(p + "arb", "vdd", p + "db", v("PRE_RD"))
    # limited pair: A branch gate db (I_A grows when s > m), B branch gate da.
    # Node names are case-insensitive in the netlist: diode nodes are ya/yb/za/zb so they
    # cannot alias the preamp outputs da/db (dev-003 aliasing bug: dA == da).
    W, L = v("TR_W"), v("TR_L")
    nl.M(p + "tt", p + "tl", "ilim_n", "0", "0", "nch", v("BIAS_W"), v("BIAS_L"))
    nl.M(p + "ta", p + "ya", p + "db", p + "tl", "0", "nch", W, L)
    nl.M(p + "tb", p + "yb", p + "da", p + "tl", "0", "nch", W, L)
    nl.M(p + "la", p + "ya", p + "ya", "vdd", WELL, "pch", v("BIAS_W"), v("BIAS_L"))
    nl.M(p + "lb", p + "yb", p + "yb", "vdd", WELL, "pch", v("BIAS_W"), v("BIAS_L"))
    # NMOS diodes carrying copies of I_A and I_B (for sink copies)
    pmos_out(nl, p + "ca", p + "ya", p + "za")
    nl.M(p + "na", p + "za", p + "za", "0", "0", "nch", v("BIAS_W"), v("BIAS_L"))
    pmos_out(nl, p + "cb", p + "yb", p + "zb")
    nl.M(p + "nb", p + "zb", p + "zb", "0", "0", "nch", v("BIAS_W"), v("BIAS_L"))
    return p + "ya", p + "yb", p + "za", p + "zb"


def g0(nl, p, src_p, sink_n, neuron_variant="nrc", cut_k=None):
    """Ten ensembles + bundle traces + AND2 tree + limited input + collector + port.
    neuron_variant: 'nrc' (v1.1 N-RC) | 'legacy' (dev-001~010 N-P1).
    cut_k: physical CUT of ensemble k's shaped trace from its AND input (construction time):
    the trace keeps its own shaping inverters plus a dummy gate load equal to the AND input,
    and the AND input is tied to ground (open path, finite load kept on both sides)."""
    if neuron_variant == "legacy":
        neuron_fn = np1_legacy
        pulse_port = "pb"  # pb low during pulse
    else:
        neuron_fn = lambda nl, p, thr, bias_k: nrc(nl, p, thr, bias_k, rdis=v("NRC_RDIS_G0"))
        pulse_port = "qb"  # qb low during pulse (v1.1)
    shaped = []
    for k in range(1, N_ENS + 1):
        e = f"{p}e{k}_"
        pt = neuron_fn(nl, e, "vthe", bias_k=k)
        pmos_out(nl, e + "ip", src_p, pt["vm"])
        nmos_out(nl, e + "in", sink_n, pt["vm"])
        tr_node = trace(nl, f"{p}b{k}_", pt[pulse_port], f"{p}b{k}", v("BT_RC"), v("BT_C"), v("BT_RL"))
        # 2-inverter buffer shapes the trace into a logic level
        inverter(nl, f"{p}b{k}_sh1", tr_node, f"{p}b{k}_n")
        inverter(nl, f"{p}b{k}_sh2", f"{p}b{k}_n", f"{p}b{k}_q")
        if cut_k == k:
            # dummy load = one NAND2 input pair (PMOS + NMOS gate) on the cut trace
            nl.M(f"{p}b{k}_cutp", "vdd", f"{p}b{k}_q", "vdd", WELL, "pch", v("INV_WP"), v("INV_L"))
            nl.M(f"{p}b{k}_cutn", "0", f"{p}b{k}_q", "0", "0", "nch", 2 * v("INV_WN"), v("INV_L"))
            shaped.append("0")
            continue
        shaped.append(f"{p}b{k}_q")
    gate = and_tree(nl, p + "and_", shaped)
    inverter(nl, p + "gi", gate, p + "gb")
    col = neuron_fn(nl, p + "col_", "vthe", bias_k=0)
    gated_source(nl, p + "cin_", "ilimp_n", col["vm"], p + "gb", W=v("BIAS_W"), reference_bias_n="ilim_n")
    port = occurrence_port(nl, p + "op_", col[pulse_port])
    # Merge collector ports: occurrence_port returns {a, ab, p, pb, trace}; add the variant-specific pulse key
    port[pulse_port] = col[pulse_port]
    return port


def receiver(nl, p, neuron_variant="nrc", role="sigma"):
    """Relation receiver (threshold vthr) + its occurrence port.
    neuron_variant: 'nrc' (v1.1 N-RC) | 'legacy' (dev-001~010 N-P1).
    role: 'sigma' (Σ spatial flow, Rdis 75k + Cm 100nF) | 'theta_cdir' (Θ/Cdir history-driven,
    Rdis 12k + Cm 1.5µF, Q1-R §4 one-time candidate)."""
    if neuron_variant == "legacy":
        pt = np1_legacy(nl, p, "vthr")
        pulse_port = "pb"
    else:
        if role == "theta_cdir":
            rdis, cm = v("NRC_RDIS_THETA_CDIR"), v("NM_CM_THETA_CDIR")
        else:
            rdis, cm = v("NRC_RDIS_RCV"), v("NM_CM")
        pt = nrc(nl, p, "vthr", bias_k=0, rdis=rdis, cm=cm)
        pulse_port = "qb"
    port = occurrence_port(nl, p + "op_", pt[pulse_port])
    port["vm"] = pt["vm"]
    return port


def rel_mirror(nl, p, mir_in, out):
    """PMOS diode (load of a relation stack) + scaled copy into a receiver membrane."""
    nl.M(p + "md", mir_in, mir_in, "vdd", WELL, "pch", v("MIR_W"), v("MIR_L"))
    nl.M(p + "mo", out, mir_in, "vdd", WELL, "pch", v("RM_OUT_W"), v("RM_OUT_L"))


def ota5n(nl, p, inp, inn, out):
    """NMOS-input 5T OTA (R2/R3 ota5 topology): current into `out` grows with
    V(inp) - V(inn). NMOS input keeps headroom at 2.7 V with inputs near vmid."""
    W, L = v("SP_W"), v("SP_L")
    nl.R(p + "b", "vdd", p + "nb", v("SP_RB"))
    nl.M(p + "mb", p + "nb", p + "nb", "0", "0", "nch", 4e-6, 4e-6)
    nl.M(p + "mt", p + "tail", p + "nb", "0", "0", "nch", 4e-6, 4e-6)
    nl.M(p + "m1", p + "d1", inp, p + "tail", "0", "nch", W, L)
    nl.M(p + "m2", out, inn, p + "tail", "0", "nch", W, L)
    nl.M(p + "m3", p + "d1", p + "d1", "vdd", WELL, "pch", W, L)
    nl.M(p + "m4", out, p + "d1", "vdd", WELL, "pch", W, L)


def build(env, vdd=None, sites=(1, 2, 3, 4), pols=POLS, layers=("g0", "theta", "sigma", "cdir", "load"),
          cut_edges=(), theta_port_cut=(), sigma_port_cut=(), sigma_readout_swap=False,
          bleed=None, instrument=False, extra_lines=(), neuron_variant="nrc",
          g0_sites=None, g0_cut=None, dc_supply=False, mirror_sites=False):
    """env: {site: [(t_on, t_off, amp_K), ...]} environment segments (same T0 background).
    neuron_variant: 'nrc' (v1.1 N-RC, default) | 'legacy' (dev-001~010 N-P1).
    Construction-time variants (Q1-R matrix):
      g0_sites    sites whose G0 ensembles are built (default: all `sites`); the spatial graph
                  keeps all four nodes, sites without G0 inject nothing (their switch gate at vdd)
      g0_cut      (pol, site, k): physical CUT of ensemble k's trace -> AND input
      dc_supply   constant DC source instead of the power-up ramp (static op cases)
      mirror_sites  real 1<->4, 2<->3 wiring of the sensor/transduction fronts to the G0 sites
    Port CUTs keep the consumer: the consumer gate is held at its off level and the source
    output keeps an equal dummy gate load."""
    nl = Netlist(instrument=instrument)
    vdd = v("VDD") if vdd is None else vdd
    if dc_supply:
        nl.V("src", "vsrc", "0", f"DC {vdd}")
        nl.R("int", "vsrc", "vdd", v("R_INT"))
        nl.C("dec", "vdd", "0", v("C_DEC"))
    else:
        supply_ramp(nl, vdd)
    references(nl)
    # 1.2 I_ref limit diodes (NMOS tail reference and PMOS copy for limited inputs)
    W, L = v("BIAS_W"), v("BIAS_L")
    nl.R("ilim", "vdd", "ilim_n", v("ILIM_R"))
    nl.M("ilimd", "ilim_n", "ilim_n", "0", "0", "nch", W, L)
    nl.M("ilimm", "ilimp_n", "ilim_n", "0", "0", "nch", W, L)
    nl.M("ilimpd", "ilimp_n", "ilimp_n", "vdd", WELL, "pch", W, L)
    T0 = v("T_BG_K")
    pulse_port = "pb" if neuron_variant == "legacy" else "qb"
    G = {}
    g0_sites = tuple(sites) if g0_sites is None else tuple(g0_sites)
    MIRROR = {1: 4, 2: 3, 3: 2, 4: 1}
    fronts = {}
    for s in sites:
        sp = f"s{s}_"
        sensor(nl, sp, env_expr(env.get(s, []), T0))
        fronts[s] = transduction(nl, sp, sp + "s")
    for s in sites:
        if "g0" not in layers or s not in g0_sites:
            continue
        # mirror_sites: the G0 of site s is wired to the front of its mirror site (real wiring)
        dA, dB, nA, nB = fronts[MIRROR[s]] if mirror_sites else fronts[s]
        for pol in pols:
            src, snk = (dA, nB) if pol == "w" else (dB, nA)
            ck = g0_cut[2] if g0_cut and (g0_cut[0], g0_cut[1]) == (pol, s) else None
            G[(pol, s)] = g0(nl, f"g{pol}{s}_", src, snk, neuron_variant=neuron_variant, cut_k=ck)
    pairs = [(i, j) for i, j in zip(sites[:-1], sites[1:]) if i in g0_sites and j in g0_sites]
    TH, SG = {}, {}
    for pol in pols:
        if "theta" in layers:
            for i, j in pairs:
                hi, hj = f"h{pol}{i}", f"h{pol}{j}"
                for node, src in ((hi, i), (hj, j)):
                    if node not in nl.domain:
                        history(nl, f"hs{pol}{src}_", G[(pol, src)][pulse_port], node)
                for a, b, d in ((i, j, "f"), (j, i, "r")):
                    rp = f"th{pol}{i}{j}{d}_"
                    relation_stack(nl, rp + "st_", f"h{pol}{a}", G[(pol, b)]["a"], rp + "mi")
                    rc = receiver(nl, rp, neuron_variant=neuron_variant, role="theta_cdir")
                    rel_mirror(nl, rp + "rm_", rp + "mi", rc["vm"])
                    TH[(pol, i, j, d)] = rc
        if "sigma" in layers:
            # sites without a G0 keep their node and injection device, switch held off (gate vdd)
            act_b = {s: (G[(pol, s)]["ab"] if (pol, s) in G else "vdd") for s in sites}
            nodes, edges = spatial_graph(nl, pol, list(sites), act_b,
                                         cut_edges=[e for (pp, e) in cut_edges if pp == pol])
            for e, (ni, se) in edges.items():
                i, j = int(e[0]), int(e[1])
                if (i, j) not in pairs:
                    continue
                for d in ("f", "r"):
                    rp = f"sg{pol}{e}{d}_"
                    rc = receiver(nl, rp, neuron_variant=neuron_variant, role="sigma")
                    fwd = (d == "f") != sigma_readout_swap
                    a, b = (ni, se) if fwd else (se, ni)
                    ota5n(nl, rp + "ota_", a, b, rc["vm"])
                    SG[(pol, i, j, d)] = rc
        if "cdir" in layers:
            for i, j in pairs:
                for d, dn in (("f", "r"), ("r", "f")):
                    rp = f"cd{pol}{i}{j}{d}_"
                    th = TH[(pol, i, j, d)]
                    sg, sg_conf = SG[(pol, i, j, d)], SG[(pol, i, j, dn)]
                    hs, hc = rp + "hs", rp + "hc"
                    sig_q = sg["ab"] if (pol, i, j, d) not in sigma_port_cut else "vdd"
                    sig_qc = sg_conf["ab"] if (pol, i, j, dn) not in sigma_port_cut else "vdd"
                    th_q = th["a"] if (pol, i, j, d) not in theta_port_cut else "0"
                    # port CUT: the source output keeps an equal dummy gate load
                    if (pol, i, j, d) in sigma_port_cut:
                        nl.M(rp + "cutsg", "vdd", sg["ab"], "vdd", WELL, "pch", 4e-6, 0.5e-6)
                    if (pol, i, j, dn) in sigma_port_cut:
                        nl.M(rp + "cutsgc", "vdd", sg_conf["ab"], "vdd", WELL, "pch", 4e-6, 0.5e-6)
                    if (pol, i, j, d) in theta_port_cut:
                        for k in range(2):
                            nl.M(rp + f"cutth{k}", "0", th["a"], "0", "0", "nch", v("REL_WP"), v("REL_LP"))
                    history(nl, rp + "hsf_", sig_q, hs)       # history of matching Sigma
                    history(nl, rp + "hcf_", sig_qc, hc)      # history of conflicting Sigma
                    rc = receiver(nl, rp, neuron_variant=neuron_variant, role="theta_cdir")
                    relation_stack(nl, rp + "st_", hs, th_q, rp + "mi")
                    rel_mirror(nl, rp + "rm_", rp + "mi", rc["vm"])
                    # conflict: H(Sigma opposite) over q(Theta) shunts the membrane to vrest
                    nl.M(rp + "kh", rc["vm"], hc, rp + "kx", "0", "nch", v("REL_WH"), v("REL_LH"))
                    nl.M(rp + "kp", rp + "kx", th_q, "vrest", "0", "nch", v("REL_WP"), v("REL_LP"))
                    if bleed and (pol, i, j, d) == bleed["which"]:
                        # local history bleed fixture: real NMOS discharging hs, gate driven by
                        # an external fixed-time PWL (protocol fixed before the run)
                        nl.V("bleedg", "bleedg", "0", bleed["pwl"])
                        nl.M(rp + "bl", hs, "bleedg", "0", "0", "nch", 4e-6, 1e-6)
                    TH[(pol, i, j, d, "cdir")] = rc
    if "load" in layers and "cdir" in layers:
        for sign, d in (("pos", "f"), ("neg", "r")):
            out = f"load_{sign}"
            nl.C("ld" + sign, out, "vmid", v("LOAD_C"))
            nl.R("ld" + sign, out, "vmid", v("LOAD_R"))
            for pol in pols:
                for i, j in pairs:
                    rc = TH[(pol, i, j, d, "cdir")]
                    gated_source(nl, f"ag{pol}{i}{j}{d}_", "irefp_n", out, rc["ab"],
                                 W=v("BIAS_W"), reference_bias_n="iref_n")
    # element-name collision guard (ngspice is case-insensitive; duplicates would merge)
    names = [l.split()[0].lower() for l in nl.lines if l and not l.startswith(".")]
    dup = {n for n in names if names.count(n) > 1} if len(names) != len(set(names)) else set()
    assert not dup, f"duplicate element names: {sorted(dup)[:5]}"
    # registered parasitic C_NODE on every electrical node (construction time, uniform)
    for n in sorted(n for n, d in list(nl.domain.items()) if d == "elec" and n != "vsrc"):
        nl.C(f"par_{n}", n, "0", v("C_NODE"))   # named by node: variants differ only where declared
    nl.lines.extend(extra_lines)
    return nl, {"G": G, "TH": TH, "SG": SG}


def census(nl):
    c = {}
    for _n, kind, _t, ex in nl.elements:
        c[kind] = c.get(kind, 0) + 1
    c["M_unit"] = int(sum(e[3]["mult"] for e in nl.elements if e[1] == "M"))
    c["N-P1"] = sum(1 for e in nl.elements if e[1] == "C" and e[0].endswith("cm"))
    return c
