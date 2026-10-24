#!/usr/bin/env python3
"""Replay the next historical 125/62.5 us qualification pair without a wall limit."""
from pathlib import Path
from datetime import datetime, timezone
import copy
import difflib
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from uuid import uuid4

import numpy as np

sys.dont_write_bytecode = True
Q = Path('/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea')
SOFTWARE = Q / 'software/thermal_g3_q1'
SOURCE = Q / 'runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.cir'
NG = Path('/workspace/thermal-g3-env/host/native/bin/ngspice')
SHORT = Path('/workspace/thermal-g3-retests/short-convergence-2026-10-24-e17ea620')
ROOT = Path('/workspace/thermal-g3-retests') / ('qualification-125-62p5us-2026-10-24-' + uuid4().hex[:8])
spec = importlib.util.spec_from_file_location('raw_helpers', '/workspace/retest-single-short-2026-10-24.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
sys.path.insert(0, str(SOFTWARE))
from observers.judges import judge
from runtime.coordinator import ABORT_MARKERS


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def append(value):
    with (ROOT / 'qualification-retest-ledger.jsonl').open('a') as f:
        f.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def vector_map(raw):
    data, cols, header = helpers.load_raw(raw)
    return {n: data[:, i] for n, i in cols.items()}, header


def complete(execution, log, raw, case, required, vectors):
    # Same checks and endpoint tolerance as the original Coordinator.completion.
    if execution['returncode'] != 0:
        return 'returncode ' + str(execution['returncode'])
    for marker in ABORT_MARKERS:
        if marker in log.lower():
            return 'log contains ' + repr(marker.strip())
    if 'Using SPARSE 1.3 as Direct Linear Solver' not in log:
        return 'Actual SPARSE selection not confirmed'
    if not raw.is_file():
        return 'no raw output'
    if not required:
        return 'required vector list empty'
    t = vectors.get('time')
    if t is None or not np.all(np.isfinite(t)) or not np.all(np.diff(t) > 0):
        return 'invalid time axis'
    if not t[-1] >= case['x_stop'] * (1 - 1e-9):
        return 'RAW ended before registered endpoint'
    for name in required:
        x = vectors.get(name.lower())
        if x is None or len(x) != len(t) or not np.all(np.isfinite(x)):
            return 'missing, short or nonfinite vector: ' + name
    return None


def main():
    ROOT.mkdir(parents=True, exist_ok=False)
    short = json.loads((SHORT / 'retest_result.json').read_text())
    assert short['status'] == 'COMPLETED_COMMON_INTERVAL_DIAGNOSTIC'
    assert short['execution']['conservative_starts_after'] == 51
    assert all(x['absolute_error_ratio'] < 1 for x in short['comparison'])
    assert short['G0_event_count_preserved']
    baseplan = json.loads((SOURCE.parent / 'plan.json').read_text())
    assert sha(SOURCE) == baseplan['deck_sha256']
    source = SOURCE.read_text()
    original_raw = str(SOURCE.with_suffix('.raw'))
    assert source.splitlines().count('tran 0.001 100.27 0 0.00025') == 1
    assert source.splitlines().count('write ' + original_raw) == 1
    protected_paths = [SOURCE, SOURCE.parent / 'plan.json', Q / 'STOPPED.json', Q / 'qualification-ledger.jsonl', Q / 'session-result.json']
    protected_paths += sorted((SOFTWARE / 'observers').glob('*.py'))
    protected = {str(p): sha(p) for p in protected_paths}
    save(ROOT / 'candidate_manifest.json', {
        'candidate': 'SPARSE_GEAR_125us_retest', 'baseline_max_step_s': .000125,
        'halfstep_max_step_s': .0000625, 'output_increment_s': .001, 'end_s': 100.27,
        'source_software': str(SOFTWARE), 'source_deck': str(SOURCE),
        'source_deck_sha256': baseplan['deck_sha256'],
        'source_cap_energy_FAIL_preserved': True, 'old_v4_recovered': False,
        'max_new_starts': 2, 'conservative_starts_before': 51, 'global_start_cap': 65,
        'wall_cap_s': None, 'automatic_retries': False, 'formal_cases_authorized_by_this_runner': False,
        'prerequisite_retest': str(SHORT),
        'user_instructions': 'Replay historical path; latest user explicitly removed wall-clock limits.',
        'protected_source_hashes': protected})
    print(json.dumps({'stage': 'qualification_pair_prepared', 'run_dir': str(ROOT)}), flush=True)
    baseline_vectors = None
    results = []
    for index, (cid, step) in enumerate([('Q1_MOTHER_PROTOCOL', .000125), ('Q1_MOTHER_HALFSTEP', .0000625)]):
        directory = ROOT / cid
        directory.mkdir(exist_ok=False)
        raw = directory / (cid + '.raw')
        deck = directory / (cid + '.cir')
        analysis = 'tran 0.001 100.27 0 ' + str(step)
        text = source.replace('tran 0.001 100.27 0 0.00025', analysis).replace('write ' + original_raw, 'write ' + str(raw))
        assert text.replace(analysis, 'tran 0.001 100.27 0 0.00025').replace('write ' + str(raw), 'write ' + original_raw) == source
        deck.write_text(text)
        (directory / 'deck.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True), text.splitlines(True), fromfile=str(SOURCE), tofile=str(deck))))
        plan = copy.deepcopy(json.loads((Q / 'runs' / cid / 'plan.json').read_text()))
        case = plan['case']
        case.update(analysis=analysis, max_step_s=step, timeout_s=None)
        plan.update(deck=str(deck), deck_sha256=sha(deck), candidate='SPARSE_GEAR_125us_retest', wall_clock_cap_s=None)
        save(directory / 'plan.json', plan)
        before = 51 + index
        with (directory / 'one-shot-reservation.json').open('x') as f:
            json.dump({'case_id': cid, 'maximum_launches': 1, 'conservative_before': before}, f)
        execution = {'case_id': cid, 'command': [str(NG), '-n', '-b', str(deck)],
                     'actual_solver_launches': 0, 'conservative_starts_before': before,
                     'conservative_starts_after': before, 'global_start_cap': 65,
                     'wall_cap_s': None, 'automatic_retries': 0, 'timed_out': False}
        save(directory / 'execution.json', execution)
        env = os.environ.copy()
        env['SPICE_SCRIPTS'] = '/workspace/thermal-g3-env/spice-scripts'
        start = time.monotonic()
        with (directory / 'ngspice.log').open('wb') as log:
            process = subprocess.Popen(execution['command'], cwd=directory, env=env,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            execution.update(actual_solver_launches=1, conservative_starts_after=before + 1,
                             pid=process.pid, started_at_UTC=datetime.now(timezone.utc).isoformat())
            save(directory / 'execution.json', execution)
            append({'record': 'actual_start', **execution})
            print(json.dumps({'stage': 'solver_started', 'case': cid, 'pid': process.pid,
                              'conservative_count': str(before + 1) + '/65', 'run_dir': str(ROOT)}), flush=True)
            process.wait()
        execution.update(returncode=process.returncode, elapsed_solver_wall_s=time.monotonic() - start,
                         ended_at_UTC=datetime.now(timezone.utc).isoformat(), process_reaped=True)
        save(directory / 'execution.json', execution)
        append({'record': 'actual_end', **execution})
        log = (directory / 'ngspice.log').read_text(errors='replace')
        completion = {'case_id': cid, 'raw_exists': raw.is_file(), 'actual_end_s': None,
                      'completion_failure': None}
        vectors = None
        if raw.is_file():
            completion.update(raw_sha256=sha(raw), raw_bytes=raw.stat().st_size)
            try:
                vectors, header = vector_map(raw)
                completion.update(actual_end_s=float(vectors['time'][-1]), raw_points=header['npts'], raw_variables=header['nvar'])
                completion['completion_failure'] = complete(execution, log, raw, case, plan['required_vectors'], vectors)
            except Exception as exc:
                completion['completion_failure'] = type(exc).__name__ + ': ' + str(exc)
        else:
            completion['completion_failure'] = 'No RAW output'
        save(directory / 'completion.json', completion)
        if completion['completion_failure'] is None:
            output = judge(case, vectors, baseline_vectors, plan['physical_ledger_plan'],
                           ammeters=plan['ammeters'], mos_nodes=plan['mos_nodes'])
            # Halfstep must also satisfy its own unchanged original functional and physical gates.
            if cid == 'Q1_MOTHER_HALFSTEP':
                own_case = copy.deepcopy(case)
                own_case['case_id'] = 'Q1_MOTHER_PROTOCOL'
                own = judge(own_case, vectors, None, plan['physical_ledger_plan'],
                            ammeters=plan['ammeters'], mos_nodes=plan['mos_nodes'])
                save(directory / 'own-full-science.json', own)
                if own['result'] != 'PASS':
                    output['result'] = own['result']
                output['own_full_scientific_result'] = own['result']
        else:
            output = {'result': 'UNMEASURED', 'why': completion['completion_failure']}
        save(directory / 'judge-output.json', output)
        record = {'case_id': cid, 'scientific': output['result'], 'completion': completion,
                  'execution': execution, 'deck_sha256': sha(deck),
                  'judge_output_sha256': sha(directory / 'judge-output.json')}
        save(directory / 'verdict-binding.json', record)
        append({'record': 'verdict', **record})
        results.append(record)
        save(ROOT / 'qualification-retest-result.json', {
            'results': results, 'global_count': before + 1,
            'old_protected_files_unchanged': all(sha(Path(p)) == h for p, h in protected.items()),
            'formal_cases_started': 0, 'next_stage_started': False,
            'overall': 'PASS' if len(results) == 2 and all(r['scientific'] == 'PASS' for r in results) else 'INCOMPLETE_OR_FAILED'})
        print(json.dumps({'stage': 'case_finished', 'case': cid, 'result': output['result'],
                          'elapsed_s': execution['elapsed_solver_wall_s'], 'raw_end_s': completion['actual_end_s']}), flush=True)
        if completion['completion_failure'] is not None or output['result'] != 'PASS':
            save(ROOT / 'STOPPED.json', {'case_id': cid, 'why': completion['completion_failure'] or output['result'],
                 'automatic_retry': False, 'next_case_started': False})
            break
        baseline_vectors = vectors
    # RAW hashes were computed once per file above and are bound in completion records.
    raw_hashes = {str(ROOT / r['case_id'] / (r['case_id'] + '.raw')): r['completion'].get('raw_sha256') for r in results}
    lines = []
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and p.name != 'SHA256SUMS':
            h = raw_hashes.get(str(p)) if p.suffix == '.raw' else sha(p)
            if h:
                lines.append(h + '  ' + str(p.relative_to(ROOT)) + '\n')
    (ROOT / 'SHA256SUMS').write_text(''.join(lines))
    print(json.dumps({'stage': 'qualification_pair_stopped', 'run_dir': str(ROOT),
                      'scientific_results': [r['scientific'] for r in results],
                      'actual_starts': len(results), 'conservative_count_after': 51 + len(results),
                      'no_automatic_formal_experiments': True}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if ROOT.exists():
            save(ROOT / 'EXECUTION_ERROR_STOPPED.json', {'error': type(exc).__name__ + ': ' + str(exc), 'automatic_retry': False})
        raise
