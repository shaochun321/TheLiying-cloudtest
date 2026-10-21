# THERMAL-G3 实际主机冻结与检查

日期：2026-10-20。当前实际主机及现有构建目录的环境准备已完成。

新冻结状态：**FROZEN_AWAITING_LAUNCH**，未就绪项为空。

FREEZE_Q1R.json SHA256：

`6d0bec4bd1b68ebf60ad5f2240d16227738c13263348880aa0eeab0551b21d48`

本次实际执行真实后端登记、原静态检查和完整无求解自检：静态 33/33、无求解自检 124/124 全部明确通过。完整输出、逐项检查 JSON 与运行时间在 evidence/host_validation/ 和 execution/ 内。没有重编已成功后端，也没有修改原 D、评分器、功能电路或模型。

真实后端：ngspice-47（OSDI/KLU）；dwarning OpenVAF 发布标签 1.0.0，实际 CLI 23.5.0；原 EKV 使用 -D__NGSPICE__ 的 Linux OSDI。实际散列及版本见 CHECK_RESULTS.json 与 backend_registration.json。版本对应证据和编译日志保留。

## 原始结果目录与取回

实际配置的 RAW 根目录：

`/workspace/scratch/8fecea1ba044/offline_backend_kit_20261020/host_work/execution/thermal_g3_q1r_runpack_9d042b00/thermal_g3_q1_raw`

已完成 1 MiB 基础设施文件的写入、fsync、回读、归档保存及完整取回；归档与载荷的 SHA256 均一致。证据见 prereg/host_storage_check_2026-10-20.json 和 evidence/host_validation/storage_probe_archive_v0.zip。探针不是电路 RAW，未用于科学裁决。冻结前可用磁盘约 27.07 GiB；这不是对全部自适应 RAW 体积的容量承诺。按原指引，在两项真实资格输出后估算后续容量，不新增 smoke。

RAW 工作目录属于当前会话；持久保留与取回走已验证的归档路径。授权运行后，每项结束先归档该次 cir/raw/log/sup.json、账本及裁决，再推进下一项。

## 身份与运行边界

当前项目目录：`/workspace/scratch/8fecea1ba044/offline_backend_kit_20261020/host_work/execution/thermal_g3_q1r_runpack_9d042b00/thermal_g3_q1`

冻结只对应当前实际主机的资产和这些路径。新冻结封存了 69 项输入，外部资产散列逐一匹配；旧 9d042b00 冻结按原工具保留为 superseded。原 source_manifest 和任务顺序未重写。原包的 INPUT_MANIFEST 仍用于来源身份；本次执行副本以新冻结和 MANIFEST_host_delivery.json 为准。

未写启动许可，实际 op/dc/tran 启动为 0，活动 Q1 账本不存在。两项资格和31项正式实验均未启动，等待用户对上述具体冻结的授权。24次开发封存、已耗22565.592149972916秒、2＋31＋4及累计48小时继承不变。

## 交付内容

顶层 FREEZE_Q1R.json 与 execution 中的实际冻结逐字节相同。CHECK_RESULTS.json 汇总本次检查；execution 保存当前执行副本及封存 v1 账本；native 保存实际 ngspice、OSDI 和运行数据；evidence 保存本次日志、逐项结果、取回探针与构建证明。OpenVAF 编译器沿用用户已提供的离线补包，精确身份已登记，不重复附上250MB程序。原工具源文件仍在此前离线补包及构建结果包中。

包内已执行完的检查脚本不应在当前冻结后重新改写其绑定文件。迁移到其他路径或主机需登记真实资产并重新冻结；本包不含启动许可。
