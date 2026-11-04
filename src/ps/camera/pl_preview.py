from preview_compat import preview_compatible
"""PL display transforms and exposure metering; same shared DMA lifecycle gate."""
from pathlib import Path
import ctypes,hashlib,json,time
import numpy as np
import pl_filters
ROOT=Path(__file__).resolve().parent
_instance=None

def checked(rc):
    if rc:
        if rc==-110:(ROOT/'preview.dma.fault').write_text('Outstanding PL preview DMA; do not reconfigure')
        raise RuntimeError('PL preview command failed: '+str(rc))

class Engine:
    def __init__(self):
        from board_dma import reservation
        reservation()
        self.proof=json.loads((ROOT/'preview_verified.json').read_text())
        assert self.proof['qualified'] and self.proof['control']==0xA10A0000
        assert self.proof.get('vessel_enhancement',{}).get('qualified'),'Vessel PL qualification missing'
        loaded=json.loads((ROOT/'loaded.json').read_text())
        assert loaded.get('state')=='operating' and preview_compatible(loaded.get('sha256'),self.proof['sha256']),'Preview bitstream mismatch'
        assert not (ROOT/'preview.dma.fault').exists(),'PL preview DMA fault requires recovery'
        self.lib=ctypes.CDLL(str(ROOT/'preview_dma.so'))
        self.lib.extra_run.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p]
        self.lib.extra_run.restype=ctypes.c_int
        self.lib.extra_maps.argtypes=[ctypes.c_void_p,ctypes.c_uint];self.lib.extra_maps.restype=ctypes.c_int
        self.lib.extra_resize.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p];self.lib.extra_resize.restype=ctypes.c_int
        checked(self.lib.extra_open())
        with np.load(str(ROOT/'rectification_maps.npz'),allow_pickle=False) as z:maps=np.ascontiguousarray([z['map0'],z['map1']],dtype=np.uint64)
        assert hashlib.sha256(maps.tobytes()).hexdigest()=='a4d933cbd6d001ce84cec73775358464689d46f95146a4fd9be05400472b2779'
        checked(self.lib.extra_maps(maps.ctypes.data,maps.nbytes))
        self.maps=maps;self.maps_dirty=False;self.maps_uploads=1
        self.calls={};self.last={}
    def run(self,frame,mode):
        loaded=json.loads((ROOT/'loaded.json').read_text())
        if pl_filters._suspended or loaded.get('state')!='operating' or not preview_compatible(loaded.get('sha256'),self.proof['sha256']):raise RuntimeError('PL preview paused or bitstream mismatch')
        if (ROOT/'preview.dma.fault').exists():raise RuntimeError('PL preview DMA fault requires recovery')
        # Fast temporarily borrows the entire reserved arena. Reload the maps
        # after every standby/reconfiguration, even if the process stayed alive.
        if self.maps_dirty:
            checked(self.lib.extra_maps(self.maps.ctypes.data,self.maps.nbytes))
            self.maps_dirty=False;self.maps_uploads+=1
        frame=np.ascontiguousarray(frame);h,w,c=frame.shape;assert c==3 and frame.dtype==np.uint8
        out=np.empty(10,np.float64) if mode==4 else np.empty((360,640,3) if mode==2 else frame.shape,np.uint8)
        timing=np.zeros(3,np.float64);start=time.monotonic()
        rc=self.lib.extra_run(frame.ctypes.data,out.ctypes.data,w,h,mode,timing.ctypes.data)
        checked(rc)
        name={1:'tone',2:'rectify',3:'guides',4:'meter',5:'vessel'}[mode];self.calls[name]=self.calls.get(name,0)+1
        self.last=dict(mode=name,copyin_ms=timing[0]*1000,device_ms=timing[1]*1000,copyout_ms=timing[2]*1000,total_ms=(time.monotonic()-start)*1000)
        return out

def run(frame,mode):
    global _instance
    with pl_filters.GATE:
        if pl_filters._suspended:
            if mode==4:return None
            raise RuntimeError('PL preview suspended')
        if _instance is None:_instance=Engine()
        return _instance.run(frame,mode)
def vessel(frame):return run(frame,5)
def tone(frame):return run(frame,1)
def rectified(frame):return run(frame,2)
def guides(frame):return run(frame,3)
def resize_pair(grid):
    # PS display packing/resizing, after the PL calibration operation.
    with pl_filters.GATE:
        if pl_filters._suspended:raise RuntimeError('PL preview suspended')
        assert _instance is not None
        grid=np.ascontiguousarray(grid);assert grid.shape==(360,640,3) and grid.dtype==np.uint8
        small=np.empty((240,640,3),np.uint8);large=np.empty((480,1280,3),np.uint8)
        checked(_instance.lib.extra_resize(grid.ctypes.data,small.ctypes.data,large.ctypes.data))
        return large,small
def meter(frame):
    a=run(frame,4)
    if a is None:return None
    return dict(left=dict(mean=float(a[0]),bright_fraction=float(a[1]),dark_fraction=float(a[2])),right=dict(mean=float(a[3]),bright_fraction=float(a[4]),dark_fraction=float(a[5])),mean=float(a[6]),bright_fraction=float(a[7]),eye_difference=float(a[8]))
def suspend(enabled):
    if _instance is not None and not _instance.lib.extra_idle():raise RuntimeError('PL preview DMA did not drain')
    if enabled and _instance is not None:_instance.maps_dirty=True
def status():
    return dict(backend='PL PXP1',calls={} if _instance is None else dict(_instance.calls),last={} if _instance is None else dict(_instance.last),maps_uploads=0 if _instance is None else _instance.maps_uploads,suspended=pl_filters._suspended)
