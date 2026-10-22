#!/usr/bin/env python3
"""Build the 31 authorized formal cases and evaluate the original prelaunch cost gate.
No solver invocation. No historical contract is modified.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import copy,csv,difflib,hashlib,json,shutil,sys,uuid
QUAL=Path("/workspace/thermal-g3-qualification/sparse-62p5us-qualification-2026-10-22-eca7cea1")
BASE=Path("/workspace/thermal-g3-qualification/sparse-125us-1800s-2026-10-22-abf2dedc")
qm=json.loads((QUAL/"CANDIDATE_MANIFEST.json").read_text());software=Path(qm["source_software"])
ROOT=Path("/workspace/thermal-g3-formal")/("formal-sparse125us-2026-10-22-"+uuid.uuid4().hex[:8])
ROOT.mkdir(parents=True,exist_ok=False);(ROOT/"inputs").mkdir()
def sha(p):
 with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False,default=float)+"\n")
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
q=json.loads((QUAL/"QUALIFICATION_COMPLETED.json").read_text())
assert q["qualification_result"]=="PASS" and q["global_starts"]==34
assert sha(QUAL/"qualification-summary.json")==q["summary_sha256"]
# Small bound PASS records only; do not reread/repackage either qualification RAW.
qualified=[]
for parent,cid in [(BASE,"Q1_MOTHER_PROTOCOL"),(QUAL,"Q1_MOTHER_HALFSTEP")]:
 d=parent/"runs"/cid;b=json.loads((d/"verdict-binding.json").read_text());e=json.loads((d/"execution.json").read_text())
 assert b["scientific"]=="PASS" and b["complete_transient"] and b["actual_end_s"]==100.27
 assert sha(b["judge_output_path"])==b["judge_output_sha256"]
 qualified.append({"case_id":cid,"scale":"mother_bench","wall_s":e["elapsed_solver_wall_s"],
 "raw_sha256":b["raw_sha256"],"binding_path":str(d/"verdict-binding.json"),"binding_sha256":sha(d/"verdict-binding.json")})
 shutil.copy2(d/"verdict-binding.json",ROOT/"inputs"/(cid+"-qualification-binding.json"))
for rel,want in qm["software_files_unchanged_from_verified_host"].items():
 assert sha(software/rel)==want,rel
sys.path.insert(0,str(software))
from runtime import decks
from runtime.coordinator import Coordinator
import config
registry=decks.registry();formal=[c for c in registry["cases"] if c["phase"]=="formal"]
assert len(formal)==31
mapped={};mapping=[]
for original in formal:
 c=copy.deepcopy(original)
 if c["analysis"]!="op":
  if c["case_id"] in ["NUM_G0_HALFSTEP","NUM_CHAIN_HALFSTEP","FULL_NUM_HALFSTEP"]:
   base=mapped[c["baseline_case_id"]]
   step=min(c["max_step_s"],base["max_step_s"]/2)
   assert step==base["max_step_s"]/2
  else:step=min(c["max_step_s"],.000125)
  assert step<=c["max_step_s"]
  c["max_step_s"]=step;c["analysis"]=c["analysis"].rsplit(" ",1)[0]+" "+f"{step:.8f}".rstrip("0")
 mapped[c["case_id"]]=c
 mapping.append({"case_id":c["case_id"],"old_max_step_s":original.get("max_step_s"),"new_max_step_s":c.get("max_step_s"),
 "old_analysis":original["analysis"],"new_analysis":c["analysis"],"timeout_s":c["timeout_s"],
 "baseline_case_id":c.get("baseline_case_id"),"depends_on":c["depends_on"]})
model=ROOT/"inputs/c05_ekv26_typ.lib";shutil.copy2(qm["model_card"]["path"],model)
cases={};sizes={}
for cid in ["Q1_MOTHER_PROTOCOL","Q1_MOTHER_HALFSTEP"]:
 sizes[cid]=len(decks.case_assets(cid)["netlist"].elements)
for original in formal:
 cid=original["case_id"];c=mapped[cid];run=ROOT/"runs"/cid;run.mkdir(parents=True)
 a=decks.case_assets(cid);raw=run/(cid+".raw");deck=run/(cid+".cir")
 source,_=decks.deck_text(cid,raw_path=str(raw),model_lib=str(model),osdi=qm["backend"]["osdi"]["path"])
 old_options=".options "+decks.OPTIONS;new_options=".options sparse method=gear reltol=1e-5 abstol=1e-16"
 assert source.count(old_options)==1
 body=source.replace(old_options,new_options)
 if c["analysis"]!=original["analysis"]:
  assert body.count("\n"+original["analysis"]+"\n")==1
  body=body.replace("\n"+original["analysis"]+"\n","\n"+c["analysis"]+"\n")
 normalized=body.replace(new_options,old_options)
 if c["analysis"]!=original["analysis"]:normalized=normalized.replace("\n"+c["analysis"]+"\n","\n"+original["analysis"]+"\n")
 assert normalized==source
 deck.write_text(body,encoding="ascii",newline="\n")
 size=len(a["netlist"].elements);sizes[cid]=size
 plan={"case":c,"original_registered_case":original,"deck":str(deck),"deck_sha256":sha(deck),
 "original_runtime_deck_sha256":hashlib.sha256(source.encode("ascii")).hexdigest(),
 "physical_netlist_and_stimulus_unchanged_after_declared_numerical_normalization":True,
 "required_vectors":a["save"],"judge_required_vectors":a["required"],
 "physical_ledger_plan":a["plan"],"mos_nodes":a["mos_nodes"],
 "ammeters":[x for x in a["save"] if x.startswith("i(v") and x!="i(vsrc)" and not x.startswith("i(va_")],
 "element_count":size,"saved_vector_count":len(a["save"]),"wall_clock_cap_s":c["timeout_s"],
 "maximum_launches":1,"expected_solver_log":"Using SPARSE 1.3 as Direct Linear Solver"}
 save(run/"plan.json",plan)
 (run/"numerical-and-path.diff").write_text("".join(difflib.unified_diff(source.splitlines(True),body.splitlines(True),
 fromfile="original_registered_KLU",tofile="candidate_SPARSE")))
 cases[cid]={"directory":str(run),"plan_sha256":sha(run/"plan.json"),"deck_sha256":sha(deck),
 "elements":size,"save_vectors":len(a["save"]),"depends_on":c["depends_on"],
 "baseline_case_id":c["baseline_case_id"],"analysis":c["analysis"],"timeout_s":c["timeout_s"]}
for a in qualified:a["elements"]=sizes[a["case_id"]];a["wall_per_element_s"]=a["wall_s"]/a["elements"]
rate=max(x["wall_per_element_s"] for x in qualified)
rows=[]
for original in formal:
 cid=original["case_id"];estimate=min(original["timeout_s"],1.5*rate*sizes[cid])
 rows.append({"case_id":cid,"elements":sizes[cid],"scale":original["scale"],"hard_cap_s":original["timeout_s"],
 "forecast_s":estimate,"rate_source":"maximum completed qualification wall/element; unmeasured formal scale fallback"})
forecast=sum(x["forecast_s"] for x in rows)
budget=json.loads((QUAL/"budget-summary.json").read_text())
known_lower_bound=budget["phase_total_charged_wall_s"]
report={"gate":"Original Coordinator.cost_gate formula; max per-element measured rate, x1.5, cap each case.",
 "source_sha256":sha(software/"runtime/coordinator.py"),"measured_qualification_rates":qualified,
 "forecast_rows":rows,"formal_forecast_s":forecast,"formal_phase_cap_s":config.PHASE_WALL_CAP_S["formal"],
 "formal_phase_spent_s":0,"formal_phase_remaining_s":config.PHASE_WALL_CAP_S["formal"],
 "global_wall_cap_s":config.GLOBAL_WALL_CAP_S,"global_exact_historical_wall_s":None,
 "known_prior_wall_lower_bound_s":known_lower_bound,
 "global_remaining_optimistic_upper_bound_s":config.GLOBAL_WALL_CAP_S-known_lower_bound,
 "global_remaining_is_exact":False,
 "formal_phase_gate_pass":forecast<=config.PHASE_WALL_CAP_S["formal"],
 "global_gate_can_pass_even_under_optimistic_bound":forecast<=config.GLOBAL_WALL_CAP_S-known_lower_bound,
 "global_starts_before":34,"new_solver_starts":0,"total_registered_formal_hard_caps_s":sum(c["timeout_s"] for c in formal)}
report["dispatch_allowed"]=report["formal_phase_gate_pass"] and report["global_gate_can_pass_even_under_optimistic_bound"]
# Call the unmodified original cost gate with a bound read-only view of the
# measured qualifications; global time is explicitly only a lower-bound proof.
class BoundCostView:
 root=str(software)
 def records(self):
  records=[]
  for x in qualified:
   aid="bound-"+x["case_id"]
   records.extend([{"rec":"start","analysis_id":aid,"case_id":x["case_id"],"scale":x["scale"]},
                   {"rec":"end","analysis_id":aid,"status":"complete","wall_s":x["wall_s"]}])
  return records
 def status(self):
  return {"phases":{"formal":{"wall_s":0}},"total_wall_s":known_lower_bound}
try:
 observed=Coordinator.cost_gate(BoundCostView(),mapped["G0_W"],"formal",{"case_sizes":sizes})
 report["unmodified_original_gate_result"]={"allowed":True,"forecast_s":observed}
except Exception as exc:
 report["unmodified_original_gate_result"]={"allowed":False,"exception_type":type(exc).__name__,"message":str(exc),
 "global_status_input_is_documented_lower_bound_not_an_exact_balance":True}
save(ROOT/"COST_GATE_REPORT.json",report)
save(ROOT/"STEP_MAPPING.json",mapping)
with (ROOT/"STEP_MAPPING.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=["case_id","old_max_step_s","new_max_step_s","timeout_s","baseline_case_id"])
 w.writeheader();w.writerows({k:r[k] for k in w.fieldnames} for r in mapping)
save(ROOT/"DEPENDENCY_GRAPH.json",{"qualification_roots":[x["case_id"] for x in qualified],
 "formal_edges":{cid:c["depends_on"] for cid,c in cases.items()},"order":list(cases)})
manifest={"candidate_id":qm["candidate_id"],"run_id":ROOT.name,"prepared_at":now(),
 "source_software":str(software),"source_qualification_commit":"b76e734d52fa65665fc136a55f89a8a8c495fa64",
 "passed_qualification":q,"qualified_evidence":qualified,"source_software_sha256":qm["software_files_unchanged_from_verified_host"],
 "backend":qm["backend"],"model_card":{"path":str(model),"sha256":sha(model)},"spice_scripts":qm["spice_scripts"],
 "cases":cases,"case_sizes":sizes,"global_starts_before":34,"global_start_cap":65,"max_formal_starts":31,
 "formal_phase_wall_cap_s":108000,"global_wall_cap_s":172800,"automatic_retries":0,
 "old_freezes_permissions_STOPPED_ledgers":"No changes; this is a separate candidate formal contract.",
 "cost_gate_preserved":True,"cost_gate_report_sha256":sha(ROOT/"COST_GATE_REPORT.json")}
save(ROOT/"FORMAL_MANIFEST.json",manifest)
save(ROOT/"FORMAL_AUTHORIZATION.json",{"user_instruction":"执行吧","scope_document":"母本与双步长资格收口裁定.md",
 "manifest_sha256":sha(ROOT/"FORMAL_MANIFEST.json"),"authorized_case_ids":list(cases),
 "max_new_solver_starts":31,"global_start_cap":65,"formal_phase_wall_cap_s":108000,
 "global_wall_cap_s":172800,"automatic_retries":0,"new_diagnostics_authorized":False,
 "no_new_qualification_solves":True,"retain_original_dependencies_judges_and_cost_gate":True})
save(ROOT/"PREFLIGHT_STATUS.json",{"status":"READY" if report["dispatch_allowed"] else "BLOCKED_BY_ORIGINAL_COST_GATE",
 "actual_solver_launches":0,"global_starts_after":34,"cases_prepared":31,
 "no_original_records_modified":True,"blocked_before_reservation":not report["dispatch_allowed"]})
if not report["dispatch_allowed"]:
 save(ROOT/"NOT_STARTED.json",{"all_formal_cases":"NOT_STARTED","reason":"Original whole-matrix cost gate refused before first reservation.",
 "global_starts":34,"no_solver_or_extra_smoke_started":True,"forecast_s":forecast})
shutil.copy2("/workspace/prepare_formal_31.py",ROOT/"prepare_formal_31.py")
save("/workspace/formal-current.json",{"root":str(ROOT),"branch":"formal/"+ROOT.name})
print(json.dumps({"root":str(ROOT),"cases_prepared":31,"formal_forecast_s":forecast,
 "formal_cap_s":108000,"global_optimistic_remaining_s":report["global_remaining_optimistic_upper_bound_s"],
 "original_gate":report["unmodified_original_gate_result"],"dispatch_allowed":report["dispatch_allowed"],
 "new_solver_starts":0},indent=2))

