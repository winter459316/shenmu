"""Start the separate resident Fast services; never programs the FPGA or takes a photo."""
from pathlib import Path
import fcntl,hashlib,json,subprocess,time
R=Path(__file__).resolve().parent

def running(name):
    found=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            args=[x.decode() for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
            cwd=(proc/'cwd').resolve()
            if any(Path(x).name==name and (Path(x) if Path(x).is_absolute() else cwd/x).resolve()==R/name for x in args):found.append(int(proc.name))
        except (OSError,UnicodeError):pass
    assert len(found)<=1,(name,found)
    return found

if __name__=='__main__':
    with (R/'runtime_start.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        proof=json.loads((R/'hardware_verified.json').read_text())
        assert proof['timing_passed'] and proof['cdc_review_passed'] and proof['hls_passed']
        for name,digest in dict(proof['sources'],**{'fast_pl.bit.bin':proof['sha256']}).items():
            assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
        assert not (R/'pl_test_private_snapshot.json').exists(),'Restore unfinished photo first'
        for name,logname in [('infer_worker.py','infer_worker.log'),('fast_job_server.py','job_server.log')]:
            pids=running(name)
            if not pids:
                with (R/logname).open('ab',buffering=0) as log:
                    proc=subprocess.Popen(['python3','-u',str(R/name)],cwd=str(R),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                pids=[proc.pid]
            print(name,pids,flush=True)
        for _ in range(60):
            try:
                status=json.loads((R/'worker_status.json').read_text())
                if status['state']=='failed':raise RuntimeError(status)
                if status['state']=='ready' and status['pid'] in running('infer_worker.py') and (R/'infer.sock').exists():
                    print('PIPELINE_RUNTIME_READY',json.dumps(status),flush=True);break
            except (FileNotFoundError,json.JSONDecodeError):pass
            time.sleep(.5)
        else:raise TimeoutError('Model still loading; inspect worker log without restarting it')
