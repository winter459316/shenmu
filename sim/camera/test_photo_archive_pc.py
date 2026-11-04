"""One measured wired transfer per archive and independent byte comparison."""
import hashlib,io,json,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
from board_console import command
import numpy as np
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(url):
    began=time.monotonic()
    with opener.open(url,timeout=30) as r:data=r.read()
    return data,time.monotonic()-began
state=json.loads(get('http://192.168.137.2:8767/stereo/status')[0])
assert not state['busy'];job=state['result_id']
old,old_seconds=get('http://192.168.137.2:8767/stereo/result.npz?id='+job)
assert hashlib.sha256(old).hexdigest()==state['metadata']['package_sha256']
print(command('python3 /tmp/usb_stereo_probe/full_v2/serve_results.py photo_stored_result.npz >/tmp/usb_stereo_probe/full_v2/photo_archive_transfer.log 2>&1 & echo READY',8))
new,new_seconds=get('http://192.168.137.2:8769/photo_stored_result.npz')
with np.load(io.BytesIO(old),allow_pickle=False) as a,np.load(io.BytesIO(new),allow_pickle=False) as b:
    assert set(a.files)==set(b.files)
    for k in a.files:assert a[k].dtype==b[k].dtype and a[k].shape==b[k].shape and a[k].tobytes()==b[k].tobytes(),k
report={'passed':True,'all_52_arrays_and_metadata_byte_exact':True,'held_job':job,
    'compressed_transfer_seconds':old_seconds,'stored_transfer_seconds':new_seconds,
    'compressed_bytes':len(old),'stored_bytes':len(new),'stored_sha256':hashlib.sha256(new).hexdigest(),
    'shutter_triggered':False}
(ROOT/'board_evidence/photo_archive_network_verified.json').write_text(json.dumps(report,indent=2),'utf8')
print(json.dumps(report,indent=2))
