"""Finite in-flight DMA cancellation and safe subsequent core access."""
import ctypes,json,time
from pathlib import Path
import numpy as np
from board_dma import Arena
from board_completion import complete,CompletionCancelled,CgStats,N
ROOT=Path(__file__).resolve().parent
with np.load(ROOT/'hardware_case.npz') as z:c={k:z[k] for k in z.files}
domain=((c['maps0']>>42)&1).astype(bool)
lib=ctypes.CDLL(str(ROOT/'usb_completion.so'));lib.usb_cg_stats.argtypes=[ctypes.POINTER(CgStats)]
a=Arena(True);seen=[];start=time.monotonic()
def cancel_inflight():
    s=CgStats();lib.usb_cg_stats(ctypes.byref(s))
    if s.active==1:seen.append({'active':s.active,'commands_completed':s.commands});return True
    return False
try:
    try:complete(c['rect0'],c['q'],c['valid'],domain,a,True,cancel=cancel_inflight)
    except CompletionCancelled:pass
    else:raise AssertionError('Did not cancel in-flight CG')
    assert seen
    s=CgStats();lib.usb_cg_stats(ctypes.byref(s));assert s.active==0 and s.error==0
    identity,_=a.command('completion',{0x20:0},timeout=2);assert identity==0x43475032
    try:complete(c['rect0'],c['q'],c['valid'],domain,a,True,cancel=lambda:True)
    except CompletionCancelled:pass
    identity,_=a.command('completion',{0x20:0},timeout=2);assert identity==0x43475032
    report={'passed':True,'cancelled_with_dma_active':seen,'driver_drained_before_rebind':True,'next_bind_and_identity_passed':True,'seconds':time.monotonic()-start}
    (ROOT/'completion_cancel_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
finally:a.close()
