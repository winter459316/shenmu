from pathlib import Path
import hashlib,json,sys
H=Path('/tmp/usb_stereo_probe/pl_pipeline_20261025');R=H.parent/'fast_infer2';S=H.parent/'usb320_hdmifps';sys.path[:0]=[str(H),str(S),str(R)]
from install_hdmi_v4 import process,terminate,launch
from switch_320_board import owners
assert not (R/'pl_test_private_snapshot.json').exists()
blob=(H/'overlap_api_final.py').read_bytes()
for root in (H,R):
 p=root/'hdmi_job_server_v4.py';assert hashlib.sha256(p.read_bytes()).hexdigest() in ['d2af7afe6f7df902f80bb01a6dcf245c3b56dda0d99ddaf618462ebc37253985', '26db55df6c1748ebe9fd24495ad4b49826d8ba594d13497cdaa17f9e251f3f6f', 'b109b160218f41b7a1c0a9e8e57d6255788c06a2b75d9413dc33304f85b7273a'];p.write_bytes(blob)
(H/'install_hdmi_v4.py').write_bytes((H/'overlap_install_final.py').read_bytes())
m=H/'hdmi_addon_manifest_v4.json';d=json.loads(m.read_text());d['hdmi_job_server_v4.py']=hashlib.sha256(blob).hexdigest();m.write_text(json.dumps(d,indent=2))
for n,v in d.items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==v,n
for item in process('hdmi_job_server_v4.py'):terminate(item)
launch('hdmi_job_server_v4.py',owners()['full_camera.py']['env'])
print('FINAL_PAYLOAD_HASHES_VERIFIED')
