# 参考数组使用说明

- `reference_arrays.npz`：参考输出。
- `candidate_arrays.npz`：对照输出。
- `array_keys.json`：需要比较的 13 项数组名称。
- `hls_fixtures.json`：HLS 输入样例索引。

在项目根目录执行：

```powershell
python skill/verify_artifacts.py compare data/reference/reference_arrays.npz data/reference/candidate_arrays.npz --keys-file data/reference/array_keys.json
```

环境需要 NumPy。脚本按类型、形状及原始字节比较数组，退出码 0 表示一致，1 表示不一致。任务编号、运行耗时等动态元数据不参与比较。
