from pathlib import Path
import hashlib,json,os,shutil,subprocess
J=json.loads(Path('/workspace/repair-current.json').read_text());P=Path(J['root']);R=Path(J['previous_batch']);D=P/'runs/C0_ORIGINAL_50MS'
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=float)+'\n')
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
e=read(D/'execution.json');assert e['solver_process_reaped'] and e['actual_solver_launches']==1 and e['returncode']==-15
try:os.kill(e['pid'],0)
except ProcessLookupError:pass
else:raise RuntimeError('Recorded native PID remains active; cannot claim ended')
c={'result':'UNMEASURED','engineering_result':'FAIL','scientific_verdict':None,'why':'Wrong initialization (uic) and output time step introduced by executor; terminated on discovery. No retry.','raw_exists':False,'raw_sha256':None,'actual_end_s':None,'qualification_claimed':False,'solver_returncode':e['returncode']}
assert not (D/'C0_ORIGINAL_50MS.raw').exists();save(D/'completion.json',c);save(D/'judge-output.json',{'result':'UNMEASURED','why':c['why'],'original_scientific_judge_executed':False})
with (P/'repair-ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'end','case':'C0_ORIGINAL_50MS',**e,**c})+'\n');f.flush();os.fsync(f.fileno())
previous=read(R/'CONTINUATION_MANIFEST.json')['protected_original_files_sha256'];verified={p:sha(p)==h for p,h in previous.items()};assert all(verified.values())
save(P/'protected-records-check.json',{'scope':'Only six original stopped-batch protected records; no repository/history/environment audit.','files':verified})
startup=read(P/'offline/original-chain-startup.json');dc=read(P/'offline/original-dc-load.json')
nodefacts=[x for x in startup['events'] if x['node'] in ['v(gw1_col_q)','v(gw2_col_q)','v(thw12f_q)','v(sgw12f_q)','v(cdw12f_q)','v(hw1)','v(hw2)']]
cause={'status':'ROOT_CAUSE_NOT_FULLY_CLOSED','startup':{'facts':nodefacts,'interpretation':'At the preserved absolute-threshold crossings, all sampled q track vdd to about 0.99999995. This supports a power-up rail-tracking transient; it does not establish a membrane-triggered causal order.','relative_vdd_is_diagnostic_only':True,'no_early_events_removed':True,'missing_critical_vectors':startup['missing_critical_vectors'],'por_effectiveness_at_event':'UNMEASURED','first_causal_stage':'UNMEASURED','new_diagnostic_status':'INVALID_EXECUTOR_SETTINGS_TERMINATED_NO_RETRY','evidence':['offline/original-chain-startup.json','runs/C0_ORIGINAL_50MS/EXECUTION_ERROR.json']},'reference':{'equation':'IL=(VDD-VR)/Rt - VR/Rb; VR=alpha*VDD - Rth*IL; dynamic C*dVR/dt=divider inflow-IL','load_sign':'positive = net current flowing out of vrest into external loads','rt_ohm':2000,'rb_ohm':1000,'rth_ohm':2000/3,'actual_internal_vdd_used':True,'dc_capacitor_current_A':0,'three_points':[{k:x[k] for k in ['case','actual_internal_vdd_V','vrest_V','unloaded_prediction_V','upper_divider_current_A','lower_divider_current_A','inferred_net_load_A','independently_recovered_resistor_load_A','unmeasured_mos_terminal_count','independent_node_residual_A']} for x in dc],'fact':'Independent resistor-current sums explain the inferred net reference load to within approximately 0.49 pA at all three supply points. Missing MOS currents prevent an independent complete-node KCL claim.','maximum_difference_A':max(abs(x['inferred_net_load_A']-x['independently_recovered_resistor_load_A']) for x in dc),'independent_complete_node_closure':'UNMEASURED','evidence':['offline/original-dc-load.json','offline/vrest-branch-inventory.json']}}
save(P/'ROOT_CAUSE_TABLE.json',cause)
steps=[('C0_ORIGINAL_50MS','INVALID_TERMINATED'),('DC_3','NOT_STARTED'),('CHAIN_STARTUP_0_3S','NOT_STARTED'),('Q1_MOTHER_PROTOCOL','NOT_STARTED'),('Q1_MOTHER_HALFSTEP','NOT_STARTED'),('CHAIN_12_W_F','NOT_STARTED'),('G0_W','NOT_STARTED'),('DC_2P7','NOT_STARTED'),('DC_3P2','NOT_STARTED')]
matrix={'result':'REPAIR_FAILED','reason':'Executor numerical/initialization error in the only optional diagnostic; no retry or candidate execution after invalid critical observation. This is an execution failure, not a scientific rejection of a physical candidate.','actual_new_solver_starts':1,'global_starts_before':39,'global_starts_after':40,'global_cap':65,'remaining_start_slots':25,'solver_wall_s':e['solver_wall_s'],'exact_global_historical_wall_s':None,'effective_wall_limit_s':None,'automatic_retries':0,'new_candidate_runs':0,'new_candidate_qualification':'NOT_GRANTED','cases':[{'case_id':cid,'status':status,'actual_starts':1 if i==0 else 0,'solver_wall_s':e['solver_wall_s'] if i==0 else 0.,'actual_end_s':None,'raw_sha256':None,'original_scientific_verdict':'UNMEASURED','reason':c['why'] if i==0 else 'Blocked: invalid preliminary diagnostic; candidate not frozen.'} for i,(cid,status) in enumerate(steps)],'original_stopped_records_unchanged':True,'no_solver_process_remaining':True}
save(P/'TEST_MATRIX_RESULT.json',matrix)
save(P/'candidate_manifest.json',{'status':'NOT_CREATED_OR_FROZEN','source_evidence_commit':'708e1033c5cb43e6f917f2ac156b041a8f2d1541','source_software':J['source'],'source_python_sha256_file':'source-files-sha256.json','physical_changes':[],'candidate_solver_starts':0,'parameters_chosen':False,'reason':'Critical original diagnostic invalidated by executor settings error; no physical candidate is represented as causally justified or validated.','old_qualification_not_inherited':True,'fixed_candidate_test_sequence':[x[0] for x in steps[1:]],'code_diff':'NO_PHYSICAL_CANDIDATE.diff'})
(P/'NO_PHYSICAL_CANDIDATE.diff').write_text('')
(P/'REPAIR_SUMMARY.md').write_text('''# 本轮执行失败，已停止（REPAIR_FAILED）

本轮已完成附件校验及零求解复核，但未形成、冻结或验证物理候选。唯一一次原版 0–50 ms 补测因执行器错误加入 `uic`，并将输出步长由 1 ms 改为 125 μs，违反“只改诊断终点及保存量”的约束。发现后立即终止；退出码 -15，实际耗时 **36.356865 秒**，没有生成 RAW，真实终点未知。该数据不用于根因或资格判断，没有自动重试。

既有完整 CHAIN RAW 已按原 SHA256 校验一次。原评分绝对阈值为 1.482405740 V；父 q 与多个关系 q 在约 10.213752 ms 交越时几乎等于当时 VDD，支持上电随轨变化的解释。POR 与关键内部比较器电位未保存，不能声称已测实 POR 有效，也不能确定异常首先发生在哪一级。旧事件全部保留。

三个旧 DC 点的净参考负载反推约为 **16.1084、18.3652、19.8744 μA**；由各电阻电压差独立恢复的负载与之相差不到 0.49 pA，足以支持带负载分压造成 vrest 下移的解释。260 个 MOS 端口电流未保存，因此完整独立节点 KCL 仍为 UNMEASURED，不能用反推值循环证明闭合。

真实新增启动 **1 次，累计 40/65，余 25 次**。本轮墙钟限制按当前用户授权解除；历史全局精确墙钟未知。候选 DC、3 s 烟雾、两项母本资格、完整 CHAIN、G0 及其余两个 DC 均未启动，均未记 PASS。旧资格只适用于旧电路，旧 FAIL、STOPPED 和账本经定点散列核对保持原样。结论是执行失败，不能据此判定整改拓扑成功或失败；本轮结束，不自动补测或继续候选。

入口：`ROOT_CAUSE_TABLE.json`、`TEST_MATRIX_RESULT.json`，原错误命令及日志见 `runs/C0_ORIGINAL_50MS/`。本次没有大波形可交付，也未重新打包旧 RAW。
''',encoding='utf-8')
# The executed deck is immutable evidence. Corrected generator is archival only and has NOT been executed.
code=P/'executor';code.mkdir()
for f in ['prepare_startup_repair.py','run_original_50ms.py','finalize_failed_startup_repair.py']:
 shutil.copy2(Path('/workspace')/f,code/f)
shutil.copy2('/workspace/prepare_original_50ms.py',code/'prepare_original_50ms_CORRECTED_NOT_EXECUTED.py')
shutil.copy2('/workspace/thermal-g3-repair/original-50ms-runner.log',D/'runner.log')
save(P/'EXECUTOR_CORRECTION_NOT_RUN.json',{'faulty_executed_analysis':'tran 0.000125 0.05 0 0.000125 uic','correct_analysis':'tran 0.001 0.05 0 0.000125','generator_correction':'Derive original analysis tokens; replace only stop token. Corrected generator archived but NOT executed.','executed_deck_not_modified':True,'reruns':0,'post_termination_record_completion':'This finalizer explicitly records absent RAW; the runner originally raised FileNotFoundError after the native process had already been terminated.','native_launches_by_finalizer':0})
state=read('/workspace/thermal-g3-latest-state.json');state.update(source_batch=str(P),global_start_count=40,unused_start_slots=25,matrix_batch_status='REPAIR_FAILED',no_legal_dependency_frontier=None,unstarted_cases_blocked_dependency=None,all_new_solver_processes_reaped=True,new_batch_solver_wall_s=e['solver_wall_s'],exact_global_historical_wall_s=None,temporary_wall_limit_waiver_scope='This now-ended repair batch only.',pushed=False,push_status='NOT_PUSHED',remote_evidence_commit=None,local_evidence_commit=None)
save('/workspace/thermal-g3-latest-state.json',state);save(P/'REPAIR_FINISHED.json',matrix)
print(json.dumps({'root':str(P),'result':matrix['result'],'actual_starts':1,'global':40,'elapsed_s':e['solver_wall_s'],'new_candidate_runs':0,'old_records_unchanged':True}))
