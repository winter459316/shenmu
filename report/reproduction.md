# 安装与复现手册

所有命令均在 `shenmu` 项目根目录执行。本手册适用于 Windows x64 电脑与 XCZU4EV 开发板，硬件工具版本为 Vivado 2026.1。

## 一、准备文件与环境

1. 安装 Python 3.12 x64、串口驱动及支持 WebGL 2 的浏览器。
2. 克隆完整仓库，保留根目录的 `private_runtime` 文件夹。
3. 连接双目 USB 摄像头、PS_ETH 网口、串口和 HDMI 显示器。
4. 开发板使用配套厂商 AArch64 Linux 基础系统；基础系统镜像需单独准备。

## 二、安装电脑端

1. 运行 `setup.cmd`，安装器自动合并 `private_runtime` 中的资产分卷。
2. 需要指定 Python 或资产位置时，改用以下命令：

   ```powershell
   ./setup.ps1 -PythonExe 'C:/Python312/python.exe' -PrivateRoot 'D:/shenmu_assets'
   ```

3. 打开 `.runtime/zu4ev_stereo/launcher/config.json`，配置实际串口号。
4. 将电脑有线网卡设置为 `192.168.137.1/24`，板卡设置为 `192.168.137.2/24`。

安装器建立独立 Python 环境并组装 `.runtime`。模型、原生库及离线安装包由配套资产目录提供。

## 三、启动系统

1. 刚上电且处于原厂 Linux 空闲状态的板卡：运行 `cold_start.cmd`。
2. 运行环境已准备的板卡：运行 `start.cmd`。
3. 运行 `open_web.cmd`，访问 `http://127.0.0.1:8849/`。
4. 运行 `status.cmd` 检查相机、模型、截面、视频及 HDMI 服务。
5. 在网页中完成预览、拍照重建、三维旋转、深度查询和截面观察。

`open_web.cmd` 用于打开电脑端页面；实时功能还需要板端服务就绪。故障处理见 [网页启动与排查](web_startup.md)。

## 四、检查文件与参考输出

```powershell
python sim/validate_repository.py
python skill/verify_artifacts.py manifest --root . --file data/provenance/manifest.json
python skill/verify_artifacts.py compare data/reference/reference_arrays.npz data/reference/candidate_arrays.npz --keys-file data/reference/array_keys.json
```

数组比较检查 13 项数组的类型、形状及数据字节。需要 NumPy 时，使用安装器生成的虚拟环境 Python。

## 五、重建 FPGA 工程

1. 安装 Vivado 2026.1 与 XCZU4EV 器件支持，配置适用许可证。
2. 在项目根目录运行：

   ```powershell
   ./build_all.ps1 -VivadoRoot 'D:/AMD/2026.1/Vivado'
   ```

3. 在 `build/output/pl1`、`pl2`、`pl3` 查看构建输出与日志。
4. 如仅需创建工程，使用 `prepare_projects.ps1`；续建参数见 [构建说明](../build/README.md)。

## 六、部署后检查

1. 确认板卡、模型、配置文件与运行清单配套。
2. 运行 `status.cmd`，检查各项服务状态。
3. 使用固定双目输入生成结果，与参考输出比较。
4. 检查预览恢复、三维交互、截面和 HDMI 显示。
5. 保留任务结果和错误日志；出现 DMA 故障或配置切换未完成时，先定位原因，再恢复服务。
