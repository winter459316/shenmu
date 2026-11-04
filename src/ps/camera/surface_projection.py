"""Derived display projection on A53; authoritative raw XYZ comes from PL."""
import numpy as np
import cv2 as cv
def geometry_q(g):return g['Q_grid']
def reproject(disparity,valid,q):
    d=np.asarray(disparity,np.float64);q=np.asarray(q,np.float64)
    mask=np.asarray(valid,bool);y,x=np.indices(d.shape)
    # The calibrated rectified Q is sparse. Explicit expressions avoid BLAS
    # thread scheduling on a 307200-row, four-column matrix multiplication.
    v=[q[k,0]*x+q[k,1]*y+q[k,2]*d+q[k,3] for k in range(4)]
    mask=mask&np.isfinite(d)&np.isfinite(v[3])&(abs(v[3])>1e-12)
    xyz=np.full(d.shape+(3,),np.nan,np.float64)
    for k in range(3):xyz[:,:,k][mask]=v[k][mask]/v[3][mask]
    mask&=np.isfinite(xyz).all(axis=2)&(xyz[:,:,2]>0);xyz[~mask]=np.nan
    xyz=xyz.astype(np.float32);return xyz,xyz.copy(),mask
def check_cancel(cancel):
    if cancel and cancel():
        from board_completion import CompletionCancelled
        raise CompletionCancelled('Surface preparation cancelled')
