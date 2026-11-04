"""PL geometry and immutable held-photo sections in the reserved Linux arena."""
import math,time
import numpy as np
from board_dma import BASE,TAG
W,H=320,360;N=W*H
def view(a,word,count,dtype):return np.frombuffer(a.memory,dtype=dtype,count=count,offset=word*16)
def _call(a,command,axis=3,center=0,half=0,include=False):
    rc,seconds=a.command('geometry',{0x18:BASE+21*N*16,0x20:command,0x28:W,0x30:H,
                                     0x38:axis,0x40:center,0x48:half,0x50:int(include),0x58:TAG})
    if rc!=1:raise RuntimeError('PL geometry rejected arguments')
    records=view(a,22*N,N*4,np.int32).reshape(H,W,4).copy()
    stats=view(a,23*N,12,np.int32).reshape(3,4).copy()
    valid=(records[:,:,3]&1)!=0;selected=(records[:,:,3]&2)!=0
    origin=(records[:,:,3]>>8)&255
    assert stats[0,0]==int(valid.sum()) and stats[0,1]==int(selected.sum())
    assert stats[0,2]==int((selected&(origin!=3)).sum()) and stats[0,3]==N-int(valid.sum())
    if selected.any():
        assert np.array_equal(stats[1,:3],records[:,:,:3][selected].min(axis=0))
        assert np.array_equal(stats[2,:3],records[:,:,:3][selected].max(axis=0))
    return records,stats,seconds
def project(a,q,source):
    q=np.asarray(q);source=np.asarray(source)
    assert q.shape==source.shape==(H,W) and np.all((source>=0)&(source<=3))
    assert np.all((q[source>0]>=16)&(q[source>0]<=2032))
    target=view(a,21*N,N*4,np.uint32).reshape(H,W,4)
    target[:]=0;target[:,:,0]=q.astype(np.uint16).astype(np.uint32)|(source.astype(np.uint32)<<16)
    del target
    records,stats,seconds=_call(a,1)
    assert np.array_equal((records[:,:,3]&1)!=0,source>0)
    return records,seconds
def section(a,records,axis,center_mm,thickness_mm,include_inferred):
    assert records.shape==(H,W,4) and records.dtype==np.int32
    if axis not in (0,1,2) or not math.isfinite(center_mm) or not math.isfinite(thickness_mm):raise ValueError('Invalid section')
    center=int(round(center_mm*4096));half=int(round(thickness_mm*2048))
    if abs(center)>2147483647 or half<0 or half>2147483647:raise ValueError('Section out of Q12 range')
    view(a,22*N,N*4,np.int32)[:]=records.ravel()
    actual,stats,seconds=_call(a,2,axis,center,half,bool(include_inferred))
    assert np.array_equal(actual[:,:,:3],records[:,:,:3]),'Section altered held coordinates'
    valid=(records[:,:,3]&1)!=0;origin=(records[:,:,3]>>8)&255
    expected=valid&(abs(records[:,:,axis].astype(np.int64)-center)<=half)
    if not include_inferred:expected&=origin!=3
    selected=(actual[:,:,3]&2)!=0
    assert np.array_equal(selected,expected),'PL section mask mismatch'
    return {'indices':np.flatnonzero(selected).astype(np.uint32),
            'xyz_q12':actual[:,:,:3][selected].copy(),
            'source':origin[selected].astype(np.uint8),'stats':stats,
            'axis':axis,'center_q12':center,'half_width_q12':half,'board_seconds':seconds}
