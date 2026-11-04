"""Archive a verified live 320 build without replacing the 640 stable project."""
import datetime,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    evidence=ROOT/'board_evidence'
    case=json.loads((evidence/'pipeline_320_pc_verified.json').read_text())
    cpu=json.loads((evidence/'completion_320_reference.json').read_text())
    hw=json.loads((ROOT/'hardware_320_verified.json').read_text())
    latest=json.loads((ROOT/'live_latest.json').read_text())
    live=ROOT/'live_captures'/latest['job_id']
    verified=json.loads((live/'verified.json').read_text())
    assert case['passed'] and cpu['passed'] and verified['passed']
    assert json.loads((evidence/'live_320_verified.json').read_text(encoding='utf8'))['passed']
    assert verified['board_metadata']['eye_size']==[320,360]
    assert verified['board_metadata']['bitstream_sha256']==hw['sha256']==sha(ROOT/'usb320.bit.bin')
    preservation=json.loads((evidence/'preservation_320_verified.json').read_text());assert preservation['passed']
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    state={'active':'USB 320x360 per eye from pre-rectification resize onward','time':stamp,
           'ui':'http://127.0.0.1:8772/','board_service':'http://192.168.137.2:8768','bitstream_sha256':hw['sha256'],
           'calibration_sha256':hw['calibration_sha256'],'last_job':latest['job_id'],
           'live':latest,'same_frame_comparison':case['comparison'],
           'completion_pl_cpu_exact':cpu['pl_cpu_completion_bit_exact'],
           'old_stable_preserved':preservation,'no_persistent_boot_write':True,
           'precision_note':'Q4 disparity / Q12 mm coordinates and solver arithmetic/convergence retained. Sampling detail and physical depth accuracy cannot be asserted identical to 640x480; comparison is not ground truth.'}
    (ROOT/'CURRENT_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf8')
    text=f'''USB 双目 320×360 当前版本 — {stamp}
页面：http://127.0.0.1:8772/
板上程序：/tmp/usb_stereo_probe/usb320，服务端口 8768。
相机原始采集 1280×480，预览 640×240。
每眼先用 INTER_AREA 缩为 320×360，随后 PL 校正、特征、SGM、补全向量、XYZ、截面与 A53 表面准备均使用此网格。
Q4 视差 / Q12 mm 坐标、FP32 补全向量与有序 FP64 归约、收敛门限和独立电脑校验保留。
横纵采样比例不同，K/P/Q 和纹理投影已相应调整；不通过额外插值伪造三维细节。
物理测距精度和细节不保证与 640×480 完全相同。

实际照片：{latest['job_id']}
板上处理：{latest['board_seconds']:.3f} 秒；独立验证：{latest['verification_seconds']:.3f} 秒；总等待：{latest['total_seconds']:.3f} 秒。
完整证据：board_evidence/pipeline_320_pc_verified.json、completion_320_reference.json、live_captures/{latest['job_id']}/verified.json。

保留原版：../usb_full；原版界面 8771 可继续查看已有照片，板上相机由新版本独占。
原稳定备份：{preservation['old_archive']}
原 OV5640 和 7020 工程未改动。
本次仅易失 PL 配置和 RAM 目录；没有写 eMMC/SD 启动镜像，断电后需重新部署/加载。
需要回退时：确认新任务 idle 后在板上执行 python3 /tmp/usb_stereo_probe/usb320/switch_320_board.py rollback。
该命令停止新板端服务，重新加载保存的 640 位流，恢复旧照片与旧相机/按键；旧电脑服务无需重启。
日常按键映射保持：PL_KEY1 模式/返回、PL_KEY2 拍照、PS_KEY2 待机、PS_KEY1 恢复；不要按 RST。
源码重建：build_completion_hls.tcl、build_geometry.tcl、build_images.tcl，然后 hdmi_v1/build_hardware.tcl；必须检查时序/CDC 后方可加载。
'''
    (ROOT/'CURRENT_STATE.txt').write_text(text,encoding='utf8')
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.cpp','.c','.h','.hpp','.tcl','.html','.so','.dll','.json','.txt','.npz','.bin')]
    files += [p for p in (ROOT/'hdmi_v1').iterdir() if p.is_file() and p.suffix in ('.tcl','.v','.sv','.xdc','.rpt','.txt','.bif')]
    files += [p for p in evidence.iterdir() if p.is_file() and p.suffix in ('.json','.npz','.png')]
    files += [live/n for n in ('board_result.npz','verified.json','report.json','reference.png','disparity.png','depth.png')]
    files += list(live.glob('section_*.json'))+list(live.glob('section_*.csv'))
    files=sorted(set(files));manifest={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in files}
    destination=ROOT/'checkpoints'/('usb_320_live_'+stamp+'.zip');destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in files:z.write(p,str(p.relative_to(ROOT)).replace('\\','/'))
        z.writestr('ARCHIVE_SHA256.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        for n,digest in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==digest,n
    result={'passed':True,'path':str(destination),'sha256':sha(destination),'bytes':destination.stat().st_size,'verified_files':len(files)}
    (ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
if __name__=='__main__':main()
