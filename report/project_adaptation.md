# 输入与截面接口设计

## 模型输入接口

`src/ps/inference/adaptation/stereo_contract.py` 提供输入组织和几何交接检查：

- 接收左右两幅 320×360、三通道 uint8 BGR 图像。
- 转换为 NCHW RGB FP32 张量，按 32 行对齐，上下各复制补齐 12 行。
- 按除以 255、减均值、除标准差的顺序归一化。
- 为左右输出分配独立连续内存。
- 检查 FP32 视差、4×4 Q 矩阵和有效域尺寸。

## 截面参数接口

`src/host/app/adaptation/section_projection.py` 面向 512×512 截面掩膜与三维显示：

- 使用 16 个小端 FP32 参数描述平面、基向量、视窗原点及像素比例。
- 将 0–100 的位置参数映射到模型包围盒的投影范围。
- 根据法向建立平面基，生成带 2% 余量的正方形视窗。
- 根据 FP32 参数生成网页显示平面与四角位置。
- 检查非有限值、零法向、非法包围盒及非正像素比例。

## 独立使用步骤

以下模块不在默认启动链路中。需要生成独立运行文件时，在项目根目录执行：

```powershell
python sim/test_model_adapter.py -v
python build/create_model_adapter_candidate.py --output D:/shenmu_review/model_adapter
python sim/test_section_adapter.py -v
python build/create_section_adapter_candidate.py --output D:/shenmu_review/section_adapter
```

输出目录应使用本机尚不存在的新目录。生成文件依赖配套模型、原生库和运行配置，不能作为完整系统单独启动。接入应用前，应检查数值输出、配置交接和完整运行流程。
