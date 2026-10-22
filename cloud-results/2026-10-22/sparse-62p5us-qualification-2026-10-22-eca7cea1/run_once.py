#!/usr/bin/env python3
"""Exactly one newly authorized solve. No old round resume, retry or formal dispatch."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,os,signal,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
CID="Q1_MOTHER_HALFSTEP";run=ROOT/"runs"/CID
if sys.argv[1:]!=["--execute-once"]:raise SystemExit("Requires --execute-once")
def sha(p):
 with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def read(p):return json.loads(Path(p).read_text())
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(p,v):
 p=Path(p);tmp=p.with_name(p.name+".tmp")
 with tmp.open("w") as f:json.dump(v,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
 tmp.replace(p)
def append(v):
 with (ROOT/"qualification-ledger.jsonl").open("a") as f:f.write(json.dumps(v)+"\n");f.flush();os.fsync(f.fileno())
m=read(ROOT/"CANDIDATE_MANIFEST.json");a=read(ROOT/"QUALIFICATION_AUTHORIZATION.json");b=read(ROOT/"baseline-reference.json")
assert sha(ROOT/"CANDIDATE_MANIFEST.json")==a["manifest_sha256"]
assert a["authorized_cases"]==[CID] and a["max_solver_starts"]==1
assert not a["formal_31_authorized"] and not a["parameter_tuning_authorized"]
assert a["baseline_global_starts"]==33 and a["global_start_cap"]==65 and 65-34==31
assert a["case_wall_cap_s"]==3600 and a["qualification_phase_wall_cap_s"]==7200
assert a["qualification_phase_prior_charged_wall_s"]+3600<=7200
assert sha(ROOT/"baseline-reference.json")==m["baseline_reference_sha256"]
assert sha(b["verdict_binding_path"])==b["verdict_binding_sha256"]
assert sha(b["judge_output_path"])==b["judge_output_sha256"]
st=Path(b["raw_path"]).stat();assert (st.st_size,st.st_mtime_ns)==(b["raw_size"],b["raw_mtime_ns"])
assert b["scientific"]=="PASS" and b["max_step_s"]==.000125
plan=read(run/"plan.json");assert sha(run/"plan.json")==m["cases"][CID]["plan_sha256"]
assert sha(plan["deck"])==plan["deck_sha256"]
for asset in list(m["backend"].values())+[m["model_card"]]:assert sha(asset["path"])==asset["sha256"]
software=Path(m["source_software"])
for rel,want in m["software_files_unchanged_from_verified_host"].items():assert sha(software/rel)==want,rel
lines=Path(plan["deck"]).read_text().splitlines()
analyses=[x.strip() for x in lines if x.strip().lower().startswith(("tran ","op ","dc ","ac ","run","resume"))]
assert analyses==["tran 0.001 100.27 0 0.0000625"]
assert not (ROOT/"STOPPED.json").exists() and not (ROOT/"SOLVE_FINISHED.json").exists()
with (run/"one-shot-reservation.json").open("x") as f:
 json.dump({"reserved_at":now(),"maximum_starts":1,"start_index":34,"wall_cap_s":3600,
 "candidate_manifest_sha256":sha(ROOT/"CANDIDATE_MANIFEST.json")},f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
append({"rec":"reserved","case_id":CID,"t":now(),"reserved_start_index":34,"deck_sha256":plan["deck_sha256"]})
e={"case_id":CID,"command":[m["backend"]["ngspice"]["path"],"-n","-b",plan["deck"]],
 "cwd":str(run),"explicit_analysis":analyses[0],"actual_solver_launches":0,"automatic_retries":0,
 "conservative_starts_before":33,"conservative_starts_after":33,"global_start_cap":65,
 "wall_clock_cap_s":3600,"kill_dispatch_s":3599.9,"returncode":None,"timed_out":False,
 "spawn_error":None,"elapsed_solver_wall_s":0.0,"signal_sent":None,"started_at_Asia_Shanghai":None}
proc=None;t0=None
try:
 env=os.environ.copy();env["SPICE_SCRIPTS"]=m["spice_scripts"]
 with (run/"ngspice.log").open("wb") as log:
  t0=time.monotonic();stamp=now()
  try:proc=subprocess.Popen(e["command"],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  except OSError as exc:e["spawn_error"]=repr(exc)
  if proc is not None:
   e.update({"actual_solver_launches":1,"pid":proc.pid,"conservative_starts_after":34,"started_at_Asia_Shanghai":stamp})
   append({"rec":"start","case_id":CID,"t":stamp,"pid":proc.pid,"global_start_index":34,"reserved_wall_s":3600})
   save(run/"execution.json",e)
   try:e["returncode"]=proc.wait(timeout=max(0,3599.9-(time.monotonic()-t0)))
   except subprocess.TimeoutExpired:
    e["timed_out"]=True;e["signal_sent"]="SIGKILL to isolated ngspice process group"
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    e["returncode"]=proc.wait()
   e["elapsed_solver_wall_s"]=time.monotonic()-t0
  log.flush();os.fsync(log.fileno())
finally:
 if proc is not None and proc.poll() is None:
  os.killpg(proc.pid,signal.SIGKILL);proc.wait();e["returncode"]=proc.returncode
  e["signal_sent"]="SIGKILL in cleanup";e["elapsed_solver_wall_s"]=time.monotonic()-t0
 e.update({"ended_at_Asia_Shanghai":now(),"solver_process_reaped":proc is not None and proc.poll() is not None,
           "wall_within_cap":e["elapsed_solver_wall_s"]<=3600})
 current=[{"path":x["path"],"exists":Path(x["path"]).exists(),"sha256":sha(x["path"]) if Path(x["path"]).is_file() else None}
          for x in m["protected_original_records"]]
 e["original_frozen_permission_ledger_stop_records_unchanged"]=current==m["protected_original_records"]
 save(run/"execution.json",e)
 append({"rec":"end","case_id":CID,"t":now(),"actual_solver_launches":e["actual_solver_launches"],
 "global_start_count":e["conservative_starts_after"],"wall_s":e["elapsed_solver_wall_s"],
 "returncode":e["returncode"],"timed_out":e["timed_out"]})
 n=e["actual_solver_launches"];prior=m["qualification_phase_prior_charged_wall_s"];wall=e["elapsed_solver_wall_s"]
 save(ROOT/"budget-summary.json",{"baseline_global_starts":33,"qualification_starts_this_round":n,
 "global_starts_after":33+n,"global_start_cap":65,"total_starts_remaining":32-n,"formal_31_reserved":31,
 "unused_diagnostic_allocation":0,"qualification_allocation_unspent":1-n,"solver_wall_charge_this_round_s":wall,
 "phase_wall_cap_s":7200,"phase_prior_charged_wall_s":prior,"phase_total_charged_wall_s":prior+wall,
 "phase_remaining_wall_s":7200-prior-wall,"global_wall_cap_s_unchanged":172800,
 "exact_prior_cumulative_wall_s":None,"formal_runs_started":0,"automatic_retries":0,
 "note":"Historical global exact wall remains incomplete; charge this exact new solver delta only."})
 save(ROOT/"SOLVE_FINISHED.json",{"case_id":CID,"actual_solver_launches":n,"no_retry":True,
 "global_starts_after":33+n,"offline_judging_only_remains":True})
print(json.dumps(e,indent=2))

