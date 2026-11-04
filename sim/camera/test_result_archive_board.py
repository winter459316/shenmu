"""One fixed-result comparison of old/new lossless packing; no capture or DMA."""
import hashlib,io,json,time
from pathlib import Path
import numpy as np
from result_archive import pack_result
ROOT=Path(__file__).resolve().parent
with np.load(ROOT/'full_pipeline_result.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files}
with np.load(ROOT/'surface_result.npz',allow_pickle=False) as z:b={k:z[k] for k in z.files}
meta=json.loads(a.pop('metadata_json').tobytes());meta['surface_preparation']=json.loads(b.pop('metadata_json').tobytes())
a.update({'display_'+k:v for k,v in b.items()})
start=time.monotonic();buf=io.BytesIO();np.savez_compressed(buf,metadata_json=np.frombuffer(json.dumps(meta).encode(),np.uint8),**a)
old_seconds=time.monotonic()-start;old_size=len(buf.getvalue());del buf
start=time.monotonic();new=pack_result(a,meta);new_seconds=time.monotonic()-start
with np.load(io.BytesIO(new),allow_pickle=False) as z:
    assert set(z.files)==set(a)|{'metadata_json'} and json.loads(z['metadata_json'].tobytes())==meta
    for k,v in a.items():
        actual=z[k];assert actual.dtype==v.dtype and actual.shape==v.shape and actual.tobytes()==v.tobytes(),k
report={'passed':True,'all_array_bytes_exact':True,'array_count':len(a),'old_compression6_seconds':old_seconds,
        'new_compression1_seconds':new_seconds,'old_bytes':old_size,'new_bytes':len(new),
        'speedup':old_seconds/new_seconds,'input_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('full_pipeline_result.npz','surface_result.npz')},
        'scope':'Fixed-result packing only; camera runtime not changed by this test.'}
(ROOT/'packing_low_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
