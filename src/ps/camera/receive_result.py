"""Receive board data without recomputing stereo, completion or projection."""
import time
from live_verify import unpack,np

def receive(data,status,job,progress):
    started=time.monotonic();progress('receive_integrity')
    # Identity, hash, bounded archive members, array shapes/types and calibration.
    a,m,digest=unpack(data,status,job)
    if not m['surface_preparation'].get('comparison_surfaces_removed'):
        raise ValueError('Unexpected surface pipeline')
    # Basic renderability checks only, not independent numerical validation.
    for key in ('dense_disparity_px','dense_depth_mm'):
        if not np.isfinite(a[key]).all() or not (a[key]>0).all():
            raise ValueError('Invalid board display values: '+key)
    faces=a['dense3d_faces']
    if faces.size and (faces.min()<0 or faces.max()>=320*360):raise ValueError('Mesh index outside image')
    report={'integrity_passed':True,'algorithm_verified':False,'job_id':job,
            'source_sha256':digest,'seconds':time.monotonic()-started,
            'scope':'Identity/hash/schema and basic renderability only; no PC stereo, completion or XYZ recomputation.'}
    return a,m,{},report
