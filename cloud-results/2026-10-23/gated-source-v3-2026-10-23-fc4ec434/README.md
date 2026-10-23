# v3 唯一候选失败证据

先读 REPAIR_SUMMARY.md、RESULTS_BRIEF.json 和 TEST_MATRIX_RESULT.json。T0正常完成，但公共参考扰动超过冻结工程门，因此首个失败停线。此项是物理候选的工程失败，不是执行器异常；后续八项没有运行。

REFERENCE_FAILURE_WINDOWS.json 给出首几个越限窗口、共同导通的开关偏置和实测支路电流。V3_TEST_CONTRACT.json 和 candidate_manifest.json 在首次启动前已冻结；candidate.diff 仅改变bundle中的gated_source函数。不能以57管模型域通过冒充完整电路或完整资格通过。

本目录只有本批新增RAW、网表、日志及小报告。原二进制RAW约3.79MB，未重新打包旧大波形。每次实际运行的RAW_DELIVERY.json列出终点、散列和复制校验；未运行项标明无RAW。所有源文件、模型和网表中绝对路径为当时云端实际路径，移植时只替换必要资产/输出路径，不能更改物理参数、刺激或数值配置。

父版本证据提交：1faf29a6e6b5041032effbae1c5c4f367076ed67。继承观察器原件已附于executor/inherited_v2_offline_helpers_source.py，其散列已固定；该文件仅供提取离线函数，勿执行顶层运行器。提取方式见run_repair_v3.py。原科学模块来自父冻结软件包，移植时须保持其散列。附带Windows离线估计脚本作为原输入保存，未在云端执行，也不替代实际T0数据。

完整下载可使用本分支Code → Download ZIP，或git clone后切换到本分支；在本目录运行 `sha256sum -c SHA256SUMS` 验证。单个报告可在文件页点击Raw/Download raw file。
