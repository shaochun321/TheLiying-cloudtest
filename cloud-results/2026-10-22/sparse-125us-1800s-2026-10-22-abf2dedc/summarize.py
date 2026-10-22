#!/usr/bin/env python3
"""Summarize this one newly authorized mother rerun; never solves."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json
r=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
d=r/"runs/Q1_MOTHER_PROTOCOL"
if not (d/"verdict-binding.json").exists():raise SystemExit("Solver or original judging still running.")
binding=read(d/"verdict-binding.json");completion=read(d/"completion.json")
execution=read(d/"execution.json");judge=read(d/"judge-output.json")
assert execution["actual_solver_launches"]==1 and execution["solver_process_reaped"]
assert sha(d/"judge-output.json")==binding["judge_output_sha256"]
def gates(value,path=""):
 out=[]
 if isinstance(value,dict):
  for k,v in value.items():
   key=path+"."+k if path else k
   if k in ["result","joint"] and isinstance(v,str) and v in ["PASS","FAIL","UNMEASURED"]:
    out.append({"gate":key,"outcome":v})
   elif isinstance(v,(list,dict)):out+=gates(v,key)
 elif isinstance(value,list):
  for k,v in enumerate(value):out+=gates(v,path+"["+str(k)+"]")
 return out
allg=gates(judge)
status=binding["scientific"]
summary={"scope":"ONE_125us_FULL_MOTHER_ONLY_NOT_TWO_RUN_QUALIFICATION",
 "candidate_id":read(r/"CANDIDATE_MANIFEST.json")["candidate_id"],
 "mother_result":status,"full_two_run_qualification_completed":False,"halfstep_started":False,
 "execution":execution,"completion":completion,"verdict_binding":binding,
 "gate_outcomes":allg,"first_nonpassing_gate_paths":[x for x in allg if x["outcome"]!="PASS"][:20],
 "budget":read(r/"budget-summary.json"),"old_qualification":"FAIL_UNCHANGED",
 "automatic_next_run":False,"formal_runs_started":0,
 "finished_at_Asia_Shanghai":datetime.now(timezone(timedelta(hours=8))).isoformat()}
(r/"qualification-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
(r/"RUN_FINISHED_NO_FURTHER_RUN.json").write_text(json.dumps({"mother_result":status,
 "full_two_run_qualification_completed":False,"halfstep_started":False,
 "no_automatic_formal_or_additional_solver_runs":True,"global_starts_after":summary["budget"]["global_starts_after"]},indent=2)+"\n")
print(json.dumps({"mother_result":status,"completion":completion,"gate_outcomes":allg,
 "budget":summary["budget"],"full_two_run_qualification_completed":False},indent=2))

