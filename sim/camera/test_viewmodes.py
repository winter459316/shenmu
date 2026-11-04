"""Finite shared pixels and physical-key dispatch checks; no real shutter."""
import hashlib,importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if sys.platform=='win32':
    sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
    sys.modules.setdefault('fcntl',types.SimpleNamespace())
import cv2,numpy as np
from shared_preview import SharedPreview
from physical_keys import Actions,MODES
OLD=ROOT.parent/('usb_320_tonemap' if sys.platform=='win32' else 'usb320_tonemap')
spec=importlib.util.spec_from_file_location('old_shared',OLD/'shared_preview.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

def run():
    frame=cv2.imread(str(ROOT/'tone_input.png'));original=frame.copy()
    current=SharedPreview();previous=old.SharedPreview();results={}
    for i,mode in enumerate(MODES):
        reference,jpeg,_=previous.render(frame,i,'color' if mode=='auto_enhanced' else mode,mode=='auto_enhanced')
        actual,encoded,_=current.render(frame,i,mode)
        assert np.array_equal(reference,actual) and jpeg==encoded,mode
        if mode=='color':assert np.array_equal(actual,frame)
        assert np.array_equal(frame,original)
        results[mode]=hashlib.sha256(actual.tobytes()).hexdigest()
    state={'mode':'color','source':'preview'};calls=[]
    def request(path,body=None):
        calls.append((path,body))
        if path=='/hdmi/status':return {'enabled':True,'source':state['source']}
        if path=='/status':return {'mode':state['mode']}
        if path=='/hdmi/preview':state['source']='preview';return {}
        if path=='/preview/mode':state['mode']=body['mode'];return {}
        raise AssertionError('Unexpected request: '+path)
    keys=Actions(request,True);cycle=[]
    for _ in MODES:
        keys.event(1,105,1);assert keys.last['result']=='mode',keys.last
        cycle.append(state['mode']);count=len(calls)
        keys.event(1,105,2);keys.event(1,105,1);assert len(calls)==count
        keys.event(1,105,0)
    assert cycle==list(MODES[1:]+MODES[:1])
    state['mode']='gray';state['source']='3d_cast'
    keys.event(1,105,1);keys.event(1,105,0)
    assert state=={'mode':'color','source':'preview'}
    keys.event(1,105,1);assert state['mode']=='auto_enhanced'
    report={'passed':True,'pixel_hashes':results,'physical_key_dispatch_cycle':cycle,
            'held_repeat_ignored':True,'three_d_returns_to_raw_color':True,
            'source_unchanged':True,'shutter_triggered':False,'physical_button_pressed':False}
    (ROOT/'viewmodes_tests.json').write_text(json.dumps(report,indent=2));return report
if __name__=='__main__':print(json.dumps(run()))
