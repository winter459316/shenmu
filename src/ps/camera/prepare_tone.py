"""Preserve stable source, capture one diagnostic frame, compare the display curve."""
import hashlib,json,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import cv2,numpy as np
from tone_map import apply,LUT
OLD=ROOT.parent/'usb_320_exposure'
old={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OLD.iterdir() if p.is_file()
     and p.suffix in ('.py','.so','.dll','.html','.npz','.bin')}
(ROOT/'PRESERVED_EXPOSURE_SHA256.json').write_text(json.dumps(old,indent=2))
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    with opener.open('http://192.168.137.2:8788'+path,timeout=15) as r:return r.read()
status=json.loads(get('/stereo/status'));assert not status['busy'] and not status['section_busy']
(ROOT/'before_status.json').write_text(json.dumps(status,indent=2))
raw=get('/snapshot.png');(ROOT/'tone_input.png').write_bytes(raw)
image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
assert image.shape==(480,1280,3)
before=image.copy();out=apply(image)
assert np.array_equal(image,before) and np.all(np.diff(LUT.astype(int))>=0)
assert out.max()<=248 and LUT[0]==0
cv2.imwrite(str(ROOT/'tone_output.png'),out)
rows=[]
for frame,label in ((image,'ORIGINAL / auto exposure'),(out,'SHADOW LIFT / soft highlights')):
    row=np.zeros((526,1280,3),np.uint8);row[:480]=frame
    cv2.putText(row,label,(18,512),cv2.FONT_HERSHEY_SIMPLEX,.8,(235,235,235),2)
    rows.append(row)
cv2.imwrite(str(ROOT/'tone_comparison.jpg'),np.vstack(rows),[cv2.IMWRITE_JPEG_QUALITY,92])
gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY);newgray=cv2.cvtColor(out,cv2.COLOR_BGR2GRAY)
shadow=(gray>=12)&(gray<70);highlight=gray>=220
report={'source_frame_only_not_photo':True,'input_pixels_unchanged':True,
        'shadow_pixels':int(shadow.sum()),'shadow_mean_before':float(gray[shadow].mean()),
        'shadow_mean_after':float(newgray[shadow].mean()),
        'highlight_mean_before':float(gray[highlight].mean()),'highlight_mean_after':float(newgray[highlight].mean()),
        'source_saturated_channel_pixels':int(np.any(image==255,axis=2).sum()),
        'result_saturated_channel_pixels':int(np.any(out==255,axis=2).sum()),
        'saturated_detail_recovered':False}
(ROOT/'tone_comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
