"""Run the existing static and synthetic selfcheck entry points, without a real solver."""
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

project = Path(sys.argv[1]).resolve()
evidence = Path(__file__).resolve().parent
env = {k: v for k, v in os.environ.items() if not k.startswith("THERMAL_G3")}
env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def sources():
    return {str(p.relative_to(project)): digest(p) for p in sorted(project.rglob("*"))
            if p.is_file() and p.suffix in (".py", ".lib") and "__pycache__" not in p.parts}

before = sources()
rows = []
for script, logname in (("tools/static_check.py", "static_check_run.txt"),
                        ("tools/selfcheck_all.py", "selfcheck_run.txt")):
    start = time.monotonic()
    at = datetime.now(timezone.utc).isoformat()
    with (project / "results" / logname).open("w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, "-u", "-B", script], cwd=project, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        code = proc.wait()
    rows.append({"script": script, "returncode": code, "started_utc": at,
                 "wall_s": time.monotonic() - start, "log": "results/" + logname,
                 "log_sha256": digest(project / "results" / logname)})
static = json.loads((project / "results/static_check.json").read_text())
checks = json.loads((project / "results/selfcheck.json").read_text())
out = {"schema": "thermal_g3.no_solver_validation.1", "runs": rows,
       "sources_unchanged_during_run": before == sources(), "source_sha256": before,
       "static_cases": static["n_cases"], "static_all_pass": static["all_pass"],
       "selfcheck_n": checks["n"], "selfcheck_pass": checks["n_pass"],
       "real_solver_starts": checks["solver_starts"],
       "production_permission_exists": (project / "prereg/LAUNCH_PERMISSION.json").exists(),
       "production_ledger_exists": (project / "results/q1_ledger.jsonl").exists()}
out["all_pass"] = (all(r["returncode"] == 0 for r in rows) and static["all_pass"]
                   and checks["n"] == checks["n_pass"] and before == sources()
                   and not out["production_permission_exists"] and not out["production_ledger_exists"])
(evidence / "validation_summary.json").write_text(json.dumps(out, indent=2) + "\n")
print("VALIDATION_SUMMARY", json.dumps({k: v for k, v in out.items() if k not in ("runs", "source_sha256")}))
sys.exit(0 if out["all_pass"] else 1)
