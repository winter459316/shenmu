"""Record verified live release without changing the preserved autofill sources."""
import hashlib,json,urllib.request,zipfile,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[1]
OLD=ROOT.parent/'usb_320_dense3d'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    with opener.open('http://127.0.0.1:8785'+path,timeout=8) as r:return json.load(r)
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
s=get('/api/status')
assert s['stage']=='ready' and not s['busy'] and not s['error']
r=s['result'];job=r['job_id'];folder=ROOT/'live_captures'/job
proof=json.loads((folder/'verified.json').read_text(encoding='utf8'))
assert proof['passed'] and proof['dense_fill']['passed'] and proof['dense_fill']['geometry']['passed']
assert hashlib.sha256((folder/'board_result.npz').read_bytes()).hexdigest()==proof['source_sha256']
manifest=json.loads((ROOT/'PRESERVED_DENSE3D_SHA256.json').read_text())
assert all(hashlib.sha256((OLD/n).read_bytes()).hexdigest()==sha for n,sha in manifest.items())
c=get('/api/camera');h=get('/api/hdmi/status');assert not c['error'] and not h['error']
geometry=proof['board_metadata']['dense_geometry']
assert proof['dense_fill']['completed_disparity_exact'] and proof['dense_fill']['second_solver_removed']
report={'passed':True,'job':job,'board_seconds':r['board_seconds'],'total_seconds':r['total_seconds'],
        'reuse':proof['board_metadata']['dense_fill'],'dense_geometry':geometry,'verification':proof['dense_fill']['geometry'],'camera':c,'hdmi':h,
        'preserved_dense3d_files':len(manifest),'previous_surface_triangles':proof['surface']['layers']['repaired']['triangles'],
        'note':'All image-grid cells connected; this does not establish physical accuracy or unseen geometry.'}
save(ROOT/'board_evidence/live_fast3d_verified.json',report)
state={'active':True,'version':'usb320-reuse-fast-completion-v1','ui':'http://127.0.0.1:8785/',
       'board_api':8786,'board_ram':'/tmp/usb_stereo_probe/usb320_fast3d','last_job':job,
       'rollback_command':'python3 /tmp/usb_stereo_probe/usb320_fast3d/switch_fast3d_board.py rollback',
       'bitstream_sha256':'1040bc3c95d76794e479d8d039f21cbfebc3086e838c507afe81a4e971c6d0b4',
       'stable_preserved':'../usb_320_dense3d','updated':datetime.datetime.now().astimezone().isoformat()}
save(ROOT/'CURRENT_STATE.json',state)
(ROOT/'CURRENT_STATE.txt').write_text('快速补全复用三维版，2026-10-17\n当前PC http://127.0.0.1:8785/，板端8786，RAM /tmp/usb_stereo_probe/usb320_fast3d。\n保留320×360及同一PL位流，去掉原额外A53红黑SOR全填充，不再执行第二次迭代。\n复用 completed_disparity_q4 全部115200像素，逐值保持；accepted来源completion_origin==0才标记匹配，其余为推测，包括第一遍已拒绝的原候选。\n快速补全的数值与上一版额外SOR补全不同，不能宣称推测区域外观或物理精度相同。原始匹配及对照表面均未修改。\n复用结果由原PL几何核投影，再按放宽条件连接229042个三角面；所有网格单元连面，未知背面不保证封闭。\n旧平滑/细节/修复表面对照仍按原样计算；截面仍使用原稳定几何。电脑继续验证及显示。\n同照片板端复用约0.063秒，替代原41.97秒的第二次补全；这是该阶段实测，非完整端到端回放。\n原版备份 before_fast3d_complete.zip，哈希见PREVIOUS_VERSION_BACKUP.json；原目录usb_320_dense3d完整保留。\n实拍总耗时、当前照片、逐值校验见board_evidence/live_fast3d_verified.json和live_captures中的verified.json。\n回退：空闲后串口执行CURRENT_STATE.json中的rollback_command，恢复原8784服务及切换前照片，打开8783。\n切换入口 switch_fast3d_board.py prepare / activate，从运行中的dense3d8784切换，prepare只执行一次。\n板上fast3d_startup_snapshot.json仅本地0600保留，不得导出；不重配置PL，不写启动介质，断电RAM服务丢失。\n冷启动依照前版本保留内存与PL启动顺序逐级恢复，再部署本版、运行同照片回放验证并切换；PC启动本目录full_host.py。\n复制的历史prepare/start/switch/finalize脚本不是本版入口，不要直接运行。本版归档入口finalize_fast3d.py。\n',encoding='utf8')
files=[p for p in ROOT.iterdir() if p.is_file() and p.name!='LATEST_CHECKPOINT.json' and p.suffix in ('.py','.html','.json','.txt','.so','.dll','.npz','.bin')]
files+=list((ROOT/'board_evidence').iterdir())+list(folder.iterdir())
files=[p for p in files if p.is_file() and 'startup_snapshot' not in p.name]
archive=ROOT/'fast3d_verified_20261017.zip'
hashes={}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for p in files:
        name=p.relative_to(ROOT).as_posix();z.write(p,name);hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    z.writestr('SHA256.json',json.dumps(hashes,indent=2))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,sha in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
save(ROOT/'LATEST_CHECKPOINT.json',{'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(files),'verified':True})
(PROJECT/'USB_CURRENT.txt').write_text('当前USB版本：candidates/usb_320_fast3d（复用快速补全，去掉第二次SOR）\n界面http://127.0.0.1:8785/；板端8786，RAM usb320_fast3d。\n详情：candidates/usb_320_fast3d/CURRENT_STATE.txt。\n原usb_320_dense3d及更早工程保持不变。\n',encoding='utf8')
p=PROJECT/'AGENTS.md';old=p.read_text(encoding='utf8')
note='- Latest active version (2026-10-17): `candidates/usb_320_fast3d`, PC UI 8785, board API 8786, RAM `usb320_fast3d`. Second expensive SOR completion removed; reuses existing completed_disparity_q4 exactly, including rejection handling. Accepted completion_origin==0 points are measured, others inferred. Same PL bitstream projects full grid; unrestricted A53 meshing retained. Old comparison surface calculations and original section geometry retained. Previous `usb_320_dense3d` preserved inactive (its historical active flag superseded). Roll back through `usb320_fast3d/switch_fast3d_board.py rollback` when idle, then open 8783. Read CURRENT_STATE.txt/JSON and LATEST_CHECKPOINT.json. No persistent boot changes.\n\n'
if note not in old:p.write_text(old.replace('# ZU4EV migration\n\n','# ZU4EV migration\n\n'+note,1),encoding='utf8')

print(json.dumps(report,ensure_ascii=False,indent=2))
