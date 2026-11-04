"""Finite HDMI lifecycle and key tests; never maps hardware or opens UVC."""
import hashlib,json,platform,sys,threading,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if platform.system()=='Windows':
    sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
    sys.modules.setdefault('fcntl',types.SimpleNamespace())
import numpy as np
from hdmi_output import HDMIOutput,FRAME_BYTES,FB0,BUFFERS,BASE,SIZE
from physical_keys import Actions

class Camera:
    def snapshot(self):return np.zeros((480,1280,3),np.uint8),1,0
    def status(self):return {'mode':'color'}
class Runtime:
    state={'busy':False,'standby':False,'result_id':'a'*32,'stage':'ready'}
    def status(self):return dict(self.state)
class FakeScanout:
    def __init__(self):self.frames=0;self.closed=False
    def status(self):return {'frames':self.frames,'vdma_status':0}
    def present(self,data):assert len(data)==FRAME_BYTES;self.frames+=1
    def close(self):self.closed=True
def wait(test):
    deadline=time.monotonic()+3
    while not test():
        assert time.monotonic()<deadline,'State transition timed out'
        time.sleep(.01)
def reject(call):
    try:call()
    except ValueError:return
    raise AssertionError('Invalid request was accepted')
def main():
    assert FB0==BASE+26*640*480*16
    assert BUFFERS[1]==FB0+FRAME_BYTES and BUFFERS[1]+FRAME_BYTES<=BASE+SIZE
    runtime=Runtime();h=HDMIOutput(Camera(),runtime,FakeScanout)
    data=bytes([17])*FRAME_BYTES;digest=hashlib.sha256(data).hexdigest()
    try:
        wait(lambda:h.status()['frames']>0)
        reject(lambda:h.accept(data[:-1],'a'*32,digest,0))
        reject(lambda:h.accept(data,'b'*32,digest,0))
        reject(lambda:h.accept(data,'a'*32,'0'*64,0))
        assert h.accept(data,'a'*32,digest,0)['accepted']
        wait(lambda:h.status()['source']=='3d_cast')
        h.preview();reject(lambda:h.accept(data,'a'*32,digest,0))
        wait(lambda:h.status()['source']=='preview')
        generation=h.status()['generation'];h.accept(data,'a'*32,digest,generation)
        runtime.state['standby']=True
        wait(lambda:h.status()['source']=='standby')
        reject(lambda:h.accept(data,'a'*32,digest,generation))
        runtime.state['standby']=False;wait(lambda:h.status()['source']=='preview')
        assert h.cast is None and not h.error
        generation=h.status()['generation'];h.accept(data,'a'*32,digest,generation)
        with h.lock:h.cast_until=time.monotonic()-1
        wait(lambda:h.status()['generation']>generation)
        reject(lambda:h.accept(data,'a'*32,digest,generation))
        calls=[]
        def key_call(path,body=None):
            calls.append((path,body))
            if path=='/hdmi/status':return {'enabled':True,'source':'3d_cast'}
            return {}
        a=Actions(key_call,pl_enabled=True)
        a.event(1,105,1);a.event(1,105,2);a.event(1,105,1)
        assert calls==[('/hdmi/status',None),('/hdmi/preview',{}),('/preview/mode',{'mode':'color'})]
        print(json.dumps({'passed':True,'architecture':platform.machine(),'physical_hardware_used':False,
                          'invalid_frames_rejected':True,'preview_generation_revokes_stale_cast':True,
                          'standby_and_expired_cast_revoked':True,'key1_returns_color_once':True,
                          'framebuffers_disjoint_from_compute':True}))
    finally:
        h.close();assert not h.worker.is_alive() and h.scanout.closed
if __name__=='__main__':main()
