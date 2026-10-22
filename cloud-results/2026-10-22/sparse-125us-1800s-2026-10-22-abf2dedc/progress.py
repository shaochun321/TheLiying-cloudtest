#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime,timezone
import json,re
r=Path(__file__).resolve().parent
for cid in ["Q1_MOTHER_PROTOCOL","Q1_MOTHER_HALFSTEP"]:
 d=r/"runs"/cid;p=d/"execution.json"
 if not p.exists():continue
 e=json.loads(p.read_text());s=(d/"ngspice.log").read_text(errors="replace") if (d/"ngspice.log").exists() else ""
 v=re.findall(r"Reference value\s*:\s*([^\r\n]+)",s)
 out={"case":cid,"global_starts":e["conservative_starts_after"],"wall_cap_s":e["wall_clock_cap_s"],
      "log_progress_s":v[-1] if v else None,"solver_reaped":e.get("solver_process_reaped",False),
      "verdict_bound":(d/"verdict-binding.json").exists(),"round_stopped":(r/"STOPPED.json").exists()}
 if e["started_at_Asia_Shanghai"]:
  out["elapsed_s"]=e["elapsed_solver_wall_s"] if out["solver_reaped"] else (datetime.now(timezone.utc)-datetime.fromisoformat(e["started_at_Asia_Shanghai"])).total_seconds()
 if out["verdict_bound"]:out["verdict"]=json.loads((d/"verdict-binding.json").read_text())["scientific"]
 print(json.dumps(out))

