"""MFS0-R2 netlist primitives — copy of the R1 mother (source_snapshot/r1_netlists/build.py)
with R2 additions: per-device W scaling (mismatch instances), M multiplier, inductor,
CCCS/VCVS/voltage-defined B elements for the electromechanical port and the field boundary.

Original R1 docstring: MFS0-R1 netlist construction (construction time only, INFRA).

Builds flat ngspice netlists from four kinds of primitives: EKV2.6 transistors (OSDI,
instance prefix N), resistors, capacitors, and sources (independent supply/boundary
sources; one device-equation B-source for the NTC thermistor and its self-heating).
Node enumeration and fixed wiring happen here; nothing in this module runs during the
transient solve.

Instrumented mode inserts a 0-V ammeter on every element terminal so that the observer
can evaluate KCL and the energy ledger from solver currents.
"""
import re
from .params import v

# n-well taps of every PMOS go to the supply source terminal (Kelvin well tap). They carry
# only junction leakage; the load current of every PMOS still flows through R_INT via its
# source terminal on node vdd. (Also avoids an ngspice-OSDI junction-limiting failure seen
# when the bulk node is a solved node; see results/dev/iso edge_pbulk_vsrc.)
WELL = "vsrc"


class Netlist:
    def __init__(self, instrument=False, wscale=None):
        self.lines = []
        self.instrument = instrument
        self.wscale = wscale or {}   # device-name prefix -> W factor (construction time)
        # (node, current_vector_name, sign) -> current INTO the element at that node
        self.terms = []
        self.elements = []   # (name, kind, [(node, vec, sign)], extra)
        # targeted terminal probes outside the ledger nodes (measurement only, no KCL claim):
        # {"element", "kind", "terminal", "node", "vec", "sign"}; sign 1 = current INTO the element
        self.probes = []
        self.domain = {}     # node -> "elec" | "therm"

    # -- helpers -------------------------------------------------------------------
    def _node(self, n, dom):
        n = n.lower()
        if n != "0":
            self.domain.setdefault(n, dom)
        return n

    def _amm(self, ename, tag, node):
        """Return the node the element terminal is attached to (an internal node behind
        a 0-V ammeter in instrumented mode) and the current-vector name.
        instrument: False | True (every terminal) | tuple of element-name prefixes (targeted
        probes on those elements) | {"nodes": [...], "terminals": [(regex, tag), ...]} (probe
        every terminal attached to one of these nodes: complete KCL at exactly the ledger
        nodes; plus targeted terminal probes, measurement only)."""
        if not self.instrument:
            return node, None
        if isinstance(self.instrument, dict):
            if node not in self.instrument["nodes"] and not self._terminal_probe(ename, tag):
                return node, None
        elif self.instrument is not True and not ename.lower().startswith(tuple(self.instrument)):
            return node, None
        inner = f"{ename}_{tag}".lower()
        vname = f"va_{ename}_{tag}".lower()
        self.lines.append(f"{vname} {node} {inner} 0")
        return inner, f"i({vname})"

    def _terminal_probe(self, ename, tag):
        return isinstance(self.instrument, dict) and any(
            t == tag and re.fullmatch(rx, ename.lower()) for rx, t in self.instrument.get("terminals", ()))

    def _ledger(self, node):
        return not isinstance(self.instrument, dict) or node in self.instrument["nodes"]

    def _two(self, kind, name, n1, n2, rest, dom, extra=None):
        n1 = self._node(n1, dom)
        n2 = self._node(n2, dom)
        probe = n1
        if isinstance(self.instrument, dict) and n1 not in self.instrument["nodes"] and n2 in self.instrument["nodes"]:
            probe = n2       # 2-terminal: one ammeter on the ledger-side terminal is enough
        if probe == n1:
            a1, vec = self._amm(name, "p", n1)
            a2 = n2
        else:
            a2, vec = self._amm(name, "n", n2)
            a1 = n1
        self.lines.append(f"{name} {a1} {a2} {rest}")
        terms = []
        if vec:
            # i(va_*) flows from the outer node into the element on the probed side
            terms = [(n1, vec, 1.0), (n2, vec, -1.0)] if probe == n1 else [(n2, vec, 1.0), (n1, vec, -1.0)]
        self.terms += terms
        self.elements.append((name, kind, terms, extra))

    # -- primitives ----------------------------------------------------------------
    def R(self, name, n1, n2, val, dom="elec"):
        self._two("R", "r" + name, n1, n2, f"{val:.6g}", dom, {"R": val})

    def C(self, name, n1, n2, val, dom="elec", ic=None):
        rest = f"{val:.6g}" + (f" ic={ic:.6g}" if ic is not None else "")
        self._two("C", "c" + name, n1, n2, rest, dom, {"C": val})

    def V(self, name, np_, nn, spec, dom="elec"):
        np_ = self._node(np_, dom)
        nn = self._node(nn, dom)
        vname = "v" + name
        self.lines.append(f"{vname} {np_} {nn} {spec}")
        vec = f"i({vname})"
        terms = [(np_, vec, 1.0), (nn, vec, -1.0)]
        self.terms += terms
        self.elements.append((vname, "V", terms, None))

    def B(self, name, n1, n2, expr, dom="elec"):
        """Current-defined device equation (I from n1 to n2 through the element)."""
        self._two("B", "b" + name, n1, n2, f"I={expr}", dom)

    def E(self, name, np_, nn, cp, cn, gain, dom="therm"):
        """VCVS used only for one-way thermal coupling (declared approximation)."""
        np_ = self._node(np_, dom)
        nn = self._node(nn, dom)
        a1, vec = self._amm("e" + name, "p", np_)
        self.lines.append(f"e{name} {a1} {nn} {cp.lower()} {cn.lower()} {gain}")
        terms = [(np_, vec, 1.0), (nn, vec, -1.0)] if vec else []
        self.terms += terms
        self.elements.append(("e" + name, "E", terms, None))

    def M(self, name, d, g, s, b, model, W, L, mult=1):
        for pre, f in self.wscale.items():
            if name.startswith(pre):
                W = W * f
        name = "n" + name
        nodes = []
        terms = []
        outer = []
        for tag, n in (("d", d), ("g", g), ("s", s), ("b", b)):
            n = self._node(n, "elec")
            outer.append(n)
            a, vec = self._amm(name, tag, n)
            nodes.append(a)
            if vec and self._terminal_probe(name, tag):
                self.probes.append({"element": name, "kind": "M", "terminal": tag, "node": n, "vec": vec, "sign": 1.0})
            if vec and self._ledger(n):
                terms.append((n, vec, 1.0))
        if mult != int(mult) or mult < 1:
            raise ValueError(f"MOSFET {name}: mult must be a positive integer, got {mult}")
        mtxt = f" M={int(mult)}" if mult != 1 else ""
        self.lines.append(f"{name} {' '.join(nodes)} {model} W={W:.4g} L={L:.4g}{mtxt}")
        self.terms += terms
        self.elements.append((name, "M", terms, {"model": model, "W": W, "L": L, "mult": mult,
                                                 "nodes": tuple(outer)}))

    def Lind(self, name, n1, n2, val, dom="elec", ic=None):
        rest = f"{val:.6g}" + (f" ic={ic:.6g}" if ic is not None else "")
        self._two("L", "l" + name, n1, n2, rest, dom, {"L": val})

    def Fsrc(self, name, n1, n2, vctrl, gain, dom="mech"):
        """CCCS: I = gain * I(vctrl), flowing n1 -> n2 through the element."""
        self._two("F", "f" + name, n1, n2, f"{vctrl} {gain:.6g}", dom)

    def Esrc(self, name, n1, n2, c1, c2, gain, dom="elec"):
        """VCVS (two-terminal output n1-n2), instrumented like a 2-terminal element."""
        self._two("E", "e" + name, n1, n2, f"{c1.lower()} {c2.lower()} {gain:.6g}", dom)

    def BV(self, name, n1, n2, expr, dom="therm"):
        """Voltage-defined B element (explicit boundary/kinematic law)."""
        self._two("BV", "b" + name, n1, n2, f"V={expr}", dom)

    def text(self):
        return "\n".join(self.lines)


# ---------------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------------

def supply(nl, vdd_val=None):
    vdd_val = v("VDD") if vdd_val is None else vdd_val
    nl.V("src", "vsrc", "0", f"DC {vdd_val}")
    nl.R("int", "vsrc", "vdd", v("R_INT"))
    nl.C("dec", "vdd", "0", v("C_DEC"))


def inverter(nl, p, a, y, wn=None, wp=None, l=None):
    wn = v("INV_WN") if wn is None else wn
    wp = v("INV_WP") if wp is None else wp
    l = v("INV_L") if l is None else l
    nl.M(p + "p", y, a, "vdd", WELL, "pch", wp, l)
    nl.M(p + "n", y, a, "0", "0", "nch", wn, l)


def nand2(nl, p, a, b, y):
    wn, wp, l = 2 * v("INV_WN"), v("INV_WP"), v("INV_L")
    nl.M(p + "pa", y, a, "vdd", WELL, "pch", wp, l)
    nl.M(p + "pb", y, b, "vdd", WELL, "pch", wp, l)
    nl.M(p + "na", y, a, p + "x", "0", "nch", wn, l)
    nl.M(p + "nb", p + "x", b, "0", "0", "nch", wn, l)


def comparator(nl, p, inp, inn, out, w1=None, w2=None, schmitt=False):
    """5-transistor NMOS-input OTA used open loop + 2 inverters.
    out high when V(inp) > V(inn) + offset(W2/W1)."""
    w1 = v("CMP_W1") if w1 is None else w1
    w2 = v("CMP_W2") if w2 is None else w2
    L = v("CMP_L")
    nl.R(p + "b", "vdd", p + "nb", v("CMP_RB"))
    nl.M(p + "mb", p + "nb", p + "nb", "0", "0", "nch", 4e-6, L)
    nl.M(p + "mt", p + "tail", p + "nb", "0", "0", "nch", 4e-6, L)
    nl.M(p + "m1", p + "d1", inp, p + "tail", "0", "nch", w1, L)
    nl.M(p + "m2", p + "o1", inn, p + "tail", "0", "nch", w2, L)
    nl.M(p + "m3", p + "d1", p + "d1", "vdd", WELL, "pch", 4e-6, L)
    nl.M(p + "m4", p + "o1", p + "d1", "vdd", WELL, "pch", 4e-6, L)
    if schmitt:
        schmitt_inv(nl, p + "i1", p + "o1", p + "o2")
    else:
        inverter(nl, p + "i1", p + "o1", p + "o2")
    inverter(nl, p + "i2", p + "o2", out)


def schmitt_inv(nl, p, a, y):
    """R2-VARIANT (revision 2): 6-transistor CMOS Schmitt-trigger inverter (hysteresis set by
    the feedback devices) - removes linear-region dwelling of the comparator output."""
    wn, wp, l = v("INV_WN"), v("INV_WP"), v("INV_L")
    nl.M(p + "p1", p + "xp", a, "vdd", WELL, "pch", wp, l)
    nl.M(p + "p2", y, a, p + "xp", WELL, "pch", wp, l)
    nl.M(p + "p3", p + "xp", y, "0", WELL, "pch", v("SCH_WF"), v("SCH_LF"))
    nl.M(p + "n1", p + "xn", a, "0", "0", "nch", wn, l)
    nl.M(p + "n2", y, a, p + "xn", "0", "nch", wn, l)
    nl.M(p + "n3", p + "xn", y, "vdd", "0", "nch", v("SCH_WF"), v("SCH_LF"))
    # interconnect/load capacitance of the regenerative nodes (explicit parasitic)
    for n in (p + "xp", p + "xn", y):
        nl.C(p + "cp" + n[-2:], n, "0", v("C_WIRE"))


def patch_thermal(nl, p, te_spec):
    """Thermal analogue of world.py SkinPatch: T_env source -> G_th -> node tp with C_th.
    Heat-flow unit of this analogue is scaled by THERM_UNIT (tau = C/G unchanged)."""
    u = v("THERM_UNIT")
    nl.V(p + "te", p + "te", "0", te_spec, dom="therm")
    nl.R(p + "gth", p + "te", p + "tp", 1.0 / (v("PATCH_G") * u), dom="therm")
    nl.C(p + "cth", p + "tp", "0", v("PATCH_C") * u, dom="therm")


def ntc_divider(nl, p, r25=None, bb=None, rs=None, rpar=None):
    """NTC body node tn (one-way coupled to patch tp, plus own Joule heat) and divider.
    R(T) = R25*exp(B*(1/T - 1/298.15)), T = 298.15 + V(tn).
    R2: r25/bb per-instance tolerance; rs = divider resistor (calibration trim value);
    rpar = optional fixed resistor in parallel with the NTC (calibration trim)."""
    r25 = v("NTC_R25") if r25 is None else r25
    bb = v("NTC_B") if bb is None else bb
    delta, tau = v("NTC_DELTA"), v("NTC_TAU")
    nl.E(p + "tbuf", p + "tq", "0", p + "tp", "0", 1.0)
    nl.R(p + "gd", p + "tq", p + "tn", 1.0 / delta, dom="therm")
    nl.C(p + "cn", p + "tn", "0", tau * delta, dom="therm")
    rexpr = f"({r25:.6g}*exp({bb:.6g}*(1/(298.15+V({p}tn))-1/298.15)))"
    nl.B(p + "ntc", "vdd", p + "s", f"V(vdd,{p}s)/{rexpr}")
    # Joule heat of the thermistor into its body node (W -> thermal analogue current)
    nl.B(p + "heat", "0", p + "tn", f"V(vdd,{p}s)*V(vdd,{p}s)/{rexpr}", dom="therm")
    nl.R(p + "rs", p + "s", "0", v("R_S") if rs is None else rs)
    if rpar is not None:
        nl.R(p + "rpar", "vdd", p + "s", rpar)


def entry(nl, p, s, pulse, pulse_b, w1_scale=1.0):
    """Entry unit: running average m of s; comparator s vs m (+ sizing offset);
    RC-delay edge detector -> one-shot pulse (active-high `pulse`, active-low `pulse_b`)."""
    nl.R(p + "ravg", s, p + "m", v("R_AVG"))
    nl.C(p + "cavg", p + "m", "0", v("C_AVG"))
    # R2-VARIANT (revision 1): resistively loaded NMOS differential preamplifier ahead of the
    # R1 comparator; symmetric loads -> no systematic offset; gain ~ gm*R_D
    nl.R(p + "ab", "vdd", p + "anb", v("PRE_RB"))
    nl.M(p + "amb", p + "anb", p + "anb", "0", "0", "nch", 4e-6, 4e-6)
    nl.M(p + "amt", p + "atl", p + "anb", "0", "0", "nch", 4e-6, 4e-6)
    nl.M(p + "am1", p + "da", s, p + "atl", "0", "nch", v("PRE_W"), v("PRE_L"))
    nl.M(p + "am2", p + "db", p + "m", p + "atl", "0", "nch", v("PRE_W"), v("PRE_L"))
    nl.R(p + "ara", "vdd", p + "da", v("PRE_RD"))
    nl.R(p + "arb", "vdd", p + "db", v("PRE_RD"))
    comparator(nl, p + "k", p + "db", p + "da", p + "c", w1=v("CMP_W1") * w1_scale,
               schmitt=True)
    inverter(nl, p + "d1", p + "c", p + "cn")
    nl.R(p + "rd", p + "cn", p + "rc", v("PULSE_RD"))
    nl.C(p + "cd", p + "rc", "0", v("PULSE_CD"))
    inverter(nl, p + "d2", p + "rc", p + "cdl")
    inverter(nl, p + "d3", p + "cdl", p + "ncd")
    nand2(nl, p + "g", p + "c", p + "ncd", pulse_b)
    inverter(nl, p + "o", pulse_b, pulse)


def history(nl, p, pulse_b, h):
    nl.M(p + "sw", p + "sd", pulse_b, "vdd", WELL, "pch", 4e-6, 0.5e-6)
    nl.R(p + "rr", p + "sd", p + "h1", v("HIST_RR"))
    nl.C(p + "c1", p + "h1", "0", v("HIST_C1"))
    nl.R(p + "r2", p + "h1", h, v("HIST_R2"))
    nl.C(p + "c2", h, "0", v("HIST_C2"))
    nl.R(p + "rl", h, "0", v("HIST_RL"))


def relation_stack(nl, p, h_src, pulse_tgt, mir_in, wh_scale=1.0):
    """r = series NMOS stack (gate h_src on top, gate pulse_tgt below) sinking current
    from the diode-connected PMOS at node mir_in. Intermediate node p+'x' is solved."""
    nl.M(p + "mh", mir_in, h_src, p + "x", "0", "nch", v("REL_WH") * wh_scale, v("REL_LH"))
    nl.M(p + "mp", p + "x", pulse_tgt, "0", "0", "nch", v("REL_WP"), v("REL_LP"))


def relation_output(nl, p, mir_in, rcv, push, cut=False):
    """PMOS mirror of one relation current: diode at mir_in (load of the stack), one
    output into the membrane `rcv`, one output into the direction node. push=True sources
    into `dirp`; push=False sources into an NMOS diode whose mirror sinks from `dirp`.
    cut=True: same devices and gate loading, but output drains tied to vdd (no transfer)."""
    W, L = v("MIR_W"), v("MIR_L")
    nl.M(p + "md", mir_in, mir_in, "vdd", WELL, "pch", W, L)
    d_rcv = "vdd" if cut else rcv
    d_dir = "vdd" if cut else ("dirp" if push else p + "nd")
    nl.M(p + "mo1", d_rcv, mir_in, "vdd", WELL, "pch", W, L)
    nl.M(p + "mo2", d_dir, mir_in, "vdd", WELL, "pch", W, L)
    if cut:
        nl.M(p + "dr", rcv, "vdd", "vdd", WELL, "pch", W, L)   # matched drain load, off
        if push:
            nl.M(p + "dr2", "dirp", "vdd", "vdd", WELL, "pch", W, L)
    if not push:
        # in cut mode nd receives no current, so the sink device is off but still loads dirp
        nl.M(p + "nd", p + "nd", p + "nd", "0", "0", "nch", v("SNK_W"), v("SNK_L"))
        nl.M(p + "ns", "dirp", p + "nd", "0", "0", "nch", v("SNK_W"), v("SNK_L"))


def receiver(nl, p, rab, rba):
    """Two membrane nodes (C_m, R_m) = the two receiver ends; direction port `dirp`:
    push-pull node (r_ab sources, r_ba sinks) integrated on C_dir with R_dir to V_mid."""
    for n in (rab, rba):
        nl.C(p + "cm" + n, n, "0", v("RCV_C"))
        nl.R(p + "rm" + n, n, "0", v("RCV_R"))
    nl.R(p + "mid1", "vdd", p + "vmid", v("DIR_RMID"))
    nl.R(p + "mid2", p + "vmid", "0", v("DIR_RMID"))
    nl.C(p + "cmid", p + "vmid", "0", v("DIR_CMID"))
    nl.C(p + "cdir", "dirp", p + "vmid", v("RCV_C"))
    nl.R(p + "rdir", "dirp", p + "vmid", v("RCV_R"))


def relation_module(nl, te_a, te_b, cut=False, swap=False, vdd=None, mismatch=0.0):
    """Full single-axis chain. te_a/te_b: boundary source specs (thermal analogue).
    cut: relation transfer to the receiver removed, loads matched (relation_output).
    swap: pair wiring permutation (a-chain drives the b side of the relation pair).
    vdd: supply override (P/R corners). mismatch: fractional W error applied to the
    channel-a comparator + input device and the r_ab history-gated device (R corners)."""
    supply(nl, vdd)
    for ch, spec in (("a", te_a), ("b", te_b)):
        patch_thermal(nl, ch + "_", spec)
        ntc_divider(nl, ch + "_")
        entry(nl, ch + "e_", ch + "_s", ch + "_p", ch + "_pb",
              w1_scale=(1.0 + mismatch) if ch == "a" else 1.0)
        history(nl, ch + "h_", ch + "_pb", ch + "_h")
    A, B = ("b", "a") if swap else ("a", "b")
    relation_stack(nl, "rab_", f"{A}_h", f"{B}_p", "mab", wh_scale=1.0 + mismatch)
    relation_stack(nl, "rba_", f"{B}_h", f"{A}_p", "mba")
    relation_output(nl, "xab_", "mab", "rcv_ab", push=True, cut=cut)
    relation_output(nl, "xba_", "mba", "rcv_ba", push=False, cut=cut)
    receiver(nl, "rx_", "rcv_ab", "rcv_ba")
