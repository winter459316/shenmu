"""Three A53 workers for independent rows, preserving ordered per-pixel FP64 sums."""
import ctypes
from pathlib import Path
import numpy as np
from surface_projection import check_cancel
_LIB=None
def plane_filter_native(disparity,valid,confidence,rgb,config,cancel=None,threads=3):
    global _LIB
    if _LIB is None:
        _LIB=ctypes.CDLL(str(Path(__file__).parent/'libsurface_native.so'))
        _LIB.surface_plane_rows.argtypes=[ctypes.c_void_p]*6+[ctypes.c_int]*3+[ctypes.c_float]*3+[ctypes.c_int]*3
        _LIB.surface_plane_rows.restype=ctypes.c_int
    d=np.ascontiguousarray(disparity,np.float32);v=np.ascontiguousarray(valid,np.uint8)
    c=np.ascontiguousarray(confidence,np.float32);rgb=np.ascontiguousarray(rgb,np.float32)
    if d.ndim!=2 or v.shape!=d.shape or c.shape!=d.shape or rgb.shape!=d.shape+(3,):raise ValueError('Surface input shape mismatch')
    if not all(np.isfinite(a).all() for a in (d,c,rgb)):raise ValueError('Surface inputs must be finite')
    if not 1<=threads<=4:raise ValueError('Invalid worker count')
    h,w=d.shape;r=config.radius
    spatial=np.array([np.exp(-(dx*dx+dy*dy)/(2*config.spatial_sigma**2)) for dy in range(-r,r+1) for dx in range(-r,r+1)],np.float32)
    out=np.empty_like(d)
    for start in range(0,h,48):
        check_cancel(cancel)
        rc=_LIB.surface_plane_rows(d.ctypes.data,v.ctypes.data,c.ctypes.data,rgb.ctypes.data,spatial.ctypes.data,out.ctypes.data,
            w,h,r,2*config.disparity_sigma_px**2,2*config.color_sigma**2,3*config.disparity_sigma_px,start,min(start+48,h),threads)
        if rc:raise RuntimeError('Native surface row worker failed: %d'%rc)
    check_cancel(cancel);return out
