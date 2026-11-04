"""Record verified live release without changing the preserved autofill sources."""
import hashlib,json,urllib.request,zipfile,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[1]
OLD=ROOT.parent/'usb_320_fast3d'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    with opener.open('http://127.0.0.1:8787'+path,timeout=8) as r:return json.load(r)
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
s=get('/api/status')
assert s['stage']=='ready' and not s['busy'] and not s['error']
r=s['result'];job=r['job_id'];folder=ROOT/'live_captures'/job
proof=json.loads((folder/'verified.json').read_text(encoding='utf8'))
assert proof['passed'] and proof['dense_fill']['passed'] and proof['dense_fill']['geometry']['passed']
assert hashlib.sha256((folder/'board_result.npz').read_bytes()).hexdigest()==proof['source_sha256']
manifest=json.loads((ROOT/'PRESERVED_FAST3D_SHA256.json').read_text())
assert all(hashlib.sha256((OLD/n).read_bytes()).hexdigest()==sha for n,sha in manifest.items())
c=get('/api/camera');h=get('/api/hdmi/status');assert not c['error'] and not h['error']
geometry=proof['board_metadata']['dense_geometry']
assert proof['dense_fill']['completed_disparity_exact'] and proof['dense_fill']['second_solver_removed']
report={'passed':True,'job':job,'board_seconds':r['board_seconds'],'total_seconds':r['total_seconds'],
        'reuse':proof['board_metadata']['dense_fill'],'dense_geometry':geometry,'verification':proof['dense_fill']['geometry'],'camera':c,'hdmi':h,
        'preserved_fast3d_files':len(manifest),'comparison_surfaces_removed':proof['surface']['comparison_surfaces_removed'],
        'note':'All image-grid cells connected; this does not establish physical accuracy or unseen geometry.'}
save(ROOT/'board_evidence/live_direct3d_verified.json',report)
state={'active':True,'version':'usb320-current-surface-only-v1','ui':'http://127.0.0.1:8787/',
       'board_api':8788,'board_ram':'/tmp/usb_stereo_probe/usb320_direct3d','last_job':job,
       'rollback_command':'python3 /tmp/usb_stereo_probe/usb320_direct3d/switch_direct3d_board.py rollback',
       'bitstream_sha256':'1040bc3c95d76794e479d8d039f21cbfebc3086e838c507afe81a4e971c6d0b4',
       'stable_preserved':'../usb_320_fast3d','updated':datetime.datetime.now().astimezone().isoformat()}
save(ROOT/'CURRENT_STATE.json',state)
(ROOT/'CURRENT_STATE.txt').write_text('仅当前表面的快速三维版，2026-10-17\nPC界面http://127.0.0.1:8787/，板端8788，RAM /tmp/usb_stereo_probe/usb320_direct3d。\n320×360，沿用同一PL位流和快速补全；直接生成全填充点云与放宽条件的229042三角面。\n已移除board_surface.prepare调用、旧版平滑/细节/修复层计算、display_*结果传输、旧表面导出及页面选择。\n原始匹配、快速补全、全填充点云/网格/纹理、来源标记及截面坐标与同照片旧版逐字节相同。原始点云PLY仍可导出。\n同照片回放证明旧对照表面15.2987秒步骤被移除；完整最新实拍耗时见board_evidence/live_direct3d_verified.json。\n当前视差和三维含推测；未知背面不保证封闭。电脑继续逐值验证和渲染；HDMI使用现有投屏流程。\n旧工程/照片备份before_direct3d_complete.zip，SHA见PREVIOUS_VERSION_BACKUP.json，原usb_320_fast3d目录保留未修改。\n回退：等待空闲后串口执行CURRENT_STATE.json的rollback_command，恢复旧8786及切换前照片，再打开8785。\n本版切换入口switch_direct3d_board.py prepare/activate，从已运行的fast3d8786切换；prepare一次运行，勿覆盖快照。\n板上direct3d_startup_snapshot.json含环境仅本地0600保存，禁止导出。位流未重载，不写启动介质，断电后RAM服务丢失。\n冷启动先依前版本恢复保留内存、原位流与相机服务，再部署本版进行回放验证及切换；PC入口本目录full_host.py。\n复制的历史prepare/start/switch/finalize脚本不作为本版入口。当前归档脚本finalize_direct3d.py。\n',encoding='utf8')
files=[p for p in ROOT.iterdir() if p.is_file() and p.name!='LATEST_CHECKPOINT.json' and p.suffix in ('.py','.html','.json','.txt','.so','.dll','.npz','.bin')]
files+=list((ROOT/'board_evidence').iterdir())+list(folder.iterdir())
files=[p for p in files if p.is_file() and 'startup_snapshot' not in p.name]
archive=ROOT/'direct3d_verified_20261017.zip'
hashes={}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for p in files:
        name=p.relative_to(ROOT).as_posix();z.write(p,name);hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    z.writestr('SHA256.json',json.dumps(hashes,indent=2))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,sha in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
save(ROOT/'LATEST_CHECKPOINT.json',{'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(files),'verified':True})
(PROJECT/'USB_CURRENT.txt').write_text('当前USB版本：candidates/usb_320_direct3d（仅当前表面，已移除旧对照表面计算）\n界面http://127.0.0.1:8787/；板上8788，RAM usb320_direct3d。\n详情：candidates/usb_320_direct3d/CURRENT_STATE.txt。\n原usb_320_fast3d及历史工程/照片保留。\n',encoding='utf8')
p=PROJECT/'AGENTS.md';old=p.read_text(encoding='utf8')
note='- Latest active version (2026-10-17): `candidates/usb_320_direct3d`, UI 8787, board API 8788, RAM `usb320_direct3d`. Old comparison surface preparation removed entirely (no board_surface.prepare, display_* arrays or old surface exports); fast completion and current unrestricted PL XYZ/A53 mesh unchanged. Same-photo all non-display arrays byte-exact. Original section geometry retained. Previous usb_320_fast3d is preserved inactive; historical active flags superseded. Roll back through usb320_direct3d/switch_direct3d_board.py rollback when idle, then open 8785. Read CURRENT_STATE.txt/JSON and LATEST_CHECKPOINT.json. Same PL bitstream, no persistent boot changes.\n\n'
if note not in old:p.write_text(old.replace('# ZU4EV migration\n\n','# ZU4EV migration\n\n'+note,1),encoding='utf8')

print(json.dumps(report,ensure_ascii=False,indent=2))
