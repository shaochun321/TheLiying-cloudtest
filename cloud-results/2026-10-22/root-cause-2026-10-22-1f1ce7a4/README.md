# THERMAL-G3：有限根因诊断与测试结果

日期：2026-10-22（Asia/Shanghai）。本轮已结束；没有进入资格或正式实验。

**结果：D1 将矩阵求解器从 KLU 改为 SPARSE 1.3 后，原母电路一次运行达到 20 ms，短程烟雾通过。按既定停止规则，D2–D4 未运行。**

| 检查/测试 | 结果 | 新增真实启动 |
|---|---|---:|
| 零求解证据、上电状态及候选支路核对 | 完成；未发现该范围内明显端口或量纲错误，根因未定位 | 0 |
| R0完成判定回归 | 2/2通过，真实中止日志和截断RAW均被正确拒绝 | 0 |
| D1 Sparse单因素对照 | 日志确认SPARSE 1.3；达到20.000000ms，无中止/失败日志 | 1 |
| D2、D3、D4 | 出现有效差异后按规则停止探索，未运行 | 0 |
| R1/R2完整资格及31项正式实验 | 未获该候选运行授权，未运行 | 0 |

## 本次观察与可支持的结论
固定KLU基线提交：c0e0e95baf0baea08b4f5c028448b377ed3a893b。
KLU基线在5.732389312857695ms报Timestep too small并中止；D1为同一母电路、同一原EKV、同一Gear及容差，仅换SPARSE并替换实际文件路径，达到20ms。
D1实际墙钟2.8219074370008457s，退出码0，未超时；1170点×96变量，95项所需观察量全部存在，RAW结构完整、数值有限、时间严格递增。项目原完成判定方法也接受该20ms完成结果。版本差异见D1-single-factor.diff，详细判定见D1-sparse/diagnostic.json。

这支持“本次上电完成对矩阵求解器选择敏感”，得到数值设置修复候选；不证明KLU存在缺陷、物理正确或完整资格通过，也未测试跨次重复性。不同自适应时间网格不能作逐行时间点对比。
20ms时vsrc=3V，vdd约2.942736V，vrest约0.638197V，por_ok约5.822586uV。参考节点未被本试验验证为稳定，未验证POR释放；不能将电源升到3V等同完整启动完成。原静态输入保持不变，不添加更长烟雾运行。

## 预算及保护
用户明确批准：“批准上限65，最多4次诊断，保留33次额度”。
本轮只用1次，累计28→29/65；总剩余36次，其中资格/正式预留33次，未用诊断额度3次。未用额度不要求继续消耗。
本轮独立扣账2.8219074370008457s。旧的三次额外启动耗时不全，未虚构精确累计墙钟或剩余墙钟；总48小时墙钟上限未改变。
authorization.json记录本轮批准；diagnostic-ledger.jsonl记录启动前预留、真实启动及结束；budget-summary.json汇总增量。没有改变旧冻结中的61次合同文件，也没有恢复旧STOPPED轮或改写旧账本/启动许可。未来候选资格须单独建立一致的候选版本与累计账务。
本目录均为独立副本与新证据，main及原交付记录未改。

## 候选与后续边界
候选只把：
    .options klu method=gear reltol=1e-5 abstol=1e-16
改为：
    .options sparse method=gear reltol=1e-5 abstol=1e-16
其余电路、器件、原EKV、输入、容差和科学观察量不变。

已核对原两项资格定义：均到100.27s，输出增量1ms；Q1_MOTHER_PROTOCOL最大积分步长250us，Q1_MOTHER_HALFSTEP为125us；各600s墙钟上限。不是把输出增量再减半。实际定义和前置条件保存在candidate.json。
本轮未运行这两项；需针对Sparse候选另行明确授权，并使用独立候选版本，沿用原科学评分及首项失败即停规则。不得覆盖旧冻结或自动开始31项正式实验。

## 文件索引
- suite-summary.json、budget-summary.json、candidate.json、EXPLORATION_STOPPED.json：本轮结论、扣账和停止边界。
- D1-sparse/mother_0_20ms.cir、c05_ekv26_typ.lib：实际电路及原器件参数库。
- D1-sparse/ngspice.log、mother_0_20ms.raw、waveform.csv：原始日志、二进制波形和同波形CSV。
- D1-sparse/diagnostic.json、raw_summary.json、execution.json、test-plan.json：设置生效、完成判定、真实运行及单一假设记录。
- D1-single-factor.diff、D1-sparse/actual-paths.diff：数值设置差异及实际路径差异。
- R0-completion-regression.json、power-on-states.json、branch-static-check.json：零求解测试与定点分析。
- REVIEW_AND_TESTS.md：预算批准前的评审和准备记录；其中“等待批准/未推送”描述的是当时状态，本README及实际运行记录为当前状态。
- run_diagnostic.py、authorization.json、diagnostic-ledger.jsonl：实际监督脚本、本轮预算批准及单独诊断账目；脚本检测到停止标记后拒绝再次启动。
- SHA256SUMS：除校验清单自身之外的所有交付文件。在本目录运行sha256sum -c SHA256SUMS只校验文件，不启动求解。

