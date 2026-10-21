# Linux 原母本 0–20 ms 上电诊断

运行ID：power-on-20ms-2026-10-22-eba1b9f9。用户单独授权的一次故障取证，不是完整资格实验。

结果：**在 5.732389312857695 ms 中止，未达到 20 ms**。日志报：
    doAnalyses: TRAN:  Timestep too small; time = 0.00573239, timestep = 3.125e-16: trouble with node "g0_vms"
    tran simulation(s) aborted
进程退出码为0，但日志和RAW共同证明瞬态未完成。日志指出g0_vms；本次证据不足以判定根因。

本次实际启动ngspice一次，只有一条显式瞬态指令。墙钟耗时 **2.5213829389999773 s**，60 s上限内自然退出，未超时。没有自动重试、调参或继续求解。保守累计按用户指定 **27/61 → 28/61**，本次实际耗时作为独立扣账增量；旧账本不改。已知历史开发耗时为22565.592149972916 s，此前额外3次启动的完整耗时当前不可得，因此budget_delta.json不虚构最新累计总耗时或精确剩余时长。

## 输入与身份
原始保存网表为交付包中的 Q1_MOTHER_PROTOCOL，SHA256：
d2edf1a4712bb2a39b8a1fb948c823922f9fbf5b58b933c34d44c4cea6e87aea。
诊断只把 tran 0.001 100.27 0 0.00025 改为 tran 0.001 0.02 0 0.00025，并替换MODEL_LIB、OSDI、RAW三个实际路径。反向替换后与原网表逐字节一致；差异见deck.diff。
Gear方法、电路、器件、全部输入（含原0–20ms电源斜坡）、保存量和容差保持不变：
    .options klu method=gear reltol=1e-5 abstol=1e-16

复用准备好的ngspice-47 Linux二进制及原EKV OSDI，未替换或重编：
- ngspice SHA256：37d80c673bc4c03904ed4434bb3aa9aecd099ecfaeb66b86730a905e8c76ed89
- EKV OSDI SHA256：7c07ae3728941189b77bf0ecfca5ebe56473d01eedc6ea59c46cc32bfdb9a43f
- 原器件参数库SHA256：f6acb2379baacfdb5f53cfc30015f3b7c5690bb1118a5e32a678b76c0b739634

独立工作目录为 /workspace/thermal-g3-diagnostics/power-on-20ms-2026-10-22-eba1b9f9。网表保留实际运行时的绝对路径以供取证。原STOPPED工作流未续跑；旧冻结、启动许可、登记及账本的存在状态和散列前后相同，详见provenance.json和execution.json。

## 交付内容
- mother_0_20ms.cir：实际执行的电路文件。
- original_Q1_MOTHER_PROTOCOL.cir、c05_ekv26_typ.lib、deck.diff：原网表、原参数库字节副本及限定差异。
- ngspice.log：完整合并标准输出和错误日志，保留原始字节。
- mother_0_20ms.raw：本次原始二进制波形。247点、96变量，时间范围0至0.005732389312857695 s。是中止前的部分瞬态波形，不是完整成功输出。
- waveform.csv：从同一RAW解码的全部变量和点，便于复核。
- raw_summary.json：RAW头、结构完整性、时间终点、末值及变量清单。RAW结构完整不等于瞬态完成；时间轴另与项目原read_raw读取器逐点核对一致。
- diagnostic.json：诊断结论、实际启动次数、耗时、终点和错误。
- execution.json、budget_delta.json：运行监控和独立预算增量，不修改原活动账本。
- provenance.json：原始输入身份、限定替换、受保护文件的运行前状态。
- run_once.py、one-shot-reservation.json：实际使用的单次监督脚本及已消费的一次性预留记录；不可据此自动重跑。源码文件交付用于审查，不是新的运行授权。
- SHA256SUMS：本目录其余全部文件的SHA256。

在本目录执行 sha256sum -c SHA256SUMS 可验证交付文件，不会运行求解器。

本次诊断已经停止。没有启动完整资格或31项正式实验，没有产生资格通过判定。即便未来达到20ms，也不等于完整资格通过。

