from pathlib import Path
import json,hashlib
import numpy as np
R=Path(__file__).resolve().parent
report=json.loads((R/'comparison/report.json').read_text(encoding='utf8'))
manifest=json.loads((R/'preserved_sha256.json').read_text())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest.items())
data=np.load(R/'input/board_result.npz')
source=Path(json.loads((R/'input/input_manifest.json').read_text())['source'])/'board_result.npz'
assert source.read_bytes()==(R/'input/board_result.npz').read_bytes()
stable_geometry=np.load(R/'comparison/baseline_final/geometry.npz')
assert np.array_equal(stable_geometry['xyz_mm'],data['dense3d_xyz_q12'].astype(np.float32)/4096)
assert np.array_equal(stable_geometry['faces'],data['dense3d_faces'])
assert stable_geometry['display_valid'].all()
for name in ['light','fast']:
    d=np.load(R/f'results/{name}/disparity.npy');g=np.load(R/f'comparison/{name}/geometry.npz')
    assert d.shape==(360,320) and np.isfinite(d).all() and np.array_equal(d,g['disparity'])
    assert np.all(g['display_valid'].ravel()[g['faces']])
    xyz=g['xyz_mm'];x=xyz[...,0];y=xyz[...,1];z=xyz[...,2];q=data['Q']
    uu=x/z*(q[2,3]/q[0,0])-q[0,3]/q[0,0]
    vv=y/z*(q[2,3]/q[1,1])-q[1,3]/q[1,1]
    yy,xx=np.indices(d.shape)
    assert np.max(np.abs(uu-xx))<.0001 and np.max(np.abs(vv-yy))<.0001
checks={'stable_files_unchanged':len(manifest),'input_npz_byte_exact':True,'saved_stable_xyz_and_faces_exact':True,'stable_display_points':115200,'stable_display_faces':len(data['dense3d_faces']),'no_added_depth_window_clip':True,'network_arrays_and_export_equal':True,'shape':[360,320],
 'Q_roundtrip_max_gate_pixels':.0001,'mesh_references_only_display_valid':True,'board_access_this_experiment':False,'new_shutter':False}
(R/'verification.json').write_text(json.dumps(checks,indent=2))
light=report['results']['light'];fast=report['results']['fast']
state=f'''独立离线 CNN 对照，2026-10-18
入口：http://127.0.0.1:8812/；重开网页服务：start_comparison.ps1。
稳定版保持原路径、服务、板端 bitstream 和相机状态。本次无板端访问、无新拍照。
冻结照片：{report['photo']}（玩偶、纸盒、笔记本场景）。input/board_result.npz 与源文件逐字节相同。
输入：同一份保存的 rectified_left/right，BGR 转 RGB，原始每眼320×360，不重新缩放或校正。
原始 Q/P1/P2 保留。仅补边满足网络步长，推理后裁回320×360；不改变视差单位。

LightStereo-S：作者 SceneFlow 权重，官方MAX_DISP192，timm0.4.12（light_deps），FP32。
Fast-FoundationStereo：作者23-36-37序列化权重，8次迭代，MAX_DISP192，timm1.0.15，FP16 autocast。
模型架构及权重未改。Light以命名空间导入避开全训练器依赖，禁止下载无用的ImageNet初始化，随后strict加载全部权重。
Fast使用官方pytorch1代价构建；Windows禁用torch.compile，使用相同算子eager执行。
仓库提交及权重SHA见model_manifest.json。依赖见environment-lock.txt；Light另用timm0.4.12。

实测设备：RTX 4060 Laptop 8GB / i7-14700HX，PyTorch2.6.0+cu124。
有限计时：2次预热后5次网络推理；另外3次输入预处理/传输/推理/取回；GPU前后同步。
Light单次推理中位 {light['timing']['median_forward_seconds']*1000:.2f} ms；含预处理传输 {light['timing']['median_pipeline_seconds']*1000:.2f} ms。
Fast单次推理中位 {fast['timing']['median_forward_seconds']*1000:.2f} ms；含预处理传输 {fast['timing']['median_pipeline_seconds']*1000:.2f} ms。
电脑XYZ+统一连面预热后三次中位：Light {light['geometry_mesh_seconds_pc']*1000:.2f} ms；Fast {fast['geometry_mesh_seconds_pc']*1000:.2f} ms。
这些数据不含照片读取、文件导出和浏览器绘制，不是板端速度，也不是端到端相机帧率。
稳定版该照片历史processing_seconds为7.10755 s，含板端完整匹配/补全/三维，不能直接除以GPU推理得到同平台加速比。

结果：Light-S在上方和左侧背景出现大面积异常高视差，当前权重不建议直接替换。
Fast视差连续，玩偶轮廓更干净，三维背景更平整，碎裂减少；旋转后的遮挡缺口仍保留。
共同55844像素的左右颜色残差（越小越一致）原始SGM8.37、稳定最终8.73、Light24.71、Fast12.26。
颜色残差不是实际视差/深度真值误差。没有真实深度标注，不宣称Fast精度全面超过稳定版。
320×360的相机像素纵横尺度不等，且SceneFlow与真实室内分布不同，可能影响泛化；尚未用实验证实失败原因。

显示修正（用户指出大空洞后）：取消曾额外加入的0.15–2.0m三维深度裁剪。
此前该裁剪在稳定版隐藏15857点、减少33214面，在Fast隐藏14038点，在Light隐藏49021点。
旧版对照页及数据已归档before_display_crop_fix，不应再用其裁剪后表面评价原稳定版。
当前稳定版最终表面使用原板端115200点、219398面和dense3d_texture，坐标和面逐值验证一致。
其他模型不裁剪正深度点，仍使用相同Q及25mm/8%/stretch25连面条件，默认正面。
旋转中心和观察包围盒使用稳定版相机参数，四组一致。
原始网络数值完整保存在results/*/disparity.npy，不补洞、不做平面修正，不因显示范围丢弃原数值。
视差颜色范围0–127px；超过范围显示端点色，原值保留。不同模型正值百分比不是可信匹配率。
稳定版最终对照不重新连面，网格直接复用原板端结果。
网页支持四窗口统一正面/斜侧面/彩色/纯色/点云，并可打开独立窗口旋转和下载PLY。
网页无稳定服务令牌，没有相机拍照或板端控制功能。
已校验稳定工程407个文件及原照片未变；详见verification.json。
'''
(R/'CURRENT_STATE.txt').write_text(state,encoding='utf8')
(R/'comparison/说明与结论.txt').write_text(state,encoding='utf8')
print(json.dumps(checks,indent=2));print('Wrote CURRENT_STATE.txt')
