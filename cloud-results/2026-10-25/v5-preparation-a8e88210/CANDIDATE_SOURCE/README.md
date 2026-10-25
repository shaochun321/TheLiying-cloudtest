# v5 实际候选源与静态网表

software 是本轮独立候选；generated-verified 是通过静态检查的三份预览模板及清单；baseline_reference 是相同数值路径下的旧物理源预览，用于对比，不是 v5 或已求解结果。generated 是首次检查器报错留下的空目录，不是有效输出。候选身份为 PREPARED_UNQUALIFIED。

SOURCE_IDENTITY.json 记录可读基线逐文件哈希、实际修改文件与显式 reference_bias_n 调用。baseline-to-v5.diff 是源码差分；每用例另有 *_netlist.diff、*_DEVICE_CHANGES.json 和 *_MOS.csv。模型卡随软件提供，原 ngspice/OSDI 不重复打包，精确身份见 ../PROVENANCE/ASSET_IDENTITY.json。

只复核现有候选可运行下列命令，不调用 ngspice。输出目录必须尚不存在；此命令只重建选定三份网表和静态清单，不颁发资格：

```sh
python generate_and_check.py --source software --out reproduced-static --baseline-artifacts baseline_reference --static-helper original_static_helpers.py
```

若需从完全相同基线重建源码，先按 SOURCE_IDENTITY 的哈希准备基线，再在新目录运行：

```sh
python reconstruct_candidate.py --baseline /path/to/verified-baseline --reference ../PROVENANCE --out new-candidate-source
```

生成器拒绝启动子进程；本包未复制 runtime/coordinator、supervisor 等求解执行器。不得将生成的 .cir 或原 config 的旧默认预算当作运行许可。原病例注册与协议未改，输出命令中的数值路径是显式登记的预览变更。真实路径绑定和新求解需要下一批具体授权。
