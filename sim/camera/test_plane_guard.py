"""Synthetic checks protect geometry at boundaries and reject unsupported fits."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np,cv2
from plane_guard import improve
yy,xx=np.indices((360,320));domain=np.ones((360,320),bool)
image=np.full((360,320,3),180,np.uint8)
ideal=np.rint((30+.02*xx+.01*yy)*16).astype(np.int16)
q=ideal.copy();q[80:100,80:100]+=20*16
origin=np.zeros(q.shape,np.uint8);origin[150:180,150:180]=2;q[150:180,150:180]-=10*16
# A differently colored object is deliberately disconnected by image edges.
cv2.rectangle(image,(220,180),(300,300),(30,30,90),-1);q[180:301,220:301]=70*16
before=q.copy();out,changed,regions,report=improve(image,q,origin,domain)
assert np.max(abs(out[82:98,82:98].astype(int)-ideal[82:98,82:98]))<=1
assert np.max(abs(out[152:178,152:178].astype(int)-ideal[152:178,152:178]))<=1
assert np.array_equal(out[180:301,220:301],before[180:301,220:301])
assert np.array_equal(q,before) and np.all(out>=16)
unsupported,mask,_,_=improve(image,q,np.ones(q.shape,np.uint8),domain)
assert not mask.any() and np.array_equal(unsupported,q)
# Multiple incompatible depths on a uniform image must not become one plane.
mixed=((xx//12)%3*30+20)*16
mixed=mixed.astype(np.int16)
out2,mask2,_,_=improve(np.full_like(image,160),mixed,np.zeros_like(origin),domain)
assert not mask2.any() and np.array_equal(out2,mixed)
result={'passed':True,'slanted_plane_preserved':True,'spike_and_dent_corrected':True,
        'object_boundary_preserved':True,'no_holes_created':True,'no_support_no_change':True,
        'no_dominant_plane_no_change':True,'raw_input_unchanged':True}
(ROOT/'algorithm_tests.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
