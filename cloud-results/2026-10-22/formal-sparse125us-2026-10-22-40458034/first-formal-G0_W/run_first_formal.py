#!/usr/bin/env python3
"""Run only formal G0_W after a separate explicit one-case cost-gate exception.
This script is not invoked by preflight and cannot authorize its own exception.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,hashlib,json,os,signal,subprocess,sys,time,traceback,types
import numpy as np
ROOT=Path(__file__).resolve().parent;CID="G0_W";run=ROOT/"runs"/CID
parser=argparse.ArgumentParser();parser.add_argument("--execute-once",action="store_true",required=True)
parser.add_argument("--authorization",type=Path,required=True);args=parser.parse_args()
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(p,v):
 p=Path(p);tmp=p.with_name(p.name+".tmp")
 tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False,default=float)+"\n");tmp.replace(p)
def append(v):
 with (ROOT/"formal-ledger.jsonl").open("a") as f:f.write(json.dumps(v,default=float)+"\n");f.flush();os.fsync(f.fileno())
m=read(ROOT/"FORMAL_MANIFEST.json");auth=read(args.authorization)
assert auth.get("approved") is True
assert auth.get("case_id")==CID and auth.get("whole_matrix_cost_gate_exception_for_this_case_only") is True
assert auth.get("manifest_sha256")==sha(ROOT/"FORMAL_MANIFEST.json")
assert auth.get("max_solver_starts")==1 and auth.get("wall_cap_s")==2700
assert auth.get("global_start_cap")==65 and auth.get("formal_phase_wall_cap_s")==108000 and auth.get("global_wall_cap_s")==172800
assert not auth.get("next_case_automatically_authorized",False)
assert not (ROOT/"STOPPED.json").exists()
assert not (ROOT/"formal-ledger.jsonl").exists(),"No retry or other first-case launch."
p=read(run/"plan.json");assert sha(run/"plan.json")==m["cases"][CID]["plan_sha256"]
assert sha(p["deck"])==p["deck_sha256"]
for x in list(m["backend"].values())+[m["model_card"]]:assert sha(x["path"])==x["sha256"]
software=Path(m["source_software"])
for rel,want in m["source_software_sha256"].items():assert sha(software/rel)==want,rel
for q in m["qualified_evidence"]:
 assert sha(q["binding_path"])==q["binding_sha256"]
 qb=read(q["binding_path"]);assert qb["scientific"]=="PASS" and qb["complete_transient"]
lines=Path(p["deck"]).read_text().splitlines()
analyses=[x.strip() for x in lines if x.strip().lower().startswith(("tran ","op ","dc ","ac ","run","resume"))]
assert analyses==[p["case"]["analysis"]]
with (run/"one-shot-reservation.json").open("x") as f:
 json.dump({"case_id":CID,"reserved_at":now(),"global_start_index":35,"max_starts":1,"wall_cap_s":2700,
 "authorization_sha256":sha(args.authorization),"manifest_sha256":sha(ROOT/"FORMAL_MANIFEST.json")},f,indent=2)
e={"case_id":CID,"analysis_id":"formal-001","phase":"formal","scale":p["case"]["scale"],
 "command":[m["backend"]["ngspice"]["path"],"-n","-b",p["deck"]],"actual_solver_launches":0,
 "automatic_retries":0,"global_starts_before":34,"global_starts_after":34,"wall_cap_s":2700,
 "watchdog_dispatch_s":2670,"kill_grace_inside_cap_s":30,"returncode":None,"timed_out":False,
 "spawn_error":None,"solver_wall_s":0.0,"started_at":None}
proc=None;t0=None
try:
 env=os.environ.copy();env["SPICE_SCRIPTS"]=m["spice_scripts"]
 with (run/"ngspice.log").open("wb") as log:
  t0=time.monotonic()
  try:proc=subprocess.Popen(e["command"],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  except OSError as exc:e["spawn_error"]=repr(exc)
  if proc is not None:
   e.update({"actual_solver_launches":1,"global_starts_after":35,"started_at":now(),"pid":proc.pid})
   append({"rec":"start","analysis_id":"formal-001","case_id":CID,"scale":p["case"]["scale"],
 "global_start_index":35,"t":e["started_at"],"manifest_sha256":sha(ROOT/"FORMAL_MANIFEST.json")})
   save(run/"execution.json",e)
   try:e["returncode"]=proc.wait(timeout=max(0,2670-(time.monotonic()-t0)))
   except subprocess.TimeoutExpired:
    e["timed_out"]=True
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    e["returncode"]=proc.wait()
   e["solver_wall_s"]=time.monotonic()-t0
finally:
 if proc is not None and proc.poll() is None:
  os.killpg(proc.pid,signal.SIGKILL);proc.wait();e["returncode"]=proc.returncode;e["solver_wall_s"]=time.monotonic()-t0
 e.update({"ended_at":now(),"solver_process_reaped":proc is not None and proc.poll() is not None,
 "wall_within_cap":e["solver_wall_s"]<=2700})
 save(run/"execution.json",e)
# Read-only original completion and science. No additional solver launch.
sys.path.insert(0,str(software))
from solver_adapter.read_raw_mmap import read_raw_mmap
from runtime.coordinator import Coordinator
from observers.judges import judge
raw=run/(CID+".raw");V=None;actual_sha=None;parse_error=None
completion={"actual_end_s":None,"expected_end_s":p["case"]["x_stop"],"raw_exists":raw.exists()}
if raw.exists():
 actual_sha=sha(raw)
 try:
  plots=read_raw_mmap(str(raw));assert len(plots)==1;V=plots[0]
  old=V["time"];new=np.ascontiguousarray(old)
  assert np.array_equal(old.view(np.uint64),new.view(np.uint64));V["time"]=new
  save(run/"time-layout.json",{"bit_patterns_identical":True,"old_stride":old.strides[0],
 "new_stride":new.strides[0],"interpolation":False,"points":len(new)})
  completion.update({"actual_end_s":float(new[-1]),"raw_points":len(new),"variables":len(V),
 "raw_sha256":actual_sha,"raw_bytes":raw.stat().st_size})
 except Exception as exc:parse_error=repr(exc)
log=(run/"ngspice.log").read_text(errors="replace")
if e["spawn_error"]:failure=e["spawn_error"]
elif e["timed_out"]:failure="timeout_killed"
elif parse_error:failure="raw_parse_error "+parse_error
else:
 original=Coordinator.completion
 fn=types.FunctionType(original.__code__,{**original.__globals__,"read_raw":lambda _: [V] if V is not None else []},
 original.__name__,original.__defaults__,original.__closure__)
 failure=fn(Coordinator.__new__(Coordinator),e["returncode"],log,str(raw),p["case"],p["required_vectors"])
if failure is None and "Using SPARSE 1.3 as Direct Linear Solver" not in log:failure="SPARSE not confirmed."
completion["completion_failure"]=failure;save(run/"completion.json",completion)
append({"rec":"end","analysis_id":"formal-001","case_id":CID,"status":failure or "complete","wall_s":e["solver_wall_s"],
 "actual_solver_launches":e["actual_solver_launches"],"global_start_count":e["global_starts_after"]})
tjudge=time.monotonic()
if failure:out={"result":"UNMEASURED","why":failure}
else:
 try:out=judge(p["case"],V,None,p["physical_ledger_plan"],ammeters=p["ammeters"],mos_nodes=p["mos_nodes"])
 except Exception as exc:out={"result":"UNMEASURED","why":repr(exc),"traceback":traceback.format_exc()}
save(run/"judge-output.json",out)
binding={"case_id":CID,"scientific":out["result"],"raw_sha256":actual_sha,"raw_path":str(raw) if raw.exists() else None,
 "deck_sha256":p["deck_sha256"],"judge_output_sha256":sha(run/"judge-output.json"),
 "complete_transient":failure is None,"actual_end_s":completion["actual_end_s"],"global_start_count":e["global_starts_after"],
 "judge_wall_s":time.monotonic()-tjudge,"next_case_automatically_authorized":False}
save(run/"verdict-binding.json",binding);append({"rec":"verdict","analysis_id":"formal-001","t":now(),**binding})
save(ROOT/"formal-budget-summary.json",{"global_starts_before":34,"new_formal_starts":e["actual_solver_launches"],
 "global_starts_after":e["global_starts_after"],"remaining_formal_starts":65-e["global_starts_after"],
 "formal_phase_cap_s":108000,"formal_wall_charge_s":e["solver_wall_s"],"global_wall_cap_s":172800,
 "global_historical_exact_wall_s":None,"actual_new_wall_delta_s":e["solver_wall_s"]})
if failure or out["result"]=="FAIL":
 save(ROOT/"STOPPED.json",{"case_id":CID,"reason":failure or "scientific FAIL","old_STOPPED_untouched":True,
 "retry_authorized":False})
save(ROOT/"FIRST_FORMAL_FINISHED.json",{"case_id":CID,"scientific":out["result"],
 "only_one_cost_gate_exception_used":True,"recompute_remaining_original_cost_gate_before_any_next_case":True,
 "no_automatic_next_run":True})
print(json.dumps({"case_id":CID,"completion":completion,"scientific":out["result"],
 "solver_wall_s":e["solver_wall_s"],"global_starts":e["global_starts_after"]},indent=2))

