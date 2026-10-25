"""Q1-R static checks of all 2+31 decks (INFRA, no solver).

Per case: rebuild the deck (runtime/decks.py), record its identity hash (<RAW> placeholder) and
check: no duplicate element names; no 'M=' instance multipliers (explicit unit devices);
every non-ground electrical node has a DC path to ground through R / MOS channel / V source;
static model domain (every MOSFET W in [0.8, 10] um and L in [0.5, 10] um, C05 card validity);
G0 structure (10 ensembles + collector per built G0) and 4 spatial nodes per polarity where Σ
is built; every save vector names a node / source that exists; every vector the case's judge
and ledger plan read is saved (and, for half-step cases, saved in the baseline deck too); baseline variants differ from their
baseline netlist only by the declared construction difference (element-name diff restricted
to the declared prefixes). Half-step decks are identical to their baseline except the analysis
line. Writes results/static_check.json and results/decks/<case>.cir (no raw path).
Instance / node / save counts feed the cost estimate (engineering prediction, not a bound).
"""
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from runtime.decks import deck_text, registry  # noqa: E402

W_RANGE, L_RANGE = (0.8e-6, 10e-6), (0.5e-6, 10e-6)
DIFF_PREFIX = {   # case -> element-name prefixes allowed to differ from its baseline
    "G0_CUT_K1": ("ngw1_b1_cut", "ngw1_and_"), "G0_CUT_K10": ("ngw1_b10_cut", "ngw1_and_"),
    "STRUCT_THETA_PORT_CUT": ("ncdw12f_",), "STRUCT_SIGMA_PORT_CUT": ("ncdw12f_", "ncdw12r_"),
    "STRUCT_CDIR_HISTORY_BLEED": ("ncdw12f_bl", "vbleedg", "cpar_bleedg"),
    "STRUCT_REAL_SIGMA_SWAP": ("nsgw12f_ota_", "nsgw12r_ota_"),
    "FULL_REAL_MIRROR": tuple(f"ng{p}{s}_e{k}_i" for p in "wc" for s in range(1, 5) for k in range(1, 11)), "FULL_SPACE_CUT": ("rspw", "rspc"),
}


def elements(text):
    out = []
    for l in text.splitlines():
        s = l.strip()
        if not s or s[0] in "*.+" or s.startswith((".", "pre_osdi", "set ", "write ", "quit", "tran", "op")):
            continue
        out.append(s.split())
    return out


def dc_graph(els):
    g = defaultdict(set)
    for e in els:
        k = e[0][0].lower()
        if k in "rv" or k == "l":
            a, b = e[1].lower(), e[2].lower()
        elif k == "n":                       # OSDI MOSFET: d g s b -> channel d-s
            a, b = e[1].lower(), e[3].lower()
        elif k == "b" and "v=" in " ".join(e).lower():
            a, b = e[1].lower(), e[2].lower()
        elif k == "b":                       # current-defined device equation (NTC): conductive
            a, b = e[1].lower(), e[2].lower()
        else:
            continue
        g[a].add(b)
        g[b].add(a)
    return g


def floating(els):
    g = dc_graph(els)
    nodes = set()
    for e in els:
        k = e[0][0].lower()
        if k in "rclvbn":
            nodes.update(x.lower() for x in e[1:5 if k == "n" else 3])
    seen, stack = {"0"}, ["0"]
    while stack:
        n = stack.pop()
        for m in g[n]:
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return sorted(n for n in nodes - seen if not n.replace(".", "").replace("-", "").isdigit())


def domain(els):
    bad = []
    for e in els:
        if e[0][0].lower() != "n":
            continue
        kv = dict(x.split("=") for x in e[6:] if "=" in x)
        W, L = float(kv["W"]), float(kv["L"])
        if not (W_RANGE[0] - 1e-12 <= W <= W_RANGE[1] + 1e-12 and L_RANGE[0] - 1e-12 <= L <= L_RANGE[1] + 1e-12):
            bad.append((e[0], W, L))
    return bad


LEDGER_NEED = {}


def normalise(els):
    """Map ammeter inner nodes back to outer nodes and drop the probes themselves."""
    outer = {}
    for e in els:
        if e[0].lower().startswith("va_"):
            outer[e[2].lower()] = e[1].lower()
    out = []
    for e in els:
        if e[0].lower().startswith("va_"):
            continue
        out.append([e[0]] + [outer.get(x.lower(), x) for x in e[1:]])
    return out


def check_case(c, decks, texts):
    text, req = deck_text(c["case_id"])
    texts[c["case_id"]] = text
    h = hashlib.sha256(text.encode()).hexdigest()
    els = elements(text)
    names = [e[0].lower() for e in els]
    r = {"sha256": h, "n_elements": len(els), "n_mos": sum(n.startswith("n") for n in names),
         "n_save": len(req), "checks": {}}
    dup = sorted({n for n in names if names.count(n) > 1})
    r["checks"]["no_duplicate_names"] = {"pass": not dup, "dup": dup[:5]}
    mult = [e[0] for e in els if any(x.lower().startswith("m=") for x in e)]
    r["checks"]["explicit_unit_devices"] = {"pass": not mult, "with_M": mult[:5]}
    fl = floating(els)
    r["checks"]["no_floating_nodes"] = {"pass": not fl, "floating": fl[:10]}
    dom = domain(els)
    r["checks"]["model_domain_geometry"] = {"pass": not dom, "outside": dom[:5]}
    allnodes = {x.lower() for e in els for x in e[1:5]}
    vsrcs = {e[0].lower() for e in els if e[0].lower().startswith("v")}
    save_line = next((l for l in text.splitlines() if l.startswith(".save ")), "")
    saved = set(save_line.split()[1:])

    def exists(vec):
        m = re.fullmatch(r"v\((.+)\)", vec)
        if m:
            return m.group(1) in allnodes
        m = re.fullmatch(r"i\((.+)\)", vec)
        return bool(m) and m.group(1) in vsrcs
    bad = [x for x in saved if not exists(x)]
    r["checks"]["save_vectors_exist"] = {"pass": not bad, "missing": sorted(bad)[:10]}
    # judge-required vectors (and the ledger plan's) are all saved in this deck
    need = set(req) | set(LEDGER_NEED.get(c["case_id"], []))
    not_saved = sorted(need - saved)
    r["checks"]["judge_vectors_saved"] = {"pass": not not_saved, "missing": not_saved[:10], "n_required": len(need)}
    g0s = sorted({m.group(1) for n in names for m in [re.match(r"cg([wc]\d)_col_cm", n)] if m})
    ok_g0 = all(sum(1 for n in names if re.fullmatch(rf"cg{g}_e\d+_cm", n)) == 10 for g in g0s)
    r["checks"]["g0_ten_plus_collector"] = {"pass": ok_g0, "g0": g0s}
    sp = defaultdict(int)
    for n in names:
        m = re.fullmatch(r"csp([wc])c\d", n)
        if m:
            sp[m.group(1)] += 1
    r["checks"]["spatial_four_nodes"] = {"pass": all(x == 4 for x in sp.values()), "nodes": dict(sp)}
    base = c.get("baseline_case_id")
    if base and base in texts:
        bt = texts[base]
        # the baseline deck saves every vector this case's judge reads from the baseline
        bsaved = set(next((l for l in bt.splitlines() if l.startswith(".save ")), "").split()[1:])
        bmiss = sorted(set(req) - bsaved) if c["case_id"].endswith("HALFSTEP") else []
        r["checks"]["baseline_vectors_saved"] = {"pass": not bmiss, "missing": bmiss[:10]}
        if c["case_id"].endswith("HALFSTEP"):
            strip = lambda t: [l for l in t.splitlines() if not l.startswith(("tran ", "* THERMAL"))]
            r["checks"]["halfstep_identity"] = {"pass": strip(text) == strip(bt)}
        else:
            # ammeter insertion renames probed terminals (<elem>_<tag>); compare element identity
            # with the probe inner nodes mapped back to their outer node
            a = {" ".join(e) for e in normalise(els)}
            b = {" ".join(e) for e in normalise(elements(bt))}
            diff = sorted({x.split()[0].lower() for x in a ^ b})
            allowed = DIFF_PREFIX.get(c["case_id"], ())
            stray = [d for d in diff if not d.startswith(allowed)]
            r["checks"]["variant_diff_declared_only"] = {"pass": bool(diff) and not stray,
                                                         "n_diff": len(diff), "stray": stray[:10]}
    r["pass"] = all(x["pass"] for x in r["checks"].values())
    return r


def main():
    reg = registry()
    out_dir = os.path.join(ROOT, "results", "decks")
    os.makedirs(out_dir, exist_ok=True)
    texts, res = {}, {}
    # baselines first
    from runtime.decks import case_assets
    from netlists.ledger_plan import save_vectors
    for c in reg["cases"]:
        a = case_assets(c["case_id"])
        LEDGER_NEED[c["case_id"]] = save_vectors(a["plan"]) if a["plan"]["nodes"] else []
    order = sorted(reg["cases"], key=lambda c: (c.get("baseline_case_id") is not None, c["case_id"]))
    for c in order:
        res[c["case_id"]] = check_case(c, None, texts)
        with open(os.path.join(out_dir, f"{c['case_id']}.cir"), "w", encoding="ascii", newline="\n") as f:
            f.write(texts[c["case_id"]])
    out = {"schema": "thermal_g3_q1r.static_check.1", "n_cases": len(res),
           "all_pass": all(r["pass"] for r in res.values()),
           "failed": {k: [n for n, x in r["checks"].items() if not x["pass"]] for k, r in res.items() if not r["pass"]},
           "cases": res}
    with open(os.path.join(ROOT, "results", "static_check.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
    print("cases", len(res), "all_pass", out["all_pass"])
    for k, v in out["failed"].items():
        print(" FAIL", k, v, {n: res[k]["checks"][n] for n in v})
    return out


if __name__ == "__main__":
    main()
