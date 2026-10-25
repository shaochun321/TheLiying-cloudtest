下载本独立分支后，在本目录运行：

```sh
python restore_raw.py --output-dir raw-original
```

只需 Python 标准库；逐片及恢复原件 SHA256 均核验，不覆盖不同内容文件。原 RAW 本地原件保留。远端复核采用实际 API 下载全部分片并流式还原、核对完整原件身份。
