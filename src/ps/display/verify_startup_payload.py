from pathlib import Path
import json,hashlib
H=Path('/tmp/usb_stereo_probe/pl_pipeline_20261025');R=H.parent/'fast_infer2'
p=H/'hdmi_addon_manifest_v4.json';blob=(H/'overlap_manifest_final.json').read_bytes();assert json.loads(p.read_bytes())==json.loads(blob)
for n,v in json.loads(blob).items():assert hashlib.sha256((H/n).read_bytes()).hexdigest()==v and hashlib.sha256((R/n).read_bytes()).hexdigest()==v,n
p.write_bytes(blob);print('OVERLAP_STARTUP_PAYLOADS_EXACT')
