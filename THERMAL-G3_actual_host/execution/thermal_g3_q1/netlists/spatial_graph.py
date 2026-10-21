"""THERMAL-G3-v1 spatial organisation Sigma_flow (plan sec.6.2; construction time, INFRA).

Per polarity: four support nodes (C_s to ground, leak R to vmid), three physical edges, each
node_i -- R_sense -- s_e -- R_transport -- node_j. Two identical OTAs read ONLY the R_sense drop
(forward: node_i vs s_e; reverse: s_e vs node_i). CUT opens R_transport (resistor removed,
its terminal nodes kept with the registered parasitic C). Injection: G0 activity gates a
PMOS copy of I_ref (ratio SP_INJ_N) into the node of the same site.
"""
from .bundle_physical import gated_source
from .params import v

C_PAR = 1e-12  # registered parasitic on every sense mid node (keeps the DAE regular)


def spatial_graph(nl, pol, sites, act_b, cut_edges=()):
    """act_b: {site: low-active activity enable of that site's G0 (op 'ab')}."""
    nodes = {s: f"sp{pol}{s}" for s in sites}
    for s, n in nodes.items():
        nl.C(f"sp{pol}c{s}", n, "0", v("SP_C"))
        nl.R(f"sp{pol}l{s}", n, "vmid", v("SP_RL"))
        # injection: unit PMOS copy of the I_ref diode, scaled by SP_INJ_N (1:2)
        # v1.1 corrected 2026-10-08: use scale parameter instead of W multiplication
        gated_source(nl, f"sp{pol}i{s}_", "irefp_n", n, act_b[s],
                     W=v("BIAS_W"), scale=v("SP_INJ_N"))
    edges = {}
    for i, j in zip(sites[:-1], sites[1:]):
        e = f"{i}{j}"
        se = f"sp{pol}s{e}"
        nl.R(f"sp{pol}rs{e}", nodes[i], se, v("SP_RS"))
        nl.C(f"sp{pol}cs{e}", se, "0", C_PAR)
        if e not in cut_edges:
            nl.R(f"sp{pol}rt{e}", se, nodes[j], v("SP_RT"))
        edges[e] = (nodes[i], se)
    return nodes, edges
