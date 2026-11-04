import json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if sys.platform=='win32':
    sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
    sys.modules.setdefault('fcntl',types.SimpleNamespace())
import numpy as np
from hdmi_fps import FrameRate
def run():
    f=FrameRate();f.select('preview',0)
    for i in range(30):f.presented((i,0),(i+1)/30)
    assert f.label()=='FPS: 30.0'
    for i in range(30):f.presented((29,0),1+(i+1)/30)
    assert f.label()=='FPS: 0.0','Repeated content counted as new frames'
    a=np.full((720,1280,3),80,np.uint8);original=a.copy();f.draw(a)
    changed=np.any(a!=original,axis=2);outside=changed.copy();outside[8:57,996:1270]=False
    assert not outside.any() and changed.any()
    f.select('raw_disparity',3);assert f.label()=='FPS: 0.0 (STILL)'
    f.select('preview',4);assert f.label()=='FPS: --'
    from test_rawhdmi import run as raw
    assert raw()['passed']
    result={'passed':True,'30_new_frames_counted':True,'duplicate_frames_not_counted':True,'overlay_only_top_right':True,'static_label':True,'raw_hdmi_regressions':True,'shutter_triggered':False}
    (ROOT/'hdmifps_tests.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':print(json.dumps(run()))
