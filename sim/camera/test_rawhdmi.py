"""Finite display-only checks, including new-result automatic selection; no real shutter."""
import hashlib,io,json,sys,threading,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if sys.platform=='win32':
    sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
    sys.modules.setdefault('fcntl',types.SimpleNamespace())
import cv2,numpy as np
from raw_disparity_hdmi import render
from hdmi_output import HDMIOutput,FRAME_BYTES
from physical_keys import Actions

class Runtime:
    def __init__(self,payload):self.payload=payload;self.job='a'*32;self.busy=False;self.standby=False
    def status(self):return {'result_id':self.job,'busy':self.busy,'standby':self.standby,'stage':'ready'}
    def result(self,job):return self.payload if job==self.job and not self.busy else None
class Camera:
    def __init__(self):self.seq=0
    def status(self):return {'mode':'color'}
    def preview_snapshot(self,*unused):
        time.sleep(.01);self.seq+=1
        return np.zeros((480,1280,3),np.uint8),self.seq,time.monotonic(),'color',0
class Scan:
    def __init__(self):self.frames=0;self.sha=None
    def present(self,data):assert len(data)==FRAME_BYTES;self.sha=hashlib.sha256(data).hexdigest();self.frames+=1
    def status(self):return {'frames':self.frames,'last_frame_sha256':self.sha}
    def close(self):pass
def await_condition(fn):
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        if fn():return
        time.sleep(.02)
    raise AssertionError('State transition timed out')
def run():
    payload=(ROOT/'held_restore.npz').read_bytes();sha=hashlib.sha256(payload).hexdigest()
    data,report=render(payload,'a'*32)
    with np.load(io.BytesIO(payload),allow_pickle=False) as a:
        q=a['disparity_q4'];valid=a['valid'].astype(bool)&(q>0)
        expected=cv2.resize((~valid).astype(np.uint8),(480,540),interpolation=cv2.INTER_NEAREST).astype(bool)
        image=np.frombuffer(data,np.uint8).reshape(720,1280,3)[80:620,400:880]
        assert np.array_equal(np.all(image==0,axis=2),expected)
    assert hashlib.sha256(payload).hexdigest()==sha
    cv2.imwrite(str(ROOT/'raw_hdmi_example.png'),np.frombuffer(data,np.uint8).reshape(720,1280,3))
    runtime=Runtime(payload);hdmi=HDMIOutput(Camera(),runtime,Scan)
    try:
        await_condition(lambda:hdmi.status()['frames']>0)
        assert hdmi.status()['source']=='preview' # held restore does not interrupt preview
        runtime.job='b'*32
        await_condition(lambda:hdmi.status()['source']=='raw_disparity')
        assert hdmi.status()['raw_job']==runtime.job
        gen=hdmi.status()['generation'];hdmi.preview()
        await_condition(lambda:hdmi.status()['source']=='preview')
        try:hdmi.raw_disparity(runtime.job,gen)
        except ValueError:pass
        else:raise AssertionError('Stale selection accepted')
        hdmi.raw_disparity(runtime.job)
        gen=hdmi.status()['generation']
        try:hdmi.accept(data,runtime.job,hashlib.sha256(data).hexdigest(),gen-1)
        except ValueError:pass
        else:raise AssertionError('Old 3D stream overwrote raw view')
        hdmi.accept(data,runtime.job,hashlib.sha256(data).hexdigest(),gen)
        await_condition(lambda:hdmi.status()['source']=='3d_cast')
        runtime.busy=True
        await_condition(lambda:hdmi.status()['source']=='preview')
        runtime.busy=False;runtime.job='c'*32
        await_condition(lambda:hdmi.status()['source']=='raw_disparity')
        runtime.standby=True
        await_condition(lambda:hdmi.status()['source']=='standby')
        runtime.standby=False
        await_condition(lambda:hdmi.status()['source']=='preview')
        assert not hdmi.status()['error']
    finally:hdmi.close()
    calls=[]
    def request(path,body=None):
        calls.append((path,body))
        if path=='/hdmi/status':return {'enabled':True,'source':'raw_disparity'}
        assert path in ('/hdmi/preview','/preview/mode')
        return {}
    keys=Actions(request,True);keys.event(1,105,1)
    assert keys.last['result']=='preview' and calls[-1]==('/preview/mode',{'mode':'color'})
    result={'passed':True,'raw_black_mask_exact':True,'new_photo_auto_display':True,'restored_photo_stays_preview':True,
      'stale_cast_rejected':True,'standby_and_new_photo_clear_display':True,'key_returns_preview':True,
      'package_unchanged':hashlib.sha256(payload).hexdigest()==sha,'frame_sha256':hashlib.sha256(data).hexdigest(),
      'renderer':report,'shutter_triggered':False}
    (ROOT/'rawhdmi_tests.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':print(json.dumps(run()))
