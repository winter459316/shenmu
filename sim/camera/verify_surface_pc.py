"""Check returned board display geometry without replacing it with PC output."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
from surface_cleanup import plane_filter,SurfaceConfig
with np.load(ROOT/'board_evidence/full_pipeline_result.npz') as z:a={k:z[k] for k in z.files if k!='metadata_json'}
with np.load(ROOT/'board_evidence/surface_result.npz') as z:b={k:z[k] for k in z.files}
meta=json.loads(b.pop('metadata_json').tobytes())
assert meta['source_sha256']==hashlib.sha256((ROOT/'board_evidence/full_pipeline_result.npz').read_bytes()).hexdigest()
y,x=np.indices((480,640));checks={}
for name,limit in (('optimized',4),('detail',4),('repaired',6)):
    xyz=b[name+'_xyz_mm'];valid=b[name+'_valid'];d=b[name+'_disparity_px'];faces=b[name+'_faces']
    assert not np.any(valid&~b['preview_valid'])
    assert np.isfinite(xyz[valid]).all() and np.all(xyz[:,:,2][valid]>0)
    hom=np.column_stack((x[valid],y[valid],d[valid],np.ones(int(valid.sum()))))@a['Q'].T
    ideal=hom[:,:3]/hom[:,3,None]
    eps=np.spacing(abs(xyz[valid])).astype(np.float64)/2+1e-7
    assert np.all(abs(xyz[valid].astype(np.float64)-ideal)<=eps),name+' projection mismatch'
    assert faces.ndim==2 and faces.shape[1]==3 and faces.min()>=0 and faces.max()<valid.size
    assert valid.ravel()[faces].all()
    v=xyz.reshape(-1,3)[faces].astype(np.float64);other=v[:,[2,0,1]];z=v[:,:,2]
    assert np.all(np.ptp(z,axis=1)<=np.maximum(5.,.02*z.min(axis=1))+1e-6)
    ray=v/v[:,:,2:3];other_ray=other/other[:,:,2:3]
    footprint=np.linalg.norm(ray-other_ray,axis=2)*(v[:,:,2]+other[:,:,2])/2
    stretch=np.linalg.norm(v-other,axis=2)/np.maximum(footprint,1e-9)
    assert stretch.max()<=limit+1e-3,(name,stretch.max())
    checks[name]={'points':int(valid.sum()),'triangles':len(faces),'max_stretch':float(stretch.max())}
valid=b['optimized_valid'];delta=abs(b['optimized_disparity_px']-a['completed_disparity_q4']/16)
assert np.all(delta[valid]<=.75001)
v=b['detail_valid']&~b['detail_supported'];assert np.array_equal(b['detail_xyz_mm'][v],b['optimized_xyz_mm'][v])
v=b['detail_valid'];assert np.array_equal(b['repaired_xyz_mm'][v],b['detail_xyz_mm'][v])
restored=b['restored_inferred'];assert np.all(b['repaired_origin'][restored]==5)
assert not np.any(restored&(a['completion_origin']==0))
# Analytic slanted-disparity plane must be retained away from the padded edge.
sy,sx=np.indices((24,32));plane=(25+.03*sx+.02*sy).astype(np.float32)
filtered=plane_filter(plane,np.ones(plane.shape,bool),np.ones(plane.shape,np.float32),np.full(plane.shape+(3,),128,np.float32),SurfaceConfig())
plane_error=float(abs(filtered[3:-3,3:-3]-plane[3:-3,3:-3]).max());assert plane_error<1e-5
report={'passed':True,'source_sha256':hashlib.sha256((ROOT/'board_evidence/surface_result.npz').read_bytes()).hexdigest(),
        'layers':checks,'analytic_slanted_plane_max_error_px':plane_error,'original_layers_preserved':True,
        'performance_pending':True,'detail_topology_fallback_on_this_scene':meta['detail']['topology_fallback_all'],
        'scope':'Returned display-layer projection/connectivity/provenance; full live UI and scene-quality acceptance remain pending.'}
(ROOT/'board_evidence/surface_pc_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
