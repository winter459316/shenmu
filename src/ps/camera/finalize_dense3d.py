"""Record verified live release without changing the preserved autofill sources."""
import hashlib,json,urllib.request,zipfile,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[1]
OLD=ROOT.parent/'usb_320_autofill'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    with opener.open('http://127.0.0.1:8783'+path,timeout=8) as r:return json.load(r)
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
s=get('/api/status')
assert s['stage']=='ready' and not s['busy'] and not s['error']
r=s['result'];job=r['job_id'];folder=ROOT/'live_captures'/job
proof=json.loads((folder/'verified.json').read_text(encoding='utf8'))
assert proof['passed'] and proof['dense_fill']['passed'] and proof['dense_fill']['geometry']['passed']
assert hashlib.sha256((folder/'board_result.npz').read_bytes()).hexdigest()==proof['source_sha256']
manifest=json.loads((ROOT/'PRESERVED_AUTOFILL_SHA256.json').read_text())
assert all(hashlib.sha256((OLD/n).read_bytes()).hexdigest()==sha for n,sha in manifest.items())
c=get('/api/camera');h=get('/api/hdmi/status');assert not c['error'] and not h['error']
geometry=proof['board_metadata']['dense_geometry']
report={'passed':True,'job':job,'board_seconds':r['board_seconds'],'total_seconds':r['total_seconds'],
        'dense_geometry':geometry,'verification':proof['dense_fill']['geometry'],'camera':c,'hdmi':h,
        'preserved_autofill_files':len(manifest),'previous_surface_triangles':proof['surface']['layers']['repaired']['triangles'],
        'note':'All image-grid cells connected; this does not establish physical accuracy or unseen geometry.'}
save(ROOT/'board_evidence/live_dense3d_verified.json',report)
state={'active':True,'version':'usb320-filled-disparity-3d-v1','ui':'http://127.0.0.1:8783/',
       'board_api':8784,'board_ram':'/tmp/usb_stereo_probe/usb320_dense3d','last_job':job,
       'rollback_command':'python3 /tmp/usb_stereo_probe/usb320_dense3d/switch_dense3d_board.py rollback',
       'bitstream_sha256':'1040bc3c95d76794e479d8d039f21cbfebc3086e838c507afe81a4e971c6d0b4',
       'stable_preserved':'../usb_320_autofill','updated':datetime.datetime.now().astimezone().isoformat()}
save(ROOT/'CURRENT_STATE.json',state)
(ROOT/'CURRENT_STATE.txt').write_text('''补全视差三维版，2026-10-17
当前界面 http://127.0.0.1:8783/，板端 API 8784，RAM usb320_dense3d。
320×360；原PL匹配及A53全填充算法不变。全填充后量化至Q4，由现有PL几何核投影全部115200点，A53连接229042三角面。
Q4量化最大0.03125像素；原匹配点的Q4及PL坐标不变。原始数组、上一版表面和PLY分别保留。
默认三维使用全填充表面；表面处理可切换“上一版表面（对照）”。含推测区域，可能跨接前后景；并非完整物体或实测精度保证。
截面仍绑定原始稳定几何，不使用本轮新增的全填充推测点。电脑负责逐值验证和WebGL显示；HDMI沿用电脑渲染投屏。
位流未更换，无新增PL资源。RAM服务断电丢失；未修改启动介质。
同照片回放、取消不发布结果、全PL坐标、每个网格单元两面、原数组逐字节保持及一次实时拍照均通过验证。
旧版本完整备份 before_dense3d_autofill_complete.zip，校验见 PREVIOUS_VERSION_BACKUP.json；旧目录保持不变。
回退：任务空闲后通过串口执行 CURRENT_STATE.json 的 rollback_command，恢复8782及原照片，再打开8781。
板上 dense3d_startup_snapshot.json 含进程环境，仅保存在板上0600，禁止导出。
本版切换入口 switch_dense3d_board.py prepare / activate；仅从已启动的autofill8782切换。prepare一次运行，勿覆盖现有快照。
冷启动需先依照usb_320及usb_320_autofill已验证流程恢复保留内存、相机服务和原位流，再部署本版文件并执行回放验证后切换。
电脑入口本目录 full_host.py。复制的历史start/switch/finalize_release.py不是本版入口；不要运行prepare_dense3d.py重复改写源码。
证据：board_evidence/live_dense3d_verified.json、geometry_replay_pc_verified.json 和 live_captures 内 verified.json。
''',encoding='utf8')
files=[p for p in ROOT.iterdir() if p.is_file() and p.name!='LATEST_CHECKPOINT.json' and p.suffix in ('.py','.html','.json','.txt','.so','.dll','.npz','.bin')]
files+=list((ROOT/'board_evidence').iterdir())+list(folder.iterdir())
files=[p for p in files if p.is_file() and 'startup_snapshot' not in p.name]
archive=ROOT/'dense3d_verified_20261017.zip'
hashes={}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for p in files:
        name=p.relative_to(ROOT).as_posix();z.write(p,name);hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    z.writestr('SHA256.json',json.dumps(hashes,indent=2))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,sha in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
save(ROOT/'LATEST_CHECKPOINT.json',{'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(files),'verified':True})
(PROJECT/'USB_CURRENT.txt').write_text('当前USB版本：candidates/usb_320_dense3d（补全视差用于PL点云与A53表面）\n界面http://127.0.0.1:8783/；板上8784。\n详情：candidates/usb_320_dense3d/CURRENT_STATE.txt。\n上一版usb_320_autofill及OV5640/7020工程保留。\n',encoding='utf8')
p=PROJECT/'AGENTS.md';old=p.read_text(encoding='utf8')
note='- Latest active version (2026-10-17): `candidates/usb_320_dense3d`, PC UI 8783, board API 8784, RAM `usb320_dense3d`. Filled disparity now feeds existing PL Q4-to-XYZ projection and A53 full-grid meshing (115200 points, 229042 faces). Previous arrays/surface layers and original section geometry preserved; inferred geometry may bridge depth boundaries. Same bitstream, no new PL resources. Read CURRENT_STATE.txt/JSON and LATEST_CHECKPOINT.json. Previous `usb_320_autofill` 8781/8782 is preserved but no longer owns camera; its historical active flag is superseded by this entry. Roll back via `usb320_dense3d/switch_dense3d_board.py rollback` after idle. No persistent boot changes.\n\n'
if note not in old:p.write_text(old.replace('# ZU4EV migration\n\n','# ZU4EV migration\n\n'+note,1),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
