# 深目内窥镜3D感知系统

本项目基于 AMD XCZU4EV，提供双目图像采集、PS/PL 协同立体匹配、图像视觉增强、三维模型显示、深度查询、交互截面、录像选帧重建及 HDMI 同步显示。硬件工程使用 Vivado 2026.1。

## 目录

| 目录 | 内容 |
|---|---|
| src/pl | PL1 预览与几何处理、PL2 卷积与反卷积、PL3 三维卷积源码 |
| src/ps | 板端采集、推理调度、DMA 接口及显示服务 |
| src/host | 网页服务、三维交互与模型导出 |
| sim | 仿真输入、离线检查脚本及结果文件 |
| build | FPGA 构建脚本及综合实现报告 |
| board | 部署脚本、配置文件、FPGA 配置文件及板端结果 |
| data | 模型说明、参考数组与性能数据 |
| skill | 文件检查、数组比较和资源交接操作流程 |
| report | 设计报告、接口说明与复现手册 |
| private_runtime | 模型、原生库、离线依赖及参考样例 |

## 运行环境

- 电脑：Windows x64、Python 3.12 x64、支持 WebGL 2 的浏览器及串口驱动。
- 开发板：正点原子 MPSoC-P4 V1.7，核心器件 XCZU4EV，配套 AArch64 Linux 系统。
- 外设：双目 USB 摄像头、串口线、以太网线和 HDMI 显示器。
- 日常运行使用配套模型、原生库及离线依赖包，无需 GPU、CUDA、PyTorch 或 Vivado。
- 重建 FPGA 工程需要 Vivado 2026.1、XCZU4EV 器件支持及适用许可证。

## 首次安装

1. 克隆本仓库，完整保留根目录的 `private_runtime` 文件夹；无需单独获取模型包。
2. 安装 Python 3.12 x64、串口驱动及支持 WebGL 2 的浏览器。
3. 在仓库根目录运行 `setup.cmd`。安装器自动校验并合并运行资产分卷，建立虚拟环境并安装离线依赖。
4. 打开 `.runtime/zu4ev_stereo/launcher/config.json`，设置设备管理器显示的实际串口号。
5. 将电脑有线网卡设置为 `192.168.137.1/24`，板卡设置为 `192.168.137.2/24`。
6. 按 [硬件连接说明](board/hardware_setup.md) 连接并启动板卡。全新板卡需先准备配套厂商 Linux 基础系统，该系统镜像不包含在仓库内。

可指定本机 Python 路径：

```powershell
./setup.ps1 -PythonExe 'C:/Python312/python.exe'
```

运行资源说明见 [private_runtime/README.md](private_runtime/README.md)。分卷合并后的缓存位于 `.runtime/cache`。运行文件根据 `board/config/source_map.json` 和 `board/config/runtime_assets.json` 组装。使用同级配套资产目录的独立交付包仍可通过 `-PrivateRoot` 指定资产位置。

## 启动和使用

1. 板卡刚上电、处于原厂 Linux 空闲状态时，运行 `cold_start.cmd` 准备运行环境。此操作使用 RAM，不写入 SD/eMMC。
2. 板卡运行环境已就绪时，运行 `start.cmd` 准备实时服务。
3. 运行 `open_web.cmd`，浏览器访问 `http://127.0.0.1:8849/`。
4. 在网页中选择预览模式；使用拍照或录像暂停帧生成三维结果，再进行旋转、深度查询和截面观察。
5. 运行 `status.cmd` 查看服务状态，运行 `stop.cmd` 结束空闲的电脑端服务。

预览刷新与拍照重建属于不同阶段。拍照重建按需执行，其耗时应以任务状态为准。

## 故障排查

运行 `diagnose.cmd`，按 [网页启动与排查](report/web_startup.md) 检查本地端口、网络和板端服务。出现 DMA 故障或未完成配置切换时，保留故障锁和快照，按恢复流程处理。

## FPGA 工程构建

在项目根目录执行以下命令，并将安装目录替换为本机路径：

```powershell
./build_all.ps1 -VivadoRoot 'D:/AMD/2026.1/Vivado'
```

默认输出目录为 `build/output`。仅创建工程时使用 `prepare_projects.ps1`，分阶段构建和续建方法见 [构建说明](build/README.md)。构建使用 `src/pl` 中的 RTL/IP；修改 HLS C++ 后，应先重新导出对应 IP。

## 文件与参考数据检查

在项目根目录执行：

```powershell
python sim/validate_repository.py
python skill/verify_artifacts.py manifest --root . --file data/provenance/manifest.json
python skill/verify_artifacts.py compare data/reference/reference_arrays.npz data/reference/candidate_arrays.npz --keys-file data/reference/array_keys.json
```

数组比较需要 NumPy，可使用安装生成的 `.runtime/zu4ev_stereo/experiments/cnn_stereo_20261018/.venv/Scripts/python.exe` 执行上述命令。

详细操作见 [复现手册](report/reproduction.md)，模块位置见 [模块索引](report/module_guide.md)。
