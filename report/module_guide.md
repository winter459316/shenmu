# 模块索引

| 目录 | 内容 |
|---|---|
| src/pl/pl1 | 预览、滤波、坐标及截面电路 |
| src/pl/pl2 | 整数卷积及 FP32 反卷积电路 |
| src/pl/pl3 | FP32 三维卷积电路 |
| src/pl/interfaces | TMDS 等接口定义 |
| src/pl/tests | 浮点与卷积仿真输入 |
| src/ps | 相机服务、模型运行、DMA 调度、显示与回放 |
| src/host | 网页服务、几何导出、WebGL 交互与界面 |
| board/deploy | 安装、组装与启动脚本 |
| board/bitstreams | PL1、PL2、PL3 配置文件 |
| board/validation | 板端输出与对照数据 |
| build | Vivado 2026.1 构建脚本与实现报告 |
| sim | 离线检查脚本与结果数据 |

运行文件映射由 `board/config/source_map.json` 定义，安装器据此建立 `.runtime`。`hls_source` 保存 HLS C++，工程构建使用导出的 RTL/IP。

独立接口示例位于 `src/ps/inference/adaptation` 和 `src/host/app/adaptation`，不属于默认启动链路。使用方法见 [接口设计说明](project_adaptation.md)。
