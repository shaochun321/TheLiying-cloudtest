# THERMAL-G3-Q1-R preparation package

Status: see `FREEZE_Q1R.json` (`status`, `not_ready_reasons`). This README contains no observed values.

## 2026-10-20 software continuation
The unfinished `tools/_block.py` is integrated as `check_support_pairs()` in
`tools/selfcheck_all.py`; its original bytes are retained with the handoff evidence.
The fixed pairs use the signed membrane ledger and continuous source attribution. Synthetic
RC fixtures test the observer only. Temporary stand-in backend registrations and permission
fixtures in the selfcheck are isolated test data and do not qualify an execution backend.
`prereg/source_manifest.json` remains the original workstation provenance; current source
hashes and revision ancestry are in `prereg/source_revision_2026-10-20.json`.
This handoff has no registered real Linux backend or launch permission. Preserve its NOT_READY
freeze until the actual execution host has its real assets and a matching new backend freeze.

## Layout
- `netlists/`: N-RC mother (`neuron_nrc.py`); full builder with Q1-R construction variants (`build_thermal_g3.py`); qualification bench (`bench_mother.py`); ledger probe plan (`ledger_plan.py`: targeted 0 V ammeters at the ledger nodes).
- `analysis/input_bounds.py`: offline **candidate estimate**, using the EKV2.6 port in `analysis/ekv26_static.py`. Its status is NO_INCOMPATIBILITY_FOUND / INCOMPATIBLE / UNKNOWN; it is never PASS. `analysis/raw_bounds.py` reads measured values (rec / op_at at q end, activity, branch charges) after the qualification solve.
- `prereg/`:
  - `make_protocol.py` → `protocol_q1r_joint.json` (derived segment durations, staggered roles);
  - `make_cases.py` → `cases_q1r.json` (2 qualification cases + the original 31 formal cases), from the in-package task table copy `inputs/`.
- `observers/`: `observers_q1r.py`, `criteria_q1r.py` (qualification gates), `judges.py` (registered judge of every case + required vectors), `ledger_q1r.py` (physical ledger), `halfstep_compare.py`.
- `runtime/`: `coordinator.py` (single entry `run_case(case_id)`: solve → completion → judge → verdict), `decks.py`, `supervisor.py` (Job Object hard deadline).
- `backend/`: EKV2.6 Verilog-A sources + includes and provenance (OSDI rebuild source for other platforms).
- `tools/`: `static_check.py`, `selfcheck_all.py`, `write_freeze.py`, `source_manifest.py`, `register_backend.py`, `make_cloud_package.py`, `check_cloud_package.py`, `render_report.py`.
- `tests/`: `fake_ngspice.py` (stand-in executable, no solver), `synth_raw.py` (synthetic legal traces for judge self-checks).

## Rebuild the package (no solver)
```
PYTHONIOENCODING=utf-8 python -B analysis/input_bounds.py
PYTHONIOENCODING=utf-8 python -B prereg/make_protocol.py
PYTHONIOENCODING=utf-8 python -B prereg/make_cases.py
PYTHONIOENCODING=utf-8 python -B tools/static_check.py
PYTHONIOENCODING=utf-8 python -B tools/selfcheck_all.py
PYTHONIOENCODING=utf-8 python -B tools/source_manifest.py
PYTHONIOENCODING=utf-8 python -B tools/write_freeze.py
PYTHONIOENCODING=utf-8 python -B tools/make_cloud_package.py   # run package + independent unpack check
PYTHONIOENCODING=utf-8 python -B tools/render_report.py
```

## Launch permission (written by the user, not by the agent)
`prereg/LAUNCH_PERMISSION.json`:
```json
{"freeze_sha256": "<sha256 of FREEZE_Q1R.json>", "phases": ["qualification", "formal", "rerun"],
 "granted_by": "<user>", "date": "<YYYY-MM-DD>"}
```
Run order is enforced by the coordinator:
1. Q1_MOTHER_PROTOCOL
2. Q1_MOTHER_HALFSTEP
3. The formal cases follow their `depends_on` entries.

Each case may run only after its dependencies have a scientific PASS recorded by the coordinator's own judge. A required scientific FAIL or a non-retryable execution failure stops the round; UNMEASURED blocks dependants. All starts of a round use the backend of its first start.
