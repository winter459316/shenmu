# 可复用检查流程

## 环境

Python 3.9 及以上；数组比较需要 NumPy。脚本在项目根目录执行。

## 文件完整性检查

```powershell
python skill/verify_artifacts.py manifest --root . --file data/provenance/manifest.json
```

脚本按清单检查文件 SHA256。修改交付文件后，应由发布者更新清单。

## 数组比较

```powershell
python skill/verify_artifacts.py compare data/reference/reference_arrays.npz data/reference/candidate_arrays.npz --keys-file data/reference/array_keys.json
```

脚本比较指定数组的类型、形状和原始字节。退出码 0 表示通过，1 表示失败。比较键由 `array_keys.json` 定义，运行耗时等动态元数据不参与比较。

## 使用范围

适用于具有确定参考输出的图像处理、信号处理及加速器工程。采用允许误差的算法时，应另行定义容差与评价指标；文件校验和字节比较不能替代测量精度评价。

## 其他流程

- [DMA 与配置交接](dma_handoff.md)：资源独占、数据完成和配置切换顺序。
- [性能与资源比较](performance_workflow.md)：输入控制、计时范围和资源统计方法。

跨板使用前，应重新定义寄存器地址、预留内存、缓存属性与 DMA 协议。
