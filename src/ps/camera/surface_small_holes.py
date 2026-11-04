"""Boundary-supported sealing of small enclosed display-mesh gaps.

Raw PL coordinates and all previous display layers are inputs only. This adds
a derived surface: ring-gated inverse-depth interpolation, not measurements.
"""
from dataclasses import dataclass,asdict
import time
import numpy as np
import cv2 as cv
from surface_holes import adaptive_faces,HoleConfig
from surface_projection import reproject,check_cancel

@dataclass(frozen=True)
class SealConfig:
    max_gap_cells:int=256
    max_gap_span:int=32
    ring_residual_p90_px:float=.35
    max_existing_change_px:float=2.
    max_completion_change_px:float=2.
    max_boundary_relative_depth_range:float=.12
    convergence_px:float=.0005
    max_iterations:int=600
    narrow_crack_kernel:int=1

def cell_counts(faces,shape):
    h,w=shape
    cell=np.stack((faces//w,faces%w),-1).min(axis=1)
    return np.bincount(cell[:,0]*(w-1)+cell[:,1],minlength=(h-1)*(w-1)).reshape(h-1,w-1)

def seal_small_holes(disparity,valid,xyz,faces,origin,preview,completed_q4,q,config=SealConfig(),cancel=None):
    start=time.monotonic();h,w=valid.shape
    d=disparity.copy();out_valid=valid.copy();out_xyz=xyz.copy();out_origin=origin.copy()
    counts=cell_counts(faces,valid.shape);gaps=counts<2
    n,labels,stats,_=cv.connectedComponentsWithStats(gaps.astype(np.uint8),8)
    chosen=np.zeros(gaps.shape,bool);candidates=0
    for i in range(1,n):
        x,y,ww,hh,area=stats[i]
        if x==0 or y==0 or x+ww==w-1 or y+hh==h-1:continue
        if area>config.max_gap_cells or max(ww,hh)>config.max_gap_span:continue
        # Components cannot extend beyond their own bounding box. Restrict the
        # label comparison to it instead of rescanning a full image per hole.
        chosen[y:y+hh,x:x+ww]|=labels[y:y+hh,x:x+ww]==i;candidates+=1
    if config.narrow_crack_kernel>1:
        kernel=np.ones((config.narrow_crack_kernel,config.narrow_crack_kernel),np.uint8)
        closed=cv.morphologyEx((counts==2).astype(np.uint8),cv.MORPH_CLOSE,kernel)
        full=valid[:-1,:-1]&valid[:-1,1:]&valid[1:,:-1]&valid[1:,1:]
        chosen|=(closed!=0)&gaps&full
    # Include one vertex halo so single-triangle cracks have interior samples.
    patch=np.zeros(valid.shape,np.uint8)
    for dy,dx in ((0,0),(0,1),(1,0),(1,1)):
        patch[dy:dy+h-1,dx:dx+w-1]|=chosen.astype(np.uint8)
    patch=cv.dilate(patch,np.ones((3,3),np.uint8),iterations=1)
    n,labels,stats,_=cv.connectedComponentsWithStats(patch,8)
    adjusted=np.zeros(valid.shape,bool);restored=np.zeros(valid.shape,bool);supported_patch=np.zeros(valid.shape,bool)
    accepted=0;reasons={};max_residual=0.;iterations=0
    def reject(why):reasons[why]=reasons.get(why,0)+1
    for i in range(1,n):
        check_cancel(cancel)
        x,y,ww,hh,area=stats[i]
        if x<1 or y<1 or x+ww>=w or y+hh>=h or area>2048:
            reject('boundary_or_merged_size');continue
        sl=(slice(y-1,y+hh+1),slice(x-1,x+ww+1))
        inside=labels[sl]==i
        ring=(cv.dilate(inside.astype(np.uint8),np.ones((3,3),np.uint8))!=0)&~inside
        mask=valid[sl];support=ring&mask
        if np.count_nonzero(support)!=np.count_nonzero(ring) or support.sum()<12 or not preview[sl][inside].all():
            reject('unsupported_ring_or_outside_domain');continue
        yy,xx=np.indices(inside.shape);xx=xx-(ww+1)/2;yy=yy-(hh+1)/2
        design=np.column_stack((np.ones(int(support.sum())),xx[support],yy[support]))
        values=disparity[sl][support].astype(np.float64)
        params,_,rank,_=np.linalg.lstsq(design,values,rcond=None)
        residual=float(np.percentile(abs(design@params-values),90))
        z=xyz[sl][support,2]
        if rank<3 or residual>config.ring_residual_p90_px:
            reject('ring_not_locally_smooth');continue
        if np.ptp(z)>max(20.,config.max_boundary_relative_depth_range*float(np.median(z))):
            reject('ring_depth_discontinuity');continue
        # Dirichlet ring is fixed. Discrete harmonic interpolation preserves
        # an affine inverse-depth plane and does not extrapolate off the ring.
        work=(params[0]+params[1]*xx+params[2]*yy).astype(np.float64)
        work[ring]=values
        center=inside[1:-1,1:-1]
        for iteration in range(config.max_iterations):
            if iteration%32==0:check_cancel(cancel)
            average=(work[:-2,1:-1]+work[2:,1:-1]+work[1:-1,:-2]+work[1:-1,2:])*.25
            target=work[1:-1,1:-1]
            delta=float(abs(target[center]-average[center]).max())
            target[center]=average[center]
            if delta<=config.convergence_px:break
        else:reject('not_converged');continue
        estimate=work[inside]
        old=disparity[sl][inside];was_valid=mask[inside]
        reference=completed_q4[sl][inside].astype(np.float64)/16
        if np.any((estimate<1)|(estimate>127)):
            reject('invalid_disparity');continue
        if np.any(abs(estimate[was_valid]-old[was_valid])>config.max_existing_change_px):
            reject('existing_depth_change');continue
        if np.any(abs(estimate[~was_valid]-reference[~was_valid])>config.max_completion_change_px):
            reject('completion_disagreement');continue
        d[sl][inside]=estimate.astype(np.float32);out_valid[sl][inside]=True
        adjusted[sl][inside&mask]=True;restored[sl][inside&~mask]=True
        out_origin[sl][inside]=5;accepted+=1;iterations+=iteration+1;max_residual=max(max_residual,residual)
        supported_patch[sl]|=inside|ring
    changed=adjusted|restored
    projected,_,projected_valid=reproject(d,out_valid,q)
    if not np.array_equal(out_valid,projected_valid):raise ValueError('Sealing introduced invalid depth')
    out_xyz[changed]=projected[changed]
    new_faces,_=adaptive_faces(out_xyz,out_valid,HoleConfig())
    # Existing triangles outside patches survive exactly; unchanged coordinates
    # are copied rather than reprojected to avoid perturbing the baseline.
    assert np.array_equal(out_xyz[valid&~changed],xyz[valid&~changed])
    new_counts=cell_counts(new_faces,valid.shape)
    report={'version':'boundary-seal-v1','parameters':asdict(config),'seconds':time.monotonic()-start,
            'candidate_gap_components':candidates,'merged_patches':n-1,'accepted_patches':accepted,'rejections':reasons,
            'adjusted_existing_display_points':int(adjusted.sum()),'restored_display_points':int(restored.sum()),
            'before_triangles':len(faces),'after_triangles':len(new_faces),'added_triangles':len(new_faces)-len(faces),
            'ring_residual_p90_max_px':max_residual,'solver_iterations_total':iterations,
            'unchanged_outside_patches':True,'new_measurements':False,
            'provenance_5':'A53 ring-supported harmonic display estimate; raw PL geometry unchanged',
            'missing_cells_before':int((counts<2).sum()),'missing_cells_after':int((new_counts<2).sum())}
    return {'xyz_mm':out_xyz,'disparity_px':d,'valid':out_valid,'grid_faces':new_faces,'provenance':out_origin,
            'adjusted_existing':adjusted,'restored_inferred':restored,'supported_patch':supported_patch,'report':report}
