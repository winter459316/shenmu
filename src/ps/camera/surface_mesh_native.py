"""Bounded, three-core FP32 mesh checking with the original operation order."""
import ctypes
from pathlib import Path
import numpy as np
_LIB=None
def triangle_stretch_native(xyz,faces):
    global _LIB
    if _LIB is None:
        _LIB=ctypes.CDLL(str(Path(__file__).parent/'libsurface_mesh.so'))
        _LIB.mesh_stretch.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*3
        _LIB.mesh_stretch.restype=ctypes.c_int
    xyz=np.ascontiguousarray(xyz,np.float32);faces=np.ascontiguousarray(faces,np.int32)
    if xyz.ndim!=3 or xyz.shape[2]!=3 or faces.ndim!=2 or faces.shape[1]!=3:raise ValueError('Invalid mesh shape')
    if xyz.shape[0]>480 or xyz.shape[1]>640:raise ValueError('Mesh exceeds native limit')
    result=np.empty(len(faces),np.float32)
    if len(faces):
        rc=_LIB.mesh_stretch(xyz.ctypes.data,faces.ctypes.data,result.ctypes.data,xyz.size//3,len(faces),3)
        if rc:raise ValueError('Native mesh failed: %d'%rc)
    return result
