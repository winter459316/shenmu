"""Finite pixel-level check of the shared display transform and exact off switch."""
import hashlib,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if sys.platform=='win32':sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import cv2,numpy as np
from tone_map import apply,LUT
from shared_preview import SharedPreview,guides
OLD=ROOT.parent/('usb_320_exposure' if sys.platform=='win32' else 'usb320_exposure')
spec=importlib.util.spec_from_file_location('stable_preview',OLD/'shared_preview.py')
stable=importlib.util.module_from_spec(spec);spec.loader.exec_module(stable)

def run():
    frame=cv2.imread(str(ROOT/'tone_input.png'));assert frame.shape==(480,1280,3)
    original=frame.copy();a=SharedPreview();b=stable.SharedPreview();modes=[]
    for index,mode in enumerate(('color','rectified','gray','median','sobel')):
        reference,jpeg,_=b.render(frame,index,mode)
        off,off_jpeg,_=a.render(frame,index,mode,False)
        assert np.array_equal(reference,off) and jpeg==off_jpeg,mode
        count=a.rectifications
        on,on_jpeg,_=a.render(frame,index,mode,True)
        assert a.rectifications==count,'Tone toggle repeated rectification'
        if mode=='color':assert np.array_equal(on,apply(frame))
        elif mode=='rectified':
            expected=guides(cv2.resize(apply(a.cached_rectified),(1280,480),interpolation=cv2.INTER_LINEAR))
            assert np.array_equal(on,expected)
        elif mode=='sobel':assert np.array_equal(on,reference) and on_jpeg==jpeg
        again,again_jpeg,_=a.render(frame,index,mode,False)
        assert np.array_equal(again,reference) and again_jpeg==jpeg,'Cached frame was altered'
        assert np.array_equal(frame,original),'Capture/matching source mutated'
        modes.append(mode)
    ramp=np.repeat(np.arange(256,dtype=np.uint8)[None,:,None],3,axis=2)
    result=apply(ramp)
    assert np.all(np.diff(result[0,:,0].astype(int))>=0)
    assert np.array_equal(result[:,:,0],result[:,:,1]) and result.min()==0 and result.max()==248
    pair=np.concatenate((original[:,:640],original[:,:640]),axis=1);enhanced=apply(pair)
    assert np.array_equal(enhanced[:,:640],enhanced[:,640:]),'Per-eye mapping differs'
    report={'passed':True,'off_byte_exact':modes,'source_unchanged':True,'one_rectification_per_frame':True,
            'shared_eye_curve':True,'monotone':True,'output_white':248,
            'source_sha256':hashlib.sha256(frame.tobytes()).hexdigest(),
            'tone_bgr_sha256':hashlib.sha256(apply(frame).tobytes()).hexdigest()}
    (ROOT/'tone_tests.json').write_text(json.dumps(report,indent=2));return report
if __name__=='__main__':print(json.dumps(run()))
