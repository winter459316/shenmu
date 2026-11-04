# FPGA 工程构建

## 环境

安装 Vivado 2026.1、XCZU4EV 器件支持及适用许可证。以下命令均在项目根目录执行。

## 创建三套工程

```powershell
./prepare_projects.ps1 -VivadoRoot 'D:/AMD/2026.1/Vivado'
```

此命令创建工程并检查接口，不执行综合与布局布线。

## 完整构建

```powershell
./build_all.ps1 -VivadoRoot 'D:/AMD/2026.1/Vivado'
```

## 单套构建与续建

```powershell
./build.ps1 -Profile pl1 -Step bit -VivadoRoot 'D:/AMD/2026.1/Vivado'
./build.ps1 -Profile pl1 -Step bit -Resume -VivadoRoot 'D:/AMD/2026.1/Vivado'
```

`Profile` 可选 `pl1`、`pl2`、`pl3`；`Step` 可选 `project`、`synth`、`bit`。已有工程需要续建时使用 `-Resume`，或通过 `-WorkRoot` 指定新的输出目录。

## 路径与输出

- 工程输入：`src/pl`。
- 构建工具：`build/tools`。
- 默认输出：`build/output/<Profile>`。
- 构建日志：输出目录中的 `migration.log`。
- 随包实现报告：`build/reports/vivado2026`。
- 随包 FPGA 配置：`board/bitstreams`。

`VivadoRoot` 应为包含 `bin/vivado.bat` 的目录，也可通过 `XILINX_VIVADO` 或系统 PATH 配置。构建直接使用导出的 RTL/IP；修改 `hls_source` 中的 C++ 后，应先重新综合并导出相应 IP。
