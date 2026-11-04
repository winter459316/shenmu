"""Preserved four display layers prepared on A53, with original PL XYZ intact."""
import hashlib,time,os
import numpy as np
from surface_cleanup import refine_surface,limit_triangle_stretch
from surface_detail import retain_surface_detail,DetailConfig
from surface_holes import repair_surface
from surface_projection import check_cancel

def make_faces(xyz,valid,absolute_jump_mm=5.,relative_jump=.02):
    h,w=valid.shape;grid=np.arange(h*w,dtype=np.int32).reshape(h,w)
    a,b,c,d=grid[:-1,:-1],grid[:-1,1:],grid[1:,:-1],grid[1:,1:]
    faces=np.concatenate((np.stack((a,c,b),-1).reshape(-1,3),np.stack((b,c,d),-1).reshape(-1,3)))
    faces=faces[valid.ravel()[faces].all(axis=1)]
    if not len(faces):return faces
    v=xyz.reshape(-1,3)[faces];z=v[:,:,2]
    area=np.linalg.norm(np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]),axis=1)
    return faces[(np.ptp(z,axis=1)<=np.maximum(absolute_jump_mm,relative_jump*z.min(axis=1)))&(area>1e-8)]

def prepare(arrays,progress=None,cancel=None,near_m=.15,far_m=2.):
    if not 0<near_m<far_m:raise ValueError('Invalid preview depth range')
    keys=('raw_xyz_q12','completed_xyz_q12','disparity_q4','completed_disparity_q4','completion_origin')
    original_hash={k:hashlib.sha256(arrays[k].tobytes()).hexdigest() for k in keys}
    start=time.monotonic();times={}
    def stage(name):
        check_cancel(cancel)
        if progress:progress(name,{})
    stage('surface_original')
    xyz=arrays['completed_xyz_q12'].astype(np.float32)/4096
    good=(arrays['completed_geometry_flags']&1)!=0
    xyz[~good]=np.nan
    preview=good&(xyz[:,:,2]>=near_m*1000)&(xyz[:,:,2]<=far_m*1000)
    if not preview.any():raise ValueError('No points in preview depth range')
    origin=arrays['completion_origin'];measured=(origin==0)&good
    rgb=arrays['rectified_left'][:,:,::-1].copy()
    faces=make_faces(xyz,preview)
    out={'preview_valid':preview,'original_faces':faces}
    stage('surface_smoothing');t=time.monotonic()
    optimized=refine_surface(arrays['completed_disparity_q4'].astype(np.float32)/16,xyz,preview,measured,rgb,arrays['Q'],cancel=cancel)
    optimized['grid_faces']=limit_triangle_stretch(optimized['xyz_mm'],make_faces(optimized['xyz_mm'],optimized['valid']))
    times['optimized']=time.monotonic()-t
    stage('surface_detail');t=time.monotonic()
    supported=measured&arrays['detail_valid']&arrays['surface_valid']
    detail=retain_surface_detail(arrays['detail_q4'],arrays['surface_q4'],supported,optimized,rgb,arrays['Q'],config=DetailConfig(),cancel=cancel)
    detail['grid_faces']=optimized['grid_faces'].copy()
    times['detail']=time.monotonic()-t
    geometry={'provenance':origin,'measured_valid':measured,'completed_q4':arrays['completed_disparity_q4'],
              'preview_valid':preview,'Q_grid':arrays['Q'],'max_disparity_px':127}
    stage('surface_holes');t=time.monotonic()
    repaired=repair_surface(geometry,detail,cancel=cancel)
    times['repaired']=time.monotonic()-t
    for prefix,layer in (('optimized',optimized),('detail',detail),('repaired',repaired)):
        out[prefix+'_xyz_mm']=layer['xyz_mm'];out[prefix+'_valid']=layer['valid'];out[prefix+'_faces']=layer['grid_faces']
        out[prefix+'_disparity_px']=layer['disparity_px']
        assert not np.any(layer['valid']&~preview),prefix+' outside preview'
        assert layer['valid'].ravel()[layer['grid_faces']].all(),prefix+' face includes invalid point'
    out['detail_supported']=detail['detail_supported'];out['repaired_origin']=repaired['provenance']
    out['restored_inferred']=repaired['restored_inferred']
    for k in keys:assert original_hash[k]==hashlib.sha256(arrays[k].tobytes()).hexdigest(),'Display preparation changed '+k
    assert np.array_equal(repaired['xyz_mm'][detail['valid']],detail['xyz_mm'][detail['valid']])
    assert np.array_equal(detail['xyz_mm'][detail['valid']&~detail['detail_supported']],optimized['xyz_mm'][detail['valid']&~detail['detail_supported']])
    report={'engine':'ZU4EV A53 display preparation','seconds':time.monotonic()-start,'stage_seconds':times,
            'plane_backend':'A53 native three workers, original FP32 weights / ordered FP64 fit' if os.environ.get('USB_SURFACE_NATIVE','0')=='1' else 'A53 NumPy reference',
            'mesh_backend':'A53 native three workers, ordered FP32' if os.environ.get('USB_MESH_NATIVE','0')=='1' else 'A53 NumPy reference',
            'holes_backend':'A53 three spawned workers for >=256 candidates, original NumPy fits' if os.environ.get('USB_HOLES_PARALLEL','0')=='1' else 'A53 serial NumPy fits',
            'preview_depth_range_m':[near_m,far_m],'preview_points':int(preview.sum()),'original_triangles':len(faces),
            'outside_preview_range':int((good&~preview).sum()),'domain_excluded':int((~good).sum()),
            'optimized':optimized['report'],'detail':detail['report'],'repaired':repaired['report'],
            'original_pl_coordinates_unchanged':True,'new_measurements':False}
    stage('surface_ready');return out,report
