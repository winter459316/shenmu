"""Moderate discontinuity limits: preserve points and short depth transitions."""
import time,platform
import numpy as np
def triangle_stretch(xyz,faces):
    if platform.machine()=='aarch64':
        from surface_mesh_native import triangle_stretch_native
        return triangle_stretch_native(xyz,faces)
    corners=xyz.reshape(-1,3)[faces];other=np.roll(corners,1,axis=1)
    rays=corners/corners[...,2:3];other_rays=other/other[...,2:3]
    footprint=np.linalg.norm(rays-other_rays,axis=2)*(corners[...,2]+other[...,2])/2
    return np.max(np.linalg.norm(corners-other,axis=2)/np.maximum(footprint,1e-9),axis=1)
VERSION='moderate-mesh-boundaries-v1'
ABS_JUMP_MM=25.;REL_JUMP=.08;MAX_STRETCH=25.
def restrict(xyz_q12,faces,cancel=None):
    start=time.monotonic()
    if cancel and cancel():raise InterruptedError('Mesh limits cancelled')
    xyz=xyz_q12.astype(np.float32)/4096
    z=xyz[:,:,2].ravel()[faces]
    depth_ok=np.ptp(z,axis=1)<=np.maximum(ABS_JUMP_MM,REL_JUMP*z.min(axis=1))
    keep=depth_ok.copy()
    if keep.any():
        stretch=triangle_stretch(xyz,faces[depth_ok])
        keep[depth_ok]=np.isfinite(stretch)&(stretch<=MAX_STRETCH)
    if cancel and cancel():raise InterruptedError('Mesh limits cancelled')
    result=faces[keep].copy()
    return result,{'version':VERSION,'engine':'A53 mesh-only discontinuity filter',
        'seconds':time.monotonic()-start,'input_triangles':len(faces),'triangles':len(result),
        'removed_triangles':int((~keep).sum()),'depth_rejected':int((~depth_ok).sum()),
        'additional_stretch_rejected':int((depth_ok&~keep).sum()),'absolute_jump_mm':ABS_JUMP_MM,
        'relative_jump':REL_JUMP,'max_stretch':MAX_STRETCH,'points_unchanged':True,
        'scope':'Only long/discontinuous triangle connections removed; short bridges remain; no object segmentation.'}
