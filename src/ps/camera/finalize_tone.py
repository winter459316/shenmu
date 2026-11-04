"""Verify old files and collect only public board evidence; archive new release."""
import base64,hashlib,json,re,sys,zipfile,zlib,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_320_exposure'
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
preserved=json.loads((ROOT/'PRESERVED_EXPOSURE_SHA256.json').read_text())
for name,digest in preserved.items():assert hashlib.sha256((OLD/name).read_bytes()).hexdigest()==digest,name
archive_old=OLD/'usb_auto_exposure_20261017.zip'
assert hashlib.sha256(archive_old.read_bytes()).hexdigest()=='ff56756cf3da7f52aca4278c11068dd370cbe041b63c7a22aa75791aaea546f7'
names=['tone_tests.json','tone_activation.json','physical_keys_status.json']
code="import base64,json,zlib;from pathlib import Path;p=Path('/tmp/usb_stereo_probe/usb320_tonemap');d={n:json.loads((p/n).read_text()) for n in "+repr(names)+"};print('PUBLIC='+base64.b64encode(zlib.compress(json.dumps(d).encode())).decode())"
raw=command('python3 -c "'+code+'"',15)
m=re.search(r'(?m)^PUBLIC=([A-Za-z0-9+/=]+)',raw);assert m
evidence=json.loads(zlib.decompress(base64.b64decode(m[1])))
assert evidence['tone_tests.json']==json.loads((ROOT/'tone_tests.json').read_text())
assert evidence['tone_activation.json']['passed']
(ROOT/'board_tone_evidence.json').write_text(json.dumps(evidence,indent=2))
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:8799/api/camera',timeout=10) as r:camera=json.load(r)
assert camera['tone_map']['enabled'] and camera['mode']=='color' and not camera['error']
timing=json.loads((ROOT/'tone_live_verified.json').read_text());assert timing['passed']
checkpoint={'active':True,'board_ram':'/tmp/usb_stereo_probe/usb320_tonemap','board_api':8788,
            'pc_ui':'http://127.0.0.1:8799/','scope':'preview only','tone_enabled':True,
            'photo_algorithm_unchanged':True,'old_source_hashes_verified':len(preserved),
            'timing':timing['timing'],'shutter_triggered':False,'ui_on_off_tested':True,
            'stable_archive':str(archive_old)}
archive=ROOT/'usb_shadow_lift_20261017.zip'
selected=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.so','.dll','.npz','.bin','.html','.json','.txt','.png','.jpg')
          and not any(s in p.name for s in ('private','live_host','LATEST_CHECKPOINT'))]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in selected:z.write(p,p.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for p in selected:assert hashlib.sha256(z.read(p.name)).digest()==hashlib.sha256(p.read_bytes()).digest()
checkpoint.update(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),verified_files=len(selected))
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(checkpoint,indent=2));print(json.dumps(checkpoint))
