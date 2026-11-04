# 性能与资源数据说明

性能数据位于 `data/metrics/optimization_comparison.csv`。原始分组、计时范围、输入条件及配置校验值见 `data/metrics/optimization`。

| 资源 | 流水线优化前 | 流水线优化后 |
|---|---:|---:|
| LUT | 78045 | 75242 |
| FF | 110635 | 76360 |
| BRAM | 107 | 107 |
| URAM | 24 | 32 |
| DSP | 668 | 686 |

此表对应同一工具链下 PL2 流水线方案的比较。Vivado 2026.1 工程的资源与时序见 `build/reports/vivado2026`。比较时应使用相同输入、精度、迭代次数和计时范围，分别统计核心计算与完整处理时间。
