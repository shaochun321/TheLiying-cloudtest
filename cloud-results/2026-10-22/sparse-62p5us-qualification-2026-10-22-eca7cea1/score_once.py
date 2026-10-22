#!/usr/bin/env python3
"""One offline original science/comparison batch; never invokes a solver."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,sys,time,traceback,types
import numpy as np
ROOT=Path(__file__).resolve().parent;CID="Q1_MOTHER_HALFSTEP";run=ROOT/"runs"/CID
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(p,v):
 p=Path(p);tmp=p.with_name(p.name+".tmp")
 tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=float)+"\n");tmp.replace(p)
def progress(stage,**values):save(ROOT/"analysis-progress.json",{"stage":stage,"t":now(),**values})
assert (ROOT/"SOLVE_FINISHED.json").exists(),"Solver still running."
assert not (run/"verdict-binding.json").exists(),"Scored already."
m=read(ROOT/"CANDIDATE_MANIFEST.json");p=read(run/"plan.json");b=read(ROOT/"baseline-reference.json")
e=read(run/"execution.json")
assert sha(ROOT/"baseline-reference.json")==m["baseline_reference_sha256"]
assert sha(b["verdict_binding_path"])==b["verdict_binding_sha256"]
assert sha(b["judge_output_path"])==b["judge_output_sha256"]
assert e["solver_process_reaped"] or e["spawn_error"]
with (ROOT/"offline-score-reservation.json").open("x") as f:
 json.dump({"started_at":now(),"maximum_batches":1,"new_solver_launches":0,
 "time_layout":"Use contiguous time from first attempt, uint64 bitwise verified."},f,indent=2)
t0=time.monotonic();progress("checking_actual_new_RAW")
software=Path(m["source_software"])
for rel,want in m["software_files_unchanged_from_verified_host"].items():
 if rel.startswith(("observers/","analysis/","netlists/","prereg/protocol_","runtime/coordinator","solver_adapter/read_raw")):
  assert sha(software/rel)==want,rel
sys.path.insert(0,str(software))
from solver_adapter.read_raw_mmap import read_raw_mmap
from runtime.coordinator import Coordinator
from observers.judges import judge
def load_layout(path,label):
 plots=read_raw_mmap(str(path));assert len(plots)==1,"Expected exactly one transient plot."
 v=plots[0];old=v["time"];new=np.ascontiguousarray(old)
 assert np.array_equal(old.view(np.uint64),new.view(np.uint64)),"Time bit patterns changed."
 v["time"]=new
 return v,{"label":label,"points":len(new),"old_time_stride_bytes":old.strides[0],
 "new_time_stride_bytes":new.strides[0],"time_bit_patterns_identical":True,
 "interpolation":False,"resampling":False}
raw=run/(CID+".raw");V=None;new_sha=None;layout=[]
completion={"case_id":CID,"expected_end_s":100.27,"actual_end_s":None,"raw_exists":raw.exists(),
 "process_returncode":e["returncode"],"solver_log_CONFIRMS_SPARSE":False,"completion_failure":None}
if raw.exists():
 new_sha=sha(raw);completion.update({"raw_sha256":new_sha,"raw_bytes":raw.stat().st_size})
 try:
  V,lr=load_layout(raw,"new_62p5us");layout.append(lr)
  completion.update({"actual_end_s":float(V["time"][-1]),"raw_points":len(V["time"]),"raw_variables":len(V)})
 except Exception as exc:completion["raw_parse_error"]=repr(exc)
log=(run/"ngspice.log").read_text(errors="replace")
completion["solver_log_CONFIRMS_SPARSE"]=p["expected_solver_log"] in log
if e["timed_out"]:completion["completion_failure"]="timeout_killed"
elif e["spawn_error"]:completion["completion_failure"]=e["spawn_error"]
elif "raw_parse_error" in completion:completion["completion_failure"]="raw_parse_error"
else:
 # Preserve the original completion bytecode and globals; substitute only its
 # reader with the already loaded exact-value vectors. Original module is not edited.
 original=Coordinator.completion
 completion_check=types.FunctionType(original.__code__,
    {**original.__globals__,"read_raw":lambda _: [V] if V is not None else []},
    original.__name__,original.__defaults__,original.__closure__)
 completion["completion_failure"]=completion_check(Coordinator.__new__(Coordinator),
    e["returncode"],log,str(raw),p["case"],p["required_vectors"])
 completion["original_completion_bytecode_used"]=True
 completion["completion_reader_adapter"]="Same mmap values, contiguous bit-identical time only."
if completion["completion_failure"] is None and not completion["solver_log_CONFIRMS_SPARSE"]:
 completion["completion_failure"]="Actual SPARSE selection not confirmed."
save(run/"completion.json",completion)
unmeasured={"result":"UNMEASURED","why":"Execution/completion failed; no science or comparison verdict.",
            "completion_failure":completion["completion_failure"]}
functional=dict(unmeasured);half=dict(unmeasured);baseline_reused=False
if completion["completion_failure"] is None:
 st=Path(b["raw_path"]).stat()
 assert (st.st_size,st.st_mtime_ns)==(b["raw_size"],b["raw_mtime_ns"]),"Verified baseline RAW changed."
 base,lr=load_layout(Path(b["raw_path"]),"bound_PASS_125us");layout.append(lr);baseline_reused=True
 assert b["max_step_s"]==.000125 and p["case"]["max_step_s"]==.0000625
 save(ROOT/"offline-time-layout-verification.json",{"vectors":layout,"new_RAW_sha256":new_sha,
  "baseline_RAW_sha256":b["raw_sha256"],"baseline_RAW_checksum_count_this_task":1,
  "original_scientific_code_unchanged":True,"new_solver_launches":0})
 mother_case=dict(p["case"]);mother_case.update({"case_id":"Q1_MOTHER_PROTOCOL","judge":"criteria_q1r.judge_joint"})
 progress("original_functional_confirmation")
 try:
  functional=judge(mother_case,V,None,p["physical_ledger_plan"],ammeters=p["ammeters"],
                   mos_nodes=p["mos_nodes"],ledger_check=False)
 except Exception as exc:
  functional={"result":"UNMEASURED","why":repr(exc),"traceback":traceback.format_exc()}
 save(run/"functional-confirmation.json",functional)
 progress("original_halfstep_comparison_and_physical_ledger",functional_result=functional["result"])
 try:
  half=judge(p["case"],V,base,p["physical_ledger_plan"],ammeters=p["ammeters"],mos_nodes=p["mos_nodes"])
 except Exception as exc:
  half={"result":"UNMEASURED","why":repr(exc),"traceback":traceback.format_exc()}
save(run/"functional-confirmation.json",functional);save(run/"judge-output.json",half)
results=[functional["result"],half["result"]]
result="FAIL" if "FAIL" in results else ("PASS" if all(x=="PASS" for x in results) else "UNMEASURED")
passed=completion["completion_failure"] is None and result=="PASS" and baseline_reused and b["scientific"]=="PASS"
binding={"case_id":CID,"scientific":result,"candidate_manifest_sha256":sha(ROOT/"CANDIDATE_MANIFEST.json"),
 "deck_sha256":p["deck_sha256"],"raw_path":str(raw) if raw.exists() else None,"raw_sha256":new_sha,
 "baseline_commit":b["commit"],"baseline_raw_sha256":b["raw_sha256"],"baseline_raw_reused":baseline_reused,
 "judge_output_path":str(run/"judge-output.json"),"judge_output_sha256":sha(run/"judge-output.json"),
 "functional_confirmation_path":str(run/"functional-confirmation.json"),
 "functional_confirmation_sha256":sha(run/"functional-confirmation.json"),
 "functional_confirmation_result":functional["result"],"numerical_and_physical_result":half["result"],
 "numerical_pair_s":[.000125,.0000625],"comparison_timing_tolerance_s":.00025,
 "complete_transient":completion["completion_failure"] is None,"actual_end_s":completion["actual_end_s"],
 "full_two_run_qualification_completed":passed,"global_start_count":e["conservative_starts_after"],
 "judge_wall_s":time.monotonic()-t0,"new_solver_launches_during_analysis":0}
save(run/"verdict-binding.json",binding)
with (ROOT/"qualification-ledger.jsonl").open("a") as f:
 f.write(json.dumps({"rec":"verdict","case_id":CID,"t":now(),**binding},default=float)+"\n")
summary={"candidate_id":m["candidate_id"],"full_two_run_qualification_completed":passed,
 "qualification_result":result,"baseline_commit":b["commit"],"baseline_mother_result":"PASS",
 "halfstep_result":result,"completion":completion,"verdict_binding":binding,
 "comparison_result":half.get("gates",{}).get("halfstep",{}).get("result","UNMEASURED"),
 "physical_ledger_result":half.get("gates",{}).get("physical_ledger",{}).get("result","UNMEASURED"),
 "functional_joint_result":functional.get("gates",{}).get("joint","UNMEASURED"),
 "budget":read(ROOT/"budget-summary.json"),"formal_31_started":0,"automatic_next_run":False,
 "old_failed_and_STOPPED_records_preserved":e["original_frozen_permission_ledger_stop_records_unchanged"]}
save(ROOT/"qualification-summary.json",summary)
if not passed:
 save(ROOT/"STOPPED.json",{"case_id":CID,"why":completion["completion_failure"] or "scientific "+result,
 "scientific":result,"actual_end_s":completion["actual_end_s"],"global_start_count":e["conservative_starts_after"],
 "next_case_or_retry_authorized":False,"old_STOPPED_state":"Preserved; separate final qualification only."})
else:
 save(ROOT/"QUALIFICATION_COMPLETED.json",{"candidate_id":m["candidate_id"],"numerical_pair_s":[.000125,.0000625],
 "baseline_commit":b["commit"],"baseline_RAW_sha256":b["raw_sha256"],"halfstep_RAW_sha256":new_sha,
 "qualification_result":"PASS","global_starts":e["conservative_starts_after"],"formal_31_authorized":False,
 "summary_sha256":sha(ROOT/"qualification-summary.json"),"completed_at":now()})
save(ROOT/"RUN_FINISHED_NO_FORMAL.json",{"full_two_run_qualification_completed":passed,"no_further_solver_runs":True,
 "formal_31_started":0,"global_starts":e["conservative_starts_after"]})
progress("finished",qualification_result=result,full_two_run_qualification_completed=passed)
print(json.dumps({"qualification_result":result,"full_two_run_qualification_completed":passed,
 "comparison_result":summary["comparison_result"],"physical_ledger_result":summary["physical_ledger_result"],
 "functional_joint_result":summary["functional_joint_result"],"judge_wall_s":binding["judge_wall_s"],
 "global_starts":e["conservative_starts_after"]},indent=2))

