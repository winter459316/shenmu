"""Six finite saved-photo replays; source-bound A/B comparison, no shutter."""
from pathlib import Path
import hashlib,json,re,shlex,statistics,subprocess,sys,time,uuid,urllib.request
U=Path(__file__).resolve().parent
E=U.parent
P=U.parents[2]
R=P/'candidates/usb_fast_infer2'
sys.path.insert(0,str(E))
from transfer import upload,command
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
SOURCE='9bd84d3050184e44bee08e1e2aa4b769'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def get(path):
    with OP.open('http://192.168.137.2:8850'+path,timeout=8) as response:return json.load(response)


def main():
    import numpy as np
    assert not(U/'benchmark_v2_launch.json').exists(),'Never duplicate this finite replay comparison'
    ref=R/'captures'/SOURCE/'board_result.npz'
    with np.load(str(ref),allow_pickle=False) as z:gold={n:z[n] for n in z.files if n!='metadata_json'}
    assert len(gold)==13
    out=U/'bench';out.mkdir(exist_ok=True)
    selector=U/'select_benchmark_board.py'
    s=(U/'activate_board.py').read_text()
    s=s.replace("choices=['activate','rollback']","choices=['baseline','direct']")
    s=s.replace("if a.mode=='activate':","if a.mode in ('baseline','direct'):")
    s=s.replace("target='infer_worker_pl3_v5_quad.py' if a.mode=='activate' else 'infer_worker.py'",
        "target='infer_worker_pl3_v5_quad.py' if a.mode=='direct' else 'infer_worker_pl3_v2.py'")
    s=s.replace("server='fast_job_server_pl3_v5_quad.py' if a.mode=='activate' else 'fast_job_server.py'",
        "server='fast_job_server_pl3_v5_quad.py' if a.mode=='direct' else 'fast_job_server_pl3_v2.py'")
    assert "choices=['baseline','direct']" in s
    if selector.exists():assert selector.read_text()==s
    else:selector.write_text(s)
    compile(s,str(selector),'exec')
    remote='pl3_v5_quad_benchmark_select_20261028.py'
    upload({remote:selector})
    before={str(p):sha(p) for p in [Path(__file__),selector,U/'pl3_usable_v5_quad_manifest_20261028.json',
        E/'usable_v2/pl3_usable_v2_manifest_20261028.json',ref]}
    (U/'benchmark_v2_launch.json').write_text(json.dumps(dict(source_photo=SOURCE,source_sha256=before,
        policies=['baseline','direct','direct','baseline','baseline','direct'],saved_photo_only=True),indent=2))
    results=[]
    for i,policy in enumerate(('baseline','direct','direct','baseline','baseline','direct')):
        assert all(sha(Path(n))==d for n,d in before.items())
        desired='fast_pl3_usable_v5_quad' if policy=='direct' else 'fast_pl3_usable_v2'
        h=get('/health');assert h['ready'] and h['model_worker']['state']=='ready'
        if h['version']!=desired:
            cmd='(python3 -u /tmp/usb_stereo_probe/pl_pipeline_20261025/'+remote+' '+policy+' > /tmp/usb_stereo_probe/pl_pipeline_20261025/v5_quad_bench_select_'+str(i)+'.log 2>&1 < /dev/null &)'
            command(cmd,8)
            deadline=time.monotonic()+65
            while time.monotonic()<deadline:
                time.sleep(1)
                try:h=get('/health')
                except (OSError,ValueError):continue
                if h['ready'] and h['version']==desired:break
            else:raise TimeoutError('Benchmark mode did not become ready; no repeated selection')
        label='%d_%s'%(i,policy)
        previous=out/(label+'_launch.json')
        assert not previous.exists();reused=False
        job=json.loads(previous.read_text())['job_id'] if reused else uuid.uuid4().hex;script='fast_capture_pl3_v5_quad.py' if policy=='direct' else 'fast_capture_pl3_v2.py'
        label='%d_%s'%(i,policy)
        if not reused:(out/(label+'_launch.json')).write_text(json.dumps(dict(job_id=job,policy=policy,worker_pid=h['model_worker']['pid']),indent=2))
        code="""from pathlib import Path
import subprocess
R=Path('/tmp/usb_stereo_probe/fast_infer2')
with (R/'jobs'/LOG).open('wb') as log:
 p=subprocess.Popen(['python3','-u',str(R/SCRIPT),JOB,'--replay',PHOTO],cwd=str(R),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print('FINITE_REPLAY_LAUNCHED',p.pid)
""".replace('LOG',repr('v5_quad_benchmark_'+label+'.log')).replace('SCRIPT',repr(script)).replace('JOB',repr(job)).replace('PHOTO',repr(SOURCE))
        answer='\nFINITE_REPLAY_LAUNCHED previously recorded job\n' if reused else command('python3 -c '+shlex.quote(code),12).replace('\r','')
        assert '\nFINITE_REPLAY_LAUNCHED ' in answer,answer[-1000:]
        print('REPLAY_STARTED',i,policy,job,flush=True)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            time.sleep(1);state=get('/status?id='+job)
            # The unmodified API associates its old active subprocess with
            # any queried job. A direct saved-photo replay has its own PID.
            # Ignore only this known overlay while waiting for the real file
            # to become ready; all other errors and the bounded timeout stop.
            if state.get('error')=='Board worker exited before completing restoration; inspect log':continue
            if state.get('stage')=='failed' or state.get('error'):raise RuntimeError(state)
            if state.get('stage')=='ready':break
        else:raise TimeoutError('Replay is not complete; inspect this job without repeating')
        assert state['stable_restored'] and state['quality_passed'] and all(state['same_photo_exact'].values())
        with OP.open('http://192.168.137.2:8850/result?id='+job,timeout=30) as response:data=response.read()
        assert len(data)==state['package_bytes'] and hashlib.sha256(data).hexdigest()==state['package_sha256']
        archive=out/(label+'.npz');archive.write_bytes(data)
        with np.load(str(archive),allow_pickle=False) as z:
            exact={n:z[n].dtype==a.dtype and z[n].shape==a.shape and z[n].tobytes()==a.tobytes() for n,a in gold.items()}
        assert all(exact.values())
        report=dict(policy=policy,job_id=job,forward_seconds=state['inference']['forward_seconds'],
            board_total_seconds=state['total_seconds'],pl3=state['inference']['pl3'],exact_arrays=exact,
            worker_pid=h['model_worker']['pid'],result_sha256=sha(archive),stable_restored=True)
        (out/(label+'_verified.json')).write_text(json.dumps(report,indent=2))
        # Normal cache-ack is sent only after the entire immutable package is
        # preserved and independently checked on PC. Source fixture stays intact.
        body=json.dumps(dict(job_id=job,package_sha256=state['package_sha256'])).encode()
        req=urllib.request.Request('http://192.168.137.2:8850/cache-ack',body,headers={'Content-Type':'application/json'})
        with OP.open(req,timeout=15) as response:ack=json.load(response)
        assert ack['released']
        results.append(report);print('REPLAY_EXACT',i,policy,report['forward_seconds'],report['board_total_seconds'],flush=True)
    medians={p:statistics.median(r['forward_seconds'] for r in results if r['policy']==p) for p in ('baseline','direct')}
    total={p:statistics.median(r['board_total_seconds'] for r in results if r['policy']==p) for p in ('baseline','direct')}
    result=dict(passed=True,source_photo=SOURCE,results=results,forward_medians=medians,
        board_total_medians=total,forward_improvement_percent=(medians['baseline']-medians['direct'])/medians['baseline']*100,
        speedup_qualified=medians['direct']<medians['baseline'],all_13_arrays_exact=True,source_sha256=before)
    (U/'benchmark_v2_verified.json').write_text(json.dumps(result,indent=2))
    print('FINITE_BENCHMARK_COMPLETE',medians,total,flush=True)


if __name__=='__main__':main()
