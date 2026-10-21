# MFS0-R1 model provenance

## Solver backend (frozen)
| Item | Value | Hash / source |
|---|---|---|
| Simulator | ngspice-47 (2026-08-11) Windows MSVC 64-bit, batch `ngspice_con.exe -b` | `tools/tools.sha256` (archive 5922…f5a), `tools/ngspice47_files.sha256` |
| Linear solver | SPARSE 1.3 (ngspice default) | — |
| Integration | `method=gear reltol=1e-5 abstol=1e-16 itl4=200`, tmax 10 ms (halved twice in the audit) | `prereg_R1.json` |

## Transistor family: EPFL-EKV v2.6 [S1]
- Equations: `tools/ekv_src/ekv26.va` (chrisenz/EKV, EKV2.6/va/code), sha256 `2785e066…bcb0`. It contains the intrinsic charge model, the junction diodes (with reverse saturation current and depletion capacitance) and the overlap capacitances. It therefore covers the plan §4.2 minimum: source–drain dependence, finite conduction, off-state tail/leakage, and port charges.
- Compiled OSDI that is actually used: `tools/ekv26_r1.osdi`, sha256 `39c1cdbc…1d77`.
  - Built with OpenVAF 1.0.0 (dwarning release, `openvaf.exe` sha256 `05dd00d6…253a`) using `-D__NGSPICE__`, so the junction-voltage limiting (`$limit pnjlim`) is active.
  - The prebuilt `ekv26.osdi` from the repository (sha256 `ec6c9168…43c4`) aborted transient runs in ngspice-47 ("timestep too small") whenever a PMOS bulk sat on a solved node. The rebuild from the same source runs the same circuits.
  - A build without limiting (`-U`) also failed.
  - Repro logs are in `results/dev/iso/`.
- Model card: `models/c05_ekv26_typ.lib`. These are the Alcatel-Mietec C05M 0.5 µm EKV v2.6 parameters (M. Bucher, EPFL, 1998), "Extracted from on-wafer DC measurements" (run 125/126), typical case (VarN = VarP = 0).
  - They are **model parameters of a published extraction, not a re-measured process**.
  - Validity stated in the card: |Vg|, |Vd| < 3.3 V; |Vs| < 2 V; W 0.8–10 µm; L 0.5–10 µm. Every device in R1 is inside this range. Note that 3.3 V is the upper corner.
  - Deviation from the VA defaults: the PMOS substrate-current parameters are set to IBA = 0. The C05 source comments out the PMOS IBA/IBB/IBN lines and states that the "Effect of substrate current on PMOS drain characteristics can be neglected". The VA default (IBA = 5e8) would otherwise switch on a current the source excludes.
- Model-internal branches (Mode swap at Vds < 0, piecewise junction capacitance, limiting) are part of the published device equations. They are not functional software decisions (plan §1.2).

## Long-term carrier: MMSS [S2], NOT READY
- `models/mmss.lib` implements the source equations as an internal state node plus B-sources. There is no clip: the rates a, b ≥ 0 keep x in [0, 1].
- Parameter sets tried, all from `knowm/memristor-models-4-all`: LTspice .sub, Xyce knowm.cir, Verilog-A defaults, and the plan's own demonstration set.
- Precheck (`reference/mmss_precheck.py` → `results/mmss_precheck.json`):
  - 120 s zero-bias retention needs Von ≥ 0.537 V (τ = 1e-4 s) or ≥ 0.596 V (τ = 1e-5 s).
  - The sourced sets have Von = 0.20–0.27 V. With them, |Δx(120 s)| = 0.4 (x0 = 0.1 → 0.5).
  - The read-disturb check fails as well.
- The solver confirms this: `validation/smoke/mmss_hold.cir` gives x(1 s) = 0.26982, and the analytic value is 0.26982.
- **Verdict: MEMORY_MODEL_NOT_READY.** No model rotation and no fallback to software clipping (plan §7.1).

## Transducer: NTC thermistor (device equation)
- Part: Murata NCP15WF104F03RC, from the Murata NCP15 specification and the R44E catalogue:
  - R25 = 100 kΩ ±1%;
  - B25/50 = 4250 K ±1%;
  - dissipation constant ≈ 1 mW/°C;
  - maximum operating current 0.032 mA.
- Equation: R(T) = R25·exp(B(1/T − 1/298.15)) (B-parameter law), with T = 298.15 K + V(tn).
- Self-heating: the thermistor's Joule power P = V²/R heats its own body node tn, which is coupled through δ to the patch temperature.
  - The datasheet gives no time constant, so the body capacity is DESIGN, with τ = 0.1 s.
  - The coupling is one-way: the patch temperature is buffered into tq. This is declared, because the patch's real heat capacity in watts is not defined by the organism model.
  - The divider current is 30 µA, below the 0.032 mA rating.

## Environment and patch (boundary)
- `nexus_v1/components/heat_source.py` `CylindricalHeatSource.temperature_at` (Gaussian field), with scenario σ = 8 (DESIGN; the default is 25).
- `nexus_v1/components/world.py`: `SkinPatch` geometry (mid ring, r = 2) and thermal constants (C = 10, G = 2 → τ = 5 s).
- The patch thermal mass is rebuilt as an RC analogue in the netlist. Its heat unit is scaled by 1e-6; τ is unchanged.
- No world code runs inside the solve. The environment only produces boundary PWL sources.
