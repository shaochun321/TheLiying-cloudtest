"""THERMAL-G3-Q1-R single production coordinator (INFRA).

Entry: run_case(case_id) only. Arbitrary netlist bodies are not accepted: the deck is rebuilt
from the frozen case registry by runtime/decks.py, the frozen model-card / OSDI paths and the raw
path are substituted, and the identity text must hash to the frozen deck hash. The solver is the
frozen ngspice; every start records the backend identity and all starts of a round must use the
backend of the first start (no cross-backend mixing; no per-backend budget).

Launch contract (one definition, all checked at every dispatch):
  FREEZE_Q1R.json            status FROZEN_AWAITING_LAUNCH; every pinned file hash matches,
                             including the external ngspice / OSDI / model card actually used
                             and the environment-override variables (must be unset or equal)
  prereg/LAUNCH_PERMISSION.json  user-written; records the sha256 of FREEZE_Q1R.json and the
                             phases it authorises
Budget: the 24 sealed v1 dev starts are inherited (v1 ledger hash pinned); qualification 2 /
formal 31 / rerun 4 / total 61; phase wall caps 1200 / 108000 / 14400 s; open starts count at
their reservation. Order: formal is dispatched only after BOTH qualification cases have a
scientific PASS; a case's dependencies and baseline must have a scientific PASS. Verdicts are
produced only by run_case itself (solve -> completion gate -> read raw -> registered judge ->
results/verdicts/<aid>.json -> verdicts.jsonl with freeze / deck / raw / backend / judge-output
hashes); there is no public way to write a verdict. A required scientific FAIL or a
non-retryable execution failure stops the round (STOPPED); UNMEASURED blocks dependants.
Cost gate: before each formal dispatch the remaining matrix is forecast from measured wall
time per element (x1.5) and refused if it exceeds the remaining phase / global time.
Rerun: only for a registered case whose last end record is a preregistered infrastructure
failure (INFRA_FAILURES); same frozen deck; functional/solver failures cannot be rerun.
Hard deadline: runtime/supervisor.py in its own process (Job Object on Windows).
Completion gate: rc 0, no abort text, raw parsed; tran: time finite, strictly increasing,
ends at the analysis stop; op: one point; the saved vector list (judge + ledger vectors) is
non-empty and every saved vector is present, full length and finite.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config  # noqa: E402
from solver_adapter.read_raw import read_raw  # noqa: E402

ABORT_MARKERS = ("simulation(s) aborted", "timestep too small", "fatal error", "no such vector",
                 "error on line", "doanalyses: ")
INFRA_FAILURES = ("launch_error", "disk_full", "raw_io_error", "supervisor_lost")
ENV_OVERRIDES = ("THERMAL_G3_NGSPICE", "THERMAL_G3_OSDI", "THERMAL_G3_MODEL_LIB")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _fwd(p):
    return p.replace("\\", "/")


class Refused(RuntimeError):
    pass


class FileLock:
    def __init__(self, path, timeout_s=60.0):
        self.path, self.timeout_s = path, timeout_s

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        t0 = time.monotonic()
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                if time.monotonic() - t0 > self.timeout_s:
                    raise Refused(f"ledger lock busy: {self.path}")
                time.sleep(0.05)

    def __exit__(self, *exc):
        os.close(self.fd)
        os.remove(self.path)


class Coordinator:
    def __init__(self, root=ROOT, ledger=None, raw_root=None, solver=None, enforce=True,
                 v1_ledger=config.V1_LEDGER, v1_sha=config.V1_LEDGER_SHA256):
        self.root = root
        self.ledger = ledger or os.path.join(root, "results", "q1_ledger.jsonl")
        self.verdicts = os.path.join(os.path.dirname(self.ledger), "verdicts.jsonl")
        self.stop_marker = os.path.join(os.path.dirname(self.ledger), "STOPPED")
        self.raw_root = raw_root or config.get_raw_root()
        self.solver = solver          # None: the frozen ngspice of this freeze's backend
        self.enforce = enforce
        self.v1_ledger, self.v1_sha = v1_ledger, v1_sha
        self.lock = FileLock(self.ledger + ".lock")

    # ------------------------------------------------------------- frozen state
    def _abs(self, p):
        """Frozen asset paths inside the package are stored relative to the package root."""
        return p if os.path.isabs(p) else os.path.join(self.root, p)

    def backend_id(self, fr):
        return {k: x["sha256"] for k, x in fr.get("external_sha256", {}).items()}

    def freeze(self):
        p = os.path.join(self.root, "FREEZE_Q1R.json")
        if not os.path.exists(p):
            raise Refused("FREEZE_Q1R.json missing")
        return json.load(open(p, encoding="utf-8")), sha(p)

    def check_contract(self, phase):
        fr, fr_sha = self.freeze()
        if not self.enforce:
            return fr
        if fr.get("status") != "FROZEN_AWAITING_LAUNCH":
            raise Refused(f"freeze status {fr.get('status')}")
        for rel, h in fr["pinned_sha256"].items():
            p = os.path.join(self.root, rel)
            if not os.path.exists(p) or sha(p) != h:
                raise Refused(f"frozen file changed or missing: {rel}")
        for name, ext in fr["external_sha256"].items():
            p = self._abs(ext["path"])
            if not os.path.exists(p) or sha(p) != ext["sha256"]:
                raise Refused(f"external asset changed: {name}")
        for k in ENV_OVERRIDES:
            if os.environ.get(k) and _fwd(os.path.abspath(os.environ[k])) != _fwd(os.path.abspath(self._abs(fr["external_sha256"][k]["path"]))):
                raise Refused(f"environment override {k} differs from the frozen asset")
        perm_p = os.path.join(self.root, "prereg", "LAUNCH_PERMISSION.json")
        if not os.path.exists(perm_p):
            raise Refused("no launch permission (prereg/LAUNCH_PERMISSION.json)")
        perm = json.load(open(perm_p, encoding="utf-8"))
        if perm.get("freeze_sha256") != fr_sha:
            raise Refused("launch permission refers to a different freeze")
        if phase not in perm.get("phases", []):
            raise Refused(f"phase {phase} not authorised")
        return fr

    # ------------------------------------------------------------- ledgers
    def inherited(self):
        if sha(self.v1_ledger) != self.v1_sha:
            raise Refused("v1 ledger hash changed")
        recs = [json.loads(l) for l in open(self.v1_ledger, encoding="utf-8") if l.strip()]
        st = [r for r in recs if r["rec"] == "start"]
        if len(st) != config.DEV_CLOSED or any(r["kind"] != "dev" for r in st):
            raise Refused("v1 ledger does not hold exactly the 24 dev starts")
        return len(st), sum(r.get("wall_s") or 0.0 for r in recs if r["rec"] == "end")

    def records(self, path=None):
        path = path or self.ledger
        if not os.path.exists(path):
            return []
        return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

    def _append(self, rec, path=None):
        path = path or self.ledger
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def status(self):
        n24, w24 = self.inherited()
        recs = self.records()
        ends = {r["analysis_id"]: r for r in recs if r["rec"] == "end"}
        ph = {k: {"starts": 0, "wall_s": 0.0} for k in config.CAPS}
        for r in recs:
            if r["rec"] == "start":
                e = ends.get(r["analysis_id"])
                ph[r["phase"]]["starts"] += 1
                ph[r["phase"]]["wall_s"] += e["wall_s"] if e else r["reserved_timeout_s"]
        return {"phases": ph, "total_starts": n24 + sum(p["starts"] for p in ph.values()),
                "total_wall_s": w24 + sum(p["wall_s"] for p in ph.values())}

    def verdict(self, case_id):
        v = [r for r in self.records(self.verdicts) if r["case_id"] == case_id]
        return v[-1]["scientific"] if v else None

    def verdict_record(self, case_id):
        v = [r for r in self.records(self.verdicts) if r["case_id"] == case_id and r["scientific"] == "PASS"]
        return v[-1] if v else None

    def _record_verdict(self, analysis_id, scientific, judge_path, required=True):
        """Private: only run_case calls this, after its own judge. Rejects unknown, incomplete,
        foreign-freeze analyses and raw files whose hash changed since the run."""
        ends = {r["analysis_id"]: r for r in self.records() if r["rec"] == "end"}
        starts = {r["analysis_id"]: r for r in self.records() if r["rec"] == "start"}
        e, st = ends.get(analysis_id), starts.get(analysis_id)
        if e is None or st is None:
            raise Refused(f"verdict refused: unknown analysis {analysis_id}")
        if e["status"] != "complete":
            raise Refused(f"verdict refused: {analysis_id} status {e['status']}")
        _, fr_sha = self.freeze()
        if st.get("freeze_sha256") != fr_sha:
            raise Refused("verdict refused: analysis belongs to a different freeze")
        raw = e["files"]["raw"]
        if raw is None or sha(raw["path"]) != raw["sha256"]:
            raise Refused("verdict refused: raw missing or changed since the run")
        rec = {"case_id": e["case_id"], "analysis_id": analysis_id, "scientific": scientific, "required": required,
               "freeze_sha256": fr_sha, "deck_sha256": st["deck_sha256"], "raw_sha256": raw["sha256"],
               "raw_path": raw["path"], "backend": st.get("backend"),
               "judge_output": {"path": _fwd(judge_path), "sha256": sha(judge_path)},
               "t": time.strftime("%Y-%m-%d %H:%M:%S")}
        self._append(rec, self.verdicts)
        if required and scientific == "FAIL":
            self._stop({"case_id": e["case_id"], "analysis_id": analysis_id, "reason": "scientific FAIL"})
        return rec

    def _stop(self, why):
        os.makedirs(os.path.dirname(self.stop_marker), exist_ok=True)
        with open(self.stop_marker, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(why))

    # ------------------------------------------------------------- cost gate
    def cost_gate(self, c, phase, fr):
        """Before a formal dispatch: forecast the remaining formal cases from the measured wall
        time per element (x1.5 margin) of completed cases of the same scale; a scale not yet
        measured uses the largest per-element rate measured so far (qualification included);
        every term is capped at the case's hard cap. Refuse if the forecast exceeds the remaining
        phase or global time. Engineering estimate, not a guaranteed bound."""
        if phase != "formal":
            return None
        reg = json.load(open(os.path.join(self.root, "prereg", "cases_q1r.json"), encoding="utf-8"))
        sizes = fr.get("case_sizes", {})
        ends = {r["analysis_id"]: r for r in self.records() if r["rec"] == "end"}
        starts = [r for r in self.records() if r["rec"] == "start"]
        done = {r["case_id"] for r in starts}
        rate = {}
        for r in starts:
            e = ends.get(r["analysis_id"])
            if e and e["status"] == "complete" and r["case_id"] in sizes:
                rate.setdefault(r["scale"], []).append(e["wall_s"] / max(1, sizes[r["case_id"]]))
        any_rate = max((max(x) for x in rate.values()), default=None)
        forecast = 0.0
        for k in reg["cases"]:
            if k["phase"] != "formal" or k["case_id"] in done:
                continue
            r = max(rate[k["scale"]]) if k["scale"] in rate else any_rate
            if r is not None and k["case_id"] in sizes:
                forecast += min(k["timeout_s"], 1.5 * r * sizes[k["case_id"]])
            else:
                forecast += k["timeout_s"]
        s = self.status()
        left_phase = config.PHASE_WALL_CAP_S["formal"] - s["phases"]["formal"]["wall_s"]
        left_total = config.GLOBAL_WALL_CAP_S - s["total_wall_s"]
        if forecast > left_phase or forecast > left_total:
            raise Refused(f"cost gate: forecast {forecast:.0f} s of remaining formal cases exceeds "
                          f"phase {left_phase:.0f} s / total {left_total:.0f} s")
        return forecast

    # ------------------------------------------------------------- dispatch
    def case(self, fr, case_id):
        reg = json.load(open(os.path.join(self.root, "prereg", "cases_q1r.json"), encoding="utf-8"))
        c = next((c for c in reg["cases"] if c["case_id"] == case_id), None)
        if c is None:
            raise Refused(f"unknown case {case_id}")
        return c

    def reserve(self, case_id, rerun=False):
        if os.path.exists(self.stop_marker):
            raise Refused("round stopped: " + open(self.stop_marker, encoding="utf-8").read()[:300])
        fr0, _ = self.freeze()
        c = self.case(fr0, case_id)
        phase = "rerun" if rerun else c["phase"]
        fr = self.check_contract(phase)
        # one backend per round: every start uses the backend of the round's first start
        first = next((r for r in self.records() if r["rec"] == "start" and r.get("backend")), None)
        if first is not None and first["backend"] != self.backend_id(fr):
            raise Refused(f"backend differs from the backend of this round's first start ({first['analysis_id']})")
        if c["phase"] == "formal":
            for q in ("Q1_MOTHER_PROTOCOL", "Q1_MOTHER_HALFSTEP"):
                if self.verdict(q) != "PASS":
                    raise Refused(f"formal refused: qualification {q} has no scientific PASS")
        for d in c["depends_on"]:
            if self.verdict(d) != "PASS":
                raise Refused(f"dependency {d} has no scientific PASS")
        if c["baseline_case_id"] and self.verdict(c["baseline_case_id"]) != "PASS":
            raise Refused(f"baseline {c['baseline_case_id']} has no scientific PASS")
        ends = [r for r in self.records() if r["rec"] == "end" and r.get("case_id") == case_id]
        if rerun:
            if not ends or ends[-1]["status"] not in INFRA_FAILURES:
                raise Refused("rerun only after a preregistered infrastructure failure of this case")
        elif ends:
            raise Refused("case already run; only an infrastructure failure may be rerun")
        cap = c["timeout_s"]
        if cap > config.TIMEOUT_BY_SCALE_S.get(c["scale"], config.TIMEOUT_BY_SCALE_S["dc_static"]) and c["analysis"] != "op":
            raise Refused("case timeout above the scale cap")
        deck = fr["decks"][case_id]
        self.cost_gate(c, phase, fr)
        with self.lock:
            s = self.status()
            p = s["phases"][phase]
            if p["starts"] >= config.CAPS[phase]:
                raise Refused(f"{phase} start cap {config.CAPS[phase]} reached")
            if s["total_starts"] >= config.GLOBAL_START_CAP:
                raise Refused("global start cap 61 reached")
            if p["wall_s"] + cap > config.PHASE_WALL_CAP_S[phase]:
                raise Refused(f"{phase} wall cap")
            if s["total_wall_s"] + cap > config.GLOBAL_WALL_CAP_S:
                raise Refused("global 48 h wall cap")
            aid = f"{ {'qualification': 'qual', 'formal': 'formal', 'rerun': 'rerun'}[phase]}-{p['starts'] + 1:03d}"
            self._append({"rec": "start", "analysis_id": aid, "phase": phase, "case_id": case_id,
                          "scale": c["scale"], "analysis": c["analysis"], "reserved_timeout_s": cap,
                          "deck_sha256": deck["sha256"], "freeze_sha256": self.freeze()[1],
                          "backend": self.backend_id(fr),
                          "t": time.strftime("%Y-%m-%d %H:%M:%S")})
        return aid, c, deck

    def completion(self, rc, log_txt, raw, c, required):
        if rc != 0:
            return f"returncode {rc}"
        low = log_txt.lower()
        for m in ABORT_MARKERS:
            if m in low:
                return f"log contains '{m.strip()}'"
        if not os.path.exists(raw):
            return "no raw output"
        try:
            V = read_raw(raw)[-1]
        except OSError:
            return "raw_io_error"
        except Exception as e:
            return f"raw parse: {e!r}"
        if not required:
            return "required vector list empty"
        if c["analysis"] == "op":
            n = None
        else:
            t = V.get("time")
            if t is None:
                return "no time axis"
            if not np.all(np.isfinite(t)) or not np.all(np.diff(t) > 0):
                return "time axis not finite / strictly increasing"
            if not (t[-1] >= c["x_stop"] * (1 - 1e-9)):
                return f"raw ends at {t[-1]:.9g}, stop {c['x_stop']}"
            n = len(t)
        for name in required:
            x = V.get(name.lower())
            if x is None:
                return f"missing vector {name}"
            if (n is not None and len(x) != n) or not np.all(np.isfinite(x)):
                return f"vector {name} short or non-finite"
        return None

    def run_case(self, case_id, rerun=False):
        aid, c, deck = self.reserve(case_id, rerun)
        fr = self.freeze()[0]
        ext = {k: _fwd(self._abs(x["path"])) for k, x in fr["external_sha256"].items()}
        solver = self.solver or [ext["THERMAL_G3_NGSPICE"]]
        wd = os.path.join(self.raw_root, aid)
        os.makedirs(wd, exist_ok=True)
        cir, raw, log, res = (os.path.join(wd, f"{aid}_{case_id}.{x}") for x in ("cir", "raw", "log", "sup.json"))
        from runtime.decks import deck_text, case_assets
        body, _ = deck_text(case_id, raw_path=_fwd(raw), model_lib=ext["THERMAL_G3_MODEL_LIB"],
                            osdi=ext["THERMAL_G3_OSDI"])
        required = case_assets(case_id)["save"]     # completion covers every saved vector
        with open(cir, "w", encoding="ascii", newline="\n") as f:
            f.write(body)
        status = None
        ident = body.replace(_fwd(raw), "<RAW>").replace(ext["THERMAL_G3_MODEL_LIB"], "<MODEL_LIB>")             .replace(ext["THERMAL_G3_OSDI"], "<OSDI>")
        if hashlib.sha256(ident.encode()).hexdigest() != deck["sha256"]:
            status = "deck_identity_mismatch"
        t0 = time.monotonic()
        rc, killed, active_after = None, False, None
        if status is None:
            try:
                sup = subprocess.Popen([sys.executable, "-B", os.path.join(self.root, "runtime", "supervisor.py"),
                                        res, str(c["timeout_s"] - config.KILL_GRACE_S), log, wd, "--",
                                        *solver, "-b", cir])
                sup.wait()
                if not os.path.exists(res):
                    status = "supervisor_lost"
                else:
                    r = json.load(open(res, encoding="utf-8"))
                    rc, killed, active_after = r["returncode"], r["killed"], r.get("active_after")
            except OSError as e:
                status = "disk_full" if getattr(e, "errno", None) == 28 else "launch_error"
        wall = time.monotonic() - t0
        txt = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
        if status is None:
            status = "timeout_killed" if killed else (self.completion(rc, txt, raw, c, required) or "complete")
        files = {k: ({"path": _fwd(p), "sha256": sha(p)} if os.path.exists(p) else None)
                 for k, p in (("cir", cir), ("log", log), ("raw", raw))}
        end = {"rec": "end", "analysis_id": aid, "case_id": case_id, "status": status, "returncode": rc,
               "wall_s": wall, "active_after": active_after, "infra_failure": status in INFRA_FAILURES,
               "files": files, "t": time.strftime("%Y-%m-%d %H:%M:%S")}
        with self.lock:
            self._append(end)
        if status == "complete":
            end["verdict"] = self._judge_and_record(aid, c, raw)
        elif status not in INFRA_FAILURES:
            # a required case that failed to execute (abort / timeout / incomplete) cannot use
            # the fault quota: the round stops at this layer
            self._stop({"case_id": case_id, "analysis_id": aid, "reason": f"execution failure: {status}"})
        return aid, end

    def _judge_and_record(self, aid, c, raw):
        """Production judging: read this raw (and the baseline raw bound to its PASS verdict),
        run the registered judge, persist its output, record the verdict with evidence."""
        from runtime.decks import case_assets
        from observers.judges import judge
        a = case_assets(c["case_id"])
        V = read_raw(raw)[-1]
        base_V, out = None, None
        base_id = c.get("baseline_case_id")
        if base_id:
            bv = self.verdict_record(base_id)
            if bv is None or not os.path.exists(bv["raw_path"]) or sha(bv["raw_path"]) != bv["raw_sha256"]:
                out = {"result": "UNMEASURED", "why": "baseline raw not bound to a PASS verdict"}
            else:
                base_V = read_raw(bv["raw_path"])[-1]
        if out is None:
            ammeters = [x for x in a["save"] if x.startswith("i(v") and x not in ("i(vsrc)",)
                        and not x.startswith("i(va_")]
            try:
                out = judge(c, V, base_V, a["plan"], ammeters=ammeters, mos_nodes=a["mos_nodes"])
            except Exception as e:      # a judge defect is never a PASS; it blocks dependants
                out = {"result": "UNMEASURED", "why": f"judge raised {e!r}"[:400]}
        jdir = os.path.join(os.path.dirname(self.ledger), "verdicts")
        os.makedirs(jdir, exist_ok=True)
        jp = os.path.join(jdir, f"{aid}_{c['case_id']}.json")
        with open(jp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, indent=1, default=float)
        return self._record_verdict(aid, out["result"], jp)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -B runtime/coordinator.py <case_id>")
    print(Coordinator().run_case(sys.argv[1]))
