"""Archive the active plane release and verify preserved stable source hashes."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'PRESERVED_SOURCE_SHA256.json').read_text())
assert all(hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest()==digest for name,digest in manifest.items())
for name in ('plane_pc_verified.json','board_evidence/plane_replay_verified.json','board_evidence/live_acceptance.json','board_evidence/preview_speed_after.json'):
    assert json.loads((ROOT/name).read_text())['passed'],name
runtime_names=['full_camera.py','full_runtime.py','usb_full_engine.py','board_plane.py','plane_guard.py','dense_fill.py','dense_geometry.py','shared_preview.py','preview_native.so','hdmi_output.py','physical_keys.py','stereo_parameters.json','rectification_maps.npz','switch_plane_board.py']
runtime={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in runtime_names}
(ROOT/'plane_runtime_manifest.json').write_text(json.dumps(runtime,indent=2))
files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.c','.so','.dll','.npz','.html','.json','.txt') and p.name not in ('live_host.json','LATEST_CHECKPOINT.json') and 'private' not in p.name and 'snapshot' not in p.name]
for name in ('board_evidence','live_captures','replay_views'):
    files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and 'private' not in p.name)
archive=ROOT/'plane_board_20261017.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert all(hashlib.sha256(z.read(p.relative_to(ROOT).as_posix())).digest()==hashlib.sha256(p.read_bytes()).digest() for p in files)
state={'active':True,'board_ram':'/tmp/usb_stereo_probe/usb320_plane','board_api':8788,'pc_ui':'http://127.0.0.1:8793/',
       'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'verified_files':len(files),
       'stable_backup':str(ROOT/'previous_stable_20261017.zip'),'stable_hashes_verified':len(manifest),
       'bitstream_unchanged':True,'plane_processor':'A53','corrected_projection':'PL','mesh':'A53','rendering':'PC',
       'original_section_geometry_preserved':True}
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(state,indent=2));print(json.dumps(state,indent=2))
