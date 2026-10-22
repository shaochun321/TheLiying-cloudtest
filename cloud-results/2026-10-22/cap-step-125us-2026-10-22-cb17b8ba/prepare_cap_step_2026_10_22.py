#!/usr/bin/env python3
"""Prepare one bounded time-step diagnostic; no solver launch."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, importlib.util, json, difflib, uuid
import numpy as np

BASE = Path("/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea")
RAW = BASE/"runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.raw"
EXPECTED = "69c950786ca768d5918f5dd79c716c0e7f8b75369f490c071c21acc5b2db7f23"
ROOT = Path("/workspace/thermal-g3-diagnostics")/("cap-step-125us-2026-10-22-"+uuid.uuid4().hex[:8])
ROOT.mkdir(parents=True, exist_ok=False)
def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
# One checksum of the original full RAW in this task.
actual_sha=sha(RAW)
if actual_sha!=EXPECTED:
    raise ValueError("Original RAW identity mismatch.")
header={};names=[]
with RAW.open("rb") as f:
    while True:
        line=f.readline()
        if not line:raise ValueError("Missing RAW header")
        s=line.decode("latin1").strip()
        if s.startswith("No. Variables:"):header["nv"]=int(s.split(":",1)[1])
        elif s.startswith("No. Points:"):header["np"]=int(s.split(":",1)[1])
        elif s.startswith("Flags:"):header["flags"]=s.split(":",1)[1].strip()
        elif s=="Variables:":
            for _ in range(header["nv"]):names.append(f.readline().decode("latin1").split()[1].lower())
        elif s=="Binary:":offset=f.tell();break
assert header["flags"]=="real" and RAW.stat().st_size==offset+header["nv"]*header["np"]*8
matrix=np.memmap(RAW,mode="r",dtype="<f8",offset=offset,shape=(header["np"],header["nv"]))
v={name:matrix[:,i] for i,name in enumerate(names)}
end_index=int(np.searchsorted(v["time"],20.5,side="right")-1)
b=float(v["time"][end_index]);n=end_index+1
assert 20.49<b<=20.5 and np.all(np.diff(v["time"][:n])>0)
cap_script=Path("/workspace/attachments/29d26056-a79b-4adc-8880-631f6c93d77f/cap_energy_forensics.py")
spec=importlib.util.spec_from_file_location("cap_analysis_only",cap_script)
cap=importlib.util.module_from_spec(spec);spec.loader.exec_module(cap)
baseline={"scope":"OFFLINE_DIAGNOSTIC_COMMON_INTERVAL_ONLY","source_RAW_sha256":actual_sha,
    "raw_sha256_checks_this_task":1,"common_end_s":b,"original_points_in_interval":n,
    "original_last_index":end_index,"original_global_result":"FAIL_UNCHANGED",
    "start_s":float(v["time"][0]),"end_s":b,"max_step_s":.00025,"capacitors":{}}
for name,key,C in [("cg0_cm","i(va_cg0_cm_p)",1e-7),("cpar_g0_vm","i(va_cpar_g0_vm_p)",5e-14)]:
    baseline["capacitors"][name]=cap.analyze(v["time"][:n],v["v(g0_vm)"][:n],v[key][:n],C)
(ROOT/"baseline_common_interval.json").write_text(json.dumps(baseline,indent=2)+"\n")
olddeck=(BASE/"runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.cir").read_text()
model=ROOT/"c05_ekv26_typ.lib";model.write_bytes((BASE/"inputs/c05_ekv26_typ.lib").read_bytes())
newraw=ROOT/"cap_step_125us.raw";newdeck=olddeck
oldanalysis="tran 0.001 100.27 0 0.00025";newanalysis=f"tran 0.001 {b:.17g} 0 0.000125"
assert olddeck.count(oldanalysis)==1
newdeck=newdeck.replace(oldanalysis,newanalysis)
for old,new in [(str(BASE/"inputs/c05_ekv26_typ.lib"),str(model)),
                (str(RAW),str(newraw))]:
    assert newdeck.count(old)==1;newdeck=newdeck.replace(old,new)
assert ".options sparse method=gear reltol=1e-5 abstol=1e-16" in newdeck
(ROOT/"cap_step_125us.cir").write_text(newdeck,encoding="ascii",newline="\n")
(ROOT/"actual-deck.diff").write_text("".join(difflib.unified_diff(olddeck.splitlines(True),newdeck.splitlines(True),
    fromfile="Sparse_250us_full_baseline",tofile="Sparse_125us_common_interval")))
common250=oldanalysis.replace("100.27",f"{b:.17g}")
(ROOT/"step-only.diff").write_text("".join(difflib.unified_diff([common250+"\n"],[newanalysis+"\n"],
    fromfile="existing_250us_RAW_common_interval",tofile="one_new_125us_run")))
manifest=json.loads((BASE/"CANDIDATE_MANIFEST.json").read_text())
plan={"run_id":ROOT.name,"purpose":"One separately authorized short common-endpoint time-step diagnostic.",
    "user_instruction":"评审后执行","task_document":"能量误差定位结果与单次短程收敛对照.md",
    "task_document_sha256":sha("/workspace/attachments/1925f041-9006-439b-8d4e-2e288fc5b156/能量误差定位结果与单次短程收敛对照.md"),
    "baseline_commit":"f2d843e77fdf444268db91cef89a38bff60bbf30",
    "analysis_results_commit":"ceec06245873ac1f2a4507861a8e251ca1c6e582",
    "original_RAW_path":str(RAW),"original_RAW_sha256":actual_sha,"original_RAW_checksums_this_task":1,
    "common_end_s":b,"baseline_points_in_common_interval":n,"baseline_max_step_s":.00025,
    "new_max_step_s":.000125,"analysis_command":newanalysis,"output_increment_s":.001,
    "deck_path":str(ROOT/"cap_step_125us.cir"),"deck_sha256":sha(ROOT/"cap_step_125us.cir"),
    "raw_path":str(newraw),"model_path":str(model),"model_sha256":sha(model),
    "backend":manifest["backend"],"spice_scripts":manifest["spice_scripts"],
    "required_vectors":[line for line in newdeck.splitlines() if line.startswith(".save ")][0].split()[1:],
    "cap_analysis_script":str(cap_script),"cap_analysis_script_sha256":sha(cap_script),
    "start_count_before":30,"start_count_after_if_launched":31,"global_start_cap":65,
    "max_solver_starts":1,"wall_cap_s":600,"automatic_retries":0,
    "diagnostic_allocation_before":3,"diagnostic_allocation_after_if_launched":2,
    "qualification_or_formal_authorized":False,"old_STOPPED_round_resume_authorized":False,
    "event_comparison":{"nodes":["v(g0_q)","v(g0_op_aq)","v(g0_op_p)"],"threshold_V":1.5,
       "edge_interpolation":"linear between original neighboring samples",
       "time_tolerance_reference_s":.0005,"reference":"existing half-step timing tolerance, not a qualification verdict"},
    "membrane_comparison":{"peak_relative_tolerance_reference":.01,"voltage_floor_V":.010,
       "independent_grid_s":.001,"metrics":["max_abs_difference","RMSE","normalized_RMSE"],
       "note":"Interpolate only for comparison metrics; never interpolate/smooth values used in energy analysis."},
    "protected_original_records":manifest["protected_original_records"]+[
       {"path":str(BASE/"STOPPED.json"),"exists":True,"sha256":sha(BASE/"STOPPED.json")},
       {"path":str(BASE/"qualification-ledger.jsonl"),"exists":True,"sha256":sha(BASE/"qualification-ledger.jsonl")}],
    "created_at_Asia_Shanghai":datetime.now(timezone(timedelta(hours=8))).isoformat()}
(ROOT/"test-plan.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n")
Path("/workspace/cap-step-current.json").write_text(json.dumps({"root":str(ROOT),"run_id":ROOT.name,"branch":"diagnostics/"+ROOT.name},indent=2)+"\n")
print(json.dumps({"root":str(ROOT),"common_end_s":b,"baseline_points":n,"analysis":newanalysis,
    "baseline_caps":{k:{key:d[key] for key in ["signed_mismatch_J","charge_consistency_term_J","product_quadrature_term_J","relative_mismatch"]} for k,d in baseline["capacitors"].items()},
    "new_solver_starts":0},indent=2))

