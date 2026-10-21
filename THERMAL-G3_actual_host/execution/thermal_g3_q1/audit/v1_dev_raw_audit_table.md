| id | tag | raw | points | x_end | h feedback (deck) | ledger error | q events (VDD/2) |
|---|---|---|---:|---:|---|---|---|
| dev-001 | np1_g0_single_site | sha a8c0218f | 123 | 0.03194 | h→ko2 (N-P1 thr feedback) | ngspice reported 'simulation(s) aborted' | v(gc1_b10_q): 0; v(gc1_b1_q): 0; v(gc1_b5_q): 0; ... |
| dev-002 | np1_g0_single_site_cnode | sha 493bbef0 | 1012 | 1.437 | h→ko2 (N-P1 thr feedback) | ngspice reported 'simulation(s) aborted' | v(gc1_b10_q): 0; v(gc1_b1_q): 0; v(gc1_b5_q): 0; ... |
| dev-003 | np1_g0_single_site_por | sha 934d929a | 19495 | 36 | h→ko2 (N-P1 thr feedback) | - | v(gw1_b1_q): n=1, first up 2.8528 / down 4.2433; v(gc1_b10_q): 0; v(gc1_b1_q): 0; ... |
| dev-004 | np1_g0_single_site_v2 | sha 9b596ee3 | 4821 | 6.904 | h→ko2 (N-P1 thr feedback) | ngspice reported 'simulation(s) aborted' | v(gw1_b1_q): n=1, first up 6.8716 / down null; v(gc1_b10_q): 0; v(gc1_b1_q): 0; ... |
| dev-005 | np1_g0_single_site_v3 | sha 9b503c03 | 10378 | 7.992 | h→ko2 (N-P1 thr feedback) | ngspice reported 'simulation(s) aborted' | v(gw1_b1_q): n=1, first up 6.8710 / down null; v(gw1_b5_q): n=1, first up 7.6400 / down null; v(gc1_b10_q): 0; ... |
| dev-006 | np1_g0_single_site_v4 | sha 87b58428 | 250275 | 36 | h→ko2 (N-P1 thr feedback) | - | v(gc1_b10_q): n=2, first up 16.8853 / down 18.4027; v(gc1_b1_q): n=2, first up 15.9064 / down 21.3513; v(gc1_b3_q): n=3, first up 12.5961 / down 14.1139; ... |
| dev-007 | np1_g0_single_site_v5 | sha adf585e3 | 262348 | 36 | h→ko2 (N-P1 thr feedback) | - | no q vector saved |
| dev-008 | np1_g0_single_site_v6 | sha bd3250d3 | 578016 | 36 | h→ko2 (N-P1 thr feedback) | - | no q vector saved |
| dev-009 | np1_g0_single_site_v7 | sha 0a32a373 | 272958 | 36 | h→ko2 (N-P1 thr feedback) | - | no q vector saved |
| dev-010 | np1_g0_single_site_v8 | absent | - | - | h→ko2 (N-P1 thr feedback) | no raw output | no raw |
| dev-011 | single_nrc | sha bd54f367 | 2412 | 5 | h→ko2 | - | no q vector saved |
| dev-012 | single_nrc | sha 75711f10 | 35120 | 5 | h→ko2 | - | v(n0_q): n=42, first up 0.3570 / down 0.3570; v(n1_q): n=42, first up 0.3576 / down 0.3577; v(n2_q): n=43, first up 0.3583 / down 0.3583 |
| dev-013 | single_nrc | sha 0ec5d7be | 1817 | 5 | h→q | - | v(n0_q): n=1, first up 0.0103 / down 0.3856; v(n1_q): n=1, first up 0.0103 / down 0.3862; v(n2_q): n=1, first up 0.0103 / down 0.3867 |
| dev-014 | single_nrc | sha 28ec7e23 | 859 | 5 | h→q | - | v(n0_q): n=1, first up 0.0103 / down null; v(n1_q): n=1, first up 0.0103 / down null; v(n2_q): n=1, first up 0.0103 / down null |
| dev-015 | single_nrc | sha 8736b32f | 871 | 5 | h→qb | - | v(n0_q): 0; v(n1_q): 0; v(n2_q): 0 |
| dev-016 | single_nrc | sha 214b9bea | 870 | 5 | h→q | - | v(n0_q): 0; v(n1_q): 0; v(n2_q): 0 |
| dev-017 | strong_input | sha f17f417a | 3177 | 5 | h→qb | - | v(n_q): n=6, first up 2.7591 / down 2.7714 |
| dev-018 | measure_currents | absent | - | - | - | no raw output | no raw |
| dev-019 | measure_currents | absent | - | - | - | no raw output | no raw |
| dev-020 | cmp_settle | sha 15613c0e | 291 | 0.05 | h→qb | - | v(cmp_q): 0 |
| dev-021 | cmp_sweep | sha f8b8b7a1 | 251 | 2.5 | h→qb | - | sweep over v(v-sweep) (no time events) |
| dev-022 | strong_input | sha 37640316 | 1025 | 5 | h→q | - | v(n_q): n=1, first up 2.7495 / down null |
| dev-023 | full_pulse | sha 9af81801 | 1325 | 8 | h→q | - | v(n_q): n=1, first up 2.7495 / down null |
| dev-024 | diagnose_q | sha 989bebad | 1025 | 5 | h→q | - | v(n_q): n=1, first up 2.7495 / down null |

Ledger: 24 starts / 24 ends, solver wall sum 22565.592 s, sha 2723fdb7a38c.
