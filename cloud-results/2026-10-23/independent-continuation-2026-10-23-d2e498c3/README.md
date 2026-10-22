# 独立分支续行结果

批次：independent-continuation-2026-10-23-d2e498c3；状态：PARTIAL。本批实际新增启动 4 次，累计 39/65。

按用户“执行，暂时解除时间限制”执行本批临时墙钟豁免；原单项、阶段和全局时限保留为历史参照，没有声称原成本门通过。启动次数、每项一次、原依赖及原科学门均保留。旧 G0_W FAIL、STOPPED、账本未改写。

本批实际求解墙钟合计 11309.627702 秒；离线评分 114.489826 秒。历史全局精确墙钟仍未知，不按零补齐。

| 项目 | 原评分/状态 | 求解耗时（秒） | RAW 终点（秒） |
|---|---|---:|---:|
| G0_C | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| G0_CUT_K1 | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| G0_CUT_K10 | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_12_W_F | FAIL | 9495.507018977005 | 39.2 |
| CHAIN_12_W_R | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_12_C_F | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_12_C_R | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_23_W_F | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_23_W_R | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_23_C_F | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_23_C_R | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_34_W_F | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_34_W_R | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_34_C_F | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| CHAIN_34_C_R | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| STRUCT_THETA_PORT_CUT | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| STRUCT_SIGMA_PORT_CUT | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| STRUCT_CDIR_HISTORY_BLEED | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| STRUCT_REAL_SIGMA_SWAP | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| INVALID_SYNC | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| INVALID_STALE | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| FULL_NOM | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| FULL_REAL_MIRROR | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| FULL_SPACE_CUT | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| FULL_NUM_HALFSTEP | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| NUM_G0_HALFSTEP | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| NUM_CHAIN_HALFSTEP | BLOCKED_DEPENDENCY | — | 不适用/未运行 |
| DC_2P7 | FAIL | 579.7534040879982 | 不适用/未运行 |
| DC_3 | FAIL | 620.276752566002 | 不适用/未运行 |
| DC_3P2 | FAIL | 614.0905263460008 | 不适用/未运行 |

各失败门及阻塞父项见 CASE_SUMMARY.json；原完整评分见各 runs/ 目录。供给的固定 BDF2 重构只作外部证据引用，未在本批重算或用于改判。

RAW_DELIVERY.json 绑定新增 RAW 的原件 SHA256 和无损分片；小 RAW 直接保存。运行 python3 restore_raw.py 可恢复并校验。没有重打包旧波形，也没有新增诊断或资格运行。
本批有限矩阵调度已结束，不自动进入根因排查、精度调整或重跑。没有宣称原 31 项全覆盖或全部通过。

本批关键结论：三个 DC 项都只有 VREST 分压比超过原 1% 门限，其余 9 门通过。CHAIN_12_W_F 的 20 个物理账节点全部通过，但 18 个功能门中 10 个 FAIL、8 个 PASS；原评分在约 0.010213752 秒记录父输出及关系节点的刺激前阈值交越，导致顺序、因果支持和端口门失败。这是原评分结果，并未另行裁定唯一物理根因。它不能归为此前 G0_W 的电容能量门失败。26 个未启动项均因失败依赖阻塞，已无合法前沿；本批结束。简明数值见 RESULTS_BRIEF.json。
