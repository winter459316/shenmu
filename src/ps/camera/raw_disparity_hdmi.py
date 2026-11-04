"""Read-only visualization of accepted pre-completion disparity; never geometry input."""
import io,time
import cv2
import numpy as np

def render(package,job):
    began=time.monotonic()
    with np.load(io.BytesIO(package),allow_pickle=False) as arrays:
        q=arrays['disparity_q4'];valid=arrays['valid'].astype(bool)
    if q.shape!=(360,320) or valid.shape!=q.shape:
        raise ValueError('Raw disparity requires the accepted 320x360 photo')
    disparity=q.astype(np.float32)/16
    valid=valid & np.isfinite(disparity) & (disparity>0)
    levels=np.zeros(q.shape,np.uint8)
    levels[valid]=np.clip(disparity[valid]/127*255,0,255).astype(np.uint8)
    colored=cv2.applyColorMap(levels,cv2.COLORMAP_JET)
    colored[~valid]=0
    canvas=np.zeros((720,1280,3),np.uint8)
    canvas[80:620,400:880]=cv2.resize(colored,(480,540),interpolation=cv2.INTER_NEAREST)
    def text(message,xy,scale=.65,color=(225,225,225)):
        cv2.putText(canvas,message,xy,cv2.FONT_HERSHEY_SIMPLEX,scale,color,1,cv2.LINE_AA)
    text('RAW DISPARITY | BEFORE HOLE FILLING',(24,34),.85)
    text('PHOTO '+job[:12]+' | 320x360 | VALID %.2f%%'%(100*valid.mean()),(24,62))
    bar=np.linspace(0,255,480).astype(np.uint8)[None,:]
    canvas[634:648,400:880]=cv2.applyColorMap(np.repeat(bar,14,axis=0),cv2.COLORMAP_JET)
    text('0 px',(400,674),.55);text('127 px',(810,674),.55)
    text('BLACK: unmatched',(20,140),.6)
    text('No hole filling',(20,170),.6)
    text('Blue: smaller disparity',(20,220),.55)
    text('Red: larger disparity',(20,248),.55)
    text('3D still uses',(925,140),.6)
    text('processed disparity',(925,170),.6)
    text('PL_KEY1: camera preview | PL_KEY2: next photo | Web: cast 3D',(24,707),.65)
    return canvas.tobytes(),{'job_id':job,'source':'disparity_q4 + valid (before completion)',
        'valid_pixels':int(valid.sum()),'invalid_pixels':int((~valid).sum()),
        'seconds':time.monotonic()-began,'geometry_input_changed':False}
