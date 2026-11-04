"""Independently verify exact reuse of the existing completion, without another solver."""
import numpy as np
import cv2
from dense_fill import VERSION

def verify_dense(a,m):
    d=a['dense_disparity_px'];z=a['dense_depth_mm'];origin=a['dense_origin'];seed=a['completion_origin']==0
    report=m['dense_fill'];assert report['version']==VERSION and report['second_solver_removed'] and report['iterations']==0
    assert d.shape==(360,320) and np.isfinite(d).all() and (d>=1).all() and (d<=127).all()
    assert np.array_equal(d,a['completed_disparity_q4'].astype(np.float32)/16)
    assert np.array_equal(d[seed],a['disparity_q4'][seed]/16)
    distance=a['dense_distance_px'];expected_distance=cv2.distanceTransform((~seed).astype(np.uint8),cv2.DIST_L2,5)
    # OpenCV 3.4 ARM and OpenCV 5 x86 accumulate chamfer distances differently.
    # Bound this diagnostic-only distance error, and require exact label agreement.
    assert np.allclose(distance,expected_distance,rtol=0,atol=.001)
    assert np.array_equal(distance<=12,expected_distance<=12)
    assert np.array_equal(origin,np.where(seed,0,np.where((distance<=12)&a['domain'],1,2)))
    y,x=np.indices(d.shape);h=np.stack((x,y,d,np.ones(d.shape)),axis=-1)@a['Q'].T
    expected=(h[:,:,2]/h[:,:,3]).astype(np.float32)
    assert np.isfinite(z).all() and (z>0).all() and np.allclose(z,expected,rtol=1e-6,atol=.001)
    assert report['measured_pixels']==int(seed.sum()) and report['inferred_pixels']==int((~seed).sum())
    return {'passed':True,'all_115200_pixels_finite':True,'accepted_original_matches_exact':True,
            'completed_disparity_exact':True,'provenance_verified':True,'second_solver_removed':True,'new_measurements':False}
