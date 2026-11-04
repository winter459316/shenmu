"""Exposure response, bounded steps, input preservation, and failed-control fallback."""
import sys,time,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if sys.platform=='win32':sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
from auto_exposure import meter,decide,AutoExposure,AUTO,ABSOLUTE,MAINS

def response(initial,scale):
    value=initial;levels=[]
    for _ in range(35):
        light=min(255,scale*value);levels.append(light)
        next_value,_=decide({'mean':light,'bright_fraction':float(light>245)},value)
        assert 3<=next_value<=300 and abs(next_value-value)<=max(1,value*.25+1)
        value=next_value
    assert 98<=levels[-1]<=126,levels
    return levels[-1]
assert response(20,1)>98 and response(300,1)<126
assert decide({'mean':10,'bright_fraction':0},300)==(300,'limit_dark')
assert decide({'mean':250,'bright_fraction':1},3)==(3,'limit_bright')
frame=np.full((480,1280,3),80,np.uint8);frame[:,640:]=160
before=hashlib.sha256(frame.tobytes()).hexdigest();m=meter(frame)
assert abs(m['left']['mean']-80)<.01 and abs(m['right']['mean']-160)<.01
assert hashlib.sha256(frame.tobytes()).hexdigest()==before
class Fake:
    instances=[];fail=False
    def __init__(self,device):
        self.values={AUTO:3,ABSOLUTE:80,MAINS:2};self.closed=False;self.instances.append(self)
    def get(self,key):return self.values[key]
    def set(self,key,value):
        if self.fail and key==MAINS:raise OSError('Simulated UVC write failure')
        self.values[key]=value;return value
    def limits(self,key):return 3,2047,1,166
    def close(self):self.closed=True
sequence=0
def sample():
    global sequence
    sequence+=1
    return np.full((480,1280,3),40,np.uint8),sequence
c=AutoExposure('fake',sample,Fake)
time.sleep(.1);Fake.instances[-1].values[AUTO]=1
time.sleep(.6);state=c.status();c.close()
assert state['updates']>=1 and state['mode']=='camera_auto'
assert Fake.instances[-1].values=={AUTO:3,ABSOLUTE:80,MAINS:2}
assert Fake.instances[-1].closed and not c.worker.is_alive()
Fake.fail=True;c=AutoExposure('fake',sample,Fake);time.sleep(.1)
assert c.status()['mode']=='camera_auto_fallback' and Fake.instances[-1].values[AUTO]==3
c.close();assert Fake.instances[-1].closed
report={'passed':True,'manual_experiment_unit_checks':True,'active_controller':'camera_auto',
        'stereo_metering':True,'input_pixels_unchanged':True,'controls_restored':True,'fallback':True}
(ROOT/'exposure_unit_tests.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
