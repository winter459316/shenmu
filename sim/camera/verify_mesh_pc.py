import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
from mesh_limits import restrict
from receive_result import receive
from render_saved import export_result
data=(ROOT/'board_evidence/candidate_photo.npz').read_bytes();held=json.loads((ROOT/'board_evidence/candidate_held.json').read_text())
with np.load(ROOT/'board_evidence/baseline_photo.npz') as z:old={k:z[k] for k in z.files if k!='metadata_json'}
with np.load(ROOT/'board_evidence/candidate_photo.npz') as z:meta=json.loads(z['metadata_json'].tobytes())
status={'busy':False,'job_id':held['job_id'],'result_id':held['job_id'],'metadata':dict(meta,package_sha256=held['sha256'],package_bytes=held['bytes'])}
a,m,b,r=receive(data,status,held['job_id'],lambda stage:None)
expected,_=restrict(old['dense3d_xyz_q12'],old['dense3d_faces']);assert np.array_equal(expected,a['dense3d_faces'])
assert all(a[k].tobytes()==v.tobytes() for k,v in old.items() if k!='dense3d_faces')
export_result(a,m,b,m['surface_preparation'],ROOT/'board_replay')
manifest=json.loads((ROOT/'PRESERVED_PLANE_SHA256.json').read_text())
assert all(hashlib.sha256((ROOT.parent/'usb_320_plane'/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
archive=ROOT/'previous_plane_stable_20261017.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in (ROOT.parent/'usb_320_plane/plane_board_20261017.zip',ROOT/'board_evidence/baseline_photo.npz',ROOT/'board_evidence/baseline_public.json',ROOT/'PRESERVED_PLANE_SHA256.json'):
        z.write(p,p.name)
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
report={'passed':True,'pc_board_faces_exact':True,'all_non_face_arrays_exact':True,'stable_files_verified':len(manifest),'faces_before':len(old['dense3d_faces']),'faces_after':len(expected),'previous_stable_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
(ROOT/'mesh_pc_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
