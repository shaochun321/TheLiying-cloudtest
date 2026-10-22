#!/usr/bin/env python3
"""Finish offline original judging after one documented data-layout correction.
Never imports or invokes a solver or resumes a stopped simulation.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,sys,time,traceback
import numpy as np
ROOT=Path(__file__).resolve().parent;run=ROOT/"runs/Q1_MOTHER_PROTOCOL"
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def save(p,v):
 tmp=Path(str(p)+".tmp")
 tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False,default=float)+"\n");tmp.replace(p)
manifest=read(ROOT/"CANDIDATE_MANIFEST.json");plan=read(run/"plan.json")
execution=read(run/"execution.json");completion=read(run/"completion.json")
correction=read(ROOT/"offline-read-layout-correction.json")
assert execution["solver_process_reaped"] and execution["returncode"]==0 and not execution["timed_out"]
assert execution["actual_solver_launches"]==1 and execution["conservative_starts_after"]==33
assert completion["completion_failure"] is None and completion["actual_end_s"]==100.27
assert not (run/"judge-output.json").exists() and not (run/"verdict-binding.json").exists()
with (ROOT/"offline-score-reservation.json").open("x") as f:
 json.dump({"started_at":now(),"offline_only":True,"maximum_layout_corrections":1,"new_solver_launches":0},f,indent=2)
t0=time.monotonic()
software=Path(manifest["source_software"])
for rel,want in manifest["software_files_unchanged_from_verified_host"].items():
 if rel.startswith(("observers/","analysis/","netlists/","prereg/protocol_")):
  assert sha(software/rel)==want,rel
raw=run/"Q1_MOTHER_PROTOCOL.raw"
actual_sha=sha(raw);assert actual_sha==completion["raw_sha256"]
sys.path.insert(0,str(software))
from solver_adapter.read_raw_mmap import read_raw_mmap
from observers.judges import judge
V=read_raw_mmap(str(raw))[-1];original_time=V["time"]
contiguous_time=np.ascontiguousarray(original_time)
assert np.array_equal(original_time.view(np.uint64),contiguous_time.view(np.uint64))
layout={"original_time_stride_bytes":original_time.strides[0],"corrected_time_stride_bytes":contiguous_time.strides[0],
 "points":len(original_time),"time_bit_patterns_identical":True,"interpolation":False,"resampling":False,
 "original_scientific_code_unchanged":True,"same_RAW_sha256":actual_sha,"new_solver_launches":0}
V["time"]=contiguous_time
save(ROOT/"offline-time-layout-verification.json",layout)
try:
 out=judge(plan["case"],V,None,plan["physical_ledger_plan"],ammeters=plan["ammeters"],mos_nodes=plan["mos_nodes"])
except Exception as exc:
 out={"result":"UNMEASURED","why":"Original judge raised "+repr(exc),"traceback":traceback.format_exc()}
save(run/"judge-output.json",out)
binding={"case_id":"Q1_MOTHER_PROTOCOL","scientific":out["result"],"candidate_manifest_sha256":sha(ROOT/"CANDIDATE_MANIFEST.json"),
 "deck_sha256":plan["deck_sha256"],"raw_path":str(raw),"raw_sha256":actual_sha,
 "judge_output_path":str(run/"judge-output.json"),"judge_output_sha256":sha(run/"judge-output.json"),
 "functional_confirmation_result":None,"numerical_pair_s":manifest["numerical_pair_s"],
 "judge_wall_s":time.monotonic()-t0,
 "abandoned_offline_analysis_wall_s":correction["first_analysis_wall_since_solver_exit_s"],
 "offline_layout_corrections":1,"new_solver_launches_during_correction":0,
 "complete_transient":True,"actual_end_s":completion["actual_end_s"],"global_start_count":33,
 "backend":manifest["backend"],"time_layout":layout}
save(run/"verdict-binding.json",binding)
with (ROOT/"qualification-ledger.jsonl").open("a") as f:f.write(json.dumps({"rec":"verdict","case_id":"Q1_MOTHER_PROTOCOL","t":now(),**binding},default=float)+"\n")
if out["result"]!="PASS":
 save(ROOT/"STOPPED.json",{"case_id":"Q1_MOTHER_PROTOCOL","why":"scientific "+out["result"],
  "scientific":out["result"],"actual_end_s":100.27,"global_start_count":33,"next_case_or_retry_authorized":False,
  "old_STOPPED_state":"Preserved; independent new round only."})
print(json.dumps({"scientific":out["result"],"judge_wall_s":binding["judge_wall_s"],"global_count":33,"new_solver_starts":0,"layout":layout},indent=2))

