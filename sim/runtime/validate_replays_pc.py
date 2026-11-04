"""Two finite saved-photo trials, with independent correctness and 2/4/8 comparisons."""
from pathlib import Path
import hashlib,json,sys,time,urllib.request,uuid
import numpy as np
from export_capture import export
R=Path(__file__).resolve().parent;P=R.parents[1];E=P/'experiments/fast_iter2_20261020'
B4=R.parent/'usb_fast_mixed4';B8=R.parent/'usb_fast_mixed'
sys.path.insert(0,str(P/'experiments/usb_camera_20261016'))
from board_console import command
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
URL='http://192.168.137.2:8850'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
write=lambda p,v:p.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf8')
def get(path):
    with OP.open(URL+path,timeout=30) as f:return f.read()
def compare(now,old):
    with np.load(now/'board_result.npz') as a,np.load(old/'board_result.npz') as b:
        exact={n:bool(np.array_equal(a[n],b[n],equal_nan=True)) for n in
               ('native_bgr','rectified_left','rectified_right','Q','P1','P2','domain')}
        assert all(exact.values()),exact
        domain=a['domain'];delta=np.abs(a['disparity'].astype(np.float64)-b['disparity'])[domain]
        common=a['valid']&b['valid'];window=common&(b['depth_mm']>=200)&(b['depth_mm']<=3000)
        assert window.sum()>100
        dz=np.abs(a['depth_mm'][window].astype(np.float64)-b['depth_mm'][window])/10
        numerical=dict(disparity_mean_px=float(delta.mean()),disparity_p95_px=float(np.percentile(delta,95)),
            disparity_p99_px=float(np.percentile(delta,99)),disparity_max_px=float(delta.max()),
            above1px_percent=float((delta>1).mean()*100),above3px_percent=float((delta>3).mean()*100),
            depth_window_p50_cm=float(np.percentile(dz,50)),depth_window_p95_cm=float(np.percentile(dz,95)),
            depth_window_p99_cm=float(np.percentile(dz,99)),
            valid_pixels2=int(a['valid'].sum()),valid_pixels_baseline=int(b['valid'].sum()),
            validity_changed_pixels=int(np.count_nonzero(a['valid']!=b['valid'])))
    with np.load(now/'geometry.npz') as a,np.load(old/'geometry.npz') as b:
        f1=np.ascontiguousarray(a['faces']).view('V12').ravel();f2=np.ascontiguousarray(b['faces']).view('V12').ravel()
        surface=dict(triangles2=len(f1),triangles_baseline=len(f2),changed_fraction=len(np.setxor1d(f1,f2))/max(1,len(f2)))
    return dict(exact_inputs=exact,numerical=numerical,surface=surface)
if __name__=='__main__':
    assert read(R/'hardware_verified.json')['timing_passed']
    assert json.loads(get('/health'))['ready']
    bases=read(B4/'replays_verified.json')['cases'];records=[]
    for base in bases:
        source=base['source_job_id'];job=uuid.uuid4().hex
        write(R/'replay_job.json',dict(job_id=job,source_job_id=source))
        out=command('python3 -u /tmp/usb_stereo_probe/fast_infer2/fast_capture_board.py '+job+' --replay '+source+
           ' >/tmp/usb_stereo_probe/fast_infer2/replay_'+job+'.log 2>&1 & echo ITER2_REPLAY_STARTED',10)
        assert 'ITER2_REPLAY_STARTED' in out
        deadline=time.monotonic()+500;last=None
        while time.monotonic()<deadline:
            s=json.loads(get('/status?id='+job))
            if s['stage']!=last:print(job[:8],s['stage'],flush=True);last=s['stage']
            assert not s.get('error'),s
            if s['stage']=='ready':break
            time.sleep(1)
        else:raise TimeoutError('Inspect active job; do not start another')
        assert s['quality_passed'] and s['stable_restored']
        payload=get('/result?id='+job);assert hashlib.sha256(payload).hexdigest()==s['package_sha256']
        folder=R/'captures'/job;folder.mkdir(parents=True)
        (folder/'board_result.npz').write_bytes(payload);write(folder/'board_status.json',s)
        report=export(folder,s);report.update(replay_only=True,source_job_id=source)
        write(folder/'report.json',report)
        with np.load(folder/'board_result.npz') as a:
            d=a['disparity'].astype(np.float64);ref=np.load(E/(source+'_reference2.npy'))
            error=np.abs(d-ref)
            implementation=dict(mean_px=float(error.mean()),p99_px=float(np.percentile(error,99)),max_px=float(error.max()))
            implementation['passed']=bool(implementation['mean_px']<=.01 and implementation['p99_px']<=.05 and implementation['max_px']<=1)
            assert implementation['passed'],implementation
        result=dict(functional_passed=True,reference2=implementation,
            job_id=job,source_job_id=source,baseline4_job_id=base['job_id'],baseline8_job_id=base['baseline_job_id'],
            forward_seconds=report['forward_seconds'],total_seconds=report['total_seconds'],
            baseline4_forward_seconds=base['forward_seconds'],baseline4_total_seconds=base['total_seconds'],
            baseline8_forward_seconds=base['baseline_forward_seconds'],baseline8_total_seconds=base['baseline_total_seconds'],
            vs4=compare(folder,B4/'captures'/base['job_id']),vs8=compare(folder,B8/'captures'/base['baseline_job_id']),
            pl=report['pl'],conv_pl=report['conv_pl'],mixed_pl=report['mixed_pl'])
        assert result['mixed_pl']['integer_stage_calls']==5 and result['mixed_pl']['fp32_fallback_blocks']==0
        records.append(result)
        write(R/'replays_verified.json',dict(functional_passed=True,cases=records))
        print(json.dumps(result),flush=True)
        body=json.dumps(dict(job_id=job,package_sha256=s['package_sha256'])).encode()
        req=urllib.request.Request(URL+'/cache-ack',body,headers={'Content-Type':'application/json'},method='POST')
        with OP.open(req,timeout=10) as f:assert json.load(f)['released']
        if len(records)==1:write(R/'latest.json',report)
    print('TWO_TWO_ITERATION_REPLAYS_COMPLETE',flush=True)
