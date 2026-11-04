"""Save measured acceleration, current runtime and a verified rollback checkpoint."""
import datetime,hashlib,json,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;E=ROOT/'board_evidence'
JOB='230052e47136402aa5c74a3bb7b46f9f'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),'utf8')
def main():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path):
        with opener.open('http://127.0.0.1:8771'+path,timeout=10) as response:return json.loads(response.read())
    host=get('/api/status');camera=get('/api/camera');hdmi=get('/api/hdmi/status')
    assert host['job_id']==JOB and host['stage']=='ready' and not host['busy'] and not host['error']
    assert not camera['error'] and not camera['standby'] and camera['age_seconds']<3
    assert hdmi['enabled'] and not hdmi['error'] and hdmi['source']=='preview' and not hdmi['vdma_status']&0xff1
    folder=ROOT/'live_captures'/JOB;verified=read(folder/'verified.json')
    assert verified['passed'] and verified['source_sha256']==sha(folder/'board_result.npz')
    meta=verified['board_metadata']
    assert meta['archive_compression']=='ZIP stored; lossless array bytes'
    assert meta['surface_preparation']['mesh_backend']=='A53 native three workers, ordered FP32'
    assert 'three spawned workers' in meta['surface_preparation']['holes_backend']
    assert meta['bitstream_sha256']=='48350af24a1a760c9f555bd6e39c2d8a0216003a580d7c08204bab5e64c2c39d'
    for name in ('photo_speed_mesh_verified.json','photo_speed_full_verified.json','photo_speed_update_verified.json','photo_archive_verified.json','photo_archive_network_verified.json','photo_speed_service_active.json'):
        assert read(E/name)['passed'],name
    assert sha(E/'photo_speed_before_update.zip')=='f8bf7cb847e8ab6e92a983a1d04b1c6fb28d61b23adb8d63fdfedc9255ba47ea'
    active=read(E/'photo_speed_service_active.json');now=datetime.datetime.now().astimezone()
    report={'passed':True,'time':now.isoformat(),'live_job':JOB,'live_timing':host['result'],
        'camera_pid':active['camera_pid'],'keys_pid':active['keys_pid'],'pc_host_restarted':False,
        'same_photo_surface':read(E/'photo_speed_update_verified.json')['tests'],
        'same_photo_archive':read(E/'photo_archive_verified.json'),'network':read(E/'photo_archive_network_verified.json'),
        'source_and_scene_note':'Same-photo equality/speed checked separately; live photo is a new scene, not a controlled end-to-end A/B.',
        'post_capture_preview_sample':{'seconds':6.015221101,'capture_fps':28.926617506,'hdmi_update_fps':29.757842147,'jpeg_fps':23.93926966,'process_cpu_percent_one_core_100':139.147004897},
        'unchanged':['matching settings','640x480 per eye','calibration','PL firmware','raw geometry','surface algorithm and thresholds','PC independent verification'],
        'new_pl_resource_usage':False,'new_acceleration':'A53 three-worker native mesh and shared-input spawned hole fits; ZIP_STORED over existing PS Ethernet',
        'physical_keys_retested':False,'live_verified_sha256':sha(folder/'verified.json')}
    save(E/'photo_speed_live_verified.json',report)
    scope=read(ROOT/'scope.json')
    scope['latest_user_boundary'].update(latest_reply='继续优化拍照后的处理速度',stop_further_optimization=False,
        latest_completed_step='A53 mesh/holes and lossless archive speedup verified; photo_speed_live_verified.json')
    save(ROOT/'scope.json',scope)
    note=f'''{now.isoformat()} PHOTO SPEED UPDATE LIVE
- User requested more speed after preview update. Camera PID{active['camera_pid']}, keys PID{active['keys_pid']}; PC8771 unchanged. No FPGA reload/PS init/boot writes. Three A53 native mesh workers + three shared-input spawn workers for hole fits; stages run sequentially. New libsurface_mesh.so; old plane library unchanged. No fast-math, no threshold/algorithm/quality changes.
- Fixed photo6fc: surface28.5319 ->18.9601s, all17 arrays byte-exact; second scene6 repair arrays exact. Shared-input worker cancellation0.898s, no surviving workers. Mesh38-42万 faces0.81-0.87 ->0.06-0.08s, FP32 results exact.
- Lossless ZIP_STORED packing7.612 ->0.431s, size32.09 ->66.73MB. Actual wired transfer0.281 ->1.203s. All52 arrays+metadata independently byte-exact on PC. Result still below existing96MiB acceptance limit.
- New actual live photo{JOB}: board34.858s, PC verification7.906s, total46.875s; surface19.058s. This fresh scene is not the same-photo end-to-end A/B. Independent PL matching/XYZ/surface checks passed. Current previewHDMI29.76FPS, fresh JPEG23.94FPS; standbyfalse. Physical keys not repressed this update.
- Enabled defaults in full_camera.py: USB_SURFACE_NATIVE=1, USB_MESH_NATIVE=1, USB_HOLES_PARALLEL=1, USB_ARCHIVE_STORED=1. Surface and archive fallback flags0 remain available. Existing PC host timing fallback fix remains disk-only; no repeat host restart attempted.
- Rollback: preserved full HDMI/key and preview checkpoints; checkpoints/photo_speed_before_20261016 and board_evidence/photo_speed_before_update.zip are original pre-update source. Old OV5640/7020 projects untouched. Remaining bottlenecks surface~19s and PCverification~8s; full original quality/cold-start scope not claimed complete.

'''
    state=ROOT/'CURRENT_STATE.txt';state.write_text(note+state.read_text('utf8'),'utf8')
    (ROOT/'PHOTO_SPEED_RELEASE.txt').write_text('拍照提速版：A53 三核网格检查、共享输入三进程补洞、网线无损未压缩传输。\n本次实拍板上34.9秒，总等待46.9秒；场景会影响耗时。固定同图表面28.5→19.0秒，全部输出字节一致。\n原640×480/目、标定、PL匹配和点云、补洞阈值、电脑独立校验保留。\n三个新增开关USB_MESH_NATIVE / USB_HOLES_PARALLEL / USB_ARCHIVE_STORED默认1；设为0可逐项回退，但应在空闲时停止相机和按键服务、保留当前照片后重启。\n旧工程与先前稳定检查点均保留，主控制页仍为http://127.0.0.1:8771/。\n','utf8')
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.py','.c','.h','.so','.html','.tcl','.xdc','.v','.sv','.txt','.npz'}]
    files += [ROOT/n for n in ('hdmi_v1.bit.bin','usb_full.bit.bin','scope.json','hdmi_hardware_verified.json','stereo_parameters.json')]
    files += [p for p in E.iterdir() if p.is_file() and (p.suffix=='.json' or p.name in {'photo_speed_before_update.zip','photo_speed_live.png'})]
    files += [folder/n for n in ('board_result.npz','verified.json','viewer.html','reference.png')]
    files=sorted(set(p for p in files if p.is_file()))
    manifest={p.relative_to(ROOT).as_posix():sha(p) for p in files}
    archive=ROOT/'checkpoints'/('usb_photo_speed_'+now.strftime('%Y%m%d_%H%M%S')+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
        z.writestr('ARCHIVE_SHA256.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(archive) as z:
        for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
    summary={'passed':True,'archive':str(archive),'sha256':sha(archive),'files_verified':len(files),'bytes':archive.stat().st_size}
    save(E/'photo_speed_checkpoint_verified.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
