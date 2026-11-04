"""Prepare a fixed-photo oracle package before exercising the new hardware."""
from evaluate_reference import *
source=SOURCE/'stereo_captures/capture_20261016_150221_0df816aa/board_result.npz'
with np.load(source) as z:frame=z['frame_bgr']
engine=StereoEngine(SOURCE/'stereo_parameters.json');out={'frame_bgr':frame};grays=[]
def integer_remap(raw,fixed,frac):
    h,w=raw.shape[:2];x=fixed[:,:,0].astype(int);y=fixed[:,:,1].astype(int)
    fx=(frac&31).astype(np.uint32);fy=(frac>>5).astype(np.uint32);result=np.zeros(raw.shape,np.uint32)
    for dy in (0,1):
        for dx in (0,1):
            xx=x+dx;yy=y+dy;valid=(xx>=0)&(xx<w)&(yy>=0)&(yy<h)
            p=raw[yy.clip(0,h-1),xx.clip(0,w-1)].astype(np.uint32)*valid[:,:,None]
            weight=(fx if dx else 32-fx)*(fy if dy else 32-fy)
            result+=p*weight[:,:,None]
    return ((result+512)>>10).astype(np.uint8)
for eye in (0,1):
    fixed,frac=cv2.convertMaps(*engine.maps[eye+1],cv2.CV_16SC2)
    maps=fixed[:,:,0].astype(np.uint16).astype(np.uint64)|(fixed[:,:,1].astype(np.uint16).astype(np.uint64)<<16)|(frac.astype(np.uint64)<<32)|(engine.support[eye+1].astype(np.uint64)<<42)
    raw=frame[:,eye*640:(eye+1)*640];rect=integer_remap(raw,fixed,frac);g=gray_u8(rect);grays.append(g)
    out['maps%d'%eye]=maps;out['rect%d'%eye]=rect
    out['features%d'%eye]=features(g).astype(np.uint64)|(engine.support[eye+1].astype(np.uint64)<<32)
    print('remap_%d_opencv_different_channels'%eye,int(np.count_nonzero(rect!=cv2.remap(raw,*engine.maps[eye+1],cv2.INTER_LINEAR))),flush=True)
l,r=grays;ls,rs=engine.support[1],engine.support[2]
q,s,m=match(l,r,ls,rs,80,480)
rq,rscore,rm=match(r[:,::-1].copy(),l[:,::-1].copy(),rs[:,::-1],ls[:,::-1],80,480)
rq,rscore,rm=[v[:,::-1].copy() for v in (rq,rscore,rm)]
valid=validity(q,s,m,rq,rscore,rm,ls,rs)
out.update(q=q,score=s,margin=m,rq=rq,rscore=rscore,rmargin=rm,valid=valid,Q=engine.p['Q'])
np.savez_compressed(HERE/'hardware_case.npz',**out)
print('HARDWARE_REFERENCE_READY',hashlib.sha256((HERE/'hardware_case.npz').read_bytes()).hexdigest(),int(valid.sum()))
