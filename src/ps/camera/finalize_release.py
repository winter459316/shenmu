import hashlib,json,urllib.request,zipfile,datetime,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1];OLD=ROOT.parent/'usb_320'
sys.path.insert(0,str(PROJECT/'experiments/usb_camera_20261016/deps'))
import cv2,numpy as np
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    with opener.open('http://127.0.0.1:8781'+path,timeout=5) as r:return json.load(r)
s=get('/api/status');assert s['stage']=='ready' and not s['busy'] and not s['error'],s['stage']
r=s['result'];job=r['job_id'];folder=ROOT/'live_captures'/job
proof=json.loads((folder/'verified.json').read_text(encoding='utf8'));assert proof['passed'] and proof['dense_fill']['passed']
c=get('/api/camera');h=get('/api/hdmi/status');assert not c['error'] and not h['error']
for name in ('disparity.png','depth.png'):
    p=cv2.imread(str(folder/name));assert p.shape==(360,320,3) and not np.any(np.all(p==0,axis=2))
manifest=json.loads((ROOT/'STABLE_SOURCE_SHA256.json').read_text())
assert all(hashlib.sha256((OLD/n).read_bytes()).hexdigest()==sha for n,sha in manifest.items())
report={'passed':True,'job':job,'board_seconds':r['board_seconds'],'total_seconds':r['total_seconds'],
        'dense_fill':r['dense_fill'],'verification':proof['dense_fill'],'camera':c,'hdmi':h,
        'original_source_files_unchanged':len(manifest),'black_pixels_in_disparity_and_depth':0}
(ROOT/'board_evidence/live_autofill_verified.json').write_text(json.dumps(report,indent=2),encoding='utf8')
state={'active':True,'version':'usb320-board-autofill-v1','ui':'http://127.0.0.1:8781/',
       'board_api':8782,'board_ram':'/tmp/usb_stereo_probe/usb320_autofill','last_job':job,
       'rollback_command':'python3 /tmp/usb_stereo_probe/usb320_autofill/switch_autofill_board.py rollback',
       'bitstream_sha256':'1040bc3c95d76794e479d8d039f21cbfebc3086e838c507afe81a4e971c6d0b4','stable_preserved':'../usb_320'}
(ROOT/'CURRENT_STATE.json').write_text(json.dumps(state,indent=2),encoding='utf8')
text='''板端自动全填充版（2026-10-17）
界面8781，板上8782，RAM /tmp/usb_stereo_probe/usb320_autofill。
以原usb_320稳定匹配为基础，不使用已回退的PS-HH混合匹配。
每眼320×360。每次拍照及PL_KEY2触发：原PL匹配/点云、原表面处理，然后A53全填充视差，最后打包。
新增dense_disparity_px/dense_depth_mm/dense_origin/dense_distance_px；原始数组不变。
默认disparity.png/depth.png使用全填充值；raw_disparity.png/raw_depth.png保留未填充图。
来源0原匹配、1邻近推测、2远处/边界外推。全填充区域不代表实测精度。
三维、截面、PLY仍使用原稳定数据，没有将全填充值替换到PL几何模块。
A53增加约数十秒，实际耗时查看live_autofill_verified.json；原PL位流、占用和时序保持不变。
取消/待机可中断迭代，已用固定照片验证取消无结果发布；本轮未要求用户物理按键测试。
已实拍并独立校验全部PL匹配/几何/表面和全填充数值，PNG有效区无黑色像素。
旧源/标定/位流备份stable_before_autofill.zip，SHA见STABLE_BACKUP.json；原OV5640/7020保留。
回退：等待任务空闲，经串口执行CURRENT_STATE.json的rollback_command，恢复旧8768服务及切换前照片，打开8772。
不重配置PL，不写启动介质。RAM服务断电丢失。
冷启动先按../usb_320已验证的保留内存流程启动稳定320位流及8768服务，再部署本目录运行文件、dense_fill.py、switch_autofill_board.py、dense_replay_verified.json，
执行prepare和activate；电脑启动本目录full_host.py。历史复制的其他switch/start脚本不作为此版入口。
板上autofill_startup_snapshot.json含进程环境仅保存在板上0600，禁止导出到检查点。
'''
(ROOT/'CURRENT_STATE.txt').write_text(text,encoding='utf8')
files=[p for p in ROOT.iterdir() if p.is_file() and p.name!='LATEST_CHECKPOINT.json' and p.suffix in ('.py','.html','.json','.txt','.so','.dll','.npz','.bin')]
files+=list((ROOT/'board_evidence').iterdir())+list(folder.iterdir())
files=[p for p in files if p.is_file()]
archive=ROOT/'autofill_verified_20261017.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    hashes={}
    for p in files:
        name=p.relative_to(ROOT).as_posix();z.write(p,name);hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    z.writestr('SHA256.json',json.dumps(hashes,indent=2))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,sha in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps({'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(files),'verified':True},indent=2))
(PROJECT/'USB_CURRENT.txt').write_text('当前USB版本：candidates/usb_320_autofill（板端自动全填充视差）\n界面http://127.0.0.1:8781/；板上8782，RAM usb320_autofill。\n详情：candidates/usb_320_autofill/CURRENT_STATE.txt。\n原稳定usb_320已完整保留，当前不占用相机。原OV5640、7020保持不变。\n',encoding='utf8')
p=PROJECT/'AGENTS.md';old=p.read_text(encoding='utf8')
note='- Latest active version (2026-10-17): `candidates/usb_320_autofill`, PC UI 8781, board API 8782, RAM `usb320_autofill`. User requested automatic board integration of full-hole disparity filling. Stable PL matching remains unchanged; A53 appends dense display disparity/depth with explicit provenance after every photo. Raw arrays, PL XYZ/sections and surface geometry remain stable. Read CURRENT_STATE.txt/JSON and LATEST_CHECKPOINT.json. Previous usb_320 is preserved, inactive on board. Roll back via `usb320_autofill/switch_autofill_board.py rollback` after idle. Hybrid HH version remains inactive.\n\n'
p.write_text(old.replace('# ZU4EV migration\n\n','# ZU4EV migration\n\n'+note,1),encoding='utf8')
print(json.dumps({'passed':True,'job':job,'board_seconds':r['board_seconds'],'total_seconds':r['total_seconds'],'fill':r['dense_fill'],'archive':str(archive)}))
