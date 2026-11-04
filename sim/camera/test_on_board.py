"""Finite fixed-photo DMA check; never opens a camera or triggers a shutter."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from board_dma import Arena,BASE,TAG
ROOT=Path(__file__).resolve().parent
with np.load(ROOT/'hardware_case.npz') as z:case={k:z[k] for k in z.files}
h,w=case['q'].shape;n=w*h;assert (w,h)==(640,480)
a=Arena(True);times={};result={}
def words(offset,count,dtype):return np.frombuffer(a.memory,dtype=dtype,count=count,offset=offset*16)
def call(core,params,label):
    rc,elapsed=a.command(core,params);assert rc==1,(label,rc);times[label]=elapsed;print(label,round(elapsed,5),flush=True)
def exact(label,got,expected):
    bad=np.count_nonzero(got!=expected);assert bad==0,(label,int(bad),got.shape)
    print(label+'_EXACT',got.size,flush=True)
try:
    # Guard space after all declared regions remains untouched.
    guard=26*n*16;pattern=bytes((i*17+33)%256 for i in range(4096));a.memory[guard:guard+4096]=pattern
    for eye in (0,1):
        raw=words(19*n+eye*n//4,n*4,np.uint8).reshape(h,w,4);raw[:,:,:3]=case['frame_bgr'][:,eye*w:(eye+1)*w];raw[:,:,3]=0
        words(19*n+n//2+eye*n//2,n,np.uint64)[:]=case['maps%d'%eye].ravel()
        params={0x18:BASE,0x20:1,0x28:w,0x30:h,0x38:eye,0x40:TAG}
        call('images',params,'rectify%d'%eye)
        got=words(20*n+n//2+eye*n//4,n*4,np.uint8).reshape(h,w,4)[:,:,:3].copy()
        exact('rect%d'%eye,got,case['rect%d'%eye]);result['rect%d'%eye]=got
        params[0x20]=2;call('images',params,'features%d'%eye)
        got=words(eye*n//2,n,np.uint64).reshape(h,w).copy();exact('features%d'%eye,got,case['features%d'%eye])
    for mirrored in (0,1):
        params={0x18:BASE,0x20:1,0x28:w,0x30:h,0x38:mirrored,0x40:80,0x48:480}
        call('sgm',params,'sgm_forward%d'%mirrored);params[0x20]=2;call('sgm',params,'sgm_backward%d'%mirrored)
        packed=words((18 if mirrored else 17)*n,n*8,np.uint16).reshape(h,w,8).copy()
        if mirrored:packed=packed[:,::-1].copy()
        names=('rq','rscore','rmargin') if mirrored else ('q','score','margin')
        arrays=(packed[:,:,0].copy().view(np.int16),packed[:,:,1],packed[:,:,2])
        for name,got in zip(names,arrays):exact(name,got,case[name]);result[name]=got.copy()
    input_words=words(21*n,n*4,np.uint32).reshape(h,w,4);input_words[:]=0
    input_words[:,:,0]=case['q'].astype(np.uint16).astype(np.uint32)|(case['valid'].astype(np.uint32)<<16)
    params={0x18:BASE+21*n*16,0x20:1,0x28:w,0x30:h,0x38:2,0x40:1000*4096,0x48:20*4096,0x50:0,0x58:TAG}
    call('geometry',params,'geometry_xyz_section')
    records=words(22*n,n*4,np.int32).reshape(h,w,4).copy();valid=(records[:,:,3]&1)!=0
    exact('geometry_valid',valid,case['valid'])
    yy,xx=np.indices((h,w));homogeneous=np.stack((xx,yy,case['q']/16,np.ones((h,w))),axis=-1)@case['Q'].T
    ideal=homogeneous[:,:,:3]/np.where(homogeneous[:,:,3:4]!=0,homogeneous[:,:,3:4],1)
    error=float(np.max(abs(records[:,:,:3][valid]/4096-ideal[valid])));assert error<.00025,error
    selected=valid&(abs(records[:,:,2].astype(np.int64)-1000*4096)<=20*4096)
    exact('section_mask',(records[:,:,3]&2)!=0,selected)
    stats=words(23*n,12,np.int32).reshape(3,4).copy();assert stats[0,0]==int(valid.sum()) and stats[0,1]==int(selected.sum())
    if selected.any():exact('section_min',stats[1,:3],records[:,:,:3][selected].min(axis=0));exact('section_max',stats[2,:3],records[:,:,:3][selected].max(axis=0))
    result.update(xyz_q12=records[:,:,:3],flags=records[:,:,3],valid=valid,Q=case['Q'])
    assert a.memory[guard:guard+4096]==pattern,'DMA exceeded declared regions'
    report={'passed':True,'full_native_eye_size':[w,h],'source_sha256':hashlib.sha256((ROOT/'hardware_case.npz').read_bytes()).hexdigest(),
            'times':times,'valid_pixels':int(valid.sum()),'geometry_max_error_mm':error,'section_pixels':int(selected.sum()),
            'rectified_rgb_and_features_exact':True,'all_disparity_score_margin_exact':True,'dma_guard_unchanged':True,
            'backend':'PL rectification/features + eight-path SGM + XYZ/section; CPU reference is validation only'}
    np.savez_compressed(ROOT/'hardware_result.npz',**result)
    (ROOT/'hardware_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
finally:
    # Destroy outstanding views before closing the mmap.
    for name in ('raw','input_words'):
        if name in globals():del globals()[name]
    a.close()
