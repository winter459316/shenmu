"""Same-photo full runtime replay with preserved filling; only new PL projection runs."""
import hashlib,http.client,io,json,uuid
from pathlib import Path
import numpy as np
import full_runtime
from switch_320_board import request
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb320_fast3d'
def main():
    s=request(8786,'/stereo/status');assert not s['busy'] and not s['section_busy'];job=s['result_id']
    c=http.client.HTTPConnection('192.168.137.2',8786,timeout=30,source_address=('127.0.0.1',0))
    c.request('GET','/stereo/result.npz?id='+job);r=c.getresponse();assert r.status==200;data=r.read();c.close()
    assert hashlib.sha256(data).hexdigest()==s['metadata']['package_sha256']
    with np.load(io.BytesIO(data),allow_pickle=False) as z:a={k:z[k] for k in z.files}
    meta=json.loads(a.pop('metadata_json').tobytes());meta['test_only']=True
    display={k[8:]:v for k,v in a.items() if k.startswith('display_')};raw={k:v for k,v in a.items() if not k.startswith('display_')}
    (ROOT/'loaded.json').write_bytes((OLD/'loaded.json').read_bytes())
    runtime=full_runtime.FullRuntime();runtime.engine.compute=lambda frame,progress,cancel:(dict(raw),dict(meta))
    runtime.job_id=uuid.uuid4().hex;runtime.busy=True
    request(8786,'/standby',{'enabled':True})
    try:
        runtime._work(None,meta['camera_sequence'],meta['source_age_seconds'],runtime.job_id)
        status=runtime.status();assert status['stage']=='ready',status
        with np.load(io.BytesIO(runtime.package),allow_pickle=False) as z:
            for k,v in a.items():
                if not k.startswith('display_'):assert z[k].tobytes()==v.tobytes(),k
            assert not any(k.startswith('display_') for k in z.files)
            assert np.array_equal(z['dense3d_q4'],a['completed_disparity_q4'])
            assert np.isfinite(z['dense_depth_mm']).all()
            assert (z['dense_depth_mm']>0).all()
        (ROOT/'geometry_replay.npz').write_bytes(runtime.package)
        (ROOT/'geometry_replay_status.json').write_text(json.dumps(status))
        cancel=full_runtime.FullRuntime();cancel.engine=runtime.engine;cancel.cancel_event.set();cancel.busy=True
        cancel._work(None,meta['camera_sequence'],0,uuid.uuid4().hex)
        assert cancel.status()['stage']=='cancelled' and cancel.package is None
        report={'passed':True,'cancel_passed':True,'all_non_display_arrays_exact':True,'comparison_surfaces_removed':True,'previous_surface_seconds':meta['surface_preparation']['seconds'],'completed_q4_reused_exact':True,'previous_fill_seconds':meta['dense_fill']['seconds'],'fast_fill':runtime.metadata['dense_fill'],'source_job':job,
                'source_sha256':hashlib.sha256(data).hexdigest(),'sha256':hashlib.sha256(runtime.package).hexdigest(),
                'bitstream_sha256':meta['bitstream_sha256'],'dense_geometry':runtime.metadata['dense_geometry']}
        (ROOT/'dense_geometry_replay_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    finally:
        request(8786,'/standby',{'enabled':s['standby']})
        assert request(8786,'/stereo/status')['result_id']==job
if __name__=='__main__':main()
