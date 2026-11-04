"""Finite pixel-parity and blocked-producer/standby concurrency regressions."""
import ast,hashlib,json,os,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
deps=ROOT.parents[1]/'experiments/usb_camera_20261016/deps'
if deps.exists():sys.path.insert(0,str(deps))
import cv2
import numpy as np
from preview_rectify import MODES,PreviewRectifier
from shared_preview import SharedPreview,filtered

def until(test,timeout=4):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if test():return
        time.sleep(.005)
    raise AssertionError('Timed out awaiting expected state')

def run(photo):
    with np.load(str(photo),allow_pickle=False) as z:frame=cv2.resize(z['frame_bgr'],(1280,480))
    original=frame.tobytes();processor=SharedPreview();reference=PreviewRectifier();reference.native=None;checks=[]
    for mode in MODES:
        hdmi,jpeg,timing=processor.render(frame,17,mode)
        small=reference.display(frame,(640,240)) if mode=='rectified' else cv2.resize(frame,(640,240),interpolation=cv2.INTER_AREA)
        big=reference.display(frame,(1280,480)) if mode=='rectified' else frame
        if mode not in ('color','rectified'):
            small=filtered(small,mode);big=cv2.cvtColor(filtered(frame,mode),cv2.COLOR_GRAY2BGR)
        ok,expected=cv2.imencode('.jpg',small,[cv2.IMWRITE_JPEG_QUALITY,75]);assert ok
        assert jpeg==expected.tobytes() and hdmi.tobytes()==big.tobytes(),mode
        checks.append(mode)
    processor.render(frame,17,'rectified');assert processor.rectifications==1
    assert frame.tobytes()==original
    # Load the actual Camera class without importing board DMA libraries on PC.
    tree=ast.parse((ROOT/'full_camera.py').read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Camera']
    entered=threading.Event();release=threading.Event();instances=[]
    class BlockedProducer(SharedPreview):
        def render(self,*args):
            if not entered.is_set():entered.set();assert release.wait(4)
            return super().render(*args)
    def factory():
        p=BlockedProducer();instances.append(p);return p
    class FakeCapture:
        def __init__(self,*args):self.released=False
        def isOpened(self):return True
        def set(self,*args):pass
        def read(self):time.sleep(.01);return True,frame.copy()
        def release(self):self.released=True
    scope={'threading':threading,'time':time,'os':os,'cv2':cv2,'MODES':MODES,'SharedPreview':factory}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'Camera','exec'),scope)
    cam=scope['Camera'](FakeCapture)
    try:
        assert entered.wait(2);n=cam.status()['sequence'];time.sleep(.08)
        assert cam.status()['sequence']>=n+3,'Capture blocked behind preview'
        cam.set_mode('rectified');release.set()
        until(lambda:cam.packet is not None and cam.packet[3]=='rectified')
        # Snapshot stays native and lossless even when display is rectified.
        raw,seq,age=cam.snapshot();assert raw.tobytes()==original and raw.shape==(480,1280,3)
        packet=cam.preview_snapshot();assert packet[3]=='rectified';assert cam.preview_jpeg()
        cam.set_standby(True)
        for call in (cam.snapshot,cam.preview_snapshot,cam.preview_jpeg):
            try:call()
            except ValueError:pass
            else:raise AssertionError('Stale frame escaped during standby')
        cam.set_standby(False);cam.set_mode('color')
        until(lambda:cam.packet is not None and cam.packet[3]=='color')
        assert not cam.status()['preview_error']
    finally:release.set();cam.close()
    assert not cam.worker.is_alive() and not cam.preview_worker.is_alive()
    return {'passed':True,'old_HDMI_and_JPEG_exact_modes':checks,'one_rectification_for_both_consumers':True,
            'capture_continues_while_preview_blocked':True,'mode_epoch_rejects_stale_packet':True,
            'native_photo_unchanged':True,'standby_resume':True,'workers_drained':True}

if __name__=='__main__':
    result=run(sys.argv[1]);(ROOT/'shared_preview_verified.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
