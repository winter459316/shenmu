"""Display transforms of one immutable photo, independent of stereo inference."""
import cv2
import numpy as np
from preview_modes import MODES
from shared_preview import filtered,guides,tone_map

NATIVE_BYTES=480*1280*3
PACKET_BYTES=NATIVE_BYTES+360*640*3
LABELS={'color':'ORIGINAL COLOR','auto_enhanced':'AUTO EXPOSURE','rectified':'RECTIFIED',
        'gray':'GRAYSCALE','median':'MEDIAN 3x3','sobel':'SOBEL EDGES'}

def pack_photo(native,rectified):
    assert native.shape==(480,1280,3) and rectified.shape==(360,640,3)
    assert native.dtype==rectified.dtype==np.uint8
    return native.tobytes()+rectified.tobytes()

class PhotoViews:
    def __init__(self,packet,job):
        if len(packet)!=PACKET_BYTES:raise ValueError('Invalid frozen stereo photo size')
        self.packet=bytes(packet);self.job=job
        self.native=np.frombuffer(self.packet,np.uint8,count=NATIVE_BYTES).reshape(480,1280,3)
        self.rectified=np.frombuffer(self.packet,np.uint8,offset=NATIVE_BYTES).reshape(360,640,3)
        self.images={};self.canvases={}
    def image(self,mode):
        if mode not in MODES:raise ValueError('Invalid photo mode')
        if mode not in self.images:
            if mode=='color':image=self.native
            elif mode=='auto_enhanced':image=tone_map(self.native)
            elif mode=='rectified':image=guides(cv2.resize(self.rectified,(1280,480),interpolation=cv2.INTER_LINEAR))
            else:image=cv2.cvtColor(filtered(self.native,mode),cv2.COLOR_GRAY2BGR)
            image.setflags(write=False);self.images[mode]=image
        return self.images[mode]
    def frame(self,mode):
        if mode not in self.canvases:
            image=self.image(mode);canvas=np.full((720,1280,3),(28,17,11),np.uint8);canvas[120:600]=image
            cv2.putText(canvas,'PHOTO '+self.job[:8]+' | '+LABELS[mode],(25,40),cv2.FONT_HERSHEY_SIMPLEX,.72,(230,235,240),2)
            cv2.putText(canvas,'PS_KEY2: photo filters   PS_KEY1: depth / 3D   PL_KEY1: live preview',(25,680),cv2.FONT_HERSHEY_SIMPLEX,.65,(190,205,220),1)
            self.canvases[mode]=canvas.tobytes()
        return self.canvases[mode]
