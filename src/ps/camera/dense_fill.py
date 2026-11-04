"""Reuse the existing verified PL/A53 completion; never run a second solver."""
import time
import cv2
import numpy as np
VERSION='reuse-pl-a53-completed-q4-v1'

def fill(a,cancel=None,progress=None):
    started=time.monotonic()
    if cancel and cancel():raise InterruptedError('Completion reuse cancelled')
    q=a['completed_disparity_q4'];seed=a['completion_origin']==0
    assert q.shape==(360,320) and np.all((q>=16)&(q<=2032)),'Existing completion must cover the complete frame'
    assert np.any(seed) and np.all(~seed|a['valid'])
    assert np.array_equal(q[seed],a['disparity_q4'][seed])
    d=q.astype(np.float32)/16
    distance=cv2.distanceTransform((~seed).astype(np.uint8),cv2.DIST_L2,5)
    origin=np.where(seed,0,np.where((distance<=12)&a['domain'],1,2)).astype(np.uint8)
    y,x=np.indices(q.shape);h=np.stack((x,y,d,np.ones(q.shape)),axis=-1)@a['Q'].T
    z=(h[:,:,2]/h[:,:,3]).astype(np.float32)
    assert np.isfinite(z).all() and (z>0).all()
    if cancel and cancel():raise InterruptedError('Completion reuse cancelled')
    return {'filled_disparity_px':d,'filled_depth_mm':z,'fill_origin':origin,'distance_to_measurement_px':distance}, {
        'version':VERSION,'engine':'Reuse existing PL CG + A53 completion; no second iterative solver',
        'seconds':time.monotonic()-started,'measured_pixels':int(seed.sum()),'inferred_pixels':int((~seed).sum()),
        'invalid_after':0,'near_inferred_pixels':int((origin==1).sum()),'far_or_border_inferred_pixels':int((origin==2).sum()),
        'iterations':0,'second_solver_removed':True,'completed_q4_exact':True,'measured_values_unchanged':True,
        'origin_labels':{'0':'accepted original match','1':'nearby fast-completion estimate','2':'far/border fast-completion estimate'},
        'physical_accuracy_verified':False,'scope':'Existing completed Q4 reused exactly for full-grid PL geometry; rejected candidates remain inferred.'}
