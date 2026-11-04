"""Collect public evidence and preserve this preview-only release; no shutter."""
import base64,hashlib,json,re,sys,urllib.request,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'usb_320_tonemap'
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
preserved=json.loads((ROOT/'PRESERVED_TONEMAP_SHA256.json').read_text())
for name,digest in preserved.items():
    assert hashlib.sha256((OLD/name).read_bytes()).hexdigest()==digest,name
old_archive=OLD/'usb_shadow_lift_20261017.zip'
assert hashlib.sha256(old_archive.read_bytes()).hexdigest()=='b5ea216d338e637d7b89a9f9656ec5bbff6feb83b7abbf33877c529f75b90271'
names=['viewmodes_tests.json','viewmodes_activation.json','physical_keys_status.json']
code="import base64,json,zlib;from pathlib import Path;p=Path('/tmp/usb_stereo_probe/usb320_viewmodes');d={n:json.loads((p/n).read_text()) for n in "+repr(names)+"};print('PUBLIC='+base64.b64encode(zlib.compress(json.dumps(d).encode())).decode())"
raw=command('python3 -c "'+code+'"',15)
m=re.search(r'(?m)^PUBLIC=([A-Za-z0-9+/=]+)',raw);assert m
evidence=json.loads(zlib.decompress(base64.b64decode(m[1])))
assert evidence['viewmodes_tests.json']['passed']
assert evidence['viewmodes_activation.json']['passed']
keys=evidence['physical_keys_status.json']
assert keys['running'] and keys['counts']['pl_key1']>=1,keys
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(url):
    with opener.open(url,timeout=15) as r:return json.load(r)
camera=get('http://127.0.0.1:8801/api/camera')
hdmi=get('http://192.168.137.2:8788/hdmi/status')
photo=get('http://192.168.137.2:8788/stereo/status')
assert not camera['error'] and not camera['preview_error'] and not hdmi['error']
assert camera['mode']=='auto_enhanced' and camera['tone_map']['enabled']
assert photo['result_id']=='dbad4e94a767485eb050e2f0c31984b8'
assert photo['metadata']['package_sha256']=='52b236410de3d991427494146f5117e62f5d8e4345ddd81ebb626a5fe6550d27'
evidence.update(camera=camera,hdmi=hdmi,user_confirmed_physical_button=True,user_confirmed_shadow_lift=True)
(ROOT/'board_viewmodes_evidence.json').write_text(json.dumps(evidence,indent=2))
checkpoint={'active':True,'board_ram':'/tmp/usb_stereo_probe/usb320_viewmodes','board_api':8788,
 'pc_ui':'http://127.0.0.1:8801/','scope':'preview only','mode':camera['mode'],
 'mode_cycle':['color','auto_enhanced','rectified','gray','median','sobel'],
 'native_camera_auto_exposure':'enabled in both raw and enhanced modes',
 'physical_button_user_confirmed':True,'photo_algorithm_unchanged':True,
 'held_photo_id':photo['result_id'],'held_sha256':photo['metadata']['package_sha256'],
 'old_source_hashes_verified':len(preserved),'previous_archive':str(old_archive),'shutter_triggered':False}
archive=ROOT/'usb_viewmodes_20261017.zip'
selected=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.so','.dll','.npz','.bin','.html','.json','.txt','.png','.jpg')
 and not any(s in p.name for s in ('private','live_host','LATEST_CHECKPOINT'))]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in selected:z.write(p,p.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for p in selected:assert hashlib.sha256(z.read(p.name)).digest()==hashlib.sha256(p.read_bytes()).digest()
checkpoint.update(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),verified_files=len(selected))
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(checkpoint,indent=2))
print(json.dumps(checkpoint))
