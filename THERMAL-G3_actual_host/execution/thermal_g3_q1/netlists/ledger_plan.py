"""Q1-R ledger probe plan (construction time, INFRA).

Each case instruments a fixed set of LEDGER NODES: every element terminal attached to one of
these nodes sits behind a 0 V ammeter (netlists/build.py, instrument={"nodes": ...}), so KCL at
these nodes is complete with solver currents, including MOS gate / displacement currents and
the parasitic C_NODE. Nodes:
  mother bench          vm, vmd, vms of each of the three roles
  G0 cases / NUM_G0     collector vm, vmd, vms of the stimulated site
  CHAIN family          Θ / Σ / Cdir (f and r) vm, vmd, vms of the case's pair and polarity, and
                        the two load rails (per-path aggregation currents); STRUCTURE / INVALID /
                        NUM_CHAIN use pair 12 warm (their baseline's set)
  FULL                  the two load rails (aggregation sources + LOAD R/C) and the vm node of
                        every relation core (Θ / Σ / Cdir, f and r, both polarities, 3 edges:
                        36 nodes; complete terminal set, so the relation-support charge account
                        uses measured currents only), plus the targeted terminal probes on the
                        relation injectors (Θ / Cdir rm_mo drain, Σ OTA m2 / m4 drains, Cdir kh
                        drain) kept as measurement-only cross-references (review 2026-10-17 §4.1)
  DC                    none (the op point saves every node and source current)
Scope (registered): KCL, charge, node-port energy and capacitor energy at these nodes; supply
energy from i(vsrc); model domain for MOS with all four terminal voltages saved. A full-network
energy closure is NOT claimed.
"""
import numpy as np


def role_nodes(prefix):
    return [prefix + n for n in ("vm", "vmd", "vms")]


def ledger_nodes(case):
    cid, grp = case["case_id"], case["group"]
    if case["builder"] == "bench_mother":
        return sum((role_nodes(p) for p in ("g0_", "sg_", "tc_")), [])
    a = case.get("build_args", {})
    if grp == "G0" or cid == "NUM_G0_HALFSTEP":
        pol = a.get("pols", ["w"])[0]
        return role_nodes(f"g{pol}1_col_")
    if grp in ("CHAIN", "STRUCTURE") or cid == "NUM_CHAIN_HALFSTEP":
        j = case["judge"]
        pol, (i, k) = j["pol"], j["pair"]
        out = []
        for kind in ("th", "sg", "cd"):
            for d in ("f", "r"):
                out += role_nodes(f"{kind}{pol}{i}{k}{d}_")
        return out + ["load_pos", "load_neg"]
    if grp == "FULL":
        vm = [f"{kind}{pol}{i}{k}{d}_vm" for pol in ("w", "c") for i, k in ((1, 2), (2, 3), (3, 4))
              for kind in ("th", "sg", "cd") for d in ("f", "r")]
        return ["load_pos", "load_neg"] + vm
    return []


# injector terminals of the relation cores (element-name regex, terminal tag)
INJECTORS = [(r"n(th|cd)[wc]\d\d[fr]_rm_mo", "d"), (r"nsg[wc]\d\d[fr]_ota_m[24]", "d"),
             (r"ncd[wc]\d\d[fr]_kh", "d")]


def ledger_terminals(case):
    return list(INJECTORS) if case["group"] == "FULL" else []


def plan_from_netlist(nl, nodes):
    """Per ledger node: list of (element, kind, current vector, sign, C) from the built
    netlist's instrumentation terms (MOS terminals on a ledger node are included)."""
    nodes = [n.lower() for n in nodes]
    by_node = {n: [] for n in nodes}
    for name, kind, terms, extra in nl.elements:
        for (n, vec, sign) in terms:
            if n in by_node:
                far = [m for (m, vv, sg) in terms if vv == vec and m != n]
                by_node[n].append({"element": name, "kind": kind, "vec": vec, "sign": sign,
                                   "C": extra.get("C") if isinstance(extra, dict) else None,
                                   "R": extra.get("R") if isinstance(extra, dict) else None,
                                   "far": far[0] if far else None})
    probes = {p["element"] + ":" + p["terminal"]: dict(p) for p in getattr(nl, "probes", [])}
    return {"nodes": nodes, "terms": by_node, "probes": probes}


def injection(V, plan, core):
    """Current (A) delivered INTO the core's vm node by its injector elements (Θ / Cdir mirror
    output, Σ OTA m2 + m4), and the conflict shunt current drawn OUT of vm (Cdir kh), from the
    ledger terms or the targeted probes, whichever the plan holds. None if not measured."""
    import re
    vm = core + "vm"
    inj_rx = (r"n(th|cd)[wc]\d\d[fr]_rm_mo", r"nsg[wc]\d\d[fr]_ota_m[24]")
    items = [it for it in plan.get("terms", {}).get(vm, [])]
    items += [p for p in plan.get("probes", {}).values() if p["node"] == vm]
    seen, inj, shunt = set(), [], []
    for it in items:
        if it["vec"] in seen:
            continue
        seen.add(it["vec"])
        e = it["element"]
        if any(re.fullmatch(rx, e) for rx in inj_rx) and e.startswith("n" + core):
            inj.append(it)
        elif e == f"n{core}kh":
            shunt.append(it)
    if not inj or any(it["vec"].lower() not in V for it in inj + shunt):
        return None, None
    i_in = -sum(it["sign"] * V[it["vec"].lower()] for it in inj)          # out of the element into vm
    i_sh = sum(it["sign"] * V[it["vec"].lower()] for it in shunt) if shunt else None
    return i_in, i_sh


def membrane_ledger(V, plan, core):
    """Signed terminal currents at the core's vm ledger node, grouped by role (A): in = into vm
    from the relation injectors (rm_mo / OTA m2 + m4), sh = kh shunt OUT of vm, leak = Rm OUT of
    vm, cap = charging into Cm + C_NODE, other = every other branch OUT of vm (reset / recovery /
    POR / comparator gate). None if the node is not a ledger node or a vector is missing (never
    zero-filled). Terminal currents are read as "into the element", hence the sign flips."""
    import re
    vm = core + "vm"
    items = plan.get("terms", {}).get(vm)
    if not items or any(it["vec"].lower() not in V for it in items):
        return None
    inj_rx = (r"n(th|cd)[wc]\d\d[fr]_rm_mo", r"nsg[wc]\d\d[fr]_ota_m[24]")
    zero = 0.0 * np.asarray(V[items[0]["vec"].lower()], dtype=float)
    g = {"in": zero.copy(), "sh": zero.copy(), "leak": zero.copy(), "cap": zero.copy(), "other": zero.copy()}
    for it in items:
        into_el = it["sign"] * np.asarray(V[it["vec"].lower()], dtype=float)
        e = it["element"]
        if any(re.fullmatch(rx, e) for rx in inj_rx):
            g["in"] = g["in"] - into_el
        elif e == f"n{core}kh":
            g["sh"] = g["sh"] + into_el
        elif e == f"r{core}rm":
            g["leak"] = g["leak"] + into_el
        elif it["kind"] == "C":
            g["cap"] = g["cap"] + into_el
        else:
            g["other"] = g["other"] + into_el          # into element == out of vm
    return g


def save_vectors(plan):
    vec = [f"v({n})" for n in plan["nodes"]]
    for n, items in plan["terms"].items():
        vec += [it["vec"] for it in items]
    vec += [p["vec"] for p in plan.get("probes", {}).values()]
    vec += ["v(vsrc)", "i(vsrc)"]
    out, seen = [], set()
    for x in vec:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
