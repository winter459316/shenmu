"""Exact image/JPEG parity and bounded latest-frame concurrency regressions."""
import ast,hashlib,importlib.util,json,os,sys,threading,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if sys.platform=='win32':
    sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
    sys.modules.setdefault('fcntl',types.SimpleNamespace())
import cv2,numpy as np
from shared_preview import SharedPreview
from preview_modes import MODES
from tone_map import description as tone_description
OLD=ROOT.parent/('usb_320_rawhdmi' if sys.platform=='win32' else 'usb320_rawhdmi')
spec=importlib.util.spec_from_file_location('previous_preview',OLD/'shared_preview.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
def until(fn,timeout=4):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if fn():return
        time.sleep(.01)
    raise AssertionError('Worker did not reach required state')
def run():
    with np.load(str(ROOT/'held_restore.npz'),allow_pickle=False) as a:frame=cv2.resize(a['frame_bgr'],(1280,480))
    original=frame.tobytes();a=SharedPreview();b=previous.SharedPreview();parity=[]
    for mode in MODES:
        h,j,_=a.render(frame,1,mode);rh,rj,_=b.render(frame,1,mode)
        assert np.array_equal(h,rh) and j==rj,mode
        parity.append(mode)
    assert a.rectifications==1 and frame.tobytes()==original
    entered=threading.Event();release=threading.Event()
    class BlockedJPEG(SharedPreview):
        def encode(self,small):
            if not entered.is_set():entered.set();assert release.wait(4)
            return super().encode(small)
    class Capture:
        def __init__(self,*unused):pass
        def isOpened(self):return True
        def set(self,*unused):pass
        def read(self):time.sleep(.033);return True,frame.copy()
        def release(self):pass
    scope=dict(threading=threading,time=time,os=os,cv2=cv2,MODES=MODES,SharedPreview=BlockedJPEG,tone_description=tone_description)
    tree=ast.parse((ROOT/'full_camera.py').read_text())
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Camera'],type_ignores=[]),'Camera','exec'),scope)
    cam=scope['Camera'](Capture)
    try:
        assert entered.wait(2);until(lambda:cam.sequence>=5 and cam.preview_count>=4)
        assert cam.jpeg_frames==0,'JPEG did not stay blocked'
        assert cam.preview_snapshot()[1]>=4,'HDMI waited for JPEG'
        raw,_,_=cam.snapshot();assert raw.tobytes()==original
        cam.set_mode('gray');until(lambda:cam.packet is not None and cam.packet[3]=='gray')
        epoch=cam.epoch;release.set();until(lambda:cam.jpeg_packet is not None)
        assert cam.jpeg_packet[3:] == ('gray',epoch),'Old-mode JPEG published'
        p=cam.preview_jpeg_packet();n=cam.preview_jpeg_packet((p[1],p[4]),.2)
        assert n[1]>p[1],'Frame-aware request did not await fresh frame'
        cam.set_standby(True)
        for fn in (cam.snapshot,cam.preview_snapshot,cam.preview_jpeg):
            try:fn()
            except ValueError:pass
            else:raise AssertionError('Standby returned stale data')
        cam.set_standby(False);until(lambda:cam.jpeg_packet is not None)
        assert cam.jpeg_packet[4]==cam.epoch
    finally:release.set();cam.close()
    assert not any(w.is_alive() for w in (cam.worker,cam.preview_worker,cam.jpeg_worker))
    from test_rawhdmi import run as raw_checks
    raw=raw_checks();assert raw['passed']
    result={'passed':True,'exact_HDMI_and_JPEG_modes':parity,'HDMI_continues_while_JPEG_blocked':True,
      'raw_photo_unchanged':True,'epoch_rejects_stale_JPEG':True,'frame_cursor_wait':True,
      'standby_resume':True,'all_three_workers_drained':True,'raw_hdmi_regressions':True,'shutter_triggered':False}
    (ROOT/'lowlatency_tests.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':print(json.dumps(run()))
