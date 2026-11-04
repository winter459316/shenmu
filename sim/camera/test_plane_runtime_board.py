"""Finite saved-photo transaction; hold live service in standby during PL access."""
import hashlib,io,json,time,uuid
from pathlib import Path
import numpy as np
import full_runtime
from plane_guard import improve
from switch_320_board import request
ROOT=Path(__file__).resolve().parent
def run():
    state=request(8788,'/stereo/status');assert not state['busy'] and not state['section_busy']
    reports=[]
    request(8788,'/standby',{'enabled':True})
    try:
        for filename in ('reference_photo.npz','baseline_photo.npz'):
            with np.load(ROOT/filename,allow_pickle=False) as z:a={k:z[k] for k in z.files}
            meta=json.loads(a.pop('metadata_json').tobytes())
            expected,changed,_,_=improve(a['rectified_left'],a['completed_disparity_q4'],a['completion_origin'],a['domain'])
            runtime=full_runtime.FullRuntime()
            runtime.engine.compute=lambda frame,progress,cancel:(dict(a),dict(meta))
            runtime.job_id=uuid.uuid4().hex;runtime.busy=True
            runtime._work(None,meta['camera_sequence'],meta['source_age_seconds'],runtime.job_id)
            assert runtime.stage=='ready',runtime.status()
            with np.load(io.BytesIO(runtime.package),allow_pickle=False) as z:
                for k,v in a.items():
                    if not k.startswith('dense'):assert z[k].tobytes()==v.tobytes(),k
                assert np.array_equal(z['dense3d_q4'],expected)
                assert np.all(z['dense_origin'][changed]==5)
                assert np.all(((z['dense3d_flags'][changed]>>8)&255)==3)
                assert np.array_equal(z['dense_depth_mm'],z['dense3d_xyz_q12'][:,:,2].astype(np.float32)/4096)
                # Independent floating Q reprojection, bound includes float32 precision.
                y,x=np.indices(expected.shape);h=np.stack((x,y,expected/16,np.ones(expected.shape)),axis=-1)@z['Q'].T
                ideal=h[:,:,:3]/h[:,:,3,None];actual=z['dense3d_xyz_q12'].astype(np.float64)/4096
                bound=np.abs(np.spacing(ideal.astype(np.float32))).astype(np.float64)+1/4096
                assert np.all(abs(actual-ideal)<=bound),'PL projection exceeds Q12/FP32 bounds'
                assert np.all(z['dense3d_flags']&1) and len(z['dense3d_faces'])==229042
            stem=filename.replace('_photo.npz','')
            (ROOT/(stem+'_replay.npz')).write_bytes(runtime.package)
            (ROOT/(stem+'_replay_status.json')).write_text(json.dumps(runtime.status()))
            reports.append({'input':filename,'job':runtime.job_id,'plane':runtime.metadata['plane_correction'],
                'geometry':runtime.metadata['dense_geometry'],'processing_seconds':runtime.metadata['processing_seconds'],
                'primary_arrays_exact':True,'corrected_q4_exact':True,'projection_passed':True})
        cancel=full_runtime.FullRuntime();cancel.engine=runtime.engine;cancel.cancel_event.set();cancel.busy=True
        cancel._work(None,meta['camera_sequence'],0,uuid.uuid4().hex)
        assert cancel.stage=='cancelled' and cancel.package is None
        report={'passed':True,'cancel_passed':True,'cases':reports,'no_new_shutter':True}
        (ROOT/'plane_replay_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    finally:
        request(8788,'/standby',{'enabled':state['standby']})
        assert request(8788,'/stereo/status')['result_id']==state['result_id']
if __name__=='__main__':run()
