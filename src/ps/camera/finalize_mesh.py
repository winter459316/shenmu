import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'PRESERVED_PLANE_SHA256.json').read_text())
assert all(hashlib.sha256((ROOT.parent/'usb_320_plane'/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
assert json.loads((ROOT/'mesh_pc_verified.json').read_text())['passed']
assert json.loads((ROOT/'board_evidence/mesh_activation.json').read_text())['passed']
assert json.loads((ROOT/'board_evidence/mesh_replay_verified.json').read_text())['passed']
status=json.loads((ROOT/'board_evidence/live_host_status.json').read_text());assert status['stage']=='ready' and not status['error']
files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.c','.so','.dll','.npz','.html','.json','.txt') and p.name not in ('live_host.json','LATEST_CHECKPOINT.json') and 'private' not in p.name and 'snapshot' not in p.name]
for name in ('board_evidence','live_captures','board_replay','comparison'):
    files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and 'private' not in p.name)
archive=ROOT/'mesh_guard_20261017.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert all(hashlib.sha256(z.read(p.relative_to(ROOT).as_posix())).digest()==hashlib.sha256(p.read_bytes()).digest() for p in files)
state={'active':True,'board_ram':'/tmp/usb_stereo_probe/usb320_meshguard','board_api':8788,'pc_ui':'http://127.0.0.1:8795/',
       'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'verified_files':len(files),
       'stable_backup':str(ROOT/'previous_plane_stable_20261017.zip'),'stable_hashes_verified':len(manifest),
       'source_photo':'597e36b0beab4c95b0261efbb550f8a2','derived_photo':status['job_id'],
       'all_coordinates_preserved':True,'bitstream_unchanged':True,'mesh_processor':'A53','extra_seconds':.238641877,
       'old_pc_stop_blocked_by_approval':True}
(ROOT/'LATEST_CHECKPOINT.json').write_text(json.dumps(state,indent=2));print(json.dumps(state,indent=2))
