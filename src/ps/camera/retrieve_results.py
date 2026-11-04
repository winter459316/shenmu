import hashlib,json,sys,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
DEFAULT=('hardware_verified.json','hardware_result.npz','loaded.json','core_identities_verified.json','dma_reservation_verified.json','hardware_test.log')
ALLOWED=set(DEFAULT)|{'completion_verified.json','completion_result.npz','completion_test.log','full_pipeline_result.npz','full_pipeline_verified.json','full_pipeline_test.log','completion_cancel_verified.json'}
names=sys.argv[1:] or DEFAULT
ALLOWED|={'surface_result.npz','surface_verified.json','surface_test.log','packing_low_verified.json','packing_test.log'}
ALLOWED|={'surface_native_result.npz','surface_native_verified.json','surface_native_full_verified.json','native_surface_test.log','native_surface_full.log'}
ALLOWED|={'surface_holes_profile.json','surface_holes_profile.log'}
ALLOWED|={'small_holes_result.npz','small_holes_verified.json'}
ALLOWED|={'small_holes_reference_result.npz','small_holes_reference_verified.json'}
ALLOWED|={'sgm_v4_result.npz','sgm_v4_verified.json','sgm_v4_test.log'}
ALLOWED|={'sgm_v4_full_result.npz','sgm_v4_full_verified.json','sgm_v4_full_test.log','sgm_v4_full_compat_failure.json'}
ALLOWED|={'hdmi_full_result.npz','hdmi_full_verified.json','hdmi_full_test.log'}
ALLOWED|={'hdmi_before_activation.zip','hdmi_activation.json','hdmi_service_active.json','physical_keys_status.json','physical_keys_hdmi.log'}
ALLOWED|={'preview_before_update.zip','preview_service_active.json'}
ALLOWED|={'photo_speed_mesh_verified.json','photo_speed_full_verified.json','photo_speed_update_verified.json','photo_archive_verified.json','photo_stored_result.npz','photo_speed_before_update.zip','photo_speed_service_active.json'}
ALLOWED|={'pipeline_320_result.npz','pipeline_320_verified.json','pipeline_320.log','activation_320.json','completion_320_reference.json'}
assert set(names)<=ALLOWED
print(command('python3 /tmp/usb_stereo_probe/usb320/serve_results.py '+' '.join(names)+' >/tmp/usb_stereo_probe/usb320/transfer.log 2>&1 & echo READY',8))
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));out=HERE/'board_evidence';out.mkdir(exist_ok=True)
hashes=json.loads((out/'sha256.json').read_text()) if (out/'sha256.json').exists() else {}
for name in names:
    with opener.open('http://192.168.137.2:8769/'+name,timeout=20) as r:data=r.read()
    (out/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
(out/'sha256.json').write_text(json.dumps(hashes,indent=2),'utf8')
print('RETRIEVED',','.join(names))
