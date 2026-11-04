"""One-time adaptation of the isolated baseline copy; never edit usb_full."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
digest=hashlib.sha256((ROOT/'stereo_parameters.json').read_bytes()).hexdigest()
with np.load(ROOT/'rectification_maps.npz') as z:maps=hashlib.sha256(z['map0'].tobytes()+z['map1'].tobytes()).hexdigest()
runtime=('usb_full_engine.py','board_dma.py','board_geometry.py','board_completion.py','full_runtime.py','full_camera.py','full_host.py','live_verify.py','verify_full_pipeline_pc.py','render_saved.py','restore_held.py','physical_keys.py','deploy.py','serve_results.py','retrieve_results.py','start_full_camera.py','save_held_for_update.py')
for name in runtime:
    p=ROOT/name;s=p.read_text()
    s=s.replace('/tmp/usb_stereo_probe/full_v2','/tmp/usb_stereo_probe/usb320')
    s=s.replace('8767','8768').replace('PORT=8771','PORT=8772')
    s=s.replace('a3a4a2efb24de9c476465a3649092917f7c1f9daf1936da8aa97433e153b2d36',digest)
    s=s.replace('0xa3a4a2ef','0x'+digest[:8]).replace('W,H=640,480','W,H=320,360').replace('W,H,D=640,480,128','W,H,D=320,360,128').replace('H,W=480,640','H,W=360,320')
    if name in ('render_saved.py','restore_held.py','verify_full_pipeline_pc.py'):
        s=s.replace('[640,480]','[320,360]').replace('(640,480)','(320,360)').replace('(480,640','(360,320')
    if name=='usb_full_engine.py':
        s=s.replace('352d54ec367a1f6bff0c7a403d9540d1d66dd3585608ea25a8b68ee14e47fba4',maps)
        s=s.replace("if frame.dtype!=np.uint8 or frame.shape!=(H,W*2,3):raise ValueError('Expected native 1280x480 USB frame')", "if frame.dtype!=np.uint8 or frame.shape!=(480,1280,3):raise ValueError('Expected native USB capture')\n        native_digest=hashlib.sha256(frame.tobytes()).hexdigest()\n        frame=np.concatenate([cv2.resize(frame[:,eye*640:(eye+1)*640],(W,H),interpolation=cv2.INTER_AREA) for eye in (0,1)],axis=1)")
        s=s.replace("'frame_sha256_bgr':hashlib.sha256(frame.tobytes()).hexdigest()", "'native_frame_sha256_bgr':native_digest,'native_capture_size':[1280,480],'resampling':'INTER_AREA before PL rectification','frame_sha256_bgr':hashlib.sha256(frame.tobytes()).hexdigest()")
    if name=='verify_full_pipeline_pc.py':s=s.replace('eye*640:(eye+1)*640','eye*320:(eye+1)*320')
    if name=='full_host.py':s=s.replace('i%640,i//640','i%320,i//320')
    # Shared hardware exclusion remains common across both projects.
    if name=='board_dma.py':s=s.replace("open('/tmp/usb_stereo_probe/usb320/dma.lock'","open('/tmp/usb_stereo_probe/full_v2/dma.lock'")
    p.write_text(s)
p=ROOT/'hr_completion.h';p.write_text(p.read_text().replace('#define HR_W 640','#define HR_W 320').replace('#define HR_H 480','#define HR_H 360'))
p=ROOT/'full_control.html';s=p.read_text().replace('每眼 640 × 480','计算每眼 320 × 360').replace('拍照仍使用每眼 640 × 480','矫正、匹配和三维均使用每眼 320 × 360');p.write_text(s)
print('ISOLATED_RUNTIME_320_ADAPTED',digest,maps)
