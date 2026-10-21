#!/usr/bin/env python3
"""Budgeted single launches only; no retry loop and no old coordinator invocation."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, json, os, signal, subprocess, sys, time

SUITE = Path(__file__).resolve().parent
if len(sys.argv) != 3 or sys.argv[1] != "--execute-once":
    raise SystemExit("Usage: run_diagnostic.py --execute-once TEST_DIRECTORY")
ROOT = (SUITE / sys.argv[2]).resolve()
if ROOT.parent != SUITE:
    raise SystemExit("Test directory must be directly inside this suite.")
def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.write("\n")
        f.flush(); os.fsync(f.fileno())
    tmp.replace(path)
def append(value):
    with (SUITE / "diagnostic-ledger.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")
        f.flush(); os.fsync(f.fileno())
auth = json.loads((SUITE / "authorization.json").read_text())
if (auth["global_start_cap"] != 65 or auth["max_new_diagnostic_starts"] != 4
    or auth["qualification_and_formal_starts_reserved"] != 33
    or auth["qualification_authorized"] or auth["formal_authorized"]):
    raise SystemExit("Authorization does not match the approved diagnostic scope.")
if (SUITE / "EXPLORATION_STOPPED.json").exists():
    raise SystemExit("Exploration is stopped; this authorization does not allow another launch.")
plan = json.loads((ROOT / "test-plan.json").read_text())
deck = ROOT / plan.get("deck_name", "mother_0_20ms.cir")
if sha(deck) != plan["deck_sha256"]:
    raise SystemExit("Prepared circuit checksum changed.")
for asset in plan["backend_and_osdi_identities"].values():
    if sha(asset["path"]) != asset["sha256"]:
        raise SystemExit("Original backend or model identity changed.")
if sha(ROOT / "c05_ekv26_typ.lib") != plan["model_sha256"]:
    raise SystemExit("Model-card copy changed.")
text = deck.read_text()
analyses = [x.strip() for x in text.splitlines()
            if x.strip().lower().startswith(("tran ", "op ", "dc ", "ac ", "run", "resume"))]
if analyses != [plan.get("analysis_command", "tran 0.001 0.02 0 0.00025")]:
    raise SystemExit("Unexpected number or kind of explicit circuit analyses.")
lock = SUITE / ".diagnostic-budget.lock"
fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
proc = None
t0 = None
record = None
try:
    ledger = SUITE / "diagnostic-ledger.jsonl"
    records = [json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
    starts = [x for x in records if x["rec"] == "start"]
    used = len(starts)
    before = auth["baseline_conservative_starts"] + used
    after = before + 1
    if used >= auth["max_new_diagnostic_starts"] or auth["global_start_cap"] - after < 33:
        raise SystemExit("Approved diagnostic allocation exhausted.")
    with (ROOT / "one-shot-reservation.json").open("x", encoding="utf-8") as f:
        json.dump({"reserved_at": now(), "test": plan["test"],
                   "conservative_start_index_reserved": after,
                   "global_start_cap": 65, "max_solver_launches_this_test": 1}, f, indent=2)
        f.write("\n"); f.flush(); os.fsync(f.fileno())
    append({"rec": "reserved", "test": plan["test"], "start_index": after,
            "t": now(), "hypothesis": plan["hypothesis"], "deck_sha256": plan["deck_sha256"]})
    record = {
        "test": plan["test"], "hypothesis": plan["hypothesis"],
        "command": [plan["backend_and_osdi_identities"]["native/bin/ngspice"]["path"], "-n", "-b", str(deck)],
        "cwd": str(ROOT), "actual_solver_launches": 0, "automatic_retries": 0,
        "conservative_starts_before": before, "conservative_starts_after": before,
        "global_start_cap": 65, "qualification_and_formal_reserved": 33,
        "wall_clock_cap_s": 60.0, "kill_dispatch_s": 59.9,
        "kill_margin_reason": "Reserve 0.1 seconds for termination/reaping inside the 60s cap.",
        "explicit_analysis_commands": analyses,
        "elapsed_solver_wall_s": 0.0, "timed_out": False, "returncode": None,
        "spawn_error": None, "signal_sent": None,
        "started_at_Asia_Shanghai": None, "ended_at_Asia_Shanghai": None,
    }
    save(ROOT / "execution.json", record)
    env = os.environ.copy(); env["SPICE_SCRIPTS"] = plan["spice_scripts"]
    with (ROOT / "ngspice.log").open("wb") as log:
        t0 = time.monotonic()
        start_time = now()
        try:
            proc = subprocess.Popen(record["command"], cwd=ROOT, env=env,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as e:
            record["spawn_error"] = repr(e)
        if proc is not None:
            record.update({"pid": proc.pid, "actual_solver_launches": 1,
                           "conservative_starts_after": after,
                           "started_at_Asia_Shanghai": start_time})
            append({"rec": "start", "test": plan["test"], "start_index": after,
                    "pid": proc.pid, "t": start_time, "command": record["command"]})
            save(ROOT / "execution.json", record)
            try:
                record["returncode"] = proc.wait(timeout=max(0.0, 59.9 - (time.monotonic() - t0)))
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                record["signal_sent"] = "SIGKILL to isolated process group"
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                record["returncode"] = proc.wait()
            record["elapsed_solver_wall_s"] = time.monotonic() - t0
        log.flush(); os.fsync(log.fileno())
finally:
    if proc is not None and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
        record["signal_sent"] = "SIGKILL in cleanup"
        record["returncode"] = proc.returncode
        record["elapsed_solver_wall_s"] = time.monotonic() - t0
    if record is not None:
        record["ended_at_Asia_Shanghai"] = now()
        record["solver_process_reaped"] = proc is not None and proc.poll() is not None
        record["wall_within_cap"] = record["elapsed_solver_wall_s"] <= 60
        protected = json.loads((SUITE / "protected-state.json").read_text())
        actual = [{"path": x["path"], "exists": Path(x["path"]).exists(),
                   "sha256": sha(x["path"]) if Path(x["path"]).is_file() else None} for x in protected]
        record["original_freeze_permission_ledger_stop_states_unchanged"] = actual == protected
        save(ROOT / "execution.json", record)
        append({"rec": "end", "test": record["test"], "t": now(),
                "actual_solver_launches": record["actual_solver_launches"],
                "wall_s": record["elapsed_solver_wall_s"], "returncode": record["returncode"],
                "timed_out": record["timed_out"], "conservative_count": record["conservative_starts_after"]})
        records = [json.loads(x) for x in (SUITE / "diagnostic-ledger.jsonl").read_text().splitlines()]
        total_new = sum(x["rec"] == "start" for x in records)
        charge = sum(x.get("wall_s", 0) for x in records if x["rec"] == "end")
        save(SUITE / "budget-summary.json", {
            "baseline_starts": 28, "diagnostic_starts_this_suite": total_new,
            "conservative_total_starts": 28 + total_new, "global_start_cap": 65,
            "remaining_total_starts": 65 - 28 - total_new,
            "qualification_and_formal_starts_reserved": 33,
            "diagnostic_starts_remaining": 4 - total_new,
            "wall_charge_this_suite_s": charge,
            "global_wall_cap_s_unchanged": 172800,
            "remaining_wall_update": "remaining_after = remaining_before - wall_charge_this_suite_s",
            "exact_historical_cumulative_wall_s": None,
            "historical_wall_limitation": "Elapsed times for three earlier launches remain unavailable. This suite records its exact incremental charge without inventing a total.",
            "qualification_started": False, "formal_started": False,
        })
    lock.unlink(missing_ok=True)
if record:
    print(json.dumps({k: record[k] for k in [
        "test", "actual_solver_launches", "conservative_starts_after",
        "elapsed_solver_wall_s", "returncode", "timed_out", "spawn_error",
        "wall_within_cap", "original_freeze_permission_ledger_stop_states_unchanged"
    ]}, indent=2))

