#!/usr/bin/env python3
"""One offline common-interval comparison; never launches a solver."""
from pathlib import Path
import hashlib, importlib.util, json, re
import numpy as np
ROOT=Path(__file__).resolve().parent
def sha(p):
    with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(name,value):
    with (ROOT/name).open("x",encoding="utf8") as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write("\n")
p=json.loads((ROOT/"test-plan.json").read_text())
e=json.loads((ROOT/"execution.json").read_text())
assert (ROOT/"RUN_FINISHED_NO_RETRY.json").exists(),"Solver still running"
assert not (ROOT/"comparison.json").exists(),"Offline comparison already exists"
spec=importlib.util.spec_from_file_location("original_cap_analysis",p["cap_analysis_script"])
cap=importlib.util.module_from_spec(spec);spec.loader.exec_module(cap)
assert sha(p["cap_analysis_script"])==p["cap_analysis_script_sha256"]
baseline=json.loads((ROOT/"baseline_common_interval.json").read_text())
raw=Path(p["raw_path"]);log=(ROOT/"ngspice.log").read_text(errors="replace")
result={"scope":"ONE_SHORT_DIAGNOSTIC_NOT_QUALIFICATION","actual_solver_starts":e["actual_solver_launches"],
    "global_starts":e["conservative_starts_after"],"elapsed_solver_wall_s":e["elapsed_solver_wall_s"],
    "original_qualification":"FAIL_UNCHANGED","old_STOPPED_preserved":e["old_freeze_permissions_STOPPED_and_ledgers_unchanged"],
    "automatic_followup":False,"requested_end_s":p["common_end_s"],
    "returncode":e["returncode"],"timed_out":e["timed_out"],
    "log_uses_sparse":"Using SPARSE" in log,
    "error_lines":[x for x in log.splitlines() if re.search(r"error|aborted|timestep too small|failed",x,re.I)],
    "original_RAW_sha256":p["original_RAW_sha256"],"original_RAW_checksum_count_this_task":1,
    "new_RAW_exists":raw.exists()}
v=None
if raw.exists():
    result["new_RAW_sha256"]=sha(raw);result["new_RAW_bytes"]=raw.stat().st_size
    try:
        v=cap.read_raw(raw);t=v["time"]
        result.update({"new_RAW_points":len(t),"new_RAW_variables":len(v),"actual_end_s":float(t[-1]),
            "start_s":float(t[0]),"time_strictly_increasing":bool(np.all(np.diff(t)>0)),
            "missing_vectors":[x for x in p["required_vectors"] if x not in v],
            "exact_common_end":float(t[-1])==p["common_end_s"]})
    except Exception as exc:result["RAW_parse_error"]=repr(exc)
valid=(v is not None and e["returncode"]==0 and not e["timed_out"]
    and result.get("time_strictly_increasing",False) and result.get("exact_common_end",False)
    and not result.get("missing_vectors") and result["log_uses_sparse"] and not result["error_lines"])
result["valid_complete_common_interval"]=valid
new={"scope":"OFFLINE_DIAGNOSTIC_COMMON_INTERVAL_ONLY","source_RAW_sha256":result.get("new_RAW_sha256"),
    "max_step_s":p["new_max_step_s"],"common_end_s":p["common_end_s"],
    "valid_complete_common_interval":valid,"capacitors":{}}
if v is not None:
    new.update({"start_s":float(v["time"][0]),"end_s":float(v["time"][-1]),"points":len(v["time"])})
    if all(k in v for k in ["v(g0_vm)","i(va_cg0_cm_p)","i(va_cpar_g0_vm_p)"]):
        for name,key,C in [("cg0_cm","i(va_cg0_cm_p)",1e-7),("cpar_g0_vm","i(va_cpar_g0_vm_p)",5e-14)]:
            new["capacitors"][name]=cap.analyze(v["time"],v["v(g0_vm)"],v[key],C)
save("new_common_interval.json",new)
if valid:
    # Read only the original comparison prefix; no second original RAW checksum.
    oldall=cap.read_raw(Path(p["original_RAW_path"]))
    n=p["baseline_points_in_common_interval"];old={k:a[:n] for k,a in oldall.items()}
    assert float(old["time"][-1])==float(v["time"][-1])
    comparisons={}
    for name,a in baseline["capacitors"].items():
        b=new["capacitors"][name];items={}
        for key in ["signed_mismatch_J","charge_consistency_term_J","product_quadrature_term_J"]:
            av,bv=a[key],b[key]
            items[key]={"baseline":av,"new":bv,"absolute_ratio":abs(bv/av) if av else None,
                        "absolute_magnitude_decreased":abs(bv)<abs(av)}
        items["relative_mismatch"]={"baseline":a["relative_mismatch"],"new":b["relative_mismatch"]}
        items["diagnostic_original_formula_gate"]={"baseline":a["original_gate_would_pass"],"new":b["original_gate_would_pass"]}
        items["leading_10ms_windows"]={"baseline":a["top_10ms_bins"][:5],"new":b["top_10ms_bins"][:5]}
        comparisons[name]=items
    result["capacitor_comparison"]=comparisons
    tol=p["event_comparison"]["time_tolerance_reference_s"]
    def edges(vectors,node):
        t,x=vectors["time"],vectors[node];threshold=p["event_comparison"]["threshold_V"]
        rising=np.flatnonzero((x[:-1]<threshold)&(x[1:]>=threshold))
        falling=np.flatnonzero((x[:-1]>=threshold)&(x[1:]<threshold))
        out={}
        for label,idx in [("rising",rising),("falling",falling)]:
            out[label]=t[idx]+(threshold-x[idx])*(t[idx+1]-t[idx])/(x[idx+1]-x[idx])
        return out
    events={};ordered=[[],[]];all_ok=True
    for node in p["event_comparison"]["nodes"]:
        a,b=edges(old,node),edges(v,node);events[node]={}
        for edge in ["rising","falling"]:
            x,y=a[edge],b[edge];same=len(x)==len(y);delta=y-x if same else np.array([])
            item={"baseline_count":len(x),"new_count":len(y),"same_count":same,
                  "max_abs_time_shift_s":float(np.max(np.abs(delta))) if len(delta) else (0.0 if same else None),
                  "first_baseline_times_s":x[:8].tolist(),"first_new_times_s":y[:8].tolist()}
            item["within_reference_tolerance"]=same and (not len(delta) or bool(np.max(np.abs(delta))<=tol))
            events[node][edge]=item;all_ok=all_ok and item["within_reference_tolerance"]
            for side,times in enumerate([x,y]):
                ordered[side]+=[(float(t),node+" "+edge+" "+str(k)) for k,t in enumerate(times)]
    for seq in ordered:seq.sort()
    labels=[[x[1] for x in seq] for seq in ordered]
    pos={label:i for i,(_,label) in enumerate(ordered[1])};violations=[]
    if set(labels[0])==set(labels[1]):
        for i,(t1,l1) in enumerate(ordered[0]):
            for t2,l2 in ordered[0][i+1:]:
                if pos[l1]>pos[l2] and max(t2-t1,abs(ordered[1][pos[l2]][0]-ordered[1][pos[l1]][0]))>tol:
                    if len(violations)<5:violations.append([l1,l2])
        order_ok=not violations
    else:order_ok=False
    result["G0_events"]={"threshold_V":1.5,"time_reference_s":tol,"nodes":events,
        "strict_cross_node_order_identical":labels[0]==labels[1],
        "order_comparable_allowing_reference_time_ties":order_ok,"first_order_violations":violations,
        "all_counts_and_shifts_within_reference":all_ok}
    end=p["common_end_s"];grid=np.r_[np.arange(0,end,.001),end]
    aa=np.interp(grid,old["time"],old["v(g0_vm)"]);bb=np.interp(grid,v["time"],v["v(g0_vm)"])
    peak_a=float(np.max(old["v(g0_vm)"]));peak_b=float(np.max(v["v(g0_vm)"]))
    scale=max(abs(peak_a),abs(peak_b),.01);rmse=float(np.sqrt(np.mean((bb-aa)**2)))
    peak_relative=abs(peak_b-peak_a)/scale
    result["membrane"]={"grid_s":.001,"grid_points":len(grid),"baseline_peak_V":peak_a,"new_peak_V":peak_b,
        "peak_relative_difference":peak_relative,"peak_within_1pct_reference":peak_relative<=.01,
        "max_abs_difference_V":float(np.max(np.abs(bb-aa))),"RMSE_V":rmse,"normalized_RMSE":rmse/scale,
        "trajectory_note":"Interpolation is only for waveform comparison; spike timing shifts may inflate pointwise differences."}
    improved=all(x[k]["absolute_magnitude_decreased"] for x in comparisons.values()
                 for k in ["signed_mismatch_J","charge_consistency_term_J"])
    behavior=all_ok and order_ok and peak_relative<=.01
    result.update({"both_caps_absolute_error_and_dominant_term_decreased":improved,
        "behavior_comparable_by_declared_references":behavior,
        "supports_time_discretization_sensitivity":improved and behavior,
        "interpretation":"One comparison supports sensitivity only if absolute errors and dominant terms decrease with comparable G0 behavior; it is not a convergence proof or a qualification pass."})
else:
    result["interpretation"]="Common-interval convergence comparison is invalid or incomplete. Deliver evidence and stop without retry."
save("comparison.json",result)
print(json.dumps({k:result[k] for k in ["valid_complete_common_interval","actual_solver_starts","global_starts","elapsed_solver_wall_s","actual_end_s","supports_time_discretization_sensitivity"] if k in result},indent=2))

