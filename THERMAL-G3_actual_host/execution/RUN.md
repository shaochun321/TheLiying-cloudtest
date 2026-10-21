# THERMAL-G3-Q1-R 原D软件接续交付

本包的新冻结：`9d042b00195dbac895f2db3677ef4754f115b68063914a3075fb0975a9b02673`，状态 **NOT_READY**。原D软件自检通过；未登记或验收真实Linux后端。
没有启动许可，没有真实 op/dc/tran，也没有生产Q1活动账本。合成轨迹只检验软件。

`tools/_block.py` 已完整集成到 `thermal_g3_q1/tools/selfcheck_all.py` 的 `check_support_pairs()`。
原稿、初轮失败记录和旧输出位于 `evidence/history/`，不作为当前通过证据。
当前结果为 selfcheck 124/124、static 33/33。
逐门结果：`thermal_g3_q1/results/selfcheck.json`、`evidence/D_fixed_pairs.json`；33份静态保存网表在 `thermal_g3_q1/results/decks/`。

重新核对包：从本目录运行 `python -B thermal_g3_q1/tools/check_cloud_package.py`。它只使用临时副本和合成后端。
重新运行软件检查：进入 `thermal_g3_q1` 后，运行 `python -B tools/static_check.py`、`python -B tools/selfcheck_all.py`。
两者不需要真实求解器。自检的后端和权限夹具仅在临时副本内生成并销毁，不能用于实际运行。

保留原2项前置、31项正式、4项合法基础设施故障重跑、24次开发封存及累计48小时。
既有耗时为 22565.592149973 秒；Q1实际启动0次。只有一个实际后端和一个活动账本。
功能电路、参数、依赖和原case表均保持原字节。FULL的38个节点测量沿用恢复的overlay，保存量为 652 列。

断点停在真实执行环境：ngspice-47、OpenVAF 1.0.0、原源文件编译的Linux OSDI、真实后端登记、主机冻结及存储/结果取回条件。
`backend/windows-x64/` 仅为原包历史资产，不是Linux工具。不要运行 `source_manifest.py` 覆盖工作站来源；当前来源见新增revision清单。
本包不授权开始电路求解，也不提供启动许可。
