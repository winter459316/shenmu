"""Generate calibration-bound PL maps, independently of any test photograph."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
USB=ROOT.parents[1]/'experiments/usb_camera_20261016'
sys.path.insert(0,str(USB/'deps'))
import cv2
import numpy as np
raw=(ROOT/'stereo_parameters.json').read_bytes();digest=hashlib.sha256(raw).hexdigest()
assert digest=='6dbbd7ca2aa6f013e4f4f0861a18f7cd2d00f2434dc2e5d53185caae2d81128d'
p=json.loads(raw);assert p['eye_size']==[320,360] and p['units']=='mm'
out={}
for eye in (1,2):
    k=str(eye)
    x,y=cv2.initUndistortRectifyMap(np.array(p['K'+k]),np.array(p['D'+k]),np.array(p['R'+k]),np.array(p['P'+k]),(320,360),cv2.CV_32FC1)
    support=cv2.erode(((x>=0)&(x<319)&(y>=0)&(y<359)).astype(np.uint8),np.ones((5,5),np.uint8)).astype(bool)
    fixed,frac=cv2.convertMaps(x,y,cv2.CV_16SC2)
    out['map'+str(eye-1)]=fixed[:,:,0].astype(np.uint16).astype(np.uint64)|(fixed[:,:,1].astype(np.uint16).astype(np.uint64)<<16)|(frac.astype(np.uint64)<<32)|(support.astype(np.uint64)<<42)
out['calibration_sha256']=np.frombuffer(digest.encode(),np.uint8)
np.savez_compressed(ROOT/'rectification_maps.npz',**out)
print('MAPS_SHA256',hashlib.sha256((ROOT/'rectification_maps.npz').read_bytes()).hexdigest())
