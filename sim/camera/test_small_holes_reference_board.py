"""Finite A53 test of the exact reference photo supplied by the user.

Loads saved arrays only; no camera, PL registers, held-photo buffers or service
state are touched. The original files are hashed before/after.
"""
import hashlib,json,platform
from pathlib import Path
import cv2,numpy as np
from surface_small_holes import seal_small_holes,cell_counts
from test_small_holes import CONFIG,check_result
ROOT=Path(__file__).resolve().parent
expected={'full_pipeline_result.npz':'7b2937f1b76895516c79b4047406474c146214aeb3d16033d16ef3cc515cbabd',
          'surface_result.npz':'fd5a37bd3cbaf0e2b7e2210c78e79f1306fffe5bb6e43b98e0118f83c5fba8cc'}
def hashes():return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in expected}
assert hashes()==expected
with np.load(ROOT/'full_pipeline_result.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files}
with np.load(ROOT/'surface_result.npz',allow_pickle=False) as z:b={k:z[k] for k in z.files}
m=json.loads(a['metadata_json'].tobytes());assert m['frame_sha256_bgr'].startswith('1c69fd2a')
r=seal_small_holes(b['repaired_disparity_px'],b['repaired_valid'],b['repaired_xyz_mm'],b['repaired_faces'],b['repaired_origin'],b['preview_valid'],a['completed_disparity_q4'],a['Q'],CONFIG)
check_result(r,b['repaired_disparity_px'],b['repaired_valid'],b['repaired_xyz_mm'],b['repaired_origin'],b['preview_valid'],a['Q'])
assert hashes()==expected
counts={}
for label,f in [('before',b['repaired_faces']),('after',r['grid_faces'])]:
    c=cell_counts(f,(480,640));_,_,stats,_=cv2.connectedComponentsWithStats((c<2).astype('uint8'),8)
    counts[label]={str(k):int((stats[1:,4]<=k).sum()) for k in (4,16,64,256)}
report=dict(r['report'],passed=True,architecture=platform.machine(),frame_sha256_bgr=m['frame_sha256_bgr'],
            source_sha256=expected,small_gap_counts=counts,shutter_triggered=False,all_input_files_unchanged=True,
            code_sha256=hashlib.sha256((ROOT/'surface_small_holes.py').read_bytes()).hexdigest())
np.savez_compressed(ROOT/'small_holes_reference_result.npz',**{k:v for k,v in r.items() if k!='report'})
(ROOT/'small_holes_reference_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
