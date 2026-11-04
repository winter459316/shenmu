"""Bind the USB PL geometry ROM to the measured calibration, never to vendor data."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]/'experiments/usb_camera_20261016'
sys.path.insert(0,str(SOURCE/'deps'))
import numpy as np
p=HERE/'stereo_parameters.json';raw=p.read_bytes();model=json.loads(raw)
assert model['eye_size']==[320,360] and model['units']=='mm'
q=np.asarray(model['Q'],np.float64);allowed=np.zeros((4,4),bool)
allowed[0,[0,3]]=True;allowed[1,[1,3]]=True;allowed[2,3]=True;allowed[3,[2,3]]=True
assert np.all(abs(q[~allowed])<1e-12)
digest=hashlib.sha256(raw).hexdigest();table=np.zeros((4,2048),np.int64);z=np.zeros(2048,np.int64)
d=np.arange(16,2033);den=q[3,2]*(d/16)+q[3,3];assert np.all(den>0)
for i,(row,col) in enumerate(((0,0),(0,3),(1,1),(1,3))):table[i,d]=np.floor(q[row,col]/den*2**24+.5).astype(np.int64)
z[d]=np.floor(q[2,3]/den*4096+.5).astype(np.int64)
assert np.all(abs(table)<2**47) and np.all(z<2**31)
errors=[]
for axis,size in ((0,320),(1,360)):
    u=np.arange(size)[:,None]
    got=(u*table[2*axis,d]+table[2*axis+1,d]+2048)>>12
    ideal=(q[axis,axis]*u+q[axis,3])/den
    errors.append(float(np.max(abs(got/4096-ideal))))
errors.append(float(np.max(abs(z[d]/4096-q[2,3]/den))))
assert max(errors)<.00025,errors
header='#pragma once\n#include <ap_int.h>\nstatic const unsigned GEOMETRY_TAG=0x'+digest[:8]+'U;\n'
header+='static const double GEOMETRY_Q[16]={'+','.join(format(v,'.17g') for v in q.flat)+'};\n'
header+='static const ap_int<48> coefficients[4][2048]={\n'+',\n'.join('{'+','.join(str(v)+'LL' for v in row)+'}' for row in table)+'};\n'
header+='static const ap_int<32> zcoeff[2048]={'+','.join(str(v) for v in z)+'};\n'
(HERE/'geometry_calibration.hpp').write_text(header,'ascii')
record={'calibration_sha256':digest,'tag':int(digest[:8],16),'positive_q4_range':[16,2032],
        'all_native_pixel_coordinates_checked':True,'max_error_mm_xyz':errors,
        'header_sha256':hashlib.sha256(header.encode()).hexdigest(),'output':'signed Q12 mm'}
(HERE/'geometry_coefficients_verified.json').write_text(json.dumps(record,indent=2),'utf8')
print(json.dumps(record))
