"""Display-only access to archived native and PL-rectified stereo arrays."""
from pathlib import Path
import re,sys,threading
import cv2,numpy as np
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent/'usb_320_hdmifps'))
from photo_views import pack_photo
from vessel_photo import VesselPhotoViews as PhotoViews,MODES

class PhotoStore:
    def __init__(self):self.lock=threading.RLock();self.photo=None;self.pngs={}
    def load(self,job):
        if not isinstance(job,str) or not re.fullmatch('[0-9a-f]{32}',job):raise ValueError('Invalid photo identity')
        if self.photo is None or self.photo.job!=job:
            with np.load(R/'captures'/job/'board_result.npz',allow_pickle=False) as a:
                packet=pack_photo(a['native_bgr'],np.concatenate([a['rectified_left'],a['rectified_right']],axis=1))
            self.photo=PhotoViews(packet,job);self.pngs={}
        return self.photo
    def packet(self,job):
        with self.lock:return self.load(job).packet
    def png(self,job,mode):
        with self.lock:
            p=self.load(job)
            if mode not in self.pngs:
                ok,png=cv2.imencode('.png',p.image(mode));assert ok
                self.pngs[mode]=png.tobytes()
            return self.pngs[mode]
