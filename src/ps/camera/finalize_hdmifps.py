import ast,base64,hashlib,json,re,sys,urllib.request,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_320_lowlatency'
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
saved=json.loads((ROOT/'PRESERVED_LOWLATENCY_SHA256.json').read_text())
for n,h in saved.items():assert hashlib.sha256((OLD/n).read_bytes()).hexdigest()==h,n
assert hashlib.sha256((OLD/'usb_lowlatency_preview_20261018.zip').read_bytes()).hexdigest()=='3cdab596529d05c5a8f27a93132f2b23199f55b1e32f88c2e727382088c84c90'
names=['hdmifps_tests.json','hdmifps_activation.json','physical_keys_status.json']
code="import base64,json,zlib;from pathlib import Path;p=Path('/tmp/usb_stereo_probe/usb320_hdmifps');d={n:json.loads((p/n).read_text()) for n in "+repr(names)+"};print('PUBLIC='+base64.b64encode(zlib.compress(json.dumps(d).encode())).decode())"
raw=command('python3 -c "'+code+'"',15);m=re.search(r'(?m)^PUBLIC=([A-Za-z0-9+/=]+)',raw);assert m
e=json.loads(zlib.decompress(base64.b64decode(m[1])))
assert e['hdmifps_tests.json']['passed'] and e['hdmifps_activation.json']['passed']
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with op.open('http://192.168.137.2:8788/hdmi/status',timeout=10) as r:h=json.load(r)
assert not h['error'] and 'FPS:' in h['fps_label'];e['current_hdmi']=h
(ROOT/'board_hdmifps_evidence.json').write_text(json.dumps(e,indent=2))
held=e['hdmifps_activation.json']['held']
with op.open('http://192.168.137.2:8788/stereo/result.npz?id='+held['job_id'],timeout=30) as r:payload=r.read()
assert hashlib.sha256(payload).hexdigest()==held['sha256'];(ROOT/'held_restore.npz').write_bytes(payload)
(ROOT/'held_restore.json').write_text(json.dumps(held,indent=2))
t=ast.parse((ROOT/'deploy_hdmifps_runtime.py').read_text());node=next(n for n in t.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='names' for x in n.targets))
files=[ROOT/n for n in ast.literal_eval(node.value.func.value).split()]
for p in files:
    assert p.is_file()
    if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
(ROOT/'startup_payload_sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
selected=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.html','.json','.npz','.so','.dll','.bin','.txt','.png') and not any(s in p.name for s in ('private','live_host','LATEST_CHECKPOINT'))]
archive=ROOT/'usb_hdmi_fps_20261018.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in selected:z.write(p,p.name)
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
report={'active':True,'board_ram':'/tmp/usb_stereo_probe/usb320_hdmifps','board_api':8788,'pc_source':'usb_320_lowlatency','pc_ui':'http://127.0.0.1:8805/',
 'fps_label':h['fps_label'],'source_files_preserved':len(saved),'held':held,'shutter_triggered':False,'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
