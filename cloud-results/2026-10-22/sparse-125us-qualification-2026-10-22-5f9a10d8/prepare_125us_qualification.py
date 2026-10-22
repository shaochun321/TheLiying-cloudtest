#!/usr/bin/env python3
"""Prepare the explicitly authorized 125/62.5us qualification; no solve."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import copy,difflib,hashlib,json,shutil,uuid
OLD=Path("/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea")
ROOT=OLD.parent/("sparse-125us-qualification-2026-10-22-"+uuid.uuid4().hex[:8])
ROOT.mkdir(exist_ok=False);(ROOT/"inputs").mkdir()
def sha(p):
 with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n")
m=json.loads((OLD/"CANDIDATE_MANIFEST.json").read_text())
manifest=copy.deepcopy(m)
manifest.update({"candidate_id":"SPARSE_GEAR_125us_original_physics_2026-10-22","run_id":ROOT.name,
 "created_at_Asia_Shanghai":datetime.now(timezone(timedelta(hours=8))).isoformat(),
 "source_qualification_commit":"f2d843e77fdf444268db91cef89a38bff60bbf30",
 "source_short_diagnostic_commit":"a03a7889e842ac0a83a6909788c45d47d57520a0",
 "source_task_document_sha256":sha("/workspace/attachments/02e2dfff-8921-41e9-8c8d-ef36a10b2b77/短程收敛诊断收口与完整资格建议.md"),
 "only_solver_configuration_delta":"Relative to executed SPARSE baseline: max step 250us to 125us; new half-step 62.5us. Physics/input/tolerances/save/scientific code unchanged.",
 "numerical_pair_s":[.000125,.0000625],"qualification_phase_wall_cap_s":3600,
 "baseline_global_starts":31,"unused_diagnostic_allocation":1,
 "budget_reallocation":{"from_unused_diagnostic":1,"to_candidate_qualification":1,
 "qualification_before":1,"qualification_after":2,"diagnostic_before":2,"diagnostic_after":1},
 "old_qualification_result":"FAIL_UNCHANGED"})
model=ROOT/"inputs/c05_ekv26_typ.lib";shutil.copy2(m["model_card"]["path"],model)
manifest["model_card"]={"path":str(model),"sha256":sha(model)}
manifest["protected_original_records"] += [
 {"path":str(OLD/n),"exists":True,"sha256":sha(OLD/n)}
 for n in ["STOPPED.json","qualification-ledger.jsonl"]]
manifest["cases"]={}
source_deck=(OLD/"runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.cir").read_text()
for cid,step,cap in [("Q1_MOTHER_PROTOCOL",.000125,1200),("Q1_MOTHER_HALFSTEP",.0000625,2400)]:
 run=ROOT/"runs"/cid;run.mkdir(parents=True)
 plan=json.loads((OLD/"runs"/cid/"plan.json").read_text())
 analysis=f"tran 0.001 100.27 0 {step:.8f}".rstrip("0")
 plan["case"].update({"max_step_s":step,"timeout_s":cap,"analysis":analysis})
 plan.update({"wall_clock_cap_s":cap,"numerical_pair_s":[.000125,.0000625],
 "candidate_scope":"new 125us baseline and 62.5us half-step; old registry is provenance only"})
 raw=run/(cid+".raw");deck=run/(cid+".cir")
 text=source_deck.replace("tran 0.001 100.27 0 0.00025",analysis)
 text=text.replace(m["model_card"]["path"],str(model))
 text=text.replace(str(OLD/"runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.raw"),str(raw))
 # Normalize only explicitly authorized step and runtime paths to prove remaining deck identical.
 normal=text.replace(analysis,"tran 0.001 100.27 0 0.00025").replace(str(model),m["model_card"]["path"]).replace(str(raw),str(OLD/"runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.raw"))
 assert normal==source_deck
 assert ".options sparse method=gear reltol=1e-5 abstol=1e-16" in text
 deck.write_text(text,encoding="ascii")
 plan.update({"deck":str(deck),"deck_sha256":sha(deck),"source_deck_sha256":sha(OLD/"runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.cir"),
 "identity_sha256":hashlib.sha256(text.encode("ascii")).hexdigest()})
 plan["prerequisite"]=None if cid=="Q1_MOTHER_PROTOCOL" else "THIS new 125us candidate completion, functional and all physical gates PASS"
 save(run/"plan.json",plan)
 (run/"source-deck.diff").write_text("".join(difflib.unified_diff(source_deck.splitlines(True),text.splitlines(True),fromfile="old_executed_sparse_250us",tofile=cid)))
 manifest["cases"][cid]={"directory":str(run),"plan_sha256":sha(run/"plan.json"),"analysis":analysis,"deadline_s":cap}
save(ROOT/"CANDIDATE_MANIFEST.json",manifest)
save(ROOT/"QUALIFICATION_AUTHORIZATION.json",{
 "user_instruction":"请执行。","scope_document":"短程收敛诊断收口与完整资格建议.md",
 "manifest_sha256":sha(ROOT/"CANDIDATE_MANIFEST.json"),"authorized_cases":list(manifest["cases"]),
 "formal_31_authorized":False,"parameter_tuning_authorized":False,"max_solver_starts":2,
 "case_wall_caps_s":[1200,2400],"qualification_phase_wall_cap_s":3600,"global_start_cap":65,
 "baseline_global_starts":31,"unused_diagnostic_reallocated_to_qualification":1,
 "stop_on_any_failure":True,"old_STOPPED_round_resume":False,"automatic_retries":0})
runner=(OLD/"run_qualification.py").read_text()
runner=runner.replace('before = 29 + len(starts)','before = 31 + len(starts)')
runner=runner.replace('if 65 - (before + 1) < 34:','if 65 - (before + 1) < 32:')
runner=runner.replace('31 formal and 3 unused diagnostic starts','31 formal and 1 unused diagnostic starts')
runner=runner.replace('with (run / "one-shot-reservation.json")', '''wall_cap = info["deadline_s"]
prior_wall = sum(x.get("wall_s",0) for x in records if x["rec"]=="end")
if prior_wall + wall_cap > 3600:
    raise SystemExit("New candidate qualification 3600s phase cap exceeded.")
assert wall_cap == (1200 if CID == "Q1_MOTHER_PROTOCOL" else 2400)
with (run / "one-shot-reservation.json")''')
runner=runner.replace('"wall_cap_s": 600','"wall_cap_s": wall_cap')
runner=runner.replace('"wall_clock_cap_s": 600, "kill_dispatch_s": 599.9','"wall_clock_cap_s": wall_cap, "kill_dispatch_s": wall_cap - 0.1')
runner=runner.replace('inside the 600s limit','inside the authorized per-case limit')
runner=runner.replace('"reserved_wall_s": 600','"reserved_wall_s": wall_cap')
runner=runner.replace('599.9 - (time.monotonic() - t0)','wall_cap - 0.1 - (time.monotonic() - t0)')
runner=runner.replace('execution["elapsed_solver_wall_s"] <= 600','execution["elapsed_solver_wall_s"] <= wall_cap')
runner=runner.replace('"baseline_global_starts": 29','"baseline_global_starts": 31')
runner=runner.replace('29 + nstarts','31 + nstarts').replace('65 - 29 - nstarts','65 - 31 - nstarts')
runner=runner.replace('"unused_diagnostic_allocation": 3','"unused_diagnostic_allocation": 1')
runner=runner.replace('"solver_wall_charge_this_round_s": wall_charge,','"solver_wall_charge_this_round_s": wall_charge, "phase_wall_cap_s": 3600, "phase_remaining_wall_s": 3600-wall_charge,')
# Reuse original memory-mapped reader for offline judging only; original completion remains unchanged.
runner=runner.replace('from solver_adapter.read_raw import read_raw','from solver_adapter.read_raw_mmap import read_raw_mmap as read_raw')
runner=runner.replace('save(run / "judge-output.json", out)', '''save(run / "judge-output.json", out)
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
    combined_result = "FAIL" if "FAIL" in [combined_result,functional_confirmation["result"]] else "UNMEASURED"''')
runner=runner.replace('"scientific": out["result"]','"scientific": combined_result')
runner=runner.replace('if out["result"] != "PASS" or','if combined_result != "PASS" or')
runner=runner.replace('("scientific " + out["result"])','("scientific " + combined_result)')
runner=runner.replace('"judge_output_sha256": sha(run / "judge-output.json"),','"judge_output_sha256": sha(run / "judge-output.json"), "functional_confirmation_result": functional_confirmation["result"] if functional_confirmation is not None else None, "numerical_pair_s": manifest["numerical_pair_s"],')
# Validate numerical metadata and a single explicit transient command before reservation.
needle='records = [json.loads(x)'
runner=runner.replace(needle,'''lines=Path(plan["deck"]).read_text().splitlines()
analyses=[x.strip() for x in lines if x.strip().lower().startswith(("tran ","op ","dc ","ac ","run","resume"))]
if analyses != [plan["case"]["analysis"]]:
    raise SystemExit("Unexpected explicit solver analysis.")
assert manifest["numerical_pair_s"] == [.000125,.0000625]
assert plan["case"]["max_step_s"] == (.000125 if CID=="Q1_MOTHER_PROTOCOL" else .0000625)
records = [json.loads(x)''')
(ROOT/"run_qualification.py").write_text(runner)
# Syntax verification only; no simulation or test launches.
compile(runner,str(ROOT/"run_qualification.py"),"exec")
shutil.copy2(OLD/"export_evidence.py",ROOT/"export_evidence.py")
shutil.copy2(OLD/"restore_raw.py",ROOT/"restore_raw.py")
save("/workspace/qualification-125us-current.json",{"root":str(ROOT),"branch":"qualification/"+ROOT.name})
print(json.dumps({"root":str(ROOT),"numerical_pair_s":manifest["numerical_pair_s"],"caps":[1200,2400],"solver_starts":0},indent=2))

