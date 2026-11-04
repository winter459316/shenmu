"""Verify immutable source/photo preservation and archive the active pipeline."""
import ast,base64,hashlib,json,re,sys,urllib.request,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_320_rawhdmi'
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
manifest=json.loads((ROOT/'PRESERVED_RAWHDMI_SHA256.json').read_text())
for n,h in manifest.items():assert hashlib.sha256((OLD/n).read_bytes()).hexdigest()==h,n
old_archive=OLD/'usb_raw_disparity_hdmi_20261018.zip'
assert hashlib.sha256(old_archive.read_bytes()).hexdigest()=='1859388346b6dc9008cfe23a1b7dfbd0d986cf7fdcf1ea5061d5b556b506698a'
tree=ast.parse((ROOT/'deploy_lowlatency_runtime.py').read_text())
node=next(t for t in tree.body if isinstance(t,ast.Assign) and any(isinstance(n,ast.Name) and n.id=='names' for n in t.targets))
names=ast.literal_eval(node.value.func.value).split();files=[ROOT/n for n in names]
assert all(p.is_file() for p in files)
for p in files:
    if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
(ROOT/'startup_payload_sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
public=['lowlatency_tests.json','lowlatency_activation.json','physical_keys_status.json']
code="import base64,json,zlib;from pathlib import Path;p=Path('/tmp/usb_stereo_probe/usb320_lowlatency');d={n:json.loads((p/n).read_text()) for n in "+repr(public)+"};print('PUBLIC='+base64.b64encode(zlib.compress(json.dumps(d).encode())).decode())"
out=command('python3 -c "'+code+'"',15)
m=re.search(r'(?m)^PUBLIC=([A-Za-z0-9+/=]+)',out);assert m
e=json.loads(zlib.decompress(base64.b64decode(m[1])))
assert e['lowlatency_tests.json']['passed'] and e['lowlatency_activation.json']['passed']
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for name,path in [('camera','/status'),('hdmi','/hdmi/status')]:
    with op.open('http://192.168.137.2:8788'+path,timeout=10) as r:e[name]=json.load(r)
assert not e['camera']['error'] and not e['camera']['preview_error'] and not e['camera']['jpeg_error'] and not e['hdmi']['error']
(ROOT/'board_lowlatency_evidence.json').write_text(json.dumps(e,indent=2))
transport=json.loads((ROOT/'transport_verified.json').read_text());assert transport['passed']
assert transport['held']['sha256']==e['lowlatency_activation.json']['held']['sha256']
checkpoint={'active':True,'date':'2026-10-18','board_api':8788,'board_ram':'/tmp/usb_stereo_probe/usb320_lowlatency',
 'pc_ui':'http://127.0.0.1:8805/','capture_fps_target':30,'independent_JPEG_worker':True,'latest_slots_no_queue':True,
 'unique_frame_HTTP_keepalive_verified':True,'all_six_mode_HDMI_JPEG_exact':True,'geometry_algorithms_unchanged':True,
 'shutter_triggered':False,'held':transport['held'],'old_source_files_verified':len(manifest),'previous_archive':str(old_archive),
 'baseline':json.loads((ROOT/'baseline.json').read_text())['rows'],'optimized':json.loads((ROOT/'optimized.json').read_text())['rows'],
 'latency_scope':'A53 frame delivery onwards; not photon-to-display latency','cold_boot_payload_files':len(files)}
selected=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.so','.dll','.npz','.bin','.html','.json','.txt','.png') and not any(s in p.name for s in ('private','live_host','LATEST_CHECKPOINT'))]
archive=ROOT/'usb_lowlatency_preview_20261018.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in selected:z.write(p,p.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for p in selected:assert hashlib.sha256(z.read(p.name)).digest()==hashlib.sha256(p.read_bytes()).digest()
checkpoint.update(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),verified_files=len(selected))
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(checkpoint,indent=2))
print(json.dumps({k:v for k,v in checkpoint.items() if k not in ('baseline','optimized')}))
