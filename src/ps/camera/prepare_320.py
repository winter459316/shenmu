"""Derive low-resolution calibration with OpenCV resize pixel-centre convention."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_full'
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
raw=(OLD/'stereo_parameters.json').read_bytes();p=json.loads(raw)
assert p['eye_size']==[640,480]
(ROOT/'native_stereo_parameters.json').write_bytes(raw)
S=np.array([[.5,0,-.25],[0,.75,-.125],[0,0,1.]])
T=np.array([[2.,0,0,.5],[0,4/3,0,1/6],[0,0,2.,0],[0,0,0,1.]])
for name in ('K1','K2','P1','P2'):p[name]=(S@np.array(p[name])).tolist()
p['Q']=(np.array(p['Q'])@T).tolist();p['eye_size']=[320,360]
p['derived_from_sha256']=hashlib.sha256(raw).hexdigest()
p['resampling']={'native_eye_size':[640,480],'size':[320,360],'method':'INTER_AREA before rectification','pixel_center_transform':S.tolist()}
# Check sparse Q and scaled P agree over 320x360 and multiple disparities.
y,x=np.indices((360,320));xx=x.ravel()[::97];yy=y.ravel()[::97]
for disparity in (1.,3.5,20.,63.,127.):
    h=np.column_stack((xx,yy,np.full(len(xx),disparity),np.ones(len(xx))))@np.array(p['Q']).T
    xyz=h[:,:3]/h[:,3,None]
    for eye in (0,1):
        proj=np.column_stack((xyz,np.ones(len(xx))))@np.array(p['P'+str(eye+1)]).T
        assert abs(proj[:,:2]/proj[:,2,None]-np.column_stack((xx-eye*disparity,yy))).max()<1e-9
(ROOT/'stereo_parameters.json').write_text(json.dumps(p,indent=2),'utf8')
digest=hashlib.sha256((ROOT/'stereo_parameters.json').read_bytes()).hexdigest()
# Reuse coefficient generator arithmetic, binding only this new calibration.
s=(OLD/'generate_geometry.py').read_text().replace("p=SOURCE/'stereo_parameters.json'","p=HERE/'stereo_parameters.json'").replace('[640,480]','[320,360]').replace('((0,640),(1,480))','((0,320),(1,360))')
(ROOT/'generate_geometry.py').write_text(s)
s=(OLD/'generate_usb_maps.py').read_text().replace('a3a4a2efb24de9c476465a3649092917f7c1f9daf1936da8aa97433e153b2d36',digest).replace('[640,480]','[320,360]').replace('(640,480)','(320,360)').replace('x<639','x<319').replace('y<479','y<359')
(ROOT/'generate_usb_maps.py').write_text(s)
print('DERIVED_320_CALIBRATION',digest)
