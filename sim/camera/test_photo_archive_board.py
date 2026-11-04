"""Finite lossless archive timing, using the preserved photo only."""
import os,json,time,hashlib,io
from pathlib import Path
import numpy as np
from result_archive import pack_result
ROOT=Path(__file__).resolve().parent
with np.load(ROOT/'held_restore.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files}
metadata=json.loads(a.pop('metadata_json').tobytes())
records=[]
for mode in ('0','1'):
    os.environ['USB_ARCHIVE_STORED']=mode;t=time.monotonic();data=pack_result(a,metadata);seconds=time.monotonic()-t
    with np.load(io.BytesIO(data),allow_pickle=False) as z:
        assert set(z.files)==set(a)|{'metadata_json'}
        for k,v in a.items():assert z[k].shape==v.shape and z[k].dtype==v.dtype and z[k].tobytes()==v.tobytes(),k
        assert json.loads(z['metadata_json'].tobytes())==metadata
    records.append({'stored':mode=='1','seconds':seconds,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    if mode=='1':(ROOT/'photo_stored_result.npz').write_bytes(data)
report={'passed':True,'all_arrays_exact':True,'members':len(a)+1,'samples':records,'shutter_triggered':False}
(ROOT/'photo_archive_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
