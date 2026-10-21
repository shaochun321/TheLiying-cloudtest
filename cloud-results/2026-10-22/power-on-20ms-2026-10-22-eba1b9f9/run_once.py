#!/usr/bin/env python3
"""Single authorized diagnostic launch. Never imports or resumes the old coordinator."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
if sys.argv[1:] != ["--execute-once"]:
    raise SystemExit("Requires explicit --execute-once; this script never starts on import.")
p = json.loads((ROOT / "provenance.json").read_text())
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def timestamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(name, data):
    target = ROOT / name
    temporary = ROOT / (name + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(target)

deck = ROOT / "mother_0_20ms.cir"
if sha(deck) != p["diagnostic_deck_sha256"]:
    raise SystemExit("Deck checksum changed; refusing launch.")
for rel, a in p["assets"].items():
    if sha(a["path"]) != a["sha256"]:
        raise SystemExit("An original asset changed; refusing launch: " + rel)
if sha(ROOT / "c05_ekv26_typ.lib") != p["assets"]["execution/thermal_g3_q1/models/c05_ekv26_typ.lib"]["sha256"]:
    raise SystemExit("Independent model-card copy changed.")
ngspice = p["assets"]["native/bin/ngspice"]["path"]
if not os.access(ngspice, os.X_OK):
    raise SystemExit("Prepared original ngspice is not executable.")
# Atomic one-use reservation. Any subsequent invocation stops, including after a crash.
with (ROOT / "one-shot-reservation.json").open("x", encoding="utf-8") as f:
    json.dump({"reserved_at": timestamp(), "authorized_max_solver_launches": 1,
               "baseline_conservative_starts": 27, "cap": 61}, f, indent=2)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())

command = [ngspice, "-n", "-b", str(deck)]
record = {
    "run_id": p["run_id"], "command": command, "cwd": str(ROOT),
    "wall_clock_cap_s": 60.0,
    "kill_dispatch_s": 59.9,
    "kill_margin_reason": "Reserve 0.1 seconds within the 60-second cap for termination and reaping.",
    "explicit_analysis_commands": ["tran 0.001 0.02 0 0.00025"],
    "note": "Transient's internal initial operating point is part of the one transient analysis; no separate op/dc command is issued.",
    "actual_solver_launches": 0, "actual_explicit_transient_invocations": 0,
    "conservative_starts_before": 27, "conservative_starts_after": 27,
    "start_cap": 61, "automatic_retries": 0, "parameter_adjustments_after_launch": 0,
    "qualification_launched": False, "formal_experiments_launched": False,
    "started_at_Asia_Shanghai": None, "ended_at_Asia_Shanghai": None,
    "elapsed_solver_wall_s": 0.0, "timed_out": False,
    "returncode": None, "spawn_error": None, "signal_sent": None,
}
env = os.environ.copy()
env["SPICE_SCRIPTS"] = p["spice_scripts"]
# -n excludes unrelated user .spiceinit. Relocated system spinit loads the original codemodels.
proc = None
t0 = None
try:
    with (ROOT / "ngspice.log").open("wb") as logfile:
        t0 = time.monotonic()
        wall_start_ns = time.time_ns()
        try:
            proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=logfile,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as e:
            record["spawn_error"] = repr(e)
        if proc is not None:
            record["pid"] = proc.pid
            record["actual_solver_launches"] = 1
            record["actual_explicit_transient_invocations"] = 1
            record["conservative_starts_after"] = 28
            record["started_at_Asia_Shanghai"] = datetime.fromtimestamp(
                wall_start_ns / 1e9, timezone(timedelta(hours=8))).isoformat()
            save("execution.json", record)
            try:
                record["returncode"] = proc.wait(
                    timeout=max(0.0, 59.9 - (time.monotonic() - t0)))
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                record["signal_sent"] = "SIGKILL to isolated process group"
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                record["returncode"] = proc.wait()
            record["elapsed_solver_wall_s"] = time.monotonic() - t0
        logfile.flush()
        os.fsync(logfile.fileno())
finally:
    if proc is not None and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        record["returncode"] = proc.returncode
        record["signal_sent"] = "SIGKILL in cleanup"
        record["elapsed_solver_wall_s"] = time.monotonic() - t0
    record["ended_at_Asia_Shanghai"] = timestamp()
    record["solver_process_reaped"] = proc is not None and proc.poll() is not None
    record["wall_within_cap"] = record["elapsed_solver_wall_s"] <= 60.0
    protected_after = []
    for old in p["protected_files_before"]:
        path = Path(old["path"])
        current = {"path": str(path), "exists": path.exists(),
                   "sha256": sha(path) if path.is_file() else None}
        protected_after.append(current)
    record["protected_files_after"] = protected_after
    record["old_freezes_permissions_ledgers_and_stop_files_unchanged"] = (
        protected_after == p["protected_files_before"])
    save("execution.json", record)
    charge = record["elapsed_solver_wall_s"] if record["actual_solver_launches"] else 0.0
    save("budget_delta.json", {
        "authority": "User-specified conservative baseline and authorization for this diagnostic.",
        "conservative_starts_before": 27,
        "actual_solver_launches_this_diagnostic": record["actual_solver_launches"],
        "conservative_starts_after": record["conservative_starts_after"],
        "start_cap": 61, "remaining_starts_after": 61 - record["conservative_starts_after"],
        "wall_charge_this_diagnostic_s": charge,
        "remaining_wall_update": "remaining_after = remaining_before - wall_charge_this_diagnostic_s",
        "global_wall_cap_s": 172800,
        "known_sealed_v1_wall_s": p["known_v1_wall_s"],
        "wall_s_of_prior_extra_three_starts": None,
        "exact_cumulative_wall_before_s": None,
        "exact_cumulative_wall_after_s": None,
        "exact_remaining_wall_after_s": None,
        "known_cumulative_wall_lower_bound_after_s": p["known_v1_wall_s"] + charge,
        "remaining_wall_upper_bound_after_s": 172800 - p["known_v1_wall_s"] - charge,
        "note": "Prior three additional launches are counted per user, but their full elapsed times are unavailable here. This delta charges the measured time without inventing a cumulative total. Old ledgers remain unchanged.",
    })
print(json.dumps({key: record[key] for key in [
    "run_id", "actual_solver_launches", "conservative_starts_before",
    "conservative_starts_after", "elapsed_solver_wall_s", "returncode",
    "timed_out", "spawn_error", "wall_within_cap",
    "old_freezes_permissions_ledgers_and_stop_files_unchanged"
]}, ensure_ascii=False, indent=2))

