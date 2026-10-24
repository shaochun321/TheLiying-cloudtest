#!/usr/bin/env python3
"""One independent replay of the documented short convergence diagnostic."""
import csv
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np

Q = Path('/workspace/thermal-g3-qualification/sparse-qualification-2026-10-22-17fb81ea')
SOURCE = Q / 'runs/Q1_MOTHER_PROTOCOL/Q1_MOTHER_PROTOCOL.cir'
BASE_RAW = SOURCE.with_suffix('.raw')
NG = Path('/workspace/thermal-g3-env/host/native/bin/ngspice')
EXPECTED_RAW = '69c950786ca768d5918f5dd79c716c0e7f8b75369f490c071c21acc5b2db7f23'
CAP_SECONDS = None  # User explicitly removed the wall-clock limit before launch.
RUN = Path('/workspace/thermal-g3-retests') / ('short-convergence-2026-10-24-' + uuid4().hex[:8])


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(name, value):
    (RUN / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def load_raw(path):
    names, header = [], {}
    with path.open('rb') as f:
        for _ in range(1000):
            line = f.readline().decode('latin1').rstrip('\r\n')
            if line.startswith('No. Variables:'):
                header['nvar'] = int(line.split(':', 1)[1])
            elif line.startswith('No. Points:'):
                header['npts'] = int(line.split(':', 1)[1])
            elif line.startswith('Flags:'):
                header['flags'] = line.split(':', 1)[1].strip()
            elif line == 'Variables:':
                for i in range(header['nvar']):
                    parts = f.readline().decode('latin1').split()
                    assert int(parts[0]) == i
                    names.append(parts[1].lower())
            elif line == 'Binary:':
                offset = f.tell()
                break
        else:
            raise ValueError('Missing RAW binary header')
    assert header['flags'] == 'real' and len(names) == header['nvar']
    assert path.stat().st_size == offset + 8 * header['npts'] * header['nvar']
    data = np.memmap(path, dtype='<f8', mode='r', offset=offset,
                     shape=(header['npts'], header['nvar']))
    columns = {n: i for i, n in enumerate(names)}
    return data, columns, header


def interval_result(data, columns, n, label):
    t = np.asarray(data[:n, columns['time']])
    v = np.asarray(data[:n, columns['v(g0_vm)']])
    assert n > 1 and np.all(np.isfinite(t)) and np.all(np.diff(t) > 0)
    h, dv = np.diff(t), np.diff(v)
    rows, windows, caps = [], [], []
    for name, cap in [('cg0_cm', 1e-7), ('cpar_g0_vm', 5e-14)]:
        current = np.asarray(data[:n, columns['i(va_' + name + '_p)']])
        assert np.all(np.isfinite(v)) and np.all(np.isfinite(current))
        power = .5 * h * (v[:-1] * current[:-1] + v[1:] * current[1:])
        state = .5 * cap * (v[1:] ** 2 - v[:-1] ** 2)
        a = .5 * (v[:-1] + v[1:]) * (.5 * h * (current[:-1] + current[1:]) - cap * dv)
        b = .25 * h * dv * np.diff(current)
        err = power - state
        integrated = float(power.sum())
        stored = float(.5 * cap * (v[-1] ** 2 - v[0] ** 2))
        error = integrated - stored
        scale = max(abs(integrated), abs(stored))
        residual = error - float(a.sum() + b.sum())
        assert abs(residual) <= max(1e-22, scale * 1e-12)
        ids = np.floor((t[:-1] + .5 * h) / .01).astype(np.int64)
        be = np.bincount(ids, weights=err)
        ba = np.bincount(ids, weights=a, minlength=len(be))
        bb = np.bincount(ids, weights=b, minlength=len(be))
        order = np.argsort(np.abs(be), kind='stable')[::-1][:10]
        cap_result = {'capacitor': name, 'C_F': cap,
                      'integrated_terminal_power_J': integrated,
                      'stored_energy_change_J': stored, 'signed_error_J': error,
                      'relative_abs_error': abs(error) / scale if scale else 0,
                      'original_formula_limit_J': max(.01 * scale, 1e-12),
                      'A_J': float(a.sum()), 'B_J': float(b.sum()),
                      'identity_residual_J': residual}
        caps.append(cap_result)
        for rank, k in enumerate(order, 1):
            windows.append({'run': label, 'capacitor': name, 'rank': rank,
                            't0_s': float(k * .01), 't1_s': min(float((k + 1) * .01), float(t[-1])),
                            'error_J': float(be[k]), 'A_J': float(ba[k]), 'B_J': float(bb[k])})
        rows.append({'run': label, 'start_s': float(t[0]), 'end_s': float(t[-1]), **cap_result})
    q = np.asarray(data[:n, columns['v(g0_q)']])
    vdd = np.asarray(data[:n, columns['v(vdd)']])
    y = q - .5 * vdd
    # Ignore the zero-supply startup interval, using the same diagnostic rule in both traces.
    active = (vdd[:-1] > 2) & (vdd[1:] > 2)
    rising = np.flatnonzero(active & (y[:-1] <= 0) & (y[1:] > 0))
    falling = np.flatnonzero(active & (y[:-1] > 0) & (y[1:] <= 0))
    def times(indices):
        return [float(t[k] - y[k] * h[k] / (y[k + 1] - y[k])) for k in indices]
    events = {'rule': 'G0 q crosses half instantaneous VDD while VDD > 2 V; diagnostic only',
              'rising_s': times(rising), 'falling_s': times(falling)}
    return {'start_s': float(t[0]), 'end_s': float(t[-1]), 'points': n,
            'capacitors': caps, 'G0_events': events}, rows, windows


def main():
    RUN.mkdir(parents=True, exist_ok=False)
    print(json.dumps({'run_dir': str(RUN), 'stage': 'preflight'}), flush=True)
    plan = json.loads((SOURCE.parent / 'plan.json').read_text())
    assert digest(SOURCE) == plan['deck_sha256']
    source_bytes = SOURCE.read_bytes()
    source = source_bytes.decode()
    assert '.options sparse method=gear reltol=1e-5 abstol=1e-16' in source
    assert not re.search(r'(?im)^\s*tran.*\buic\b', source)
    assert digest(BASE_RAW) == EXPECTED_RAW  # Exactly one original RAW checksum.
    data, columns, header = load_raw(BASE_RAW)
    baseline_time = data[:, columns['time']]
    n = int(np.searchsorted(baseline_time, 20.5, side='right'))
    endpoint = float(baseline_time[n - 1])
    assert 20.49 < endpoint <= 20.5
    baseline, rows, windows = interval_result(data, columns, n, 'baseline_250us')
    save('baseline_common_interval.json', baseline)
    target_raw = RUN / 'short_125us.raw'
    target_deck = RUN / 'short_125us.cir'
    old_tran = 'tran 0.001 100.27 0 0.00025'
    new_tran = 'tran 0.001 ' + repr(endpoint) + ' 0 0.000125'
    assert source.splitlines().count(old_tran) == 1
    old_write = 'write ' + str(BASE_RAW)
    assert source.splitlines().count(old_write) == 1
    edited = source.replace(old_tran, new_tran).replace(old_write, 'write ' + str(target_raw))
    assert edited.replace(new_tran, old_tran).replace('write ' + str(target_raw), old_write) == source
    target_deck.write_text(edited)
    (RUN / 'deck.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True), edited.splitlines(True), fromfile=str(SOURCE), tofile=str(target_deck))))
    save('test_plan.json', {'scope': 'one independent historical short-diagnostic replay; not qualification',
         'source_deck': str(SOURCE), 'source_deck_sha256': plan['deck_sha256'],
         'source_raw': str(BASE_RAW), 'source_raw_sha256': EXPECTED_RAW,
         'source_raw_checksum_count_this_replay': 1,
         'instructions': '/workspace/attachments/4a00890b-f639-4458-9d4d-bd7aad07ee9d/能量误差定位结果与单次短程收敛对照.md',
         'target_end_s': endpoint, 'baseline_points_in_common_interval': n,
         'baseline_tran': old_tran, 'diagnostic_tran': new_tran,
         'modified_lines': ['tran endpoint and maximum step', 'output RAW destination'],
         'max_solver_launches': 1, 'wall_cap_s': CAP_SECONDS,
         'conservative_global_starts_before': 50, 'global_start_cap': 65,
         'budget_provenance': 'Last available v4 conversation record: 50/65. Restored 30/65 snapshot is not a reset or new budget.',
         'automatic_retry': False, 'automatic_next_case': False,
         'original_scientific_FAIL_preserved': True, 'v4_recovered': False})
    assert os.access(NG, os.X_OK)
    for asset in re.findall(r'(?im)^\s*(?:\.include|pre_osdi)\s+(\S+)', source):
        assert Path(asset).is_file(), asset
    protected = [SOURCE, SOURCE.parent / 'plan.json', Q / 'STOPPED.json', Q / 'qualification-ledger.jsonl', Q / 'session-result.json']
    protected_hashes = {str(p): digest(p) for p in protected}
    # One reservation for this unique run; no automatic retry or subsequent case.
    with (RUN / 'one-shot-reservation.json').open('x') as f:
        json.dump({'max_starts': 1, 'baseline_count': 50, 'allocated_after_actual_spawn': 51}, f)
    execution = {'actual_solver_launches': 0, 'conservative_starts_before': 50,
                 'conservative_starts_after': 50, 'global_start_cap': 65,
                 'automatic_retries': 0, 'timed_out': False,
                 'wall_cap_s': CAP_SECONDS, 'command': [str(NG), '-n', '-b', str(target_deck)]}
    save('execution.json', execution)
    env = os.environ.copy()
    env['SPICE_SCRIPTS'] = '/workspace/thermal-g3-env/spice-scripts'
    start = time.monotonic()
    with (RUN / 'ngspice.log').open('wb') as log:
        process = subprocess.Popen(execution['command'], cwd=RUN, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        execution.update(actual_solver_launches=1, conservative_starts_after=51,
                         started_at_UTC=datetime.now(timezone.utc).isoformat(), pid=process.pid)
        save('execution.json', execution)
        print(json.dumps({'stage': 'solver_started', 'pid': process.pid, 'conservative_count': '51/65', 'run_dir': str(RUN)}), flush=True)
        process.wait()
    execution.update(elapsed_solver_wall_s=time.monotonic() - start, returncode=process.returncode,
                     ended_at_UTC=datetime.now(timezone.utc).isoformat(), process_reaped=True)
    save('execution.json', execution)
    save('retest-ledger.json', {'starts_before': 50, 'starts_after': 51,
         'new_starts': 1, 'global_cap': 65,
         'new_wall_charge_s': execution['elapsed_solver_wall_s'],
         'exact_lifetime_wall_total_s': None, 'old_ledger_overwritten': False,
         'budget_provenance': 'Historical v4 chat record, not the restored old 30/65 snapshot.'})
    result = {'scope': 'short diagnostic replay only', 'execution': execution,
              'target_end_s': endpoint, 'raw_exists': target_raw.is_file(),
              'raw_actual_end_s': None, 'qualification_verdict': 'NOT_RUN',
              'formal_experiments_started': 0, 'next_case_started': False,
              'original_protected_files_unchanged': all(digest(Path(p)) == h for p, h in protected_hashes.items())}
    if target_raw.is_file():
        result['raw_sha256'] = digest(target_raw)
        result['raw_bytes'] = target_raw.stat().st_size
        try:
            new_data, new_columns, new_header = load_raw(target_raw)
            result['raw_actual_end_s'] = float(new_data[-1, new_columns['time']])
            result['raw_points'] = new_header['npts']
            assert set(new_columns) == set(columns)
            assert execution['returncode'] == 0 and not execution['timed_out']
            assert abs(result['raw_actual_end_s'] - endpoint) < 1e-12
            diagnostic, new_rows, new_windows = interval_result(new_data, new_columns, new_header['npts'], 'diagnostic_125us')
            save('diagnostic_common_interval.json', diagnostic)
            rows += new_rows
            windows += new_windows
            result['comparison'] = []
            for old, new in zip(baseline['capacitors'], diagnostic['capacitors']):
                result['comparison'].append({'capacitor': old['capacitor'],
                    'baseline_error_J': old['signed_error_J'], 'diagnostic_error_J': new['signed_error_J'],
                    'absolute_error_ratio': abs(new['signed_error_J']) / abs(old['signed_error_J']),
                    'baseline_A_J': old['A_J'], 'diagnostic_A_J': new['A_J'],
                    'baseline_B_J': old['B_J'], 'diagnostic_B_J': new['B_J']})
            result['G0_events_baseline'] = baseline['G0_events']
            result['G0_events_diagnostic'] = diagnostic['G0_events']
            result['G0_event_count_preserved'] = all(len(baseline['G0_events'][k]) == len(diagnostic['G0_events'][k]) for k in ['rising_s', 'falling_s'])
            grid = np.append(np.arange(0, endpoint, .001), endpoint)
            base_vm = np.interp(grid, baseline_time[:n], data[:n, columns['v(g0_vm)']])
            new_vm = np.interp(grid, new_data[:, new_columns['time']], new_data[:, new_columns['v(g0_vm)']])
            result['G0_vm_common_1ms_grid'] = {'points': len(grid), 'max_abs_difference_V': float(np.max(np.abs(base_vm - new_vm))), 'rmse_V': float(np.sqrt(np.mean((base_vm - new_vm) ** 2))), 'diagnostic_metric_only': True}
            result['status'] = 'COMPLETED_COMMON_INTERVAL_DIAGNOSTIC'
        except Exception as e:
            result['status'] = 'RAW_OR_ANALYSIS_ERROR_STOPPED'
            result['error'] = type(e).__name__ + ': ' + str(e)
    else:
        result['status'] = 'TIMEOUT_STOPPED' if execution['timed_out'] else 'NO_RAW_STOPPED'
    for name, content in [('energy_common_interval.csv', rows), ('top_10ms_windows.csv', windows)]:
        with (RUN / name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(content[0]))
            writer.writeheader()
            writer.writerows(content)
    save('retest_result.json', result)
    (RUN / 'SHA256SUMS').write_text(''.join(digest(p) + '  ' + p.name + '\n' for p in sorted(RUN.iterdir()) if p.is_file() and p.name != 'SHA256SUMS' and p != target_raw))
    print(json.dumps({'run_dir': str(RUN), **result}, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if RUN.exists():
            save('execution_error.json', {'error': type(exc).__name__ + ': ' + str(exc), 'automatic_retry': False})
        raise
