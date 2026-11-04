"""Native-only surface pipeline versus preserved board reference, same photo."""
import os
os.environ['USB_SURFACE_NATIVE']='1'
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import hashlib,json,time
from pathlib import Path
import numpy as np
from board_surface import prepare
ROOT=Path(__file__).resolve().parent
with np.load(ROOT/'full_pipeline_result.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files if k!='metadata_json'}
with np.load(ROOT/'surface_result.npz',allow_pickle=False) as z:b={k:z[k] for k in z.files}
reference_meta=json.loads(b.pop('metadata_json').tobytes())
out,report=prepare(a,lambda stage,details:print(stage,flush=True))
checks={}
for name,expected in b.items():
    actual=out[name]
    assert actual.dtype==expected.dtype and actual.shape==expected.shape,name
    exact=actual.tobytes()==expected.tobytes()
    checks[name]={'shape':list(actual.shape),'dtype':str(actual.dtype),'exact_bytes':exact}
    assert exact,name+' changed'
assert set(out)==set(b)
report.update(passed=True,all_surface_arrays_bit_exact=True,checks=checks,reference_seconds=reference_meta['seconds'],
              reference_sha256=hashlib.sha256((ROOT/'surface_result.npz').read_bytes()).hexdigest(),
              library_sha256=hashlib.sha256((ROOT/'libsurface_native.so').read_bytes()).hexdigest(),
              code_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('surface_cleanup.py','surface_native.py','board_surface.py')})
np.savez_compressed(ROOT/'surface_native_result.npz',metadata_json=np.frombuffer(json.dumps(report).encode(),np.uint8),**out)
(ROOT/'surface_native_full_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':True,'seconds':report['seconds'],'stage_seconds':report['stage_seconds']}),flush=True)
