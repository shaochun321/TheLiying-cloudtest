"""THERMAL-G3-v1 occurrence port (plan sec.5.3; construction time, INFRA).

An organisation's own pulse q (from its N-RC comparator output) charges an activity trace; the
shaped trace aq marks one activity interval (trigger, sustain, exit by RC decay below the shaping
trip, re-arm when the trace is low). A rising-edge one-shot of aq gives exactly one canonical
entry pulse (op_p / op_pb) per activity interval; it cannot re-fire until aq has fallen (exit)
and risen again. Port currents are built by consumers as gated copies of the I_ref diode, so the
transmitted quantity is I_out ~ I_ref * gate (the y_hat = I_out/I_ref of the plan is only the
observer's description; nothing divides on line).

v1.1: src_qb replaces src_pb (N-RC v1.1 convention: qb low during pulse, PMOS switch on).
"""
from .build import inverter, nand2
from .neuron_nrc import trace
from .params import v


def occurrence_port(nl, p, src_qb):
    """Activity trace + shaped output + one-shot entry pulse. src_qb: qb low during pulse."""
    act = p + "at"
    trace(nl, p + "t", src_qb, act, v("OP_RC"), v("OP_C"), v("OP_RL"))
    # 2-inverter buffer shapes the trace into a logic level
    inverter(nl, p + "sh1", act, p + "an")
    inverter(nl, p + "sh2", p + "an", p + "aq")
    inverter(nl, p + "ab", p + "aq", p + "aqb")
    # entry one-shot: delay aq through RC, entry = aq AND NOT(delayed aq)
    nl.R(p + "dr", p + "aq", p + "ad", v("OP_PULSE_R"))
    nl.C(p + "dc", p + "ad", "0", v("OP_PULSE_C"))
    inverter(nl, p + "d2", p + "ad", p + "adn")
    nand2(nl, p + "g", p + "aq", p + "adn", p + "pb")
    inverter(nl, p + "o", p + "pb", p + "p")
    return {"a": p + "aq", "ab": p + "aqb", "p": p + "p", "pb": p + "pb", "trace": act}
