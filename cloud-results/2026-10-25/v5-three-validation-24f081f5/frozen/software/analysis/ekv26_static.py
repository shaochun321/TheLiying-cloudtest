"""EKV v2.6 static drain current, ported line by line from the compiled Verilog-A source
(work/mfs0_r1/tools/ekv_src/ekv26.va, sha 2785e066..., lines 45-66 y_fv macro and 282-517
static equations). Used ONLY offline for the Q1 preparation bounds (INFRA): it never runs in
a solve and never replaces a device. Junction diodes, charges and noise are not ported.

Mismatch parameters AVTO/AKP/AGAMMA keep their 1e-6 defaults (no statistics). The channel
current is multiplied by the instance multiplier m; this assumes the netlist 'M=' binds to
the OSDI $mfactor (registered as an assumption in input_bounds.py).
"""
import math

K_B, Q_E, T0C = 1.380649e-23, 1.602176634e-19, 273.15
EPS0 = 8.85418781762039e-12  # P_EPS0 in constants.vams

# C05 typical card (models/c05_ekv26_typ.lib); TEMP not given -> circuit temperature
CARDS = {
    "nch": dict(TYPE=1, TNOM=25.5, COX=3.4e-3, XJ=0.1e-6, VTO=0.61, GAMMA=0.66, PHI=0.8, KP=169e-6,
                E0=99.0e6, UCRIT=4.3e6, DL=-0.07e-6, DW=0.025e-6, LAMBDA=0.27, LETA=0.39, WETA=0.1,
                Q0=230e-6, LK=0.66e-6, TCV=1.7e-3, BEX=-1.57, UCEX=1.6, THETA=0.0),
    "pch": dict(TYPE=-1, TNOM=25.5, COX=3.4e-3, XJ=0.1e-6, VTO=-0.57, GAMMA=0.64, PHI=0.68, KP=39.6e-6,
                E0=56.4e6, UCRIT=20.0e6, DL=-0.05e-6, DW=0.14e-6, LAMBDA=1.2, LETA=0.51, WETA=0.01,
                Q0=180e-6, LK=0.67e-6, TCV=-1.36e-3, BEX=-1.22, UCEX=2.0, THETA=0.0),
}


def _y_fv(t):
    if t > -0.35:
        z0 = 2.0 / (1.3 + t - math.log(t + 1.6))
        zk = (2.0 + z0) / (1.0 + t + math.log(z0))
        return (1.0 + t + math.log(zk)) / (2.0 + zk)
    if t > -15.0:
        z0 = 1.55 + math.exp(-t)
        zk = (2.0 + z0) / (1.0 + t + math.log(z0))
        return (1.0 + t + math.log(zk)) / (2.0 + zk)
    if t > -23.0:
        return 1.0 / (2.0 + math.exp(-t))
    return math.exp(t) + 1e-64


def ids(model, W, L, vd, vg, vs, vb, m=1, temp_c=27.0, NS=1):
    """Drain-to-source channel current (A) of one instance; sign follows SPICE convention
    (positive = current into the drain terminal through the channel to the source)."""
    p = CARDS[model]
    TYPE = p["TYPE"]
    epssil = 11.7 * EPS0
    eps_COX = epssil / p["COX"]
    Lc = math.sqrt(eps_COX * p["XJ"])
    Lc_LAMBDA = Lc * p["LAMBDA"]
    eps_COX_W = 3.0 * eps_COX * p["WETA"]
    eps_COX_L = eps_COX * p["LETA"]
    T0 = p["COX"] / (epssil * p["E0"])
    V0 = (p["Q0"] + p["Q0"]) / p["COX"]
    eta_qi = 0.5 if TYPE > 0 else 0.3333333333333
    T = temp_c + T0C
    Tnom = p["TNOM"] + T0C
    Vt = K_B * T / Q_E
    Vt_01, Vt_4 = 0.1 * Vt, 4 * Vt
    Vt_Vt = Vt * Vt
    Vt_Vt_2, Vt_Vt_16 = 2 * Vt_Vt, 16 * Vt_Vt
    Eg = 1.16 - 7.02e-4 * T * T / (T + 1108.0)
    refEg = 1.16 - (7.02e-4 * Tnom * Tnom) / (Tnom + 1108.0)
    deltaT, ratioT = T - Tnom, T / Tnom
    VTO_T = p["VTO"] - p["TCV"] * deltaT
    KP_T = p["KP"] * ratioT ** p["BEX"]
    UCRIT_T = p["UCRIT"] * ratioT ** p["UCEX"]
    PHI_T = p["PHI"] * ratioT - 3.0 * Vt * math.log(ratioT) - refEg * ratioT + Eg
    tmp2 = PHI_T - 0.2
    PHI_T = 0.5 * (tmp2 + math.sqrt(tmp2 * tmp2 + Vt * Vt)) + 0.2
    sqrt_PHI = math.sqrt(PHI_T)
    inv_UCRIT = 1.0 / UCRIT_T
    Lc_UCRIT = Lc * UCRIT_T
    Leff, Weff = L + p["DL"], W + p["DW"]
    Vc = UCRIT_T * Leff
    log_Vc_Vt = Vt * (math.log(0.5 * Vc / Vt) - 0.6)
    VTO_S = VTO_T if TYPE > 0 else -VTO_T
    KP_Weff = Weff * KP_T
    GAMMA_S = p["GAMMA"]
    GAMMA_sqrt_PHI = GAMMA_S * sqrt_PHI
    vL = 0.28 * (Leff / (p["LK"] * NS) - 0.1)
    sqv = 1.0 / (1.0 + 0.5 * (vL + math.sqrt(vL * vL + 1.936e-3)))
    deltaVFB = V0 * sqv * sqv

    VG, VS, VD = TYPE * (vg - vb), TYPE * (vs - vb), TYPE * (vd - vb)
    mode = 1
    if VD - VS < 0:
        mode, VS, VD = -1, VD, VS
    VGstar = VG - VTO_S - deltaVFB + PHI_T + GAMMA_sqrt_PHI
    VGprime = 0.5 * (VGstar + math.sqrt(VGstar * VGstar + 2.0 * Vt_Vt_16))
    PHI_VS = PHI_T + VS
    sqrt_PHI_VS = math.sqrt(0.5 * (PHI_VS + math.sqrt(PHI_VS * PHI_VS + Vt_Vt_16)))
    PHI_VD = PHI_T + VD
    sqrt_PHI_VD = math.sqrt(0.5 * (PHI_VD + math.sqrt(PHI_VD * PHI_VD + Vt_Vt_16)))
    WETA_W = eps_COX_W * m / Weff
    LETA_L = eps_COX_L * NS / Leff
    big_sqrt_VP0 = math.sqrt(VGprime + 0.25 * GAMMA_S * GAMMA_S)
    VP0 = VGprime - PHI_T - GAMMA_S * (big_sqrt_VP0 - 0.5 * GAMMA_S)
    sqrt_PHI_VP0 = math.sqrt(VP0 + PHI_T + Vt_01)
    GAMMAstar = GAMMA_S - LETA_L * (sqrt_PHI_VS + sqrt_PHI_VD) + WETA_W * sqrt_PHI_VP0
    GAMMAprime = 0.5 * (GAMMAstar + math.sqrt(GAMMAstar * GAMMAstar + Vt_01))
    big_sqrt_VP = math.sqrt(VGprime + 0.25 * GAMMAprime * GAMMAprime)
    VP = VGprime - PHI_T - GAMMAprime * (big_sqrt_VP - 0.5 * GAMMAprime)
    yk = _y_fv((VP - VS) / Vt)
    if_ = yk * (1.0 + yk)
    sqrt_if = math.sqrt(if_)
    Vt_Vc = Vt / Vc
    VDSS = Vc * (math.sqrt(0.25 + sqrt_if * Vt_Vc) - 0.5)
    Vds = 0.5 * (VD - VS)
    deltaV_2 = Vt_Vt_16 * (p["LAMBDA"] * (sqrt_if - VDSS / Vt) + 15.625e-3)
    sqrt_VDSS_deltaV = math.sqrt(VDSS * VDSS + deltaV_2)
    sqrt_Vds_VDSS_deltaV = math.sqrt((Vds - VDSS) ** 2 + deltaV_2)
    Vip = sqrt_VDSS_deltaV - sqrt_Vds_VDSS_deltaV
    VDSSprime = Vc * (math.sqrt(0.25 + (sqrt_if - 0.75 * math.log(if_)) * Vt_Vc) - 0.5) + log_Vc_Vt
    Vdsprime = Vds - VDSSprime
    t1 = (VP - Vds - VS - math.sqrt(VDSSprime * VDSSprime + deltaV_2)
          + math.sqrt(Vdsprime * Vdsprime + deltaV_2)) / Vt
    yk = _y_fv(t1)
    irprime = yk * (1.0 + yk)
    deltaL = Lc_LAMBDA * math.log(1.0 + (Vds - Vip) / Lc_UCRIT)
    Lprime = Leff - deltaL + (Vds + Vip) * inv_UCRIT
    Lmin = 0.1 * Leff
    Leq = 0.5 * (Lprime + math.sqrt(Lprime * Lprime + Lmin * Lmin))
    yk = _y_fv((VP - VD) / Vt)
    ir = yk * (1.0 + yk)
    sif2, sir2 = 0.25 + if_, 0.25 + ir
    sif, sir = math.sqrt(sif2), math.sqrt(sir2)
    VP_PHI_eps = VP + PHI_T + 1.0e-6
    sqrt_PHI_VP_2 = 2.0 * math.sqrt(VP_PHI_eps)
    n_1 = GAMMA_S / sqrt_PHI_VP_2
    n_1_n = GAMMA_S / (sqrt_PHI_VP_2 + GAMMA_S)
    qi = -(1.0 + n_1) * Vt * ((4.0 / 3.0) * (sir2 + sir * sif + sif2) / (sif + sir) - 1.0)
    qb = -0.5 * GAMMA_S * sqrt_PHI_VP_2 - n_1_n * qi
    if (qb + eta_qi * qi) > 0.0:
        E0_Q_1 = 1.0 + T0 * (qb + eta_qi * qi)
    else:
        E0_Q_1 = 1.0 - T0 * (qb + eta_qi * qi)
    beta = KP_Weff * (1.0 + T0 * GAMMA_sqrt_PHI) / (Leq * E0_Q_1)
    nslope = 1.0 + GAMMA_S / (2.0 * math.sqrt(PHI_T + VP + Vt_4))
    Ispec = Vt_Vt_2 * nslope * beta
    Id = Ispec * (if_ - irprime)
    return TYPE * mode * Id * m
