# 上电/参考整改执行记录：REPAIR_FAILED

先读 [REPAIR_SUMMARY.md](REPAIR_SUMMARY.md)，逐项状态见 [TEST_MATRIX_RESULT.json](TEST_MATRIX_RESULT.json)。这是执行错误的完整记录，不是物理候选验证通过或科学性失败。

原版补测误加 uic、改变输出步长，发现后已终止，消耗一次真实启动 36.356865 秒，累计 40/65。没有 RAW；没有重试；没有候选、资格或其他正式测试。旧 STOPPED/FAIL/账本保持原样。

`runs/C0_ORIGINAL_50MS/C0_ORIGINAL_50MS.cir` 是实际执行的错误命令原件，未改写。`executor/prepare_original_50ms_CORRECTED_NOT_EXECUTED.py` 仅保存修正后的生成逻辑，**未运行，不表示补测成功**。原 runner 在进程终止后因不存在的 RAW 又报 FileNotFoundError，见 runner.log；completion.json 如实记录无 RAW，未启动任何新进程。

所有既有大波形仅作一次离线读取和 SHA256 身份校验，本目录不重新打包旧波形。入口证据提交为 708e1033c5cb43e6f917f2ac156b041a8f2d1541。仓库路径均为本独立分支新增文件。

完整下载可使用本分支 GitHub 页面 Code → Download ZIP，或 git clone 后切换到本分支；单个文件页面可点击 Raw/Download raw file。取得目录后运行 `sha256sum -c SHA256SUMS` 核对文件。
