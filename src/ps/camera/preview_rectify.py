"""A53 preview only: reuse fixed-point maps bound to PL photos; no DMA."""
import hashlib
import ctypes
import sys
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
CALIBRATION='6dbbd7ca2aa6f013e4f4f0861a18f7cd2d00f2434dc2e5d53185caae2d81128d'
MAP_CONTENT='a4d933cbd6d001ce84cec73775358464689d46f95146a4fd9be05400472b2779'
from preview_modes import PREVIEW_MODES as MODES

class PreviewRectifier:
    def __init__(self):
        assert hashlib.sha256((ROOT/'stereo_parameters.json').read_bytes()).hexdigest()==CALIBRATION
        with np.load(str(ROOT/'rectification_maps.npz'),allow_pickle=False) as z:
            assert z['calibration_sha256'].tobytes().decode()==CALIBRATION
            packed=[z['map%d'%eye].copy() for eye in (0,1)]
        assert hashlib.sha256(b''.join(m.tobytes() for m in packed)).hexdigest()==MAP_CONTENT
        self.packed=np.ascontiguousarray(packed,dtype=np.uint64)
        self.native=None
        if sys.platform.startswith('linux') and (ROOT/'preview_native.so').exists():
            self.native=ctypes.CDLL(str(ROOT/'preview_native.so'))
            assert self.native.preview_native_version()==2
            self.native.preview_area.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
            self.native.preview_area.restype=None
            self.native.preview_remap.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
            self.native.preview_remap.restype=None
            self.native.preview_pipeline.argtypes=[ctypes.c_void_p]*4
            self.native.preview_pipeline.restype=None
        self.maps=[]
        for m in packed:
            assert m.shape==(360,320) and m.dtype==np.uint64
            xy=np.empty((360,320,2),np.int16)
            xy[:,:,0]=(m&65535).astype(np.uint16).view(np.int16)
            xy[:,:,1]=((m>>16)&65535).astype(np.uint16).view(np.int16)
            frac=((m>>32)&1023).astype(np.uint16)
            self.maps.append((xy,frac))

    def rectified(self,frame):
        if frame.dtype!=np.uint8 or frame.shape!=(480,1280,3):
            raise ValueError('Expected native stereo frame')
        if self.native is not None:
            raw=np.ascontiguousarray(frame);area=np.empty((360,640,3),np.uint8);out=np.empty_like(area)
            self.native.preview_pipeline(raw.ctypes.data,self.packed.ctypes.data,area.ctypes.data,out.ctypes.data)
            return out
        eyes=[cv2.resize(frame[:,eye*640:(eye+1)*640],(320,360),interpolation=cv2.INTER_AREA) for eye in (0,1)]
        return self.rectified_grid(np.concatenate(eyes,axis=1))

    def rectified_grid(self,frame):
        assert frame.shape==(360,640,3) and frame.dtype==np.uint8
        return np.concatenate([cv2.remap(frame[:,eye*320:(eye+1)*320],*self.maps[eye],
                    interpolation=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)
                    for eye in (0,1)],axis=1)

    def display(self,frame,size):
        # Restore camera 4:3 per-eye aspect for display, not compute-grid aspect.
        result=cv2.resize(self.rectified(frame),size,interpolation=cv2.INTER_LINEAR)
        for y in range(size[1]//6,size[1],size[1]//6):
            cv2.line(result,(0,y),(size[0]-1,y),(0,220,0),1)
        cv2.line(result,(size[0]//2,0),(size[0]//2,size[1]-1),(220,220,220),1)
        return result
