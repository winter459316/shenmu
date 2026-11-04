"""Display-only hole repair, with explicit inferred provenance and edge limits.

Keep every existing detail coordinate unchanged. Restore excluded completion
only when a robust local disparity plane has matched support, then choose the
safer diagonal of each grid cell. No extrapolation beyond the image domain.
"""
from dataclasses import dataclass, asdict
from surface_cleanup import np, triangle_stretch
from surface_projection import reproject, geometry_q, check_cancel


@dataclass(frozen=True)
class HoleConfig:
    support_radius: int = 32
    minimum_matches: int = 16
    candidate_agreement_px: float = 1.25
    minimum_consensus_fraction: float = .65
    plane_residual_p90_px: float = .25
    max_completion_change_px: float = .5
    max_triangle_stretch: float = 6.
    absolute_jump_mm: float = 5.
    relative_jump: float = .02


def adaptive_faces(xyz, valid, config=HoleConfig()):
    """At most two non-overlapping triangles/cell; do not bridge depth steps."""
    h,w=valid.shape;index=np.arange(h*w,dtype=np.int32).reshape(h,w)
    a,b,c,d=[x.ravel() for x in (index[:-1,:-1],index[:-1,1:],index[1:,:-1],index[1:,1:])]
    patterns=np.stack((np.stack((np.stack((a,c,b),-1),np.stack((b,c,d),-1)),1),
                       np.stack((np.stack((a,c,d),-1),np.stack((a,d,b),-1)),1)),1)
    flat=patterns.reshape(-1,3)
    good=valid.ravel()[flat].all(axis=1)
    z=xyz[...,2].ravel()[flat]
    good &= np.ptp(z,axis=1)<=np.maximum(config.absolute_jump_mm,config.relative_jump*z.min(axis=1))
    stretch=np.full(len(flat),np.inf,np.float32)
    stretch[good]=triangle_stretch(xyz,flat[good])
    good &= np.isfinite(stretch)&(stretch<=config.max_triangle_stretch)
    good=good.reshape(-1,2,2);stretch=stretch.reshape(-1,2,2)
    count=good.sum(axis=2)
    score=np.where(good,stretch,0).sum(axis=2)
    choice=((count[:,1]>count[:,0])|((count[:,1]==count[:,0])&(score[:,1]+1e-5<score[:,0]))).astype(int)
    rows=np.arange(len(patterns));selected=patterns[rows,choice];included=good[rows,choice]
    return selected[included],int(((choice==1)&(count[:,1]>0)).sum())


def repair_surface(geometry, detail, config=HoleConfig(), cancel=None):
    valid=detail['valid'].copy();xyz=detail['xyz_mm'].copy();d=detail['disparity_px'].copy()
    origin=geometry['provenance'].copy()
    seed=geometry['measured_valid']&valid
    original=geometry['completed_q4'].astype(np.float32)/16
    candidates=geometry['preview_valid']&~valid&~geometry['measured_valid']
    # Reject candidates discarded as isolated matches. They are not resurrected
    # simply because the user requests visually complete surfaces.
    restored=np.zeros(valid.shape,bool);radius=config.support_radius
    h,w=valid.shape
    maximum_disparity=float(geometry.get('max_disparity_px',127))
    for y,x in zip(*np.nonzero(candidates)):
        check_cancel(cancel)
        y0,y1=max(0,y-radius),min(h,y+radius+1);x0,x1=max(0,x-radius),min(w,x+radius+1)
        sy,sx=np.nonzero(seed[y0:y1,x0:x1]);values=d[y0+sy,x0+sx]
        if len(values)<config.minimum_matches:continue
        agree=np.abs(values-original[y,x])<=config.candidate_agreement_px
        if agree.sum()<config.minimum_matches or agree.mean()<config.minimum_consensus_fraction:continue
        dx=(sx[agree]+x0-x).astype(float);dy=(sy[agree]+y0-y).astype(float);values=values[agree]
        design=np.column_stack((np.ones(len(dx)),dx,dy))
        distance_weight=np.exp(-(dx*dx+dy*dy)/(2*(radius/2)**2))
        keep=np.ones(len(values),bool)
        for _ in range(3):
            if keep.sum()<config.minimum_matches:break
            if np.ptp(dx[keep])<6 or np.ptp(dy[keep])<6:break
            weighted=design[keep]*np.sqrt(distance_weight[keep,None])
            params,_,rank,_=np.linalg.lstsq(weighted,values[keep]*np.sqrt(distance_weight[keep]),rcond=None)
            if rank<3:break
            residual=np.abs(design@params-values)
            keep=residual<=max(.12,min(.5,2.5*float(np.median(residual))))
        else:
            if keep.sum()<config.minimum_matches or keep.mean()<config.minimum_consensus_fraction:continue
            if np.percentile(residual[keep],90)>config.plane_residual_p90_px:continue
            estimate=float(params[0])
            if not 1<=estimate<maximum_disparity or abs(estimate-original[y,x])>config.max_completion_change_px:continue
            d[y,x]=estimate;restored[y,x]=True
    valid|=restored
    projected,_,projected_valid=reproject(d,valid,geometry_q(geometry))
    if not np.array_equal(valid,projected_valid):raise ValueError('Hole repair introduced invalid depth')
    xyz[restored]=projected[restored];origin[restored]=5
    faces,alternative_cells=adaptive_faces(xyz,valid,config)
    report={'version':'surface-holes-v1','parameters':asdict(config),
            'input_points':int(detail['valid'].sum()),'input_triangles':len(detail['grid_faces']),
            'excluded_completion_candidates':int(candidates.sum()),'restored_inferred_points':int(restored.sum()),
            'output_points':int(valid.sum()),'output_triangles':len(faces),'alternative_diagonal_cells':alternative_cells,
            'existing_detail_coordinates_unchanged':True,'new_measurements':False,
            'provenance_5':'A53 local-plane display estimate; not a measured depth',
            'note':'Depth discontinuities, unsupported regions and unseen surfaces remain open.'}
    return {'xyz_mm':xyz,'valid':valid,'disparity_px':d,'provenance':origin,
            'restored_inferred':restored,'grid_faces':faces,'report':report}
