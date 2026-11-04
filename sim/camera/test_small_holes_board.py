"""One held photo only: board A53 sealing, no camera open and no shutter."""
import hashlib,http.client,io,json,platform,time
from pathlib import Path
import numpy as np
from surface_small_holes import seal_small_holes,cell_counts
from test_small_holes import CONFIG,check_result,geometric_tests
import cv2
ROOT=Path(__file__).resolve().parent
JOB='6bed0c1a3fcd43a08fcbb8ff69838f67'
def get(path):
    c=http.client.HTTPConnection('192.168.137.2',8767,timeout=20,source_address=('127.0.0.1',0))
    try:
        c.request('GET',path);r=c.getresponse();data=r.read();assert r.status==200;return data
    finally:c.close()
tests=geometric_tests();status=json.loads(get('/stereo/status'))
assert status['result_id']==JOB and status['job_id']==JOB and not status['busy'] and not status['section_busy']
data=get('/stereo/result.npz?id='+JOB);source=hashlib.sha256(data).hexdigest()
assert source==status['metadata']['package_sha256']
with np.load(io.BytesIO(data),allow_pickle=False) as z:a={k:z[k] for k in z.files}
before={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in a.items()}
names=('display_repaired_disparity_px','display_repaired_valid','display_repaired_xyz_mm','display_repaired_faces','display_repaired_origin','display_preview_valid','completed_disparity_q4','Q')
r=seal_small_holes(*[a[k] for k in names],config=CONFIG)
check_result(r,a[names[0]],a[names[1]],a[names[2]],a[names[4]],a[names[5]],a['Q'])
assert before=={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in a.items()},'Input changed'
after=json.loads(get('/stereo/status'));assert after['job_id']==JOB and after['metadata']['package_sha256']==source
counts={}
for label,f in [('before',a[names[3]]),('after',r['grid_faces'])]:
    cells=cell_counts(f,(480,640));n,labels,stats,_=cv2.connectedComponentsWithStats((cells<2).astype('uint8'),8)
    counts[label]={str(k):int((stats[1:,4]<=k).sum()) for k in (4,16,64,256)}
report=dict(r['report'],passed=True,geometric_tests=tests,small_gap_counts=counts,job_id=JOB,source_sha256=source,
            architecture=platform.machine(),all_input_arrays_unchanged=True,shutter_triggered=False,
            code_sha256=hashlib.sha256((ROOT/'surface_small_holes.py').read_bytes()).hexdigest())
np.savez_compressed(ROOT/'small_holes_result.npz',**{k:v for k,v in r.items() if k!='report'})
(ROOT/'small_holes_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
