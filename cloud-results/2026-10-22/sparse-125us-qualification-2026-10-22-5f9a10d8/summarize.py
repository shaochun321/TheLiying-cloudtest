#!/usr/bin/env python3
"""Summarize completed evidence without solving or altering scientific outputs."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib
r=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
manifest=read(r/"CANDIDATE_MANIFEST.json")
cases={}
for cid,info in manifest["cases"].items():
 d=Path(info["directory"]);b=d/"verdict-binding.json"
 if b.exists():
  item={"state":"FINISHED","execution":read(d/"execution.json"),"completion":read(d/"completion.json"),
        "verdict_binding":read(b)}
  j=read(d/"judge-output.json")
  def outcomes(value,path=""):
   out=[]
   if isinstance(value,dict):
    for k,v in value.items():
     key=path+"."+k if path else k
     if k in ["result","joint"] and v in ["PASS","FAIL","UNMEASURED"]:out.append({"gate":key,"outcome":v})
     elif isinstance(v,(dict,list)):out+=outcomes(v,key)
   elif isinstance(value,list):
    for i,v in enumerate(value):out+=outcomes(v,path+"["+str(i)+"]")
   return out
  item["gate_outcomes"]=outcomes(j)
  if (d/"functional-confirmation.json").exists():
   item["halfstep_functional_gate_outcomes"]=outcomes(read(d/"functional-confirmation.json"))
  cases[cid]=item
 elif (d/"execution.json").exists():raise SystemExit("Case still executing or judging.")
 else:cases[cid]={"state":"NOT_STARTED"}
budget=read(r/"budget-summary.json")
both=all(v.get("verdict_binding",{}).get("scientific")=="PASS" and v.get("completion",{}).get("completion_failure") is None for v in cases.values())
status="PASS" if both else ("STOPPED" if (r/"STOPPED.json").exists() else "INCOMPLETE")
if status=="INCOMPLETE":raise SystemExit("Authorized conditional qualification still pending; do not finalize.")
summary={"candidate_id":manifest["candidate_id"],"numerical_pair_s":manifest["numerical_pair_s"],
 "status":status,"cases":cases,"budget":budget,"old_qualification":"FAIL_UNCHANGED",
 "formal_31_started":0,"automatic_retries":0,"old_STOPPED_round_resumed":False,
 "stop_record":read(r/"STOPPED.json") if (r/"STOPPED.json").exists() else None,
 "finished_at_Asia_Shanghai":datetime.now(timezone(timedelta(hours=8))).isoformat(),
 "manifest_sha256":sha(r/"CANDIDATE_MANIFEST.json")}
(r/"qualification-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
(r/"RUN_FINISHED_NO_FORMAL.json").write_text(json.dumps({"qualification_status":status,
 "no_automatic_formal_or_additional_solver_runs":True,"global_starts_after":budget["global_starts_after"]},indent=2)+"\n")
print(json.dumps({"status":status,"cases":{k:v.get("verdict_binding",{}).get("scientific",v["state"]) for k,v in cases.items()},"budget":budget},indent=2))

