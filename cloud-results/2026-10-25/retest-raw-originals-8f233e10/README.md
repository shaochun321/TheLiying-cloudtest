# THERMAL-G3 RAW 原件的无损交付

本目录提供本轮4份RAW的完整原始字节。因为单份原件超过Git的单文件限制，传输采用gzip无损压缩，再切成不超过40 MiB的分片。没有转换格式、重采样或更改波形。4份原件总计2,278,212,926字节，压缩分片总计1,306,433,721字节，共33片。

下载此分支的仓库ZIP并解压，进入解压后的仓库目录，运行：

```sh
python cloud-results/2026-10-25/retest-raw-originals-8f233e10/restore_raw.py --output-dir raw-originals
```

只需要Python标准库。脚本会验证每个分片、完整gzip流和每份还原RAW的大小与SHA256；4项均PASS才表示恢复成功。已有不同内容文件不会被覆盖。只想验证而不保存还原文件，可添加 `--verify-only`。

原件名及科学范围：
- short_125us.raw：短程步长诊断，终点20.499988707436106秒。
- Q1_MOTHER_PROTOCOL.raw：125微秒完整资格，终点100.27秒，PASS。
- Q1_MOTHER_HALFSTEP.raw：62.5微秒完整对照，终点100.27秒，PASS。
- G0_W.raw：正式首项，终点64.8秒，电容能量门FAIL；其余30项未启动。

来源的小文件证据提交为8f233e106d75e9399e6ab0fc1930262385ec31a1。原始身份见RAW_MANIFEST.json与ORIGINAL_SHA256SUMS。SOURCE路径仅记录云端原件位置，不是下载链接。所有原RAW仍保留，不新增求解，累计54/84不变。

GitHub Release的附件上传端uploads.github.com返回401；此次改用已验证的Git通道。只有DELIVERY_COMPLETE.json出现且全部分片齐全，才表示4份原件均已交付。仓库中是无损分片，恢复后的.raw才是逐字节相同的原件。
