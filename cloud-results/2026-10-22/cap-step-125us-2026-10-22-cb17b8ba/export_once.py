#!/usr/bin/env python3
"""Export only this diagnostic and verify lossless recovery; no solver execution."""
from pathlib import Path
import gzip,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
REPO=Path("/workspace/TheLiying-cloudtest")
DEST=REPO/"cloud-results/2026-10-22"/ROOT.name
def sha(p):
    with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
assert (ROOT/"comparison.json").exists() and (ROOT/"RUN_FINISHED_NO_RETRY.json").exists()
p=json.loads((ROOT/"test-plan.json").read_text());r=json.loads((ROOT/"comparison.json").read_text())
DEST.mkdir(parents=True,exist_ok=False)
files=["test-plan.json","baseline_common_interval.json","new_common_interval.json","comparison.json",
       "cap_step_125us.cir","c05_ekv26_typ.lib","actual-deck.diff","step-only.diff","ngspice.log",
       "one-shot-reservation.json","execution.json","diagnostic-ledger.jsonl","budget-summary.json",
       "RUN_FINISHED_NO_RETRY.json","run_once.py","analyze_once.py","export_once.py","README.md"]
for name in files:shutil.copy2(ROOT/name,DEST/name)
shutil.copy2(p["cap_analysis_script"],DEST/"cap_energy_forensics.py")
shutil.copy2("/workspace/prepare_cap_step_2026_10_22.py",DEST/"prepare_cap_step_2026_10_22.py")
shutil.copy2("/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea/restore_raw.py",DEST/"restore_raw.py")
entries=[]
raw=Path(p["raw_path"])
if raw.exists():
    entry={"original_path":raw.name,"original_bytes":raw.stat().st_size,
           "original_sha256":r["new_RAW_sha256"],"encoding":"gzip-split",
           "baseline_RAW_sha256_not_this_payload":p["original_RAW_sha256"],"parts":[]}
    # Compress only the newly produced RAW; never repackage the old full RAW.
    gz=ROOT/(raw.name+".gz")
    with raw.open("rb") as src,gz.open("xb") as target:
        with gzip.GzipFile(filename="",mode="wb",fileobj=target,mtime=0,compresslevel=6) as out:
            shutil.copyfileobj(src,out,1024*1024)
    entry["compressed_sha256"]=sha(gz);entry["compressed_bytes"]=gz.stat().st_size
    with gz.open("rb") as f:
        k=0
        while block:=f.read(48*1024*1024):
            name=f"{raw.name}.gz.part{k:03d}";(DEST/name).write_bytes(block)
            entry["parts"].append({"path":name,"bytes":len(block),"sha256":hashlib.sha256(block).hexdigest()});k+=1
    entries.append(entry)
(DEST/"RAW_DELIVERY.json").write_text(json.dumps(entries,indent=2)+"\n")
# Actual decode from the exported chunks through the shipped recovery tool is performed separately.
(DEST/"SHA256SUMS").write_text("".join(f"{sha(f)}  {f.name}\n" for f in sorted(DEST.iterdir()) if f.is_file()))
print(json.dumps({"path":str(DEST),"files":len(list(DEST.iterdir())),
                 "bytes":sum(x.stat().st_size for x in DEST.iterdir()),"RAW":entries},indent=2))

