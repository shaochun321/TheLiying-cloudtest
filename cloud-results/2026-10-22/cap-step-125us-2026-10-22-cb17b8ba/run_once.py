#!/usr/bin/env python3
"""One separately authorized short diagnostic; never retries or resumes old rounds."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib,json,os,signal,subprocess,sys,time

ROOT=Path(__file__).resolve().parent
if sys.argv[1:]!=["--execute-once"]:
    raise SystemExit("Requires --execute-once.")
def sha(path):
    with Path(path).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(path,value):
    path=Path(path);tmp=path.with_name(path.name+".tmp")
    with tmp.open("w",encoding="utf8") as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
    tmp.replace(path)
def append(value):
    with (ROOT/"diagnostic-ledger.jsonl").open("a",encoding="utf8") as f:
        f.write(json.dumps(value,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
p=json.loads((ROOT/"test-plan.json").read_text())
if sha(p["deck_path"])!=p["deck_sha256"] or sha(p["model_path"])!=p["model_sha256"]:
    raise SystemExit("Prepared deck/model changed.")
for a in p["backend"].values():
    if sha(a["path"])!=a["sha256"]:raise SystemExit("Prepared original backend/model changed.")
lines=Path(p["deck_path"]).read_text().splitlines()
analyses=[x.strip() for x in lines if x.strip().lower().startswith(("tran ","op ","dc ","ac ","run","resume"))]
if analyses!=[p["analysis_command"]]:raise SystemExit("Unexpected explicit analysis.")
if p["start_count_before"]!=30 or p["global_start_cap"]!=65 or p["max_solver_starts"]!=1:
    raise SystemExit("Approved count scope changed.")
with (ROOT/"one-shot-reservation.json").open("x",encoding="utf8") as f:
    json.dump({"reserved_at":now(),"maximum_starts":1,"start_index":31,"wall_cap_s":600,
               "purpose":p["purpose"],"test_plan_sha256":sha(ROOT/"test-plan.json")},f,indent=2)
    f.write("\n");f.flush();os.fsync(f.fileno())
append({"rec":"reserved","t":now(),"start_index":31,"analysis":p["analysis_command"],"deck_sha256":p["deck_sha256"]})
r={"command":[p["backend"]["ngspice"]["path"],"-n","-b",p["deck_path"]],
   "cwd":str(ROOT),"explicit_analysis":p["analysis_command"],"actual_solver_launches":0,
   "conservative_starts_before":30,"conservative_starts_after":30,"global_start_cap":65,
   "wall_cap_s":600,"kill_dispatch_s":599.9,"automatic_retries":0,"timed_out":False,
   "elapsed_solver_wall_s":0.0,"returncode":None,"spawn_error":None,
   "started_at_Asia_Shanghai":None,"signal_sent":None}
proc=None;t0=None
try:
    env=os.environ.copy();env["SPICE_SCRIPTS"]=p["spice_scripts"]
    with (ROOT/"ngspice.log").open("wb") as out:
        t0=time.monotonic();started=now()
        try:
            proc=subprocess.Popen(r["command"],cwd=ROOT,env=env,stdout=out,
                                  stderr=subprocess.STDOUT,start_new_session=True)
        except OSError as exc:r["spawn_error"]=repr(exc)
        if proc is not None:
            r.update({"pid":proc.pid,"actual_solver_launches":1,
                      "conservative_starts_after":31,"started_at_Asia_Shanghai":started})
            append({"rec":"start","t":started,"pid":proc.pid,"start_index":31,"command":r["command"]})
            save(ROOT/"execution.json",r)
            try:r["returncode"]=proc.wait(timeout=max(0,599.9-(time.monotonic()-t0)))
            except subprocess.TimeoutExpired:
                r["timed_out"]=True;r["signal_sent"]="SIGKILL to isolated process group"
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                r["returncode"]=proc.wait()
            r["elapsed_solver_wall_s"]=time.monotonic()-t0
        out.flush();os.fsync(out.fileno())
finally:
    if proc is not None and proc.poll() is None:
        os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        r["signal_sent"]="SIGKILL in cleanup";r["returncode"]=proc.returncode
        r["elapsed_solver_wall_s"]=time.monotonic()-t0
    r["ended_at_Asia_Shanghai"]=now()
    r["process_reaped"]=proc is not None and proc.poll() is not None
    r["wall_within_cap"]=r["elapsed_solver_wall_s"]<=600
    current=[{"path":x["path"],"exists":Path(x["path"]).exists(),
              "sha256":sha(x["path"]) if Path(x["path"]).is_file() else None}
             for x in p["protected_original_records"]]
    r["old_freeze_permissions_STOPPED_and_ledgers_unchanged"]=current==p["protected_original_records"]
    save(ROOT/"execution.json",r)
    append({"rec":"end","t":now(),"actual_solver_launches":r["actual_solver_launches"],
            "global_starts":r["conservative_starts_after"],"solver_wall_s":r["elapsed_solver_wall_s"],
            "returncode":r["returncode"],"timed_out":r["timed_out"]})
    save(ROOT/"budget-summary.json",{
        "global_start_cap":65,"global_count_before":30,"new_diagnostic_starts":r["actual_solver_launches"],
        "global_count_after":r["conservative_starts_after"],
        "total_starts_remaining":65-r["conservative_starts_after"],
        "diagnostic_allocation_before":3,"diagnostic_allocation_remaining":3-r["actual_solver_launches"],
        "formal_starts_reserved":31,"unused_qualification_allocation":1,
        "solver_wall_charge_this_run_s":r["elapsed_solver_wall_s"],
        "global_wall_cap_s_unchanged":172800,"historical_exact_cumulative_wall_s":None,
        "wall_delta_update":"remaining_after = remaining_before - solver_wall_charge_this_run_s",
        "qualification_or_formal_runs_started":0,
        "note":"Old three extra launch durations remain incomplete; no invented cumulative wall balance."})
    save(ROOT/"RUN_FINISHED_NO_RETRY.json",{"diagnostic_execution_finished":True,
         "no_automatic_next_run":True,"old_qualification_result":"FAIL_UNCHANGED",
         "old_STOPPED_round_resumed":False,"global_starts":r["conservative_starts_after"]})
print(json.dumps(r,indent=2))

