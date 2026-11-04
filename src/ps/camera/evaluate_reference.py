"""Offline same-photo quality study of the new PL arithmetic; no board operations."""
import ctypes, hashlib, json, sys, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]/'experiments/usb_camera_20261016'
sys.path[:0]=[str(SOURCE/'deps'),str(SOURCE),str(SOURCE/'pl_match_v1')]
import cv2
import numpy as np
from usb_stereo_engine import StereoEngine
from pl_reference import gray_u8,POP

def features(gray):
    """Original independent Census formula, sized from this photograph."""
    h,w=gray.shape
    pad=cv2.copyMakeBorder(gray,2,2,2,2,cv2.BORDER_REPLICATE)
    f=np.zeros(gray.shape,np.uint32);bit=0
    for dy in range(5):
        for dx in range(5):
            if (dy,dx)==(2,2):continue
            f|=(pad[dy:dy+h,dx:dx+w]<gray).astype(np.uint32)<<bit
            bit+=1
    return f|(gray.astype(np.uint32)<<24)
lib=ctypes.CDLL(str(HERE/'reference_sgm.dll'))
u16=np.ctypeslib.ndpointer(dtype=np.uint16,flags='C_CONTIGUOUS')
i16=np.ctypeslib.ndpointer(dtype=np.int16,flags='C_CONTIGUOUS')
lib.reference_sgm.argtypes=[u16,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,i16,u16,u16]

def match(l,r,ls,rs,p1,p2):
    h,w=l.shape;c=np.full((h,w,128),65535,np.uint16)
    lf,rf=features(l),features(r)
    for d in range(128):
        xor=(lf[:,d:]^rf[:,:w-d])&0xffffff
        ham=POP[xor&255]+POP[(xor>>8)&255]+POP[(xor>>16)&255]
        value=2*ham.astype(np.uint16)+np.minimum(abs(l[:,d:].astype(np.int16)-r[:,:w-d].astype(np.int16))//4,31)
        agg=cv2.boxFilter(value.astype(np.float32),-1,(3,3),normalize=False,borderType=cv2.BORDER_CONSTANT)
        out=c[3:h-3,d+3:w-3,d]
        out[:]=agg[3:h-3,3:w-d-3].astype(np.uint16)
        out[~(ls[3:h-3,d+3:w-3]&rs[3:h-3,3:w-d-3])]=65535
    q=np.empty((h,w),np.int16);s=np.empty((h,w),np.uint16);m=np.empty_like(s)
    assert lib.reference_sgm(c,w,h,p1,p2,q,s,m)==0
    return q,s,m

def validity(q,s,m,rq,rs,rm,ls,rights,minimum=24,ratio=.03):
    h,w=q.shape;y,x=np.indices((h,w));xr0=np.rint(x-q/16).astype(int);xr=xr0.clip(0,w-1)
    conf=(m>=np.maximum(minimum,s.astype(float)*ratio))
    rc=rm>=np.maximum(minimum,rs.astype(float)*ratio)
    valid=(q>=16)&(q<127*16)&(xr0>=3)&(xr0<w-3)&ls&rights[y,xr]&conf&rc[y,xr]
    valid &= (rq[y,xr]>=16)&(abs(q.astype(int)-rq[y,xr])<=16)
    return valid

if __name__=='__main__':
    source=Path(sys.argv[1]) if len(sys.argv)>1 else SOURCE/'stereo_captures/capture_20261016_150221_0df816aa/board_result.npz'
    with np.load(source) as z:a={k:z[k] for k in z.files}
    engine=StereoEngine(SOURCE/'stereo_parameters.json')
    l,r=gray_u8(a['rectified_left']),gray_u8(a['rectified_right']);ls,rs=engine.support[1],engine.support[2]
    results=[]
    for p1,p2 in ((80,480),(160,720)):
        start=time.perf_counter();q,s,m=match(l,r,ls,rs,p1,p2)
        rq,rscore,rm=match(r[:,::-1].copy(),l[:,::-1].copy(),rs[:,::-1],ls[:,::-1],p1,p2)
        rq,rscore,rm=[v[:,::-1].copy() for v in (rq,rscore,rm)]
        valid=validity(q,s,m,rq,rscore,rm,ls,rs);base=a['valid'].astype(bool);shared=valid&base
        record={'p1':p1,'p2':p2,'reference_cpu_seconds':time.perf_counter()-start,
                'valid_pixels':int(valid.sum()),'valid_fraction':float(valid.mean()),
                'baseline_pixels':int(base.sum()),'shared_pixels':int(shared.sum()),
                'new_pixels':int((valid&~base).sum()),'lost_pixels':int((base&~valid).sum()),
                'baseline_overlap_agreement_1px':float(np.mean(abs(q[shared].astype(int)-a['disparity_q4'][shared])<=16)),
                'note':'Offline algorithm reference, not PL timing or ground-truth accuracy'}
        np.savez_compressed(HERE/('reference_%d_%d.npz'%(p1,p2)),q=q,score=s,margin=m,rq=rq,rscore=rscore,rmargin=rm,valid=valid)
        results.append(record);print(json.dumps(record),flush=True)
    (HERE/'reference_quality.json').write_text(json.dumps({'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'profiles':results},indent=2),'utf8')
