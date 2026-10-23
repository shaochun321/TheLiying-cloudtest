# v2 执行器纠错及单候选整改证据

先读 REPAIR_SUMMARY.md、RESULTS_BRIEF.json、TEST_MATRIX_RESULT.json；预检见 EXECUTOR_PREFLIGHT.json，冻结与最小差异见 candidate_manifest.json、candidate.diff。所有正式科学模块保持原文件；追加诊断向量与原评分输入视图分离，来源锚点政策已冻结。

旧错误启动记录仍在父提交 62a6b07e106e46d4bdb3652f63f34c728b46afd8，旧完整运行证据在 708e1033c5cb43e6f917f2ac156b041a8f2d1541。旧完整 RAW 未重复下载、散列、评分或打包。

每个 runs/<id>/RAW_DELIVERY.json 指明原 RAW、散列、真实终点及恢复方法。分片是一条 gzip 流，须按编号拼接后解压；完整解压内容已与运行时 RAW SHA256 核对。没有启动的项目没有 RAW，不记 PASS。实际命令引用云端绝对路径；移植时仅替换模型卡、原 OSDI 和输出文件路径，不能改变分析/电路/刺激/容差。

使用 GitHub 本分支 Code → Download ZIP 或 git clone 后取得整个目录，再在目录内执行 `sha256sum -c SHA256SUMS`。单个小报告可在 GitHub 文件页点击 Raw/Download raw file。
