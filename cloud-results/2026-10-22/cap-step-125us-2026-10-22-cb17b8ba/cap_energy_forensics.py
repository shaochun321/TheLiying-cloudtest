"""Read-only capacitor-energy diagnostics. Never invokes SPICE or changes a verdict."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

EXPECTED_RAW = '69c950786ca768d5918f5dd79c716c0e7f8b75369f490c071c21acc5b2db7f23'


def read_raw(path):
    header = {}
    names = []
    with path.open('rb') as f:
        while True:
            line = f.readline()
            if not line:
                raise ValueError('Missing Binary header')
            s = line.decode('latin-1').strip()
            if s.startswith('No. Variables:'):
                header['nv'] = int(s.split(':', 1)[1])
            elif s.startswith('No. Points:'):
                header['np'] = int(s.split(':', 1)[1])
            elif s.startswith('Flags:') and s.split(':', 1)[1].strip() != 'real':
                raise ValueError('Only real-valued raw supported')
            elif s == 'Variables:':
                for _ in range(header['nv']):
                    names.append(f.readline().decode('latin-1').split()[1].lower())
            elif s == 'Binary:':
                offset = f.tell()
                break
    expected_bytes = offset + header['nv'] * header['np'] * 8
    if path.stat().st_size != expected_bytes:
        raise ValueError('RAW size inconsistent with one complete real plot')
    data = np.memmap(path, dtype='<f8', mode='r', offset=offset,
                     shape=(header['np'], header['nv']))
    if not np.isfinite(data).all():
        raise ValueError('Non-finite RAW values')
    return {name: data[:, k] for k, name in enumerate(names)}


def total(a):
    return math.fsum(map(float, a))


def analyze(t, v, current, capacitance):
    dt, dv, di = np.diff(t), np.diff(v), np.diff(current)
    vbar = (v[:-1] + v[1:]) * 0.5
    qtrap = dt * (current[:-1] + current[1:]) * 0.5
    power_trap = dt * (v[:-1] * current[:-1] + v[1:] * current[1:]) * 0.5
    # Exact algebraic decomposition of this discrete estimator, not a new score.
    charge_term = vbar * (qtrap - capacitance * dv)
    product_term = dt * dv * di * 0.25
    residual_segments = charge_term + product_term
    energy_integral = total(power_trap)
    state_change = 0.5 * capacitance * (float(v[-1]) ** 2 - float(v[0]) ** 2)
    mismatch = energy_integral - state_change
    denominator = max(abs(energy_integral), abs(state_change))
    worst = np.argsort(np.abs(residual_segments))[-20:][::-1]
    intervals = []
    for k in worst:
        k = int(k)
        intervals.append(dict(index=k, start_s=float(t[k]), end_s=float(t[k + 1]),
                              dt_s=float(dt[k]), dv_V=float(dv[k]),
                              signed_residual_J=float(residual_segments[k]),
                              charge_term_J=float(charge_term[k]),
                              product_term_J=float(product_term[k])))
    bins = np.floor(((t[:-1] + t[1:]) * 0.5 - t[0]) / 0.01).astype(np.int64)
    signed_bins = np.bincount(bins, weights=residual_segments)
    absolute_bins = np.bincount(bins, weights=np.abs(residual_segments))
    leading_bins = np.argsort(absolute_bins)[-20:][::-1]
    segments = [dict(start_s=float(t[0] + k * 0.01), width_s=0.01,
                     signed_residual_J=float(signed_bins[k]),
                     absolute_residual_sum_J=float(absolute_bins[k])) for k in leading_bins]
    # Bins locate interval contributions using midpoint assignment, not partial-bin integration.
    return dict(C_F=capacitance, energy_trap_J=energy_integral,
                state_energy_change_J=state_change, signed_mismatch_J=mismatch,
                relative_mismatch=abs(mismatch) / denominator if denominator else None,
                original_threshold_J=max(0.01 * denominator, 1e-12),
                original_gate_would_pass=abs(mismatch) <= max(0.01 * denominator, 1e-12),
                charge_consistency_term_J=total(charge_term),
                product_quadrature_term_J=total(product_term),
                decomposition_roundoff_J=mismatch - total(charge_term) - total(product_term),
                endpoint_charge_change_C=float(capacitance * (v[-1] - v[0])),
                integrated_current_C=total(qtrap),
                power_absolute_integral_J=total(dt * (np.abs(v[:-1] * current[:-1]) +
                                                       np.abs(v[1:] * current[1:])) * 0.5),
                top_intervals=intervals, top_10ms_bins=segments)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--raw', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    ap.add_argument('--expected-sha256', default=EXPECTED_RAW,
                    help='Default binds the full qualification RAW; empty disables only this binding.')
    args = ap.parse_args()
    raw = args.raw.resolve(strict=True)
    dest = args.out_dir.resolve()
    if dest.exists():
        raise FileExistsError('Use a new output directory; evidence is never overwritten')
    digest = hashlib.sha256()
    with raw.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    actual_sha = digest.hexdigest()
    if args.expected_sha256 and actual_sha != args.expected_sha256.lower():
        raise ValueError('RAW SHA256 differs from expected evidence')
    vectors = read_raw(raw)
    t, v = vectors['time'], vectors['v(g0_vm)']
    if len(t) < 2 or not np.all(np.diff(t) > 0):
        raise ValueError('Time must strictly increase')
    result = dict(scope='OFFLINE_DIAGNOSTIC_ONLY', new_solver_starts=0,
                  raw_sha256=actual_sha, points=len(t), variables=len(vectors),
                  start_s=float(t[0]), end_s=float(t[-1]), capacitors={},
                  interpretation_limits=[
                      'Discrete decomposition is an identity, not proof of physical correctness.',
                      'It separates estimator terms; it does not identify their ultimate cause.',
                      'Original qualification FAIL remains unchanged.',
                      'No interpolation, smoothing, downsampling or threshold change is applied.'])
    for label, key, c in [('cg0_cm', 'i(va_cg0_cm_p)', 1e-7),
                          ('cpar_g0_vm', 'i(va_cpar_g0_vm_p)', 5e-14)]:
        result['capacitors'][label] = analyze(t, v, vectors[key], c)
    dest.mkdir(parents=True)
    (dest / 'cap_energy_analysis.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for label, item in result['capacitors'].items():
        with (dest / (label + '_top_intervals.csv')).open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(item['top_intervals'][0]))
            writer.writeheader()
            writer.writerows(item['top_intervals'])
    print(json.dumps(dict(scope=result['scope'], new_solver_starts=0,
                          raw_sha256=actual_sha, output=str(dest)), ensure_ascii=False))


if __name__ == '__main__':
    main()
