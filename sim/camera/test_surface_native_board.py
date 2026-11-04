"""Finite same-input precision and time checks; production service is untouched."""
import hashlib,json,time,traceback
from pathlib import Path
import numpy as np
import surface_cleanup,surface_detail,board_surface
from surface_native import plane_filter_native
ROOT=Path(__file__).resolve().parent
reference=surface_cleanup.plane_filter
records=[]
def compare(d,valid,confidence,rgb,config,cancel=None):
    start=time.monotonic();expected=reference(d,valid,confidence,rgb,config,cancel);old=time.monotonic()-start
    start=time.monotonic();actual=plane_filter_native(d,valid,confidence,rgb,config,cancel,threads=3);new=time.monotonic()-start
    different=actual.view(np.uint32)!=expected.view(np.uint32)
    record={'shape':list(d.shape),'radius':config.radius,'reference_seconds':old,'native_seconds':new,'different_pixels':int(different.sum()),
            'max_abs_difference_px':float(abs(actual-expected).max()),'exact_bytes':actual.tobytes()==expected.tobytes()}
    records.append(record);print(json.dumps(record),flush=True)
    if different.any():
        np.savez_compressed(ROOT/'native_plane_difference.npz',d=d,valid=valid,confidence=confidence,rgb=rgb,expected=expected,actual=actual)
        raise AssertionError('Native plane is not bit-exact')
    return expected
try:
    rng=np.random.RandomState(39);y,x=np.indices((24,32));d=(25+.03*x+.02*y).astype(np.float32)
    for radius in (1,3):
        config=surface_cleanup.SurfaceConfig(radius=radius)
        compare(d,np.ones(d.shape,bool),np.ones(d.shape,np.float32),np.full(d.shape+(3,),128,np.float32),config)
        mask=rng.random_sample(d.shape)>.2
        compare(d+rng.normal(0,.15,d.shape).astype(np.float32),mask,rng.random_sample(d.shape).astype(np.float32),rng.randint(0,256,d.shape+(3,)).astype(np.float32),config)
    surface_cleanup.plane_filter=compare;surface_detail.plane_filter=compare
    with np.load(ROOT/'full_pipeline_result.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files if k!='metadata_json'}
    _,report=board_surface.prepare(a)
    result={'passed':True,'all_plane_outputs_bit_exact':True,'calls':records,'surface_report':report,
            'library_sha256':hashlib.sha256((ROOT/'libsurface_native.so').read_bytes()).hexdigest()}
except Exception as exc:
    result={'passed':False,'error':str(exc),'calls':records};traceback.print_exc()
(ROOT/'surface_native_verified.json').write_text(json.dumps(result,indent=2));print(json.dumps({'passed':result['passed'],'calls':len(records)}),flush=True)
if not result['passed']:raise SystemExit(1)
