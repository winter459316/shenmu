"""Finite geometric checks for inferred display sealing; no camera/PL access."""
import hashlib,json,platform,time
import numpy as np
from surface_small_holes import seal_small_holes,SealConfig
from surface_holes import adaptive_faces,HoleConfig
from surface_projection import reproject
CONFIG=SealConfig(ring_residual_p90_px=.75)

def check_result(r,d,valid,xyz,origin,preview,q):
    changed=r['adjusted_existing']|r['restored_inferred']
    assert not np.any(r['valid']&~preview)
    assert np.array_equal(r['valid'],valid|r['restored_inferred'])
    assert np.array_equal(r['xyz_mm'][valid&~changed],xyz[valid&~changed])
    assert np.array_equal(r['provenance'],np.where(changed,5,origin))
    assert np.all(abs(r['disparity_px'][r['adjusted_existing']]-d[r['adjusted_existing']])<=CONFIG.max_existing_change_px+1e-5)
    y,x=np.indices(valid.shape);v=r['valid'];dd=r['disparity_px'][v]
    hom=np.column_stack((x[v],y[v],dd,np.ones(int(v.sum()))))@q.T
    ideal=hom[:,:3]/hom[:,3,None]
    assert np.max(abs(r['xyz_mm'][v].astype(float)-ideal))<.001
    # Exact regeneration enforces the original triangle discontinuity/stretch
    # rules; sealing never relaxes them globally or within a patch.
    faces,_=adaptive_faces(r['xyz_mm'],r['valid'],HoleConfig())
    assert np.array_equal(faces,r['grid_faces'])

def geometric_tests():
    n=40;y,x=np.indices((n,n));q=np.array([[1,0,0,-20],[0,1,0,-20],[0,0,0,350],[0,0,1/60,0]],float)
    report={}
    for name,truth in [('plane',35+.02*x+.03*y),('curved',35+.0006*(x-20)**2+.0004*(y-20)**2)]:
        d=truth.astype('float32');valid=np.ones((n,n),bool);valid[18:21,18:21]=False
        xyz,_,_=reproject(d,valid,q);f,_=adaptive_faces(xyz,valid);origin=np.zeros(valid.shape,'uint8')
        r=seal_small_holes(d,valid,xyz,f,origin,np.ones_like(valid),np.rint(truth*16).astype('int16'),q,CONFIG)
        check_result(r,d,valid,xyz,origin,np.ones_like(valid),q)
        error=float(abs(r['disparity_px'][~valid]-truth[~valid]).max())
        assert r['valid'].all() and error<.03,(name,error,r['report'])
        report[name]={'all_hole_points_restored':True,'max_disparity_error_px':error}
    # A coherent foreground island must not be flattened into its background.
    d=(35+.02*x+.03*y).astype('float32');d[18:22,18:22]+=8
    valid=np.ones((n,n),bool);xyz,_,_=reproject(d,valid,q);f,_=adaptive_faces(xyz,valid);origin=np.zeros(valid.shape,'uint8')
    r=seal_small_holes(d,valid,xyz,f,origin,valid,np.rint(d*16).astype('int16'),q,CONFIG)
    assert not r['adjusted_existing'].any() and np.array_equal(r['xyz_mm'],xyz)
    report['foreground_island_preserved']=True
    # A missing strip touching the field boundary is not an enclosed hole.
    valid[:,:4]=False;xyz,_,_=reproject(d,valid,q);f,_=adaptive_faces(xyz,valid)
    r=seal_small_holes(d,valid,xyz,f,origin,np.ones_like(valid),np.rint(d*16).astype('int16'),q,CONFIG)
    assert not r['valid'][:,:4].any();report['open_boundary_preserved']=True
    return report
if __name__=='__main__':print(json.dumps({'passed':True,'geometric':geometric_tests(),'architecture':platform.machine()}))
