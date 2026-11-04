"""One preview producer, two consumers. Immutable input and calibrated pixels."""
import time,json,sys,threading
from pathlib import Path
import cv2
from preview_rectify import PreviewRectifier
from tone_map import apply as tone_map_cpu

def guides_cpu(image):
    h,w=image.shape[:2]
    for y in range(h//6,h,h//6):cv2.line(image,(0,y),(w-1,y),(0,220,0),1)
    cv2.line(image,(w//2,0),(w//2,h-1),(220,220,220),1)
    return image

_config=Path(__file__).resolve().parent/'filters_config.json'
PL_FILTERS_ENABLED=sys.platform.startswith('linux') and _config.is_file() and json.loads(_config.read_text()).get('enabled',False)
if PL_FILTERS_ENABLED:
    import pl_filters
    FILTER_GATE=pl_filters.GATE
else:FILTER_GATE=threading.RLock()
EXTRA_ENABLED=PL_FILTERS_ENABLED and (Path(__file__).resolve().parent/'preview_config.json').is_file() and json.loads((Path(__file__).resolve().parent/'preview_config.json').read_text()).get('enabled',False)
if EXTRA_ENABLED:import pl_preview
def guides(image):return pl_preview.guides(image) if EXTRA_ENABLED else guides_cpu(image)
def tone_map(image):return pl_preview.tone(image) if EXTRA_ENABLED else tone_map_cpu(image)

def vessel(frame):
    if EXTRA_ENABLED:return pl_preview.vessel(frame)
    from vessel_enhance import apply
    return apply(frame)

def filtered(frame,mode):
    if PL_FILTERS_ENABLED:return pl_filters.filtered(frame,mode)
    return filtered_cpu(frame,mode)

def filtered_cpu(frame,mode):
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    if mode=='median':return cv2.medianBlur(gray,3)
    if mode=='sobel':
        x=cv2.Sobel(gray,cv2.CV_16S,1,0);y=cv2.Sobel(gray,cv2.CV_16S,0,1)
        return cv2.addWeighted(cv2.convertScaleAbs(x),.5,cv2.convertScaleAbs(y),.5,0)
    return gray

class SharedPreview:
    def __init__(self):
        self.rectifier=PreviewRectifier();self.cached_sequence=None;self.cached_rectified=None
        self.rectifications=0

    def prepare(self,frame,sequence,mode):
        start=time.monotonic();rectify_seconds=0;tone_seconds=0
        if mode=='rectified':
            if self.cached_sequence!=sequence:
                t=time.monotonic();self.cached_rectified=pl_preview.rectified(frame) if EXTRA_ENABLED else self.rectifier.rectified(frame)
                rectify_seconds=time.monotonic()-t
                self.cached_sequence=sequence;self.rectifications+=1
            grid=self.cached_rectified
            if EXTRA_ENABLED:
                hdmi,small=pl_preview.resize_pair(grid)
                small=guides(small);hdmi=guides(hdmi)
            else:
                small=guides(cv2.resize(grid,(640,240),interpolation=cv2.INTER_LINEAR))
                hdmi=guides(cv2.resize(grid,(1280,480),interpolation=cv2.INTER_LINEAR))
        else:
            if mode=='auto_enhanced':
                t=time.monotonic();frame=tone_map(frame);tone_seconds=time.monotonic()-t
            # Share the native-resolution PL result. JPEG runs independently;
            # neither consumer modifies this array or runs a second filter.
            hdmi=frame;small=frame
            if mode=='vessel':
                small=vessel(frame);hdmi=small
            elif mode not in ('color','auto_enhanced'):
                small=filtered(frame,mode)
                hdmi=cv2.cvtColor(small,cv2.COLOR_GRAY2BGR)
        return hdmi,small,{'rectify_ms':rectify_seconds*1000,'tone_ms':tone_seconds*1000,
            'image_ms':(time.monotonic()-start)*1000,'total_ms':(time.monotonic()-start)*1000}

    @staticmethod
    def encode(small):
        ok,encoded=cv2.imencode('.jpg',small,[cv2.IMWRITE_JPEG_QUALITY,75])
        if not ok:raise RuntimeError('Preview encoding failed')
        return encoded.tobytes()

    def render(self,frame,sequence,mode):
        # Compatibility for offline parity checks. Live HDMI does not wait for JPEG.
        hdmi,small,timing=self.prepare(frame,sequence,mode)
        began=time.monotonic();jpeg=self.encode(small)
        timing['jpeg_ms']=(time.monotonic()-began)*1000;timing['total_ms']+=timing['jpeg_ms']
        return hdmi,jpeg,timing
