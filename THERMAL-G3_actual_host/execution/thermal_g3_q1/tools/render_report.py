"""Render the Q1-R closure delivery report from the generated JSON (INFRA).
Every result and number comes from results/selfcheck.json, results/static_check.json,
results/cloud_unpack_check.json, analysis/input_bounds.json, prereg/cases_q1r.json and
FREEZE_Q1R.json; the text only names what each item checks.
Output: cell-cell/工作报告/THERMAL-G3-Q1-R准备包交付_D补齐_2026-10-10.md (earlier delivery reports are
not touched by this script).
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, ROOT)
OUT = os.path.join(REPO, "cell-cell", "工作报告", "THERMAL-G3-Q1-R准备包交付_D补齐_2026-10-10.md")
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))

# review 2026-10-10 closure items -> what was implemented -> selfcheck items that test it
CLOSURE = [
    ("A 母本弱输入带符号 + rec/活动/支路回读",
     "criteria_q1r 弱门按证书 weak_expected_du 的符号判定（Σ 反向弱输入使膜电位下降）；新增 trace/rec 在每次 q 结束时充足的门；"
     "analysis/raw_bounds.py 回读每个 q 结束时的 rec/op_at、活动窗、各段支路电荷，与离线估算并列，随母本判定输出保存",
     ["judge_normal_passes", "judge_sigma_negative_weak_passes", "judge_weak_wrong_sign_fails",
      "judge_rec_not_charged_at_q_end_fails", "judge_trace_not_charged_at_q_end_fails", "judge_no_recovery_fails",
      "readback_unmeasured_without_raw", "readback_rec_activity_branches_measured", "readback_branches_unmeasured_without_plan"]),
    ("B 生产入口：求解→完成门→读 raw→登记判定→逐门证据→裁决→放行",
     "run_case 完成后调用 observers/judges.judge，写 results/verdicts/<aid>_<case>.json，"
     "裁决绑定 freeze/deck/raw/backend/判定输出散列；公开 record_verdict 已删除，私有入口拒绝未知、未完成、他冻结、raw 被改的分析；"
     "科学 FAIL 与执行失败停轮；UNMEASURED 不放行；成本门按实测每元件墙钟预测；一轮只用首个启动的后端",
     ["coord_qual_protocol_judged_pass", "coord_verdict_bound_to_freeze_deck_raw_judge", "coord_formal_refused_until_halfstep_pass",
      "coord_halfstep_judged_against_protocol_raw", "coord_formal_unblocked_after_qual_pass", "coord_num_g0_halfstep_vs_g0_w_pass",
      "coord_required_fail_stops_round", "coord_unmeasured_blocks_dependants", "coord_aborted_raw_no_verdict_round_stopped",
      "coord_record_verdict_guards", "coord_cost_gate_forecast_from_measured", "coord_cost_gate_refuses_over_budget",
      "coord_backend_fixed_by_first_start", "coord_infra_failure_rerunnable", "coord_rerun_only_after_infra_failure",
      "full_num_halfstep_vs_full_nom_shift_fails"]),
    ("C 判定所需向量与保存表闭合；物理账有数据",
     "保存表 = 判定所需 ∪ 账本探针（netlists/ledger_plan.py 的定点 0 V 电流计）；静态检查逐例核对，并核对半步基线网表；"
     "CHAIN 保存 load_pos/load_neg；半步比较用显式角色映射；observers/ledger_q1r.py 做 KCL/电荷/能量/电容能量与模型域；"
     "DC 判定核对电源 KCL、分压比、偏置电流与模型域；完成门覆盖全部保存量",
     ["static_chain_closure_passes", "static_chain_missing_load_pos_caught", "static_halfstep_baseline_missing_vector_caught",
      "deck_identity_independent_of_backend_paths", "chain_missing_load_pos_unmeasured", "num_g0_mapping_passes",
      "halfstep_formal_missing_vector_unmeasured", "halfstep_without_baseline_unmeasured",
      "ledger_current_plus5pct_fails_CHAIN_12_W_F", "ledger_current_plus5pct_fails_FULL_NOM", "ledger_missing_current_not_pass",
      "dc_references_at_10V_fail", "dc_supply_kcl_mismatch_fails", "dc_model_domain_outside_fails", "coord_nan_rejected"]),
    ("D 原 31 例的正式语义（窗口、因果、返回、重复、对基线）",
     "observers/judges.py：G0 逐步共同迹窗/AND/集电/端口因果/返回/重复，CUT 无组输出；CHAIN 相对父与刺激的因果、Θ/Σ/Cdir 支撑、"
     "负载消耗、返回；STRUCTURE 对基线 raw；FULL 按暖/冷块计分；NUM 半步；DC 静态账",
     ["formal_legal_synthetic_all_pass", "g0_no_common_trace_window_fails", "g0_no_repeat_fails", "g0_port_twice_fails",
      "g0_collector_before_and_fails", "g0_cut_group_output_fails", "g0_cut_without_baseline_unmeasured",
      "chain_child_before_parents_fails", "chain_theta_outside_target_activity_fails", "chain_load_not_consumed_fails",
      "chain_opposite_cdir_fails", "chain_not_returned_fails", "struct_port_cut_cdir_fires_fails",
      "struct_without_baseline_unmeasured", "struct_bleed_history_not_bled_fails", "struct_swap_not_reversed_fails",
      "invalid_sync_not_synchronous_fails", "invalid_stale_history_valid_fails", "full_silent_parents_fails",
      "full_wrong_window_fails", "full_mirror_unswapped_fails", "full_space_cut_edge_fires_fails",
      "full_cool_rail_not_consumed_fails"]),
]


# limited supplement (review 2026-10-10 §2): real support gate -> what it checks -> counterexample items
SUPPORT = [
    ("theta_support_all_events",
     "每个 Θ 事件：源历史 ≥ H_VALID 且由源集电事件形成、目标 G0 活动口为高；支持区间内注入支路电荷 ≥ (1−TOL)·Cm·Δvm，且该电荷 ≥ (1−TOL) 落在支持区间；进入前膜状态从静息起",
     ["support_review_chain_no_history_no_spatial_fails", "support_review_full_no_activity_fails",
      "support_theta_injection_outside_support_fails", "support_theta_vm_without_charge_fails"]),
    ("sigma_spatial_support_all_events",
     "每个 Σ 事件：实际空间节点差 sp_i − sp_s（r 向取反，SWAP 变体按声明取反）≥ V_FLOOR 且由 G0 活动抬起；OTA m4+m2 净注入电荷解释膜上升；全程等电位则全部 Σ 事件不成立",
     ["support_review_chain_no_history_no_spatial_fails", "support_sigma_equipotential_fails"]),
    ("cdir_hs_from_matching_sigma",
     "hs 每次上升都落在同向 Σ 活动内（加历史 RC 时间）",
     ["support_hs_without_matching_sigma_fails"]),
    ("cdir_support_all_events",
     "每个 Cdir 事件（不只第一个）：hs ≥ H_VALID 且同向 Θ 活动口为高；注入电荷与膜状态同 Θ",
     ["support_review_chain_no_history_no_spatial_fails", "support_later_unsupported_event_fails"]),
    ("cdir_conflict_consistent",
     "hc（反向 Σ 历史）与 Θ 活动同时为高处冲突分流 kh 有电流且 Cdir 不进入；其余 Θ 活动期分流电荷 ≤ TOL × 注入电荷",
     ["support_conflict_with_cdir_firing_fails"]),
    ("ports_canonical",
     "每个关系核与两端 G0：活动口上升前有 q（端口延迟内）；q 在活动内或随后进入活动；每段活动恰一个规范脉冲；活动外无脉冲",
     ["support_review_full_no_activity_fails", "support_cdir_activity_zero_load_claimed_fails",
      "support_pulse_outside_activity_fails", "support_two_pulses_in_one_activity_fails"]),
    ("load_consumed_in_cdir_activity",
     "每段 Cdir 活动内该路径汇聚电流中位数 ≥ (1−TOL)·Iref，负载轨高出 vmid ≥ (1−TOL)·Iref·R·(1−e^{−T/τ})；活动外路径电荷 ≤ TOL × 活动内 + 10 pA × 时长",
     ["support_review_full_no_activity_fails", "support_load_current_outside_cdir_activity_fails",
      "support_cdir_activity_zero_load_claimed_fails"]),
    ("load_pos/neg_quiet_outside_cdir_activity",
     "负载轨在所有对应 Cdir 活动（加 5τ 衰减）之外不抬升",
     ["support_rail_rise_without_cdir_activity_fails", "support_review_full_no_activity_fails"]),
]
SUPPORT_PASS = ["formal_legal_synthetic_all_pass", "support_legal_sigma_before_theta_integration_delay_passes",
                "support_injection_read_from_ledger_terms", "support_full_injection_read_from_probes"]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    sc, st, ce, ca, fr = (J("results/selfcheck.json"), J("results/static_check.json"), J("analysis/input_bounds.json"),
                          J("prereg/cases_q1r.json"), J("FREEZE_Q1R.json"))
    up = J("results/cloud_unpack_check.json") if os.path.exists(os.path.join(ROOT, "results", "cloud_unpack_check.json")) else None
    from tools.make_cloud_package import NOT_READY, topo
    sup = sorted(f for f in os.listdir(ROOT) if f.startswith("FREEZE_Q1R_superseded_"))
    nom = ce["nom"]
    it = sc["items"]
    L = []
    L.append("# THERMAL-G3-Q1-R 准备包交付·D 补齐（2026-10-10）\n")
    L.append("日期：2026-10-10")
    L.append("执行依据：`交叉比对/THERMAL-G3-Q1-R收口交付_独立裁定与有限补齐_2026-10-10.md` §2（原 D 支持与消费语义）；"
             "前序：`交叉比对/THERMAL-G3-Q1-R准备包交付_独立裁定与收口执行清单_2026-10-10.md`（A–D）及用户补充 §3.1")
    L.append("代码路径：`research/thermal_g3_q1/`")
    L.append(f"冻结文件：`research/thermal_g3_q1/FREEZE_Q1R.json`（sha256 `{sha(os.path.join(ROOT, 'FREEZE_Q1R.json'))}`）；"
             f"旧冻结保留为 {', '.join('`' + s + '`' for s in sup) or '无'}")
    L.append("生成方式：本文由 `tools/render_report.py` 从 selfcheck / static_check / cloud_unpack_check / input_bounds / cases / FREEZE 生成；"
             "结果与数值均为读取，不是手填\n")
    L.append("## 一、结论\n")
    L.append(f"- 冻结状态：**{fr['status']}**；未就绪原因：{fr['not_ready_reasons'] or '无'}。冻结的后端：{fr.get('backend')}。")
    L.append(f"- 本轮求解启动：**{sc['solver_starts']} 次**（自检与解包检查只用替身可执行文件写合成 raw）。")
    L.append(f"- 无求解自检：{sc['n_pass']}/{sc['n']} PASS。静态检查：{st['n_cases']} 份网表，all_pass={st['all_pass']}。")
    L.append(f"- 离线候选估算：**{ce['status']}**（没有找到不相容约束，**不是资格**）。")
    if up:
        L.append(f"- 云端运行包：`{up['zip']['name']}`（sha256 `{up['zip']['sha256']}`，放在 git 之外）。"
                 f"在项目外的新临时目录解包检查：all_pass={up['all_pass']}。云端环境 {len(NOT_READY)} 项登记为 **NOT_READY**。")
    L.append("- 资格状态：母本、G0、关系、全网、物理账本均**未取得**；合成数据只检验判定软件，不说明电路行为。\n")
    L.append("## 二、D 补齐：真实支持门 → 检查内容 → 命中的反例\n")
    L.append("实现：`observers/support_q1r.py`（`edge_support`），由 `observers/judges.py` 在 CHAIN、STRUCTURE（SWAP 按声明反向读出）"
             "和 FULL（每极性每边）调用；覆盖每条边六个核的全部事件，不强迫 Σ 在 Θ 之后，事件可在支持结束后的比较器有限延迟 D_CMP 内进入，"
             "规范脉冲按活动入口计。阈值：H_VALID = 证书 valid_entry_min，H_GATE = H_VALID/2，V_FLOOR = 10 mV，TOL = 0.10，"
             "D_CMP = 2·max_step + 1 ms，D_PORT = 5·OP_RC·OP_C + D_CMP。缺量返回 UNMEASURED。\n")
    L.append("自检项结果为 PASS 表示：该反例在所列支持门上被判 FAIL（按要求拒绝），且整体判定不是 PASS。\n")
    L.append("| 支持门 | 检查内容 | 命中的反例（自检项） | 自检结果 |\n|---|---|---|---|")
    for g, what, names in SUPPORT:
        for n in names:
            L.append(f"| {g} | {what} | {n} | {it.get(n, {}).get('result', 'MISSING')} |")
            what = "〃"
    L.append("")
    L.append("| 必须通过的合法记录 | 结果 |\n|---|---|")
    for n in SUPPORT_PASS:
        L.append(f"| {n} | {it.get(n, {}).get('result', 'MISSING')} |")
    L.append("")
    L.append("新增的测量量（只加测量，不改功能电路，不增 case 与求解次数）：CHAIN 族账本节点加 `load_pos`/`load_neg`（各路径汇聚电流 "
             "`i(va_nag…_cp_d)` 与轨上 KCL）；FULL 加 60 个定点端子电流探针（Θ/Cdir `rm_mo` 漏极、Σ OTA `m2`/`m4` 漏极、Cdir `kh` 漏极，"
             "仅测量，不计入 KCL）及空间节点 `sp*`、边中点 `sp*s*`、Cdir `hs`/`hc` 电压。网表身份因此改变，已重新冻结。\n")
    L.append("## 三、原收口项回归（实现 → 自检项 → 结果）\n")
    for title, what, names in CLOSURE:
        L.append(f"### {title}\n")
        L.append(what + "\n")
        L.append("| 自检项 | 结果 |\n|---|---|")
        for n in names:
            L.append(f"| {n} | {it.get(n, {}).get('result', 'MISSING')} |")
        L.append("")
    L.append("物理账范围（登记，非全网）：账本节点上每个端子都经 0 V 电流计（含 MOS 栅/位移电流与 C_NODE），"
             "检查 KCL（10 ms 分箱，p99 ≤ 1e-3、峰值 ≤ 1e-2）、节点端口能量（≤ 1 %）、每个电容的储能变化；电源能量只报告；"
             "模型域检查四端电压均保存的 MOS。母本：三角色 vm/vmd/vms；G0：集电核；CHAIN 族：Θ/Σ/Cdir 正反与两条负载轨；FULL：两条负载轨"
             "（关系注入端子探针只作测量，不计入 KCL）；DC：工作点全节点。"
             "**不声称全网能量闭合。**\n")
    L.append("## 四、三类状态分列\n")
    L.append("### A. 代码已实现并自检（全部自检项）\n")
    L.append("| 自检项 | 结果 |\n|---|---|")
    for k, x in it.items():
        L.append(f"| {k} | {x['result']} |")
    L.append("")
    L.append("| 静态检查（每份网表）| 元件 | MOS | 判定所需+账本向量 | 结果 |\n|---|---:|---:|---:|---|")
    for k, r in sorted(st["cases"].items()):
        n_req = r["checks"].get("judge_vectors_saved", {}).get("n_required", "")
        L.append(f"| {k} | {r['n_elements']} | {r['n_mos']} | {n_req} | {'PASS' if r['pass'] else 'FAIL'} |")
    L.append("")
    L.append(f"案例矩阵：分组计数 {ca['counts']}；qualification {ca['n_qualification']}，formal {ca['n_formal']}。"
             f"任务表读包内副本 `{ca['task_table']['path']}`（sha256 `{ca['task_table']['sha256'][:16]}…`）。\n")
    L.append("### B. 候选估算（离线，不是资格）\n")
    L.append("| 角色 | 弱输入期望 Δu (mV) | 检查 | 结果 | 裕量 (mV) |\n|---|---:|---|---|---:|")
    for role, rr in nom["roles"].items():
        for k, c in rr["checks"].items():
            m = c.get("margin_V")
            L.append(f"| {role} | {rr['weak_expected_du_V'] * 1e3:.1f} | {k} | {'PASS' if c['pass'] else 'FAIL'} | "
                     f"{'' if m is None else f'{m * 1e3:.1f}'} |")
    L.append("\n未取得来源的假设：" + "；".join(ce["assumptions_unsourced"]) + "。\n")
    L.append("### C. 动态未测（只能由求解给出）\n")
    for x in nom["dynamic_unmeasured"]:
        L.append(f"- {x}")
    L.append("- 母本回读（`analysis/raw_bounds.py`）的实测值：两项前置求解之前全部 UNMEASURED\n")
    L.append("## 五、云端运行包（§3.1，已按新冻结重建）\n")
    if up:
        L.append("| 解包检查项 | 结果 |\n|---|---|")
        for k, x in up["items"].items():
            L.append(f"| {k} | {'PASS' if x.get('pass') else 'FAIL'} |")
        L.append("")
    L.append("包内：补丁后的代码、2+31 协议、节点/向量映射（账本计划 + 判定）、观测器与生产判定入口、参数、模型卡、VA 源与 include、"
             "来源记录、v1 账本封存快照、预算合同、输入散列清单、运行时身份清单、RUN.md、tasks.json、Windows 平台二进制登记。")
    L.append("后端策略：一轮只用首个启动（Q1_MOTHER_PROTOCOL）的后端；如用云端，从 Q1_MOTHER_PROTOCOL 起就用云端；"
             "不设跨平台比较门，不按后端另开 61 次预算，重跑名额不是平台比较配额。\n")
    L.append("| NOT_READY 项 | 原因 |\n|---|---|")
    for x in NOT_READY:
        L.append(f"| {x['item']} | {x['why']} |")
    L.append("")
    L.append("## 六、勘误（前两份交付报告）\n")
    L.append("- `工作报告/THERMAL-G3-Q1-R准备包交付_收口_2026-10-10.md`（冻结 2b55a993）把原 D 判为已完成，不成立："
             "`chain_core` 只核首次 q 先后与目标/Θ 活动，`judge_full` 只核块内首次 q、负载幅度与末态；评审的两类反例"
             "（CHAIN 源历史/匹配历史为 0 且空间节点全程等于 vmid；FULL 全部活动口与脉冲口为 0）当时整体 PASS、物理账 PASS。"
             "本轮由第二节的支持门拒绝，冻结 2b55a993 保留为 superseded。")
    L.append("- 更早的 `工作报告/THERMAL-G3-Q1-R准备包交付_2026-10-10.md` 的四项错误见该文件顶部勘误。\n")
    L.append("## 七、启动方式（由用户授权）\n")
    L.append("用户写入 `research/thermal_g3_q1/prereg/LAUNCH_PERMISSION.json`（freeze_sha256 为本冻结文件的散列）：\n")
    L.append("```json\n" + json.dumps(fr["permission_format"], ensure_ascii=False) + "\n```\n")
    order = topo(sorted(ca["cases"], key=lambda c: (c["phase"] != "qualification", c["case_id"])))
    L.append("执行顺序：先两项前置（各 600 s 上限），再按依赖顺序跑 31 项：" + " → ".join(order) + "。")
    L.append("唯一入口 `python -B runtime/coordinator.py <case_id>`；预算 dev 24（已封）/ qualification 2 / formal 31 / rerun 4 = 61；"
             "累计墙钟 48 h；阶段墙钟 1200 / 108000 / 14400 s。\n")
    L.append("## 八、未完成项\n")
    L.append("- 两项前置求解与 31 项正式求解：等待用户授权。")
    L.append("- 云端执行：NOT_READY 各项需在执行主机上完成（后端登记、主机冻结、用户对该冻结的授权）。")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
