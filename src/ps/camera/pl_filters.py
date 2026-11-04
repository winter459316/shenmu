from preview_compat import preview_compatible
"""Qualified PL display filters; no software fallback labelled as hardware."""
from pathlib import Path
import ctypes,json,threading,time,sys
import numpy as np
GATE=threading.RLock()
ROOT=Path(__file__).resolve().parent
_instance=None;_suspended=False

def suspend(enabled):
    global _suspended
    with GATE:
        if _instance is not None and not _instance.lib.filters_idle():raise RuntimeError('PL display filter DMA did not drain')
        extra=sys.modules.get('pl_preview')
        if extra is not None:extra.suspend(enabled)
        _suspended=bool(enabled)

class Engine:
    def __init__(self):
        from board_dma import reservation
        reservation()
        self.proof=json.loads((ROOT/'filters_verified.json').read_text())
        assert self.proof['qualified'] and self.proof['control']==0xA1090000
        self.lib=ctypes.CDLL(str(ROOT/'filter_dma.so'))
        self.lib.filters_run.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p]
        self.lib.filters_run.restype=ctypes.c_int
        assert self.lib.filters_open()==0,'Cannot map reserved PL filter buffers'
        self.calls=0;self.by_mode={};self.total=np.zeros(3);self.last={}
    def run(self,frame,mode):
        loaded=json.loads((ROOT/'loaded.json').read_text())
        if _suspended or loaded.get('state')!='operating' or not preview_compatible(loaded.get('sha256'),self.proof['sha256']):raise RuntimeError('PL filters paused or bitstream mismatch')
        if (ROOT/'filter.dma.fault').exists():raise RuntimeError('PL filter fault requires verified reload')
        frame=np.ascontiguousarray(frame);h,w,c=frame.shape
        assert c==3 and frame.dtype==np.uint8
        out=np.empty((h,w),np.uint8);timing=np.zeros(3,np.float64);start=time.monotonic()
        result=self.lib.filters_run(frame.ctypes.data,out.ctypes.data,w,h,{'gray':1,'median':2,'sobel':3}[mode],timing.ctypes.data)
        if result:
            if result==-110:(ROOT/'filter.dma.fault').write_text('PL filter timeout; outstanding DMA must be drained before reconfiguration')
            raise RuntimeError('PL filter failed: '+str(result))
        self.calls+=1;self.by_mode[mode]=self.by_mode.get(mode,0)+1;self.total+=timing
        self.last=dict(mode=mode,width=w,height=h,copyin_ms=timing[0]*1000,device_ms=timing[1]*1000,copyout_ms=timing[2]*1000,total_ms=(time.monotonic()-start)*1000)
        return out

def filtered(frame,mode):
    global _instance
    with GATE:
        if _suspended:raise RuntimeError('PL filters suspended')
        if _instance is None:_instance=Engine()
        return _instance.run(frame,mode)

def status():
    # Observational snapshot: never invert Camera.lock -> GATE during status.
    return dict(backend='PL PFL1',suspended=_suspended,calls=0 if _instance is None else _instance.calls,
                by_mode={} if _instance is None else dict(_instance.by_mode),last={} if _instance is None else dict(_instance.last))
