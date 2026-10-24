#!/usr/bin/env python3
"""Replay the registered formal sequence with approved cap 84; stop on first failure."""
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
QUAL = Path('/workspace/thermal-g3-retests/qualification-125-62p5us-2026-10-24-58804272')
SOURCE = Path('/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea/software/thermal_g3_q1')
ROOT = Path('/workspace/thermal-g3-retests') / ('formal-matrix-2026-10-24-' + uuid4().hex[:8])
NG = Path('/workspace/thermal-g3-env/host/native/bin/ngspice')
MODEL = Path('/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea/inputs/c05_ekv26_typ.lib')
OSDI = Path('/workspace/thermal-g3-env/host/native/models/ekv26_linux.osdi')
sys.path.insert(0, str(SOURCE))
from runtime.decks import deck_text, case_assets
from runtime.coordinator import ABORT_MARKERS
from solver_adapter.read_raw import read_raw
from observers.judges import judge


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def append(obj):
    with (ROOT / 'formal-retest-ledger.jsonl').open('a') as f:
        f.write(json.dumps(obj, ensure_ascii=False, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def completion(execution, log, case, vectors, names):
    if execution['returncode'] != 0:
        return 'returncode ' + str(execution['returncode'])
    for marker in ABORT_MARKERS:
        if marker in log.lower():
            return 'log contains ' + repr(marker.strip())
    if case['analysis'] != 'op':
        if 'Using SPARSE 1.3 as Direct Linear Solver' not in log:
            return 'SPARSE solver not confirmed'
        t = vectors.get('time')
        if t is None or not np.all(np.isfinite(t)) or not np.all(np.diff(t) > 0):
            return 'invalid time axis'
        if not t[-1] >= case['x_stop'] * (1 - 1e-9):
            return 'RAW ended early'
        n = len(t)
    else:
        n = None
    if not names:
        return 'no required vectors'
    for name in names:
        x = vectors.get(name.lower())
        if x is None or (n is not None and len(x) != n) or not np.all(np.isfinite(x)):
            return 'missing, short or nonfinite ' + name
    return None


def main():
    # Hard prerequisite: this runner cannot start while the pair is incomplete or failed.
    q = json.loads((QUAL / 'qualification-retest-result.json').read_text())
    assert q['overall'] == 'PASS' and len(q['results']) == 2
    assert q['global_count'] == 53 and q['old_protected_files_unchanged']
    for record in q['results']:
        assert record['scientific'] == 'PASS' and record['completion']['completion_failure'] is None
        assert record['completion']['actual_end_s'] == 100.27
    approval = json.loads((QUAL / 'BUDGET_APPROVAL_84.json').read_text())
    assert approval['approved_global_start_cap'] == 84
    stageplan = json.loads((QUAL / 'NEXT_FORMAL_STAGE_PLAN.json').read_text())
    assert stageplan['status'] == 'AUTHORIZED_CONDITIONAL_ON_BOTH_QUALIFICATIONS_PASS'
    assert len(stageplan['formal_cases']) == 31
    assert sha(stageplan['source_cases_path']) == stageplan['source_cases_sha256']
    ROOT.mkdir(parents=True, exist_ok=False)
    save(ROOT / 'candidate_manifest.json', {
        'candidate': 'SPARSE_GEAR_125us_original_physics_retest_2026-10-24',
        'source_software': str(SOURCE), 'qualification_results': str(QUAL),
        'qualification_result_sha256': sha(QUAL / 'qualification-retest-result.json'),
        'stage_plan_sha256': sha(QUAL / 'NEXT_FORMAL_STAGE_PLAN.json'),
        'global_count_before': 53, 'global_start_cap': 84, 'formal_cases_reserved': 31,
        'wall_cap_s': None, 'stop_on_first_failure': True, 'automatic_retries': False,
        'automatic_repairs_or_diagnostics': False, 'old_freezes_and_ledgers_preserved': True,
        'ngspice': str(NG), 'ngspice_sha256': sha(NG),
        'osdi': str(OSDI), 'osdi_sha256': sha(OSDI),
        'model_card': str(MODEL), 'model_card_sha256': sha(MODEL)})
    originals = [SOURCE / 'prereg/cases_q1r.json', SOURCE / 'runtime/decks.py']
    originals += sorted((SOURCE / 'observers').glob('*.py'))
    protected = {str(p): sha(p) for p in originals}
    prepared = []
    # Register all original cases and their exact allowed numerical changes before any start.
    for item in stageplan['formal_cases']:
        case = copy.deepcopy(item['case'])
        cid = case['case_id']
        directory = ROOT / cid
        directory.mkdir(exist_ok=False)
        raw = directory / (cid + '.raw')
        deck = directory / (cid + '.cir')
        assets = case_assets(cid)
        original, required = deck_text(cid, raw_path=str(raw), model_lib=str(MODEL), osdi=str(OSDI))
        old_options = '.options klu method=gear reltol=1e-5 abstol=1e-16'
        new_options = '.options sparse method=gear reltol=1e-5 abstol=1e-16'
        assert original.splitlines().count(old_options) == 1
        old_analysis = item['original_analysis']
        assert original.splitlines().count(old_analysis) == 1
        text = original.replace(old_options, new_options).replace('\n' + old_analysis + '\n', '\n' + case['analysis'] + '\n')
        assert text.replace(new_options, old_options).replace('\n' + case['analysis'] + '\n', '\n' + old_analysis + '\n') == original
        deck.write_text(text)
        (directory / 'numerical-only.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile='registered-original-case', tofile='candidate-case')))
        plan = {'case': case, 'original_analysis': old_analysis, 'deck': str(deck),
                'deck_sha256': sha(deck), 'physical_ledger_plan': assets['plan'],
                'mos_nodes': assets['mos_nodes'],
                'ammeters': [x for x in assets['save'] if x.startswith('i(v') and x != 'i(vsrc)' and not x.startswith('i(va_')],
                'required_vectors': assets['save'], 'judge_required_vectors': required,
                'maximum_launches': 1, 'wall_cap_s': None}
        save(directory / 'plan.json', plan)
        prepared.append(plan)
    save(ROOT / 'FORMAL_STAGE_PLAN.json', {'cases': [p['case'] for p in prepared],
         'start_count': 53, 'global_cap': 84, 'wall_cap_s': None, 'stop_on_failure': True})
    print(json.dumps({'stage': 'formal_cases_prepared', 'run_dir': str(ROOT), 'count': len(prepared)}), flush=True)
    passed = {r['case_id']: {'raw': str(QUAL / r['case_id'] / (r['case_id'] + '.raw'))} for r in q['results']}
    results, raw_hashes = [], {}
    for index, plan in enumerate(prepared):
        case = plan['case']
        cid = case['case_id']
        assert all(x in passed for x in case.get('depends_on', []))
        before = 53 + len(results)
        assert before < 84
        directory = ROOT / cid
        raw = directory / (cid + '.raw')
        with (directory / 'one-shot-reservation.json').open('x') as f:
            json.dump({'case_id': cid, 'maximum_launches': 1, 'count_before': before, 'cap': 84}, f)
        execution = {'case_id': cid, 'command': [str(NG), '-n', '-b', plan['deck']],
                     'actual_solver_launches': 0, 'conservative_starts_before': before,
                     'conservative_starts_after': before, 'global_start_cap': 84,
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
            print(json.dumps({'stage': 'formal_solver_started', 'case': cid, 'pid': process.pid,
                              'conservative_count': str(before + 1) + '/84', 'run_dir': str(ROOT)}), flush=True)
            process.wait()
        execution.update(returncode=process.returncode, elapsed_solver_wall_s=time.monotonic() - start,
                         ended_at_UTC=datetime.now(timezone.utc).isoformat(), process_reaped=True)
        save(directory / 'execution.json', execution)
        append({'record': 'actual_end', **execution})
        info = {'case_id': cid, 'actual_end_s': None, 'raw_exists': raw.is_file(), 'completion_failure': None}
        output = None
        if raw.is_file():
            info.update(raw_sha256=sha(raw), raw_bytes=raw.stat().st_size)
            raw_hashes[str(raw)] = info['raw_sha256']
            try:
                vectors = read_raw(str(raw))[-1]
                info.update(raw_variables=len(vectors), raw_points=len(next(iter(vectors.values()))))
                if 'time' in vectors:
                    info['actual_end_s'] = float(vectors['time'][-1])
                log = (directory / 'ngspice.log').read_text(errors='replace')
                info['completion_failure'] = completion(execution, log, case, vectors, plan['required_vectors'])
                if info['completion_failure'] is None:
                    base_id = case.get('baseline_case_id')
                    base = read_raw(passed[base_id]['raw'])[-1] if base_id else None
                    output = judge(case, vectors, base, plan['physical_ledger_plan'],
                                   ammeters=plan['ammeters'], mos_nodes=plan['mos_nodes'])
                    del base, vectors
            except Exception as exc:
                info['completion_failure'] = type(exc).__name__ + ': ' + str(exc)
        else:
            info['completion_failure'] = 'No RAW output'
        if output is None:
            output = {'result': 'UNMEASURED', 'why': info['completion_failure']}
        save(directory / 'completion.json', info)
        save(directory / 'judge-output.json', output)
        record = {'case_id': cid, 'scientific': output['result'], 'completion': info,
                  'execution': execution, 'judge_output_sha256': sha(directory / 'judge-output.json')}
        save(directory / 'verdict-binding.json', record)
        append({'record': 'verdict', **record})
        results.append(record)
        summary = {'formal_results': results, 'formal_started': len(results),
                   'conservative_global_count': before + 1, 'global_start_cap': 84,
                   'remaining_registered_cases': [p['case']['case_id'] for p in prepared[index + 1:]],
                   'old_source_files_unchanged': all(sha(Path(p)) == h for p, h in protected.items()),
                   'automatic_repairs_or_diagnostics_started': False,
                   'overall': 'PASS' if len(results) == 31 and all(r['scientific'] == 'PASS' for r in results) else 'INCOMPLETE_OR_FAILED'}
        save(ROOT / 'FORMAL_MATRIX_RESULT.json', summary)
        print(json.dumps({'stage': 'formal_case_finished', 'case': cid, 'scientific': output['result'],
                          'elapsed_solver_wall_s': execution['elapsed_solver_wall_s'], 'raw_end_s': info['actual_end_s']}), flush=True)
        if output['result'] != 'PASS' or info['completion_failure'] is not None:
            save(ROOT / 'STOPPED.json', {'case_id': cid, 'scientific': output['result'],
                 'completion_failure': info['completion_failure'], 'global_count': before + 1,
                 'automatic_retry': False, 'next_formal_case_started': False,
                 'automatic_repair_or_diagnostic_started': False})
            break
        passed[cid] = {'raw': str(raw)}
    (ROOT / 'SHA256SUMS').write_text(''.join((raw_hashes[str(p)] if p.suffix == '.raw' else sha(p)) + '  ' + str(p.relative_to(ROOT)) + '\n' for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
    print(json.dumps({'stage': 'formal_matrix_stopped', 'run_dir': str(ROOT),
                      'started': len(results), 'results': [r['scientific'] for r in results]}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if ROOT.exists():
            save(ROOT / 'EXECUTION_ERROR_STOPPED.json', {'error': type(exc).__name__ + ': ' + str(exc),
                 'automatic_retry': False, 'no_extra_solver_started_after_error': True})
        raise
