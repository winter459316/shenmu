"""Version acceptance gates and unchanged historical photo acceptance."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
from hardware_catalog import STABLE_SHA,WINDOW_V4_SHA,HDMI_V1_SHA,variant,loaded_variant,result_variant
def reject(fn,*args):
    try:fn(*args)
    except ValueError:return
    raise AssertionError('Invalid hardware was accepted')
assert result_variant({'bitstream_sha256':STABLE_SHA})['sgm_revision'] is None
assert result_variant({'bitstream_sha256':WINDOW_V4_SHA,'sgm_revision':0x53574E34})['name']=='usb_full_sgm_window_v4'
assert result_variant({'bitstream_sha256':HDMI_V1_SHA,'sgm_revision':0x53574E34})['hdmi']
reject(result_variant,{'bitstream_sha256':HDMI_V1_SHA})
reject(variant,'0'*64);reject(variant,None)
reject(loaded_variant,{'sha256':STABLE_SHA,'version':'usb_full_v2','state':'programming'})
reject(result_variant,{'bitstream_sha256':WINDOW_V4_SHA})
reject(result_variant,{'bitstream_sha256':WINDOW_V4_SHA,'sgm_revision':0x53574E33})
reject(result_variant,{'bitstream_sha256':STABLE_SHA,'hardware_variant':'usb_full_sgm_window_v4'})
from live_verify import unpack,np
job='6bed0c1a3fcd43a08fcbb8ff69838f67';p=ROOT/'live_captures'/job/'board_result.npz';data=p.read_bytes()
with np.load(p,allow_pickle=False) as z:m=json.loads(z['metadata_json'].tobytes())
status={'job_id':job,'result_id':job,'busy':False,'metadata':dict(m,package_sha256=hashlib.sha256(data).hexdigest(),package_bytes=len(data))}
arrays,metadata,digest=unpack(data,status,job)
assert metadata['bitstream_sha256']==STABLE_SHA and len(arrays)==51
report={'passed':True,'old_live_package_accepted':True,'unknown_or_mislabelled_hardware_rejected':True,
        'new_variant_requires_hardware_revision':True,'hardware_loaded':False,'production_restarted':False}
(ROOT/'board_evidence/hardware_catalog_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
