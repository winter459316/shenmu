"""Finite fake-UVC fault test: no physical camera, no PL, no shutter."""
import hashlib,importlib.util,json,platform,sys,threading,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
# Camera acquisition can be tested without constructing any board/DMA runtime.
sys.modules.setdefault('full_runtime',types.SimpleNamespace(FullRuntime=None))
SOURCE=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'full_camera.py'
spec=importlib.util.spec_from_file_location('camera_recovery_under_test',SOURCE)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);Camera=module.Camera
import numpy as np

class Capture:
    def __init__(self,number,fail,release_log):
        self.number=number;self.fail=fail;self.release_log=release_log;self.closed=False
    def isOpened(self):return self.number!=1
    def set(self,*unused):pass
    def read(self):
        time.sleep(.01)
        if self.number==2:return True,np.zeros((240,640,3),np.uint8)
        if self.fail.is_set():return False,None
        return True,np.full((480,1280,3),self.number,np.uint8)
    def release(self):
        assert not self.closed,'Handle released twice'
        self.closed=True;self.release_log.append(self.number)

def wait_for(condition,timeout=4):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if condition():return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for acquisition state')

def main():
    handles=[];released=[];fail=threading.Event()
    def opener(*unused):
        c=Capture(len(handles)+1,fail,released);handles.append(c);return c
    c=Camera(opener)
    try:
        wait_for(lambda:c.sequence>=2)
        frame,seq,age=c.snapshot();assert np.all(frame==3) and age<1
        assert c.recovery_count==2 and released==[1,2]
        fail.set();wait_for(lambda:bool(c.error))
        try:c.snapshot();raise AssertionError('Stale frame was accepted')
        except ValueError:pass
        assert c.frame is None and c.jpeg is None
        fail.clear();wait_for(lambda:c.sequence>seq and not c.error)
        frame,seq,_=c.snapshot();assert np.all(frame==4) and c.worker.is_alive()
        c.standby=True;wait_for(lambda:c.error=='Standby')
        opens=len(handles);time.sleep(.12);assert len(handles)==opens
        c.standby=False;wait_for(lambda:c.sequence>seq and not c.error)
        frame,_,_=c.snapshot();assert np.all(frame==5)
        print(json.dumps({'passed':True,'open_failure':True,'wrong_dimensions':True,'read_failure_recovered':True,
                          'stale_snapshot_rejected':True,'standby_resume':True,'physical_uvc_opened':False,'shutter_triggered':False,
                          'architecture':platform.machine(),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()}))
    finally:
        c.running=False;c.worker.join(timeout=2)
        assert not c.worker.is_alive()
        assert len(released)==len(handles) and len(set(released))==len(handles)
if __name__=='__main__':main()
