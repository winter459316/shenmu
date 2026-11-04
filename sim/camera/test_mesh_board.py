"""One held-photo remesh; no shutter, PL writes, or coordinate changes."""
import hashlib,io,json,os,uuid
from pathlib import Path
import numpy as np
from mesh_limits import restrict
from result_archive import pack_result
ROOT=Path(__file__).resolve().parent
def run():
    with np.load(ROOT/'baseline_photo.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files}
    m=json.loads(a.pop('metadata_json').tobytes());original={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in a.items()}
    faces,report=restrict(a['dense3d_xyz_q12'],a['dense3d_faces']);assert 0<len(faces)<=len(a['dense3d_faces'])
    a['dense3d_faces']=faces
    # Existing coordinates, colors, matching, plane correction and hole filling unchanged.
    assert all(hashlib.sha256(v.tobytes()).hexdigest()==original[k] for k,v in a.items() if k!='dense3d_faces')
    cancelled=False
    try:restrict(a['dense3d_xyz_q12'],faces,lambda:True)
    except InterruptedError:cancelled=True
    assert cancelled
    # A short depth step stays connected; a long step is cut.
    xyz=np.array([[[0,0,300],[1,0,303]],[[0,1,300],[1,1,303]]],np.float32)
    f=np.array([[0,2,1],[1,2,3]],np.int32)
    assert len(restrict(np.rint(xyz*4096).astype(np.int32),f)[0])==2
    xyz[:,1,2]=400
    assert len(restrict(np.rint(xyz*4096).astype(np.int32),f)[0])==0
    source_job=m['job_id'];m['job_id']=uuid.uuid4().hex
    m['dense_geometry'].update(triangles=len(faces),depth_jump_culling=True,stretch_culling=True,mesh_limits=report)
    m['remesh']={'source_job':source_job,'seconds':report['seconds'],'new_capture':False,'all_non_face_arrays_exact':True,'note':'Held-photo remesh; original capture timings retained.'}
    package=pack_result(a,m);(ROOT/'candidate_photo.npz').write_bytes(package)
    old=json.loads((ROOT/'baseline_public.json').read_text())['held']
    held={'job_id':m['job_id'],'sha256':hashlib.sha256(package).hexdigest(),'bytes':len(package),'total_seconds':old['total_seconds']}
    (ROOT/'candidate_held.json').write_text(json.dumps(held))
    proof={'passed':True,'cancel_passed':True,'short_bridge_retained':True,'long_bridge_removed':True,
           'all_non_face_arrays_exact':True,'source_job':source_job,'candidate_job':m['job_id'],'mesh':report}
    (ROOT/'mesh_replay_verified.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof),flush=True)
if __name__=='__main__':run()
