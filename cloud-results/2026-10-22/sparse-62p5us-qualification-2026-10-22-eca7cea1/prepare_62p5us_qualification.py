#!/usr/bin/env python3
"""Prepare one authorized 62.5us comparison; no solver launch."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import copy,difflib,hashlib,json,shutil,uuid
BASE=Path("/workspace/thermal-g3-qualification/sparse-125us-1800s-2026-10-22-abf2dedc")
ROOT=BASE.parent/("sparse-62p5us-qualification-2026-10-22-"+uuid.uuid4().hex[:8])
ROOT.mkdir(exist_ok=False);(ROOT/"inputs").mkdir()
def sha(p):
 with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n")
m=json.loads((BASE/"CANDIDATE_MANIFEST.json").read_text())
budget=json.loads((BASE/"budget-summary.json").read_text())
binding_path=BASE/"runs/Q1_MOTHER_PROTOCOL/verdict-binding.json"
bound=json.loads(binding_path.read_text());baseline_raw=Path(bound["raw_path"])
assert bound["scientific"]=="PASS" and bound["complete_transient"] and bound["actual_end_s"]==100.27
assert sha(BASE/"CANDIDATE_MANIFEST.json")==bound["candidate_manifest_sha256"]
assert sha(bound["judge_output_path"])==bound["judge_output_sha256"]
# Exactly one cryptographic check of the old baseline RAW in this task.
base_sha=sha(baseline_raw)
assert base_sha==bound["raw_sha256"]=="f62e385ac452b5e33a0a324787ddd949214489de5c1d9d0e85f845d2d38ea203"
st=baseline_raw.stat()
baseline={"commit":"664866bdafada095112d76c93109c07c9556af8a",
 "raw_path":str(baseline_raw),"raw_sha256":base_sha,"raw_checksum_count_this_task":1,
 "raw_size":st.st_size,"raw_mtime_ns":st.st_mtime_ns,
 "verdict_binding_path":str(binding_path),"verdict_binding_sha256":sha(binding_path),
 "judge_output_path":bound["judge_output_path"],"judge_output_sha256":bound["judge_output_sha256"],
 "scientific":"PASS","complete_transient":True,"actual_end_s":100.27,"max_step_s":.000125}
save(ROOT/"baseline-reference.json",baseline)
shutil.copy2(binding_path,ROOT/"inputs/baseline-verdict-binding.json")
shutil.copy2(bound["judge_output_path"],ROOT/"inputs/baseline-judge-output.json")
manifest=copy.deepcopy(m)
prior=budget["phase_total_charged_wall_s"]
assert budget["global_starts_after"]==33 and budget["unused_diagnostic_allocation"]==1
assert prior+3600<=7200
manifest.update({"run_id":ROOT.name,"created_at_Asia_Shanghai":datetime.now(timezone(timedelta(hours=8))).isoformat(),
 "purpose":"Single final 62.5us full numerical qualification against bound 125us PASS; no formal runs.",
 "source_task_document_sha256":sha("/workspace/attachments/01336110-b15b-4901-9826-9c32c4c216e0/母本通过裁定与最后一项资格对照建议.md"),
 "baseline_global_starts":33,"max_qualification_starts":1,"unused_diagnostic_allocation":0,
 "qualification_phase_wall_cap_s":7200,"qualification_phase_prior_charged_wall_s":prior,
 "only_solver_configuration_delta":"Relative to bound PASS 125us: max step 125us to 62.5us and runtime file paths only.",
 "numerical_pair_s":[.000125,.0000625],"passed_baseline":baseline,
 "budget_reallocation":{"from_unused_diagnostic":1,"to_final_qualification":1,
 "diagnostic_before":1,"diagnostic_after":0,"reserved_formal_starts":31},
 "baseline_reference_sha256":sha(ROOT/"baseline-reference.json")})
manifest["protected_original_records"] += [
 {"path":str(BASE/n),"exists":True,"sha256":sha(BASE/n)} for n in
 ["CANDIDATE_MANIFEST.json","QUALIFICATION_AUTHORIZATION.json","qualification-ledger.jsonl",
  "RUN_FINISHED_NO_FURTHER_RUN.json","runs/Q1_MOTHER_PROTOCOL/verdict-binding.json"]]
model=ROOT/"inputs/c05_ekv26_typ.lib";shutil.copy2(m["model_card"]["path"],model)
manifest["model_card"]={"path":str(model),"sha256":sha(model)}
cid="Q1_MOTHER_HALFSTEP";run=ROOT/"runs"/cid;run.mkdir(parents=True)
plan=json.loads((BASE/"runs/Q1_MOTHER_PROTOCOL/plan.json").read_text())
old_deck=Path(plan["deck"]).read_text();raw=run/(cid+".raw");deck=run/(cid+".cir")
old_analysis="tran 0.001 100.27 0 0.000125";analysis="tran 0.001 100.27 0 0.0000625"
assert old_deck.count(old_analysis)==1
text=old_deck.replace(old_analysis,analysis).replace(m["model_card"]["path"],str(model)).replace(str(baseline_raw),str(raw))
normal=text.replace(analysis,old_analysis).replace(str(model),m["model_card"]["path"]).replace(str(raw),str(baseline_raw))
assert normal==old_deck
deck.write_text(text,encoding="ascii")
plan["case"].update({"case_id":cid,"analysis":analysis,"max_step_s":.0000625,"timeout_s":3600,
 "baseline_case_id":"Q1_MOTHER_PROTOCOL","depends_on":["Q1_MOTHER_PROTOCOL"],"judge":"halfstep_compare.compare"})
plan.update({"deck":str(deck),"deck_sha256":sha(deck),"identity_sha256":sha(deck),
 "source_deck_sha256":sha(BASE/"runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.cir"),
 "wall_clock_cap_s":3600,"prerequisite":"Bound 664866b 125us mother completion + all original science PASS.",
 "candidate_scope":"One 62.5us full halfstep against passed 125us, with its own original functional and physical gates.",
 "baseline_reference_sha256":sha(ROOT/"baseline-reference.json"),
 "comparison_timing_tolerance_s":.00025})
save(run/"plan.json",plan)
(run/"source-deck.diff").write_text("".join(difflib.unified_diff(old_deck.splitlines(True),text.splitlines(True),fromfile="bound_PASS_125us",tofile="new_62p5us")))
(ROOT/"step-only.diff").write_text("".join(difflib.unified_diff([old_analysis+"\n"],[analysis+"\n"],fromfile="PASS_125us",tofile="62p5us")))
manifest["cases"]={cid:{"directory":str(run),"plan_sha256":sha(run/"plan.json"),"analysis":analysis,"deadline_s":3600}}
save(ROOT/"CANDIDATE_MANIFEST.json",manifest)
save(ROOT/"QUALIFICATION_AUTHORIZATION.json",{"user_instruction":"评审后执行",
 "scope_document":"母本通过裁定与最后一项资格对照建议.md","manifest_sha256":sha(ROOT/"CANDIDATE_MANIFEST.json"),
 "authorized_cases":[cid],"max_solver_starts":1,"case_wall_cap_s":3600,"qualification_phase_wall_cap_s":7200,
 "qualification_phase_prior_charged_wall_s":prior,"baseline_global_starts":33,"global_start_cap":65,
 "last_diagnostic_start_reallocated_to_qualification":1,"formal_31_authorized":False,
 "parameter_tuning_authorized":False,"automatic_retries":0,"stop_on_any_failure":True,
 "old_STOPPED_round_resume":False})
for name in ["export_evidence.py","restore_raw.py","progress.py"]:
 shutil.copy2(BASE/name,ROOT/name)
save("/workspace/qualification-62p5us-current.json",{"root":str(ROOT),"branch":"qualification/"+ROOT.name})
print(json.dumps({"root":str(ROOT),"baseline_SHA_verified_once":base_sha,"starts_before":33,
 "starts_after_if_launched":34,"case_wall_cap_s":3600,"phase_prior_s":prior,"phase_cap_s":7200,
 "remaining_formal_starts_after":31,"solver_starts_now":0},indent=2))

