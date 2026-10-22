#!/usr/bin/env python3
"""Execute one separately authorized Sparse qualification case, then original judging."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, json, os, signal, subprocess, sys, time, traceback

ROOT = Path(__file__).resolve().parent
if len(sys.argv) != 3 or sys.argv[1] != "--execute-once":
    raise SystemExit("Use --execute-once CASE_ID. No automatic execution or retry.")
CID = sys.argv[2]
def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(path, obj):
    path = Path(path); tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=float)
        f.write("\n"); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)
def append(obj):
    with (ROOT / "qualification-ledger.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=float) + "\n")
        f.flush(); os.fsync(f.fileno())
manifest = json.loads((ROOT / "CANDIDATE_MANIFEST.json").read_text())
auth = json.loads((ROOT / "QUALIFICATION_AUTHORIZATION.json").read_text())
manifest_sha = sha(ROOT / "CANDIDATE_MANIFEST.json")
if manifest_sha != auth["manifest_sha256"] or CID not in auth["authorized_cases"]:
    raise SystemExit("Candidate manifest or case is not authorized.")
if auth["formal_31_authorized"] or auth["parameter_tuning_authorized"]:
    raise SystemExit("Authorization scope changed.")
if (ROOT / "STOPPED.json").exists():
    raise SystemExit("This candidate round is STOPPED; no next case or retry.")
info = manifest["cases"][CID]
run = Path(info["directory"])
if sha(run / "plan.json") != info["plan_sha256"]:
    raise SystemExit("Case plan changed.")
plan = json.loads((run / "plan.json").read_text())
if sha(plan["deck"]) != plan["deck_sha256"]:
    raise SystemExit("Case deck changed.")
software = Path(manifest["source_software"])
for rel, expected in manifest["software_files_unchanged_from_verified_host"].items():
    if sha(software / rel) != expected:
        raise SystemExit("Original copied science/software input changed: " + rel)
for asset in list(manifest["backend"].values()) + [manifest["model_card"]]:
    if sha(asset["path"]) != asset["sha256"]:
        raise SystemExit("Backend/model identity changed.")
if CID == "Q1_MOTHER_HALFSTEP":
    verdict_path = ROOT / "runs/Q1_MOTHER_PROTOCOL/verdict-binding.json"
    if not verdict_path.exists():
        raise SystemExit("First qualification has no bound scientific PASS.")
    bound = json.loads(verdict_path.read_text())
    if (bound["scientific"] != "PASS" or bound["candidate_manifest_sha256"] != manifest_sha
        or sha(bound["raw_path"]) != bound["raw_sha256"]
        or sha(bound["judge_output_path"]) != bound["judge_output_sha256"]):
        raise SystemExit("First qualification prerequisite identity/PASS failed.")
lines=Path(plan["deck"]).read_text().splitlines()
analyses=[x.strip() for x in lines if x.strip().lower().startswith(("tran ","op ","dc ","ac ","run","resume"))]
if analyses != [plan["case"]["analysis"]]:
    raise SystemExit("Unexpected explicit solver analysis.")
assert manifest["numerical_pair_s"] == [.000125,.0000625]
assert plan["case"]["max_step_s"] == (.000125 if CID=="Q1_MOTHER_PROTOCOL" else .0000625)
records = [json.loads(x) for x in (ROOT / "qualification-ledger.jsonl").read_text().splitlines()] if (ROOT / "qualification-ledger.jsonl").exists() else []
starts = [x for x in records if x["rec"] == "start"]
if len(starts) >= 1 or any(x["case_id"] == CID for x in records if x["rec"] in ("reserved", "start")):
    raise SystemExit("No retry or extra qualification launch is authorized.")
before = 32 + len(starts)
if 65 - (before + 1) < 32:
    raise SystemExit("31 formal and 1 unused diagnostic starts must remain reserved.")
wall_cap = info["deadline_s"]
prior_wall = sum(x.get("wall_s",0) for x in records if x["rec"]=="end")
if manifest["qualification_phase_prior_charged_wall_s"] + prior_wall + wall_cap > 3600:
    raise SystemExit("New candidate qualification 3600s phase cap exceeded.")
assert wall_cap == 1800 and CID == "Q1_MOTHER_PROTOCOL"
with (run / "one-shot-reservation.json").open("x", encoding="utf-8") as f:
    json.dump({"case_id": CID, "reserved_at": now(), "reserved_start_index": before + 1,
               "candidate_manifest_sha256": manifest_sha, "wall_cap_s": wall_cap}, f, indent=2)
    f.write("\n"); f.flush(); os.fsync(f.fileno())
append({"rec": "reserved", "case_id": CID, "reserved_start_index": before + 1,
        "t": now(), "candidate_manifest_sha256": manifest_sha, "deck_sha256": plan["deck_sha256"]})
execution = {
    "case_id": CID, "candidate_id": manifest["candidate_id"],
    "candidate_manifest_sha256": manifest_sha,
    "command": [manifest["backend"]["ngspice"]["path"], "-n", "-b", plan["deck"]],
    "cwd": str(run), "actual_solver_launches": 0, "automatic_retries": 0,
    "conservative_starts_before": before, "conservative_starts_after": before,
    "global_start_cap": 65, "wall_clock_cap_s": wall_cap, "kill_dispatch_s": wall_cap - 0.1,
    "kill_margin_reason": "Reserve 0.1 seconds inside the authorized per-case limit for termination/reaping.",
    "explicit_analysis": plan["case"]["analysis"], "timed_out": False,
    "returncode": None, "spawn_error": None, "signal_sent": None,
    "elapsed_solver_wall_s": 0.0, "started_at_Asia_Shanghai": None,
}
save(run / "execution.json", execution)
proc = None; t0 = None
try:
    env = os.environ.copy(); env["SPICE_SCRIPTS"] = manifest["spice_scripts"]
    with (run / "ngspice.log").open("wb") as log:
        t0 = time.monotonic(); stamp = now()
        try:
            proc = subprocess.Popen(execution["command"], cwd=run, env=env,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as e:
            execution["spawn_error"] = repr(e)
        if proc is not None:
            execution.update({"actual_solver_launches": 1, "pid": proc.pid,
                              "conservative_starts_after": before + 1,
                              "started_at_Asia_Shanghai": stamp})
            append({"rec": "start", "case_id": CID, "t": stamp, "pid": proc.pid,
                    "global_start_index": before + 1, "deck_sha256": plan["deck_sha256"],
                    "candidate_manifest_sha256": manifest_sha,
                    "backend": manifest["backend"], "reserved_wall_s": wall_cap})
            save(run / "execution.json", execution)
            try:
                execution["returncode"] = proc.wait(timeout=max(0.0, wall_cap - 0.1 - (time.monotonic() - t0)))
            except subprocess.TimeoutExpired:
                execution["timed_out"] = True
                execution["signal_sent"] = "SIGKILL to isolated process group"
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                execution["returncode"] = proc.wait()
            execution["elapsed_solver_wall_s"] = time.monotonic() - t0
        log.flush(); os.fsync(log.fileno())
finally:
    if proc is not None and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
        execution["returncode"] = proc.returncode
        execution["signal_sent"] = "SIGKILL in cleanup"
        execution["elapsed_solver_wall_s"] = time.monotonic() - t0
    execution["ended_at_Asia_Shanghai"] = now()
    execution["solver_process_reaped"] = proc is not None and proc.poll() is not None
    execution["wall_within_cap"] = execution["elapsed_solver_wall_s"] <= wall_cap
    protected = manifest["protected_original_records"]
    current = [{"path": x["path"], "exists": Path(x["path"]).exists(),
                "sha256": sha(x["path"]) if Path(x["path"]).is_file() else None} for x in protected]
    execution["original_frozen_permission_ledger_stop_records_unchanged"] = current == protected
    save(run / "execution.json", execution)
    append({"rec": "end", "case_id": CID, "t": now(), "returncode": execution["returncode"],
            "timed_out": execution["timed_out"], "wall_s": execution["elapsed_solver_wall_s"],
            "actual_solver_launches": execution["actual_solver_launches"],
            "global_start_count": execution["conservative_starts_after"]})
    recs = [json.loads(x) for x in (ROOT / "qualification-ledger.jsonl").read_text().splitlines()]
    nstarts = sum(x["rec"] == "start" for x in recs)
    wall_charge = sum(x.get("wall_s", 0) for x in recs if x["rec"] == "end")
    save(ROOT / "budget-summary.json", {
        "baseline_global_starts": 32, "qualification_starts_this_round": nstarts,
        "global_starts_after": 32 + nstarts, "global_start_cap": 65,
        "total_starts_remaining": 65 - 32 - nstarts, "formal_31_reserved": 31,
        "unused_diagnostic_allocation": 1, "qualification_allocation_unspent": 1 - nstarts,
        "solver_wall_charge_this_round_s": wall_charge, "phase_wall_cap_s": 3600, "phase_remaining_wall_s": 3600-manifest["qualification_phase_prior_charged_wall_s"]-wall_charge, "phase_prior_charged_wall_s": manifest["qualification_phase_prior_charged_wall_s"], "phase_total_charged_wall_s": manifest["qualification_phase_prior_charged_wall_s"]+wall_charge,
        "global_wall_cap_s_unchanged": 172800,
        "exact_prior_cumulative_wall_s": None,
        "note": "Earlier three extra launch durations remain incomplete; charge the exact new delta without inventing a total.",
        "formal_runs_started": 0, "diagnostic_runs_started": 0,
    })

# Completion and science are offline analysis of this one run, not another solver start.
sys.path.insert(0, str(software))
from runtime.coordinator import Coordinator
from solver_adapter.read_raw_mmap import read_raw_mmap as read_raw
from observers.judges import judge
log = (run / "ngspice.log").read_text(errors="replace")
raw = run / (CID + ".raw")
completion = {
    "case_id": CID, "expected_end_s": plan["case"]["x_stop"],
    "solver_log_CONFIRMS_SPARSE": plan["expected_solver_log"] in log,
    "raw_exists": raw.exists(), "actual_end_s": None, "raw_points": None,
    "process_returncode": execution["returncode"], "completion_failure": None,
}
if execution["spawn_error"]:
    completion["completion_failure"] = execution["spawn_error"]
elif execution["timed_out"]:
    completion["completion_failure"] = "timeout_killed"
else:
    completion["completion_failure"] = Coordinator.completion(
        Coordinator.__new__(Coordinator), execution["returncode"], log, str(raw),
        plan["case"], plan["required_vectors"])
if completion["completion_failure"] is None and not completion["solver_log_CONFIRMS_SPARSE"]:
    completion["completion_failure"] = "Actual SPARSE selection was not confirmed."
V = None
if raw.exists():
    try:
        V = read_raw(str(raw))[-1]
        if "time" in V:
            completion["actual_end_s"] = float(V["time"][-1])
            completion["raw_points"] = len(V["time"])
        completion["raw_variables"] = len(V)
        completion["raw_bytes"] = raw.stat().st_size
        completion["raw_sha256"] = sha(raw)
    except Exception as exc:
        completion["raw_parse_error"] = repr(exc)
        if completion["completion_failure"] is None:
            completion["completion_failure"] = "raw_parse_error"
save(run / "completion.json", completion)
judge_started = time.monotonic()
if completion["completion_failure"] is not None:
    out = {"result": "UNMEASURED", "why": "No scientific verdict: execution/completion failed.",
           "completion_failure": completion["completion_failure"]}
else:
    try:
        base_V = None
        if CID == "Q1_MOTHER_HALFSTEP":
            binding = json.loads((ROOT / "runs/Q1_MOTHER_PROTOCOL/verdict-binding.json").read_text())
            base_V = read_raw(binding["raw_path"])[-1]
        out = judge(plan["case"], V, base_V, plan["physical_ledger_plan"],
                    ammeters=plan["ammeters"], mos_nodes=plan["mos_nodes"])
    except Exception as exc:
        out = {"result": "UNMEASURED", "why": "Original judge raised " + repr(exc),
               "traceback": traceback.format_exc()}
save(run / "judge-output.json", out)
functional_confirmation = None
if CID == "Q1_MOTHER_HALFSTEP" and completion["completion_failure"] is None:
    # Original half-step judge checks NUM plus physical ledger. Additionally run
    # original mother functional gate on this RAW without repeating its ledger.
    mother_case = json.loads((ROOT/"runs/Q1_MOTHER_PROTOCOL/plan.json").read_text())["case"]
    try:
        functional_confirmation = judge(mother_case, V, None, plan["physical_ledger_plan"],
                    ammeters=plan["ammeters"], mos_nodes=plan["mos_nodes"], ledger_check=False)
    except Exception as exc:
        functional_confirmation = {"result":"UNMEASURED","why":repr(exc)}
    save(run/"functional-confirmation.json",functional_confirmation)
combined_result = out["result"]
if functional_confirmation is not None and functional_confirmation["result"] != "PASS":
    combined_result = "FAIL" if "FAIL" in [combined_result,functional_confirmation["result"]] else "UNMEASURED"
binding = {
    "case_id": CID, "scientific": combined_result,
    "candidate_manifest_sha256": manifest_sha, "deck_sha256": plan["deck_sha256"],
    "raw_path": str(raw) if raw.exists() else None,
    "raw_sha256": sha(raw) if raw.exists() else None,
    "judge_output_path": str(run / "judge-output.json"),
    "judge_output_sha256": sha(run / "judge-output.json"), "functional_confirmation_result": functional_confirmation["result"] if functional_confirmation is not None else None, "numerical_pair_s": manifest["numerical_pair_s"],
    "judge_wall_s": time.monotonic() - judge_started,
    "complete_transient": completion["completion_failure"] is None,
    "actual_end_s": completion["actual_end_s"],
    "global_start_count": execution["conservative_starts_after"],
    "backend": manifest["backend"],
}
save(run / "verdict-binding.json", binding)
append({"rec": "verdict", "case_id": CID, "t": now(), **binding})
if combined_result != "PASS" or completion["completion_failure"] is not None:
    save(ROOT / "STOPPED.json", {
        "case_id": CID, "why": completion["completion_failure"] or ("scientific " + combined_result),
        "scientific": combined_result, "actual_end_s": completion["actual_end_s"],
        "global_start_count": execution["conservative_starts_after"],
        "next_case_or_retry_authorized": False,
        "old_STOPPED_state": "Preserved; this is a separate candidate-round STOPPED record.",
    })
print(json.dumps({"case_id": CID, "actual_solver_launches": execution["actual_solver_launches"],
    "wall_s": execution["elapsed_solver_wall_s"], "timed_out": execution["timed_out"],
    "completion": completion, "scientific": combined_result,
    "global_count": execution["conservative_starts_after"],
    "round_stopped": (ROOT / "STOPPED.json").exists()}, indent=2))

