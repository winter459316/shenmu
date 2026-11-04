"""Frozen-photo vessel display using the same qualified PL transform as preview."""
import cv2,numpy as np
from photo_views import PhotoViews,MODES as BASE_MODES
from shared_preview import vessel
MODES=BASE_MODES+('vessel',)
class VesselPhotoViews(PhotoViews):
    def image(self,mode):
        if mode!='vessel':return super().image(mode)
        if mode not in self.images:
            image=vessel(self.native);image.setflags(write=False);self.images[mode]=image
        return self.images[mode]
    def frame(self,mode):
        if mode!='vessel':return super().frame(mode)
        if mode not in self.canvases:
            canvas=np.full((720,1280,3),(28,17,11),np.uint8);canvas[120:600]=self.image(mode)
            cv2.putText(canvas,'PHOTO '+self.job[:8]+' | VESSEL ENHANCEMENT',(25,40),cv2.FONT_HERSHEY_SIMPLEX,.72,(230,235,240),2)
            cv2.putText(canvas,'PS_KEY2: photo filters   PS_KEY1: depth / 3D   PL_KEY1: live preview',(25,680),cv2.FONT_HERSHEY_SIMPLEX,.65,(190,205,220),1)
            self.canvases[mode]=canvas.tobytes()
        return self.canvases[mode]
