# 下载并恢复本轮4份RAW原件

推荐使用Git下载到一个新目录，避免大ZIP生成通道等待。它包含33个无损gzip分片，约1.31 GB；还原后的4份RAW总计约2.28 GB。请预留约6 GB空间用于仓库、传输文件和还原原件。

```sh
git clone --depth 1 --single-branch --branch raw/retest-originals-2026-10-25-8f233e10 https://github.com/shaochun321/TheLiying-cloudtest.git raw-delivery
cd raw-delivery
python cloud-results/2026-10-25/retest-raw-originals-8f233e10/restore_raw.py --output-dir raw-originals
```

需要Git和Python标准库，不需要NumPy、SciPy或ngspice。私有仓库请使用有权访问的GitHub账号正常登录Git；不要把Token发到聊天。

脚本依次验证每片、合并gzip流和每份原RAW的SHA256。四个文件均显示PASS后，原件位于raw-originals目录，校验记录为raw-originals/RESTORE_VERIFICATION.json。已有不同内容文件不会被覆盖。

原件清单与SHA256见cloud-results/2026-10-25/retest-raw-originals-8f233e10/RAW_MANIFEST.json和ORIGINAL_SHA256SUMS。此交付是字节完全一致的恢复，不是转换或重采样后的波形。source_path只是来源记录，不是下载地址。

小文件证据中的“RAW未上传”是当时的历史状态。本轮新的DELIVERY_COMPLETE.json和本目录的远端下载验证记录，描述这次完整原件交付。

实验结果不变：125/62.5微秒完整资格PASS；G0_W完成64.8秒，但collector电容能量门FAIL，其余30项未启动。没有新增求解，累计54/84。
