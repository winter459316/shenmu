"""Derived surface only: fit dominant planes within edge-bounded low-texture regions.

No coordinates, white-color threshold, object labels or calibration-specific plane.
Raw disparity, matched flags and original point cloud stay unchanged.
"""
import time
import cv2
import numpy as np

def improve(image,q4,origin,domain):
    started=time.monotonic();d=q4.astype(np.float32)/16
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    # Local range in every color channel protects both luminance and color edges.
    high=cv2.dilate(image,np.ones((5,5),np.uint8));low=cv2.erode(image,np.ones((5,5),np.uint8))
    texture=(high.astype(np.int16)-low).max(axis=2)
    flat=(texture<=22)&domain
    flat=cv2.morphologyEx(flat.astype(np.uint8),cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(flat,connectivity=8)
    out=d.copy();changed=np.zeros(d.shape,bool);region_map=np.zeros(d.shape,np.int32);reports=[]
    yy,xx=np.indices(d.shape);rng=np.random.RandomState(71)
    for label in range(1,count):
        area=int(stats[label,cv2.CC_STAT_AREA])
        if area<800:continue
        region=labels==label;seeds=region&(origin==0)
        sy,sx=np.where(seeds);n=len(sx)
        report={'label':label,'pixels':area,'seeds':n,'accepted':False}
        reports.append(report)
        if n<100 or n/area<.08:continue
        X=np.column_stack((sx/d.shape[1],sy/d.shape[0],np.ones(n)))
        v=d[seeds].astype(np.float64)
        sample=np.arange(n) if n<=1500 else rng.choice(n,1500,replace=False)
        A=X[sample];values=v[sample];best=None;best_score=-1
        for trial in range(64):
            ids=rng.choice(len(sample),3,replace=False)
            if abs(np.linalg.det(A[ids]))<.002:continue
            beta=np.linalg.solve(A[ids],values[ids]);residual=abs(A@beta-values)
            score=int((residual<=2).sum())
            if score>best_score:best_score=score;best=beta
        if best is None:continue
        for unused in range(3):
            inliers=abs(X@best-v)<=2
            if inliers.sum()<100:break
            best=np.linalg.lstsq(X[inliers],v[inliers],rcond=None)[0]
        inliers=abs(X@best-v)<=2;ratio=float(inliers.mean())
        report.update(inlier_fraction=ratio,plane=best.tolist())
        # A majority must agree in depth and cover a substantial region footprint.
        if ratio<.65:continue
        inlier_mask=np.zeros(d.shape,np.uint8);inlier_mask[sy[inliers],sx[inliers]]=1
        seed_span=np.ptp(sx[inliers])*np.ptp(sy[inliers])
        box=stats[label];box_area=int(box[cv2.CC_STAT_WIDTH])*int(box[cv2.CC_STAT_HEIGHT])
        if seed_span<box_area*.35:continue
        predicted=best[0]*xx/d.shape[1]+best[1]*yy/d.shape[0]+best[2]
        if np.any((predicted[region]<1)|(predicted[region]>127)):continue
        # Project supported low-texture interiors onto their dominant plane.
        # A residual cutoff leaves measured noise as small bumps in lit meshes.
        # Keep the boundary band untouched; all changed points remain inferred.
        interior=cv2.erode(region.astype(np.uint8),np.ones((5,5),np.uint8),borderType=cv2.BORDER_CONSTANT)!=0
        replace=interior&(np.rint(predicted*16)!=q4)
        out[replace]=predicted[replace];changed|=replace;region_map[region]=label
        report.update(accepted=True,changed=int(replace.sum()))
    result=np.clip(np.rint(out*16),16,2032).astype(np.int16)
    return result,changed,region_map,{'seconds':time.monotonic()-started,'regions':reports,
        'changed_pixels':int(changed.sum()),'empty_pixels':int((result<16).sum()),
        'scope':'derived display geometry; inferred plane corrections, not measurements'}
