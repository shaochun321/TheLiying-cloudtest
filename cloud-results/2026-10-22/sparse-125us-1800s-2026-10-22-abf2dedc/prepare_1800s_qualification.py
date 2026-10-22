#!/usr/bin/env python3
"""Prepare one newly authorized 1800-second rerun; no solver launch."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import copy,difflib,hashlib,json,shutil,uuid
OLD=Path("/workspace/thermal-g3-qualification/sparse-125us-qualification-2026-10-22-5f9a10d8")
ROOT=OLD.parent/("sparse-125us-1800s-2026-10-22-"+uuid.uuid4().hex[:8])
ROOT.mkdir(exist_ok=False);(ROOT/"inputs").mkdir()
def sha(p):
 with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n")
m=json.loads((OLD/"CANDIDATE_MANIFEST.json").read_text())
prior=json.loads((OLD/"budget-summary.json").read_text())["solver_wall_charge_this_round_s"]
assert prior<1200 and prior+1800<=3600
manifest=copy.deepcopy(m)
manifest.update({"run_id":ROOT.name,"created_at_Asia_Shanghai":datetime.now(timezone(timedelta(hours=8))).isoformat(),
 "source_timeout_commit":"4c61f50460616e705ffac9bbaa5efc5a30836765",
 "baseline_global_starts":32,"max_qualification_starts":1,
 "qualification_phase_prior_charged_wall_s":prior,
 "purpose":"One explicitly authorized 30-minute rerun of the 125us full mother only, no halfstep.",
 "numerical_pair_s":[.000125,.0000625],
 "only_solver_configuration_delta":"No science/numerical change from timed-out 125us candidate; per-run wall limit 1200 to 1800 seconds and runtime paths only."})
model=ROOT/"inputs/c05_ekv26_typ.lib";shutil.copy2(m["model_card"]["path"],model)
manifest["model_card"]={"path":str(model),"sha256":sha(model)}
manifest["protected_original_records"] += [
 {"path":str(OLD/n),"exists":True,"sha256":sha(OLD/n)}
 for n in ["STOPPED.json","qualification-ledger.jsonl","QUALIFICATION_AUTHORIZATION.json","CANDIDATE_MANIFEST.json"]]
cid="Q1_MOTHER_PROTOCOL";run=ROOT/"runs"/cid;run.mkdir(parents=True)
plan=json.loads((OLD/"runs"/cid/"plan.json").read_text())
olddeck=Path(plan["deck"]).read_text()
newraw=run/(cid+".raw");newdeck=run/(cid+".cir")
oldraw=OLD/"runs"/cid/(cid+".raw")
text=olddeck.replace(m["model_card"]["path"],str(model)).replace(str(oldraw),str(newraw))
assert text.replace(str(model),m["model_card"]["path"]).replace(str(newraw),str(oldraw))==olddeck
assert "tran 0.001 100.27 0 0.000125" in text
newdeck.write_text(text,encoding="ascii")
plan["case"]["timeout_s"]=1800
plan.update({"deck":str(newdeck),"deck_sha256":sha(newdeck),"identity_sha256":hashlib.sha256(text.encode("ascii")).hexdigest(),
 "source_deck_sha256":sha(OLD/"runs"/cid/(cid+".cir")),"wall_clock_cap_s":1800,
 "candidate_scope":"Only 125us mother rerun; 62.5us halfstep not authorized in this new round."})
save(run/"plan.json",plan)
(run/"source-deck.diff").write_text("".join(difflib.unified_diff(olddeck.splitlines(True),text.splitlines(True),fromfile="timed_out_125us",tofile="same_125us_new_paths")))
manifest["cases"]={cid:{"directory":str(run),"plan_sha256":sha(run/"plan.json"),"analysis":plan["case"]["analysis"],"deadline_s":1800}}
save(ROOT/"CANDIDATE_MANIFEST.json",manifest)
save(ROOT/"QUALIFICATION_AUTHORIZATION.json",{"user_instruction":"请你执行吧。上限为30分钟",
 "manifest_sha256":sha(ROOT/"CANDIDATE_MANIFEST.json"),"authorized_cases":[cid],
 "formal_31_authorized":False,"parameter_tuning_authorized":False,
 "halfstep_authorized_this_round":False,"max_solver_starts":1,"case_wall_caps_s":[1800],
 "qualification_phase_wall_cap_s":3600,"qualification_phase_prior_charged_wall_s":prior,
 "global_start_cap":65,"baseline_global_starts":32,"stop_on_any_failure":True,
 "old_STOPPED_round_resume":False,"automatic_retries":0})
runner=(OLD/"run_qualification.py").read_text()
runner=runner.replace("if len(starts) >= 2","if len(starts) >= 1")
runner=runner.replace("before = 31 + len(starts)","before = 32 + len(starts)")
runner=runner.replace('if prior_wall + wall_cap > 3600:', 'if manifest["qualification_phase_prior_charged_wall_s"] + prior_wall + wall_cap > 3600:')
runner=runner.replace('assert wall_cap == (1200 if CID == "Q1_MOTHER_PROTOCOL" else 2400)', 'assert wall_cap == 1800 and CID == "Q1_MOTHER_PROTOCOL"')
runner=runner.replace('"baseline_global_starts": 31','"baseline_global_starts": 32')
runner=runner.replace('31 + nstarts','32 + nstarts').replace('65 - 31 - nstarts','65 - 32 - nstarts')
runner=runner.replace('"qualification_allocation_unspent": 2 - nstarts','"qualification_allocation_unspent": 1 - nstarts')
runner=runner.replace('"phase_remaining_wall_s": 3600-wall_charge,',
 '"phase_remaining_wall_s": 3600-manifest["qualification_phase_prior_charged_wall_s"]-wall_charge, "phase_prior_charged_wall_s": manifest["qualification_phase_prior_charged_wall_s"], "phase_total_charged_wall_s": manifest["qualification_phase_prior_charged_wall_s"]+wall_charge,')
# One offline original completion pass, original science unchanged.
compile(runner,str(ROOT/"run_qualification.py"),"exec")
(ROOT/"run_qualification.py").write_text(runner)
for name in ["progress.py","export_evidence.py","restore_raw.py"]:
 shutil.copy2(OLD/name,ROOT/name)
save("/workspace/qualification-1800s-current.json",{"root":str(ROOT),"branch":"qualification/"+ROOT.name})
print(json.dumps({"root":str(ROOT),"maximum_new_starts":1,"wall_cap_s":1800,"phase_prior_charged_s":prior,"global_before":32,"global_after_if_launched":33,"solver_starts_now":0},indent=2))

