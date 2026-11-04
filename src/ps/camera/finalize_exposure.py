"""Record checked runtime evidence and preserve the previous release."""
import base64,hashlib,json,re,sys,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
preserved=json.loads((ROOT/'PRESERVED_MESHGUARD_SHA256.json').read_text())
for name,digest in preserved.items():
    assert hashlib.sha256((ROOT.parent/'usb_320_meshguard'/name).read_bytes()).hexdigest()==digest,name
files=['cold_start_verified.json','exposure_probe.json','physical_keys_status.json']
code="import base64,json,zlib;from pathlib import Path;p=Path('/tmp/usb_stereo_probe/usb320_exposure');d={n:json.loads((p/n).read_text()) for n in "+repr(files)+"};print('PUBLIC='+base64.b64encode(zlib.compress(json.dumps(d).encode())).decode())"
raw=command('python3 -c "'+code+'"',15)
line=re.search(r'(?m)^PUBLIC=([A-Za-z0-9+/=]+)',raw);assert line
evidence=json.loads(zlib.decompress(base64.b64decode(line[1])))
(ROOT/'board_public_evidence.json').write_text(json.dumps(evidence,indent=2))
assert evidence['cold_start_verified.json']['passed']
proof=json.loads((ROOT/'exposure_live_verified.json').read_text());assert proof['passed']
same=['usb_full_engine.py','full_runtime.py','board_completion.py','board_geometry.py','board_plane.py',
      'plane_guard.py','mesh_limits.py','dense_fill.py','dense_geometry.py','preview_rectify.py','shared_preview.py',
      'stereo_parameters.json','rectification_maps.npz','physical_keys.py','hdmi_output.py']
assert all((ROOT/n).read_bytes()==(ROOT.parent/'usb_320_meshguard'/n).read_bytes() for n in same)
checkpoint={'active':True,'board_ram':'/tmp/usb_stereo_probe/usb320_exposure','board_api':8788,
            'pc_ui':'http://127.0.0.1:8797/','exposure_backend':'camera native AE/AGC, A53 supervision',
            'native_auto_already_factory_default':True,'power_line_hz':50,'preview_fps':proof['color_preview_fps'],
            'original_source_hashes_verified':len(preserved),'photo_and_algorithms_preserved':True,
            'manual_exposure_experiment_rejected':True,'shutter_triggered':False,
            'stable_archive':'../usb_320_meshguard/mesh_guard_20261017.zip'}
archive=ROOT/'usb_auto_exposure_20261017.zip'
selected=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.so','.dll','.npz','.bin','.html','.json','.txt')
          and not any(w in p.name for w in ('private','live_host','LATEST_CHECKPOINT'))]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in selected:z.write(p,p.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for p in selected:assert hashlib.sha256(z.read(p.name)).digest()==hashlib.sha256(p.read_bytes()).digest()
checkpoint.update(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),verified_files=len(selected))
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(checkpoint,indent=2))
print(json.dumps(checkpoint))
