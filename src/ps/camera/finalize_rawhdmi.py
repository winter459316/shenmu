"""Archive public evidence and verify preservation; never export private environments."""
import ast,base64,hashlib,json,re,sys,urllib.request,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_320_viewmodes'
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
manifest=json.loads((ROOT/'PRESERVED_VIEWMODES_SHA256.json').read_text())
for n,h in manifest.items():assert hashlib.sha256((OLD/n).read_bytes()).hexdigest()==h,n
old_archive=OLD/'usb_viewmodes_20261017.zip'
assert hashlib.sha256(old_archive.read_bytes()).hexdigest()=='977b6c3f1ee5aa8791fdad039a4dcfe8847a2499238354a43d1058760e7be79d'
tree=ast.parse((ROOT/'deploy_rawhdmi_runtime.py').read_text())
node=next(t for t in tree.body if isinstance(t,ast.Assign) and any(isinstance(n,ast.Name) and n.id=='names' for n in t.targets))
names=ast.literal_eval(node.value.func.value).split();files=[ROOT/n for n in names]
assert all(p.is_file() for p in files)
for p in files:
    if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
(ROOT/'startup_payload_sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
public=['rawhdmi_tests.json','rawhdmi_activation.json','physical_keys_status.json']
code="import base64,json,zlib,hashlib;from pathlib import Path;from raw_disparity_hdmi import render;p=Path('/tmp/usb_stereo_probe/usb320_rawhdmi');d={n:json.loads((p/n).read_text()) for n in "+repr(public)+"};held=json.loads((p/'held_restore.json').read_text());frame,report=render((p/'held_restore.npz').read_bytes(),held['job_id']);d.update(expected_frame_sha256=hashlib.sha256(frame).hexdigest());print('PUBLIC='+base64.b64encode(zlib.compress(json.dumps(d).encode())).decode())"
out=command('cd /tmp/usb_stereo_probe/usb320_rawhdmi && python3 -c "'+code+'"',20)
m=re.search(r'(?m)^PUBLIC=([A-Za-z0-9+/=]+)',out);assert m
e=json.loads(zlib.decompress(base64.b64decode(m[1])))
assert e['rawhdmi_tests.json']['passed'] and e['rawhdmi_activation.json']['passed']
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with op.open('http://192.168.137.2:8788/hdmi/status',timeout=10) as r:h=json.load(r)
assert not h['error'] and h['source']=='raw_disparity'
assert h['last_frame_sha256']==e['expected_frame_sha256']
e.update(hdmi=h,user_confirmed_hdmi=True)
(ROOT/'board_rawhdmi_evidence.json').write_text(json.dumps(e,indent=2))
live=json.loads((ROOT/'rawhdmi_live_verified.json').read_text());assert live['passed']
checkpoint={'active':True,'date':'2026-10-18','board_api':8788,'board_ram':'/tmp/usb_stereo_probe/usb320_rawhdmi',
 'pc_ui':'http://127.0.0.1:8803/','preview_only_change':True,'raw_disparity_source':'disparity_q4 + valid',
 'geometry_uses_processed_disparity':True,'all_photo_bytes_unchanged':True,'held':live['held'],
 'shutter_triggered':False,'new_capture_auto_display_test':'PC/A53 simulated publication; no real shutter this turn',
 'user_confirmed_hdmi':True,'scanout_sha_verified':True,'old_source_files_verified':len(manifest),
 'previous_archive':str(old_archive),'fresh_boot_payload_files':len(files)}
selected=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.so','.dll','.npz','.bin','.html','.json','.txt','.png') and not any(s in p.name for s in ('private','live_host','LATEST_CHECKPOINT'))]
archive=ROOT/'usb_raw_disparity_hdmi_20261018.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in selected:z.write(p,p.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for p in selected:assert hashlib.sha256(z.read(p.name)).digest()==hashlib.sha256(p.read_bytes()).digest()
checkpoint.update(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),verified_files=len(selected))
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(checkpoint,indent=2));print(json.dumps(checkpoint))
