"""Project the full-fill Q4 grid with PL; A53 makes a complete display mesh."""
import time
import cv2
import numpy as np
from board_dma import Arena
from board_geometry import project
from mesh_limits import restrict
def generate(a,cancel=None):
    began=time.monotonic()
    if cancel and cancel():raise InterruptedError('Dense geometry cancelled')
    q=np.clip(np.rint(a['dense_disparity_px']*16),16,2032).astype(np.int16)
    source=np.where((a['dense_origin']==0),a['match_source'],3).astype(np.uint8)
    arena=Arena(True)
    try:records,seconds=project(arena,q,source)
    finally:arena.close()
    if cancel and cancel():raise InterruptedError('Dense geometry cancelled')
    xyz=records[:,:,:3].copy();assert ((records[:,:,3]&1)!=0).all()
    grid=np.arange(360*320,dtype=np.int32).reshape(360,320)
    tl,tr,bl,br=[v.ravel() for v in (grid[:-1,:-1],grid[:-1,1:],grid[1:,:-1],grid[1:,1:])]
    z=xyz[:,:,2].ravel().astype(np.int64)
    alternate=np.abs(z[tl]-z[br])<np.abs(z[tr]-z[bl])
    faces=np.stack((np.stack((tl,bl,tr),1),np.stack((tr,bl,br),1)),1)
    faces[alternate]=np.stack((np.stack((tl,bl,br),1),np.stack((tl,br,tr),1)),1)[alternate]
    faces=faces.reshape(-1,3).astype(np.int32)
    faces,mesh_report=restrict(xyz,faces,cancel)
    texture=a['rectified_left'].copy();support=a['domain']
    if not support.all():
        _,labels=cv2.distanceTransformWithLabels((~support).astype(np.uint8),cv2.DIST_L2,5,labelType=cv2.DIST_LABEL_PIXEL)
        lookup=np.zeros((int(labels.max())+1,3),np.uint8);lookup[labels[support]]=texture[support]
        texture[~support]=lookup[labels[~support]]
    arrays={'dense3d_q4':q,'dense3d_xyz_q12':xyz,'dense3d_flags':records[:,:,3].copy(),
            'dense3d_faces':faces,'dense3d_texture':texture}
    report={'engine':'PL Q4-to-Q12 projection; A53 complete image-grid mesh','points':int(q.size),
            'triangles':len(faces),'empty_grid_cells':0,'pl_projection_seconds':seconds,'seconds':time.monotonic()-began,
            'quantization_max_disparity_error_px':float(np.max(abs(q/16-a['dense_disparity_px']))),
            'inferred_points':int((a['dense_origin']!=0).sum()),'depth_jump_culling':True,'stretch_culling':True,
            'mesh_limits':mesh_report,
            'original_geometry_preserved':True,'physical_accuracy_verified':False}
    return arrays,report
