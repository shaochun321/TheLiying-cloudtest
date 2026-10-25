"""Q1-R mother-qualification bench (construction time, INFRA).

Three N-RC role representatives share the real supply ramp, POR, references and bias diodes:
  G0         collector-role N-RC (vthe, Rdis NRC_RDIS_G0, Cm NM_CM)
  Sigma      Σ receiver (vthr, Rdis NRC_RDIS_RCV, Cm NM_CM)
  Theta_Cdir Θ/Cdir receiver (vthr, Rdis NRC_RDIS_THETA_CDIR, Cm NM_CM_THETA_CDIR)
Role parameters are passed to nrc() directly (no text substitution).

Inputs are the ACTUAL branch types, each behind a 0 V ammeter whose current is saved:
  G0         three gated PMOS copies: weak irefp 1.2/4 um, valid irefp 4/4 um, max ilimp 4/4 um
             (the max branch is the collector's real limited input)
  Sigma      the real ota5n reading two stimulus nodes; the stimulus levels are the 4-node graph
             drops of the certificate (idle / reverse event / forward event / fully steered)
  Theta_Cdir the real relation_stack + rel_mirror; stack gates driven by stimulus sources
             (history level: one source pulse / chain entry level / continuous bound; pulse
             gate high only inside the role's active segments)
Stimulus sources are frozen PWLs with finite edges and plateaus; they read no circuit node.

Outputs use the real occurrence_port(), loaded by the same consumer gate types and the maximum
fan-out each role has in build_thermal_g3 (history switch PMOS 4/0.5, stack/conflict NMOS 4/1,
gated-source switch PMOS 4/1). Load devices are declared gate loads (drain/source/bulk tied).
C_NODE is added on every electrical node as in build_thermal_g3.build().
"""
import json
import os

from .build import Netlist, WELL
from .build_thermal_g3 import ota5n, rel_mirror
from .build import relation_stack
from .bundle_physical import gated_source
from .neuron_nrc import nrc, references, supply_ramp
from .occurrence_port import occurrence_port
from .params import v

Q1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = {"G0": "g0_", "Sigma": "sg_", "Theta_Cdir": "tc_"}
ACTIVE = ("weak", "valid", "max", "reinput")


def pwl_levels(plan_role, levels, base, edge):
    """Piecewise-constant stimulus: `levels[label]` inside segments, `base` elsewhere."""
    pts = [(0.0, base)]
    for s in plan_role:
        lab = s.get("label")
        if lab in levels:
            a, b, y = s["t_start_s"], s["t_end_s"], levels[lab]
            pts += [(a, base), (a + edge, y), (b, y), (b + edge, base)]
    return "PWL(" + " ".join(f"{t:.6g} {x:.6g}" for t, x in pts) + ")"


def gate_load_pmos(nl, name, gate, W, L):
    nl.M(name, "vdd", gate, "vdd", WELL, "pch", W, L)


def gate_load_nmos(nl, name, gate, W, L):
    nl.M(name, "0", gate, "0", "0", "nch", W, L)


def ammeter(nl, name, branch_out, node):
    """0 V source: i(v<name>) is the branch current into `node`."""
    nl.V(name, branch_out, node, "DC 0")
    return f"i(v{name})"


def build_bench(protocol=None, cert=None, vdd=None, instrument=False):
    """Returns (Netlist, meta). meta: role prefixes, saved vectors, stimulus levels, protocol."""
    protocol = protocol or json.load(open(os.path.join(Q1, "prereg", "protocol_q1r_joint.json"), encoding="utf-8"))
    cert = cert or json.load(open(os.path.join(Q1, "analysis", "input_bounds.json"), encoding="utf-8"))
    vdd = v("VDD") if vdd is None else vdd
    edge = protocol["edge_s"]
    plan = protocol["roles"]
    nom = cert["nom"]
    nl = Netlist(instrument=instrument)
    supply_ramp(nl, vdd)
    references(nl)
    W, L = v("BIAS_W"), v("BIAS_L")
    nl.R("ilim", "vdd", "ilim_n", v("ILIM_R"))
    nl.M("ilimd", "ilim_n", "ilim_n", "0", "0", "nch", W, L)
    nl.M("ilimm", "ilimp_n", "ilim_n", "0", "0", "nch", W, L)
    nl.M("ilimpd", "ilimp_n", "ilimp_n", "vdd", WELL, "pch", W, L)
    save = ["v(vdd)", "v(vrest)", "v(vthe)", "v(vthr)", "v(vmid)", "v(por_ok)"]
    meta = {"prefix": PREFIX, "ammeters": {}, "stimulus": {}}

    # ---------------- G0 (collector role)
    p = PREFIX["G0"]
    g0 = nrc(nl, p, "vthe", bias_k=0, rdis=v("NRC_RDIS_G0"), cm=v("NM_CM"))
    am = {}
    for lab, diode, bias_n, Wc, Lc in (("weak", "irefp_n", "iref_n", 1.2e-6, 4e-6), ("valid", "irefp_n", "iref_n", 4e-6, 4e-6),
                               ("max", "ilimp_n", "ilim_n", 4e-6, 4e-6)):
        labs = {lab} if lab != "valid" else {"valid", "reinput"}
        nl.V(f"{p}g{lab}", f"{p}g{lab}", "0", pwl_levels(plan["G0"], {k: 0.0 for k in labs}, vdd, edge))
        gated_source(nl, f"{p}i{lab}_", diode, f"{p}o{lab}", f"{p}g{lab}", W=Wc, L=Lc, reference_bias_n=bias_n)
        am[lab] = ammeter(nl, f"{p}a{lab}", f"{p}o{lab}", g0["vm"])
        save.append(f"v({p}g{lab})")
    meta["ammeters"]["G0"] = am
    port = occurrence_port(nl, p + "op_", g0["qb"])
    gate_load_pmos(nl, p + "ld_hsw", g0["qb"], 4e-6, 0.5e-6)          # source history switch
    for k in range(2):                                                 # target stack pulse gates
        gate_load_nmos(nl, f"{p}ld_mp{k}", port["a"], v("REL_WP"), v("REL_LP"))
    gate_load_pmos(nl, p + "ld_inj", port["ab"], 4e-6, 1e-6)           # spatial injection switch
    meta["G0"] = {**g0, **{f"op_{k}": x for k, x in port.items()}}

    # ---------------- Sigma receiver
    p = PREFIX["Sigma"]
    sg = nrc(nl, p, "vthr", bias_k=0, rdis=v("NRC_RDIS_RCV"), cm=v("NM_CM"))
    gr = nom["roles"]["Sigma"]["inputs_graph"]
    lv_inp = {"weak": gr["reverse"][0], "valid": gr["single"][0], "reinput": gr["single"][0],
              "max": gr["vmid"] + 0.3}
    lv_inn = {"weak": gr["reverse"][1], "valid": gr["single"][1], "reinput": gr["single"][1],
              "max": gr["vmid"] - 0.3}
    nl.V(p + "sp", p + "sp", "0", pwl_levels(plan["Sigma"], lv_inp, gr["idle"][0], edge))
    nl.V(p + "sn", p + "sn", "0", pwl_levels(plan["Sigma"], lv_inn, gr["idle"][1], edge))
    ota5n(nl, p + "ota_", p + "sp", p + "sn", p + "oo")
    meta["ammeters"]["Sigma"] = {"ota": ammeter(nl, p + "aota", p + "oo", sg["vm"])}
    save += [f"v({p}sp)", f"v({p}sn)"]
    port = occurrence_port(nl, p + "op_", sg["qb"])
    for k in range(2):                                                 # matching + conflict history
        gate_load_pmos(nl, f"{p}ld_hsw{k}", port["ab"], 4e-6, 0.5e-6)
    meta["Sigma"] = {**sg, **{f"op_{k}": x for k, x in port.items()}}
    meta["stimulus"]["Sigma"] = {"inp": lv_inp, "inn": lv_inn, "idle": gr["idle"]}

    # ---------------- Theta / Cdir receiver
    p = PREFIX["Theta_Cdir"]
    tc = nrc(nl, p, "vthr", bias_k=0, rdis=v("NRC_RDIS_THETA_CDIR"), cm=v("NM_CM_THETA_CDIR"))
    hl = nom["history_levels_V"]
    h_bound = nom["roles"]["Theta_Cdir"]["inputs_h_bound_V"]
    lv_h = {"weak": hl["single_pulse"], "valid": hl["valid_entry_min"], "reinput": hl["valid_entry_min"],
            "max": h_bound}
    nl.V(p + "hs", p + "hs", "0", pwl_levels(plan["Theta_Cdir"], lv_h, 0.0, edge))
    nl.V(p + "pg", p + "pg", "0", pwl_levels(plan["Theta_Cdir"], {k: vdd for k in ACTIVE}, 0.0, edge))
    relation_stack(nl, p + "st_", p + "hs", p + "pg", p + "mi")
    rel_mirror(nl, p + "rm_", p + "mi", p + "oo")
    meta["ammeters"]["Theta_Cdir"] = {"rel": ammeter(nl, p + "arel", p + "oo", tc["vm"])}
    save += [f"v({p}hs)", f"v({p}pg)"]
    port = occurrence_port(nl, p + "op_", tc["qb"])
    for k in range(2):                                                 # Cdir stack + conflict gates
        gate_load_nmos(nl, f"{p}ld_mp{k}", port["a"], v("REL_WP"), v("REL_LP"))
    gate_load_pmos(nl, p + "ld_out", port["ab"], 4e-6, 1e-6)           # load gated-source switch
    meta["Theta_Cdir"] = {**tc, **{f"op_{k}": x for k, x in port.items()}}
    meta["stimulus"]["Theta_Cdir"] = {"h": lv_h}

    # ---------------- saved vectors per role
    for role in ("G0", "Sigma", "Theta_Cdir"):
        pr = PREFIX[role]
        save += [f"v({pr}{n})" for n in ("vm", "h", "q", "qb", "rec", "vmd")]
        save += [f"v({pr}op_{n})" for n in ("at", "aq", "aqb", "p", "pb")]
        save += list(meta["ammeters"][role].values())
    # registered parasitic C_NODE on every electrical node (as build_thermal_g3.build)
    names = [l.split()[0].lower() for l in nl.lines if l and not l.startswith(".")]
    assert len(names) == len(set(names)), "duplicate element names"
    for n in sorted(n for n, d in list(nl.domain.items()) if d == "elec" and n != "vsrc"):
        nl.C(f"par_{n}", n, "0", v("C_NODE"))   # named by node: variants differ only where declared
    meta["save"] = save
    meta["protocol_total_s"] = protocol["total_s"]
    return nl, meta
