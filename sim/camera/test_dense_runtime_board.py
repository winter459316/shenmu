"""Finite lifecycle replay; all existing PL/photo arrays are held inputs, no shutter or DMA."""
import hashlib,http.client,io,json,uuid
from pathlib import Path
import numpy as np
import full_runtime
from switch_320_board import request
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb320'
def main():
    s=request(8768,'/stereo/status');assert not s['busy'] and not s['section_busy'];job=s['result_id']
    c=http.client.HTTPConnection('192.168.137.2',8768,timeout=30,source_address=('127.0.0.1',0))
    c.request('GET','/stereo/result.npz?id='+job);r=c.getresponse();assert r.status==200;data=r.read();c.close()
    assert hashlib.sha256(data).hexdigest()==s['metadata']['package_sha256']
    with np.load(io.BytesIO(data),allow_pickle=False) as z:a={k:z[k] for k in z.files}
    metadata=json.loads(a.pop('metadata_json').tobytes());metadata['test_only']=True
    display={k[8:]:v for k,v in a.items() if k.startswith('display_')};raw={k:v for k,v in a.items() if not k.startswith('display_')}
    (ROOT/'loaded.json').write_bytes((OLD/'loaded.json').read_bytes())
    full_runtime.prepare=lambda arrays,progress,cancel:(display,metadata['surface_preparation'])
    runtime=full_runtime.FullRuntime();runtime.engine.compute=lambda frame,progress,cancel:(dict(raw),dict(metadata))
    runtime.job_id=uuid.uuid4().hex;runtime.busy=True
    runtime._work(None,metadata['camera_sequence'],metadata['source_age_seconds'],runtime.job_id)
    status=runtime.status();assert status['stage']=='ready',status
    with np.load(io.BytesIO(runtime.package),allow_pickle=False) as z:
        for k,value in a.items():assert z[k].dtype==value.dtype and z[k].shape==value.shape and z[k].tobytes()==value.tobytes(),k
    (ROOT/'dense_replay.npz').write_bytes(runtime.package)
    (ROOT/'dense_replay_status.json').write_text(json.dumps(status))
    cancel=full_runtime.FullRuntime();cancel.engine=runtime.engine;cancel.cancel_event.set();cancel.busy=True
    cancel._work(None,metadata['camera_sequence'],0,uuid.uuid4().hex)
    assert cancel.status()['stage']=='cancelled' and cancel.package is None
    report={'passed':True,'cancel_passed':True,'original_arrays_exact':True,'source_job':job,
            'source_sha256':hashlib.sha256(data).hexdigest(),'sha256':hashlib.sha256(runtime.package).hexdigest(),
            'bitstream_sha256':metadata['bitstream_sha256'],'dense_fill':runtime.metadata['dense_fill']}
    (ROOT/'dense_replay_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if __name__=='__main__':main()
