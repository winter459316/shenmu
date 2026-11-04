"""320x360 image-guided completion, with an explicitly selected PL CG.

The original PL disparities stay immutable. Display completion carries the old
0..4 provenance; it must never be relabelled as a stereo measurement.
"""
import ctypes,hashlib,json,threading,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
W,H=320,360;N=W*H
_LOCK=threading.Lock()
class CompletionCancelled(RuntimeError):pass
class Stats(ctypes.Structure):
    _fields_=[(n,ctypes.c_uint) for n in ('phase measured inferred local extrapolated iterations converged residual_ppm error processed rejected zero_rejected unsupported_rejected'.split())]
class CgStats(ctypes.Structure):
    _fields_=[(n,ctypes.c_double) for n in ('prepare_seconds device_seconds copy_seconds reduction_seconds'.split())]+[(n,ctypes.c_uint) for n in ('commands multiplies updates directions error active'.split())]
def fields(s):return {n:getattr(s,n) for n,_ in s._fields_}

def complete(left,raw_q,valid,domain,arena=None,use_pl=True,progress=None,cancel=None):
    if not _LOCK.acquire(False):raise RuntimeError('Completion already owns the solver')
    lib=None;bound=False
    try:
        left=np.ascontiguousarray(left,dtype=np.uint8)
        raw_q=np.ascontiguousarray(raw_q,dtype=np.int16)
        valid=np.asarray(valid,dtype=bool);domain=np.asarray(domain,dtype=bool)
        assert left.shape==(H,W,3) and raw_q.shape==valid.shape==domain.shape==(H,W)
        assert not np.any(valid&~domain) and np.any(valid)
        assert np.all((raw_q[valid]>=16)&(raw_q[valid]<=2032))
        original_hash=hashlib.sha256(raw_q.tobytes()).hexdigest()
        negative=np.full((H,W),-32768,np.int16);negative[valid]=-raw_q[valid]
        bits=np.packbits(domain.ravel().reshape(-1,8)[:,::-1],axis=1).ravel().copy().view(np.uint32)
        output=np.empty((H,W),np.int16);origins=np.empty((H,W),np.uint8)
        lib=ctypes.CDLL(str(ROOT/'usb_completion.so'))
        ptr=ctypes.c_void_p
        lib.hr_completion_workspace_bytes.restype=ctypes.c_size_t
        lib.hr_completion_begin.argtypes=[ptr,ctypes.c_size_t,ptr,ptr,ptr,ptr,ptr]
        lib.hr_completion_step.argtypes=[ptr,ctypes.c_uint]
        lib.hr_completion_stats.argtypes=[ptr,ctypes.POINTER(Stats)]
        lib.usb_cg_bind.argtypes=[ptr,ptr,ctypes.c_uint64,ctypes.c_int]
        lib.usb_cg_stats.argtypes=[ctypes.POINTER(CgStats)]
        if use_pl:
            assert arena is not None,'PL completion requires the exclusive Arena'
            from board_dma import BASE
            identity,_=arena.command('completion',{0x20:0},timeout=2)
            assert identity==0x43475032,'Completion IP identity mismatch'
            address=ctypes.addressof(ctypes.c_char.from_buffer(arena.memory))+24*N*16
            registers=ctypes.addressof(ctypes.c_char.from_buffer(arena.controls['completion']))
            rc=lib.usb_cg_bind(address,registers,BASE+24*N*16,1)
        else:rc=lib.usb_cg_bind(None,None,0,0)
        if rc:raise RuntimeError('CG bind failed: %d'%rc)
        bound=True
        size=lib.hr_completion_workspace_bytes();workspace=ctypes.create_string_buffer(size)
        rc=lib.hr_completion_begin(workspace,size,left.ctypes.data,negative.ctypes.data,bits.ctypes.data,output.ctypes.data,origins.ctypes.data)
        assert rc==0,('completion begin',rc)
        stats=Stats();cg=CgStats();start=last=time.monotonic();phase_time={};previous=1;phase_start=start
        while True:
            if cancel and cancel():raise CompletionCancelled('Photo cancelled')
            rc=lib.hr_completion_step(workspace,4096)
            lib.hr_completion_stats(workspace,ctypes.byref(stats));now=time.monotonic()
            if stats.phase!=previous:
                phase_time[str(previous)]=phase_time.get(str(previous),0)+now-phase_start
                previous=stats.phase;phase_start=now
            if progress and now-last>=.3:
                progress('completion',dict(fields(stats),elapsed_seconds=now-start));last=now
            if rc<0:raise RuntimeError('Completion failed: '+json.dumps(fields(stats)))
            if rc:break
            if now-start>240:raise TimeoutError('Completion exceeded 240 seconds')
        lib.usb_cg_stats(ctypes.byref(cg))
        result=-output
        assert hashlib.sha256(raw_q.tobytes()).hexdigest()==original_hash,'Original disparity changed'
        assert np.array_equal(result[origins==0],raw_q[origins==0])
        assert not np.any((origins==0)&~valid)
        assert np.array_equal(origins==3,~domain)
        report=dict(fields(stats),cg=fields(cg),seconds=time.monotonic()-start,phase_seconds=phase_time,
                    backend='PL FP32 CG + A53 ordered FP64 reductions and image guidance' if use_pl else 'A53 completion reference',
                    original_disparity_sha256=original_hash,workspace_bytes=size)
        return result,origins,report
    finally:
        if lib is not None and bound:
            rc=lib.usb_cg_finish()
            if rc:
                (ROOT/'dma.fault').write_text('Completion DMA fault %d; verified PL reload required'%rc)
                _LOCK.release()
                raise RuntimeError('Completion DMA failed to finish safely: %d'%rc)
        _LOCK.release()
