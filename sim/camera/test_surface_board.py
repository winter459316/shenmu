"""One saved result through all four display layers on A53."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import hashlib,json,time,resource
from pathlib import Path
import numpy as np
from board_surface import prepare
ROOT=Path(__file__).resolve().parent
path=ROOT/'full_pipeline_result.npz';before=hashlib.sha256(path.read_bytes()).hexdigest()
with np.load(path) as z:a={k:z[k] for k in z.files if k!='metadata_json'}
out,report=prepare(a,lambda name,details:print(name,round(time.monotonic(),3),flush=True))
report.update(source_sha256=before,passed=True,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
report['code_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('board_surface.py','surface_cleanup.py','surface_detail.py','surface_holes.py','surface_projection.py')}
assert before==hashlib.sha256(path.read_bytes()).hexdigest()
np.savez_compressed(ROOT/'surface_result.npz',metadata_json=np.frombuffer(json.dumps(report).encode(),np.uint8),**out)
(ROOT/'surface_verified.json').write_text(json.dumps(report,indent=2));print('SURFACE_PASS',json.dumps(report),flush=True)
