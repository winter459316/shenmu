"""Fixed shared stereo tone curve for display; never modifies matcher input.

Black stays black, shadows/midtones rise, highlights have a soft shoulder.
The same monotone curve is applied to all BGR channels and both eyes.
No per-eye histogram adaptation, temporal pumping, or local halo amplification.
Clipped source detail cannot be recovered by this display transform.
"""
import cv2
import numpy as np

X=np.array([0,4,8,16,32,64,96,128,160,192,224,240,255],np.float64)
Y=np.array([0,4,11,25,51,98,131,159,183,204,225,237,248],np.float64)
LUT=np.rint(np.interp(np.arange(256),X,Y)).astype(np.uint8)
LUT.setflags(write=False)

def apply(image):
    if image.dtype!=np.uint8:raise ValueError('Tone curve requires uint8 pixels')
    return cv2.LUT(image,LUT)

def description(enabled=True):
    return {'enabled':enabled,'name':'shadow_lift_soft_highlights_v1',
            'processor':'A53','shared_stereo_curve':True,'adaptive_per_eye':False,
            'scope':'web and HDMI preview','matcher_input_changed':False,
            'source_clipped_detail_recovered':False,'output_white':248,
            'curve':list(zip(X.astype(int).tolist(),Y.astype(int).tolist()))}
