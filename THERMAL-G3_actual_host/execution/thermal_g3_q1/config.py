"""THERMAL-G3-Q1 configuration: budget contract, wall-clock caps, paths (INFRA).

Contract adopted by the user 2026-10-09 (交叉比对/THERMAL-G3-Q1_冻结候选资格验收提案_2026-10-09.md §2):
  dev 24 (closed, inherited from the sealed v1 ledger) / qualification 2 / formal 31 / rerun 4
  = 61 solver starts in total. Every explicit op/dc/tran start counts, including failed,
  timed-out or stopped ones; there is no free "smoke" or measurement analysis.
Wall clock (solver process time, summed over all processes): 48 h cumulative. Future phase
caps: qualification 1200 s, formal 108000 s, rerun 14400 s. Spent time is derived from the
ledgers at run time, never typed in here.
"""
import os
import platform

# ---- budget contract (counts) ----
DEV_CLOSED = 24
CAPS = {"qualification": 2, "formal": 31, "rerun": 4}
GLOBAL_START_CAP = 61
assert DEV_CLOSED + sum(CAPS.values()) == GLOBAL_START_CAP

# ---- wall clock (seconds of solver process time) ----
GLOBAL_WALL_CAP_S = 48 * 3600
PHASE_WALL_CAP_S = {"qualification": 1200, "formal": 108000, "rerun": 14400}

# ---- per-analysis hard caps by scale (s); the stop grace is inside the cap ----
TIMEOUT_BY_SCALE_S = {
    "mother_bench": 600,
    "single_site_single_polarity": 2700,
    "two_actual_G0_parent_chain": 5400,
    "four_sites_both_polarities_124_cores": 14400,
    "dc_static": 900,
}
KILL_GRACE_S = 30   # watchdog fires at cap - grace so that kill + teardown stay within the cap

ROOT = os.path.abspath(os.path.dirname(__file__))
V1_ROOT = os.path.join(os.path.dirname(ROOT), "thermal_g3_v1")
# sealed v1 ledger (24 dev starts); its hash is pinned so inheritance cannot drift
V1_LEDGER = os.path.join(V1_ROOT, "results", "analysis_ledger.jsonl")
V1_LEDGER_SHA256 = "2723fdb7a38ce500f909bacdc698dd5045515318a67209b275e2d1d077f95fa9"

# Local defaults of this workstation. A run package (tools/make_cloud_package.py) never relies on
# them: the backend is taken from prereg/backend_registration.json when present (written by
# tools/register_backend.py on the execution host), and raw output defaults to a sibling folder.
_CODEX = "C:/Users/shaoc/Documents/Codex/2026-09-24/files-mentioned-by-the-user-2026/work"
BACKEND_REGISTRATION = os.path.join(ROOT, "prereg", "backend_registration.json")


def is_windows():
    return platform.system() == "Windows"


def backend_registration():
    if not os.path.exists(BACKEND_REGISTRATION):
        return None
    import json
    return json.load(open(BACKEND_REGISTRATION, encoding="utf-8"))


def _registered(key):
    reg = backend_registration()
    if reg is None:
        return None
    p = reg["assets"][key]["path"]
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def get_ngspice_path():
    return os.environ.get("THERMAL_G3_NGSPICE") or _registered("THERMAL_G3_NGSPICE") or (
        f"{_CODEX}/mfs0_r1/tools/ngspice47/Spice64/bin/ngspice_con.exe")


def get_osdi_path():
    return os.environ.get("THERMAL_G3_OSDI") or _registered("THERMAL_G3_OSDI") or f"{_CODEX}/mfs0_r1/tools/ekv26_r1.osdi"


def get_model_lib_path():
    return os.environ.get("THERMAL_G3_MODEL_LIB") or os.path.join(ROOT, "models", "c05_ekv26_typ.lib")


def get_ledger_path():
    return os.environ.get("THERMAL_G3_Q1_LEDGER") or os.path.join(ROOT, "results", "q1_ledger.jsonl")


def get_raw_root():
    """Waveforms stay outside git: env, else the workstation folder if it exists, else a sibling
    folder of the package (run package layout)."""
    if os.environ.get("THERMAL_G3_Q1_RAW_ROOT"):
        return os.environ["THERMAL_G3_Q1_RAW_ROOT"]
    if os.path.isdir(_CODEX):
        return f"{_CODEX}/thermal_g3_q1_raw"
    return os.path.join(os.path.dirname(ROOT), "thermal_g3_q1_raw")
