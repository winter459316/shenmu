import hashlib,json,time
from pathlib import Path
import cv2,numpy as np
from preview_rectify import PreviewRectifier
ROOT=Path(__file__).resolve().parent
fast=PreviewRectifier();assert fast.native is not None
reference=PreviewRectifier();reference.native=None
rng=np.random.RandomState(71)
frames=[np.load(str(ROOT/'profile_native.npy')),rng.randint(0,256,(480,1280,3)).astype(np.uint8),
        np.zeros((480,1280,3),np.uint8),np.full((480,1280,3),255,np.uint8)]
# Test exact half-way rounding with all consecutive input intensities.
frames.append(np.resize(np.arange(256,dtype=np.uint8),(480,1280,3)))
rows=[]
for frame in frames:
    old_area=np.concatenate([cv2.resize(frame[:,e*640:(e+1)*640],(320,360),interpolation=cv2.INTER_AREA) for e in (0,1)],axis=1)
    new_area=np.empty_like(old_area);fast.native.preview_area(frame.ctypes.data,new_area.ctypes.data)
    assert new_area.tobytes()==old_area.tobytes(),('resize mismatch',int(np.count_nonzero(new_area!=old_area)))
    before=frame.tobytes();t=time.monotonic();got=fast.rectified(frame);elapsed=time.monotonic()-t
    wanted=reference.rectified(frame)
    assert got.tobytes()==wanted.tobytes(),('rectify mismatch',int(np.count_nonzero(got!=wanted)))
    assert frame.tobytes()==before
    rows.append({'native_ms':elapsed*1000,'sha256':hashlib.sha256(got.tobytes()).hexdigest()})
report={'passed':True,'area_and_rectification_byte_exact':True,'cases':rows,'native_sha256':hashlib.sha256((ROOT/'preview_native.so').read_bytes()).hexdigest()}
(ROOT/'preview_native_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
