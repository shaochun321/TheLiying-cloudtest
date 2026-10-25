"""Q1-R deck construction from the frozen case registry (INFRA, construction time).

deck_text(case_id, raw_path) rebuilds the solver deck of a registered case: builder + frozen
arguments + environment stimulus + analysis + save list + includes. The identity text (hashed in
the freeze) carries <RAW>, <MODEL_LIB> and <OSDI> placeholders, so it is independent of the
analysis id and of where the backend is installed.
Returns (deck_text, required_vectors).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config  # noqa: E402

OPTIONS = "sparse method=gear reltol=1e-5 abstol=1e-16"   # inherited (v1 runner/dev.py; dev-008 itl4 lesson)


def _fwd(p):
    return p.replace("\\", "/")


def registry():
    return json.load(open(os.path.join(ROOT, "prereg", "cases_q1r.json"), encoding="utf-8"))


def netlist_for(c, instrument_nodes=None, terminals=()):
    from netlists.build_thermal_g3 import build
    from netlists.bench_mother import build_bench
    inst = {"nodes": [n.lower() for n in instrument_nodes], "terminals": list(terminals)}         if (instrument_nodes or terminals) else False
    if c["builder"] == "bench_mother":
        nl, meta = build_bench(instrument=inst)
        return nl, meta
    args = dict(c["build_args"])
    env = {int(k): [tuple(s) for s in v] for k, v in (c["env"] or {}).items()}
    for k in ("theta_port_cut", "sigma_port_cut", "cut_edges"):
        if k in args:
            args[k] = [tuple(x) for x in args[k]]
    if "g0_cut" in args:
        args["g0_cut"] = tuple(args["g0_cut"])
    if "bleed" in args:
        args["bleed"] = {"which": tuple(args["bleed"]["which"]), "pwl": args["bleed"]["pwl"]}
    for k in ("sites", "g0_sites", "pols", "layers"):
        if k in args:
            args[k] = tuple(args[k])
    nl, _ = build(env, instrument=inst, **args)
    return nl, None


def case_assets(case_id):
    """Build one registered case: netlist (with ledger probes), ledger plan, MOS node map, the
    judge's required vectors and the save list (= required + ledger + bench meta), deduplicated."""
    from netlists.ledger_plan import ledger_nodes, ledger_terminals, plan_from_netlist, save_vectors
    from observers.judges import required
    c = next(c for c in registry()["cases"] if c["case_id"] == case_id)
    lnodes = ledger_nodes(c)
    nl, meta = netlist_for(c, lnodes, ledger_terminals(c))
    plan = plan_from_netlist(nl, lnodes) if (lnodes or nl.probes) else {"nodes": [], "terms": {}, "probes": {}}
    req = list(required(c))
    save = []
    if meta is not None:
        save += meta["save"]
    save += req
    if lnodes or plan["probes"]:
        save += save_vectors(plan)
    seen, out = set(), []
    for x in save:
        x = x.lower()
        if x not in seen:
            seen.add(x)
            out.append(x)
    mos = {e[0]: e[3]["nodes"] for e in nl.elements if e[1] == "M"}
    if c["analysis"] == "op":
        # op point: every electrical node voltage, explicitly named (model domain of every MOS)
        out += [f"v({n})" for n in sorted(nl.domain) if nl.domain[n] == "elec" and f"v({n})" not in seen]
        req = req + []
    return {"case": c, "netlist": nl, "plan": plan, "required": [x.lower() for x in req], "save": out,
            "mos_nodes": mos, "bench_meta": meta}


PLACEHOLDERS = ("<RAW>", "<MODEL_LIB>", "<OSDI>")


def deck_text(case_id, raw_path="<RAW>", model_lib="<MODEL_LIB>", osdi="<OSDI>"):
    """Deck of a registered case. With the default placeholders this is the deck IDENTITY text
    (hashed in the freeze, independent of where the backend is installed); the coordinator
    substitutes the raw path and the frozen model-card / OSDI paths at dispatch."""
    a = case_assets(case_id)
    c = a["case"]
    lines = [f"* THERMAL-G3-Q1-R {case_id}", f".include {model_lib}", a["netlist"].text(),
             f".options {OPTIONS}"]
    lines.append(".save " + " ".join(a["save"]))
    lines += [".control", f"pre_osdi {osdi}", "set filetype=binary",
              c["analysis"], f"write {raw_path}", "quit", ".endc", ".end", ""]
    return "\n".join(lines), list(a["required"])
