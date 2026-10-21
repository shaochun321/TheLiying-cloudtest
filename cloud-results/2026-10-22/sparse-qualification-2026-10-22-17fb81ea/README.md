# Sparse 候选完整资格：首项科学判定失败，已停轮

日期：2026-10-22（Asia/Shanghai）。候选 SPARSE_GEAR_original_physics_2026-10-22。
输入证据固定提交：4dbcdaa774a8d26bf24fe9680da667bd8fb1bdd7。

## 结果
Q1_MOTHER_PROTOCOL使用原物理电路、原EKV及参数卡、原输入、Gear、容差和保存量，仅将矩阵求解器明确选为SPARSE 1.3。
实际瞬态完成100.27s，419026点×96变量；原完成判定通过。进程退出码0，无中止/超时，原始RAW字节完整。
实际求解墙钟 **522.8353252679999s**（600s上限内）。离线原科学评分另耗时50.2334580250008s，不是新的求解启动。
原 criteria_q1r.judge_joint：**PASS**；G0、Sigma、Theta_Cdir各9/9项功能门通过，共27/27。
原注册总评分附加的 physical_ledger：**FAIL**；因此整体资格为 **FAIL**，不能把功能联合门PASS报告成完整资格PASS。

失败定位于原物理账目中的 g0_vm / cg0_cm 电容能量闭合门：
| 量 | 值 |
|---|---:|
| 电容 | 100nF，原值未改 |
| 积分端口功率 | 4.9698115307922595e-8J |
| 端点储能变化 | 4.891270844016791e-8J |
| 差值 | 7.854068677546823e-10J |
| 原允许差值 | 4.96981153079226e-10J |
| 误差相对原归一化尺度 | 约1.58036%，原阈值1% |

同一节点的KCL门及节点总端口能量门通过，50fF寄生电容门也通过；不能据这个结果直接宣称电路物理上不守恒或某模型有缺陷。离散时间、积分/采样及其他误差原因本轮未区分。没有修改原判据，也没有用新归一化方式改判。
完整原输出见runs/Q1_MOTHER_PROTOCOL/judge-output.json；只读复算说明见failure-analysis.json。

## 停止与预算
已写本候选独立STOPPED.json。首项未通过必要科学判据，Q1_MOTHER_HALFSTEP **未启动**；其已准备网表只作记录，NOT_RUN.json说明原因。
没有重试、调参、新诊断、更长烟雾或正式实验。
本轮真实启动1次，保守累计29→**30/65**；剩余35次：31项正式额度、3次未用诊断额度、1次未用资格额度。剩余额度不构成越过科学失败的许可。
本轮求解耗时按522.8353252679999s单独扣账；旧三次额外启动耗时仍不全，未虚构精确累计墙钟。总48小时墙钟上限保持不变。

## 身份与原记录保护
使用仓库外独立候选副本。CANDIDATE_MANIFEST.json绑定两项候选网表、原科学代码/输入54个文件、后端及模型散列；复制的软件和判据内容未改。
QUALIFICATION_AUTHORIZATION.json绑定本次“审核后执行”请求及所附任务书，仅覆盖两项有顺序、各最多一次的资格，不授权31项正式实验。
运行使用本候选独立监督、起止登记和累计次数核算，调用未改的原完成判定与原注册judge（包括物理账目），不调用或恢复旧STOPPED轮。历史FREEZE及原61次合同保留作来源；新65次总上限按此前用户明确批准在独立账务中继承。
旧冻结、旧停止状态、原启动许可、原账本及main均未改。没有新建旧流程的启动许可，没有重跑整套环境准备或软件自检。

## 交付与复核
- CANDIDATE_MANIFEST.json、QUALIFICATION_AUTHORIZATION.json：候选身份及本轮授权边界。
- qualification-ledger.jsonl、budget-summary.json、STOPPED.json、session-result.json：实际启动、扣账和停止记录。
- runs/Q1_MOTHER_PROTOCOL/：实际电路、原始/候选身份网表、单行求解器差异、真实路径差异、完整日志、原评分及RAW身份。
- runs/Q1_MOTHER_HALFSTEP/：准备资料和NOT_RUN.json，无运行日志或波形。
- inputs/c05_ekv26_typ.lib：本次实际读取的原器件参数库。
- run_qualification.py：本轮实际使用的监督与判定脚本；停止标记和一次性记录阻止重复启动。
- RAW_DELIVERY.json、SHA256SUMS：交付RAW及所有文件的字节身份。
原始RAW为321814571字节，SHA256：
69c950786ca768d5918f5dd79c716c0e7f8b75369f490c071c21acc5b2db7f23。
为满足GitHub单文件限制，交付包采用无损gzip分片，原始RAW仍保留在本地主机。分片顺序、原始/压缩SHA256在RAW_DELIVERY.json；导出时已完整解压验证。
下载整个目录后运行：
    sha256sum -c SHA256SUMS
    python3 restore_raw.py --output-dir restored-raw
restore_raw.py只恢复并核对原始RAW，不运行求解；已有目标文件会拒绝覆盖。
software/副本未重复上传，其54项代码/输入字节身份已登记；原软件主体可由原交付目录取得。

