"""Swap only idle resident model workers to bound RAM use; never programs PL."""
from pathlib import Path
import fcntl,json,os,signal,subprocess,sys,time
R=Path(__file__).resolve().parent;B=R.parent/'fast_transport2'

def worker(root, startup_cleanup=False):
    p=root/'worker_status.json'
    if not p.exists():return None
    info=json.loads(p.read_text());pid=int(info['pid']);proc=Path('/proc')/str(pid)
    try:
        if '\nState:\tZ' in (proc/'status').read_text():return None
        args=[x.decode() for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
        cwd=(proc/'cwd').resolve()
        matches=any(Path(x).name=='infer_worker.py' and (Path(x) if Path(x).is_absolute() else cwd/x).resolve()==root/'infer_worker.py' for x in args)
        assert matches,'PID does not match the expected worker'
    except FileNotFoundError:return None
    allowed=('ready','loading','failed') if startup_cleanup else ('ready',)
    assert info['state'] in allowed,'Wait for the current inference to finish'
    return pid

def stop_idle(root, startup_cleanup=False):
    pid=worker(root,startup_cleanup)
    if pid is None:return
    os.kill(pid,signal.SIGTERM)
    for _ in range(50):
        proc=Path('/proc')/str(pid)
        if not proc.exists() or '\nState:\tZ' in (proc/'status').read_text():return
        time.sleep(.1)
    raise TimeoutError('Model worker did not exit; no further stop signal was sent')

def start(root):
    subprocess.run(['python3',str(root/'start_runtime_board.py')],cwd=str(root),check=True,timeout=40)

if __name__=='__main__':
    assert sys.argv[1:] in (['activate'],['rollback'],['unload'])
    with (R.parent/'fast_pl/capture.lock').open('a+') as capture,(R/'resident_switch.lock').open('a+') as switch:
        fcntl.flock(capture,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(switch,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (R/'pl_test_private_snapshot.json').exists(),'Restore the unfinished PL switch before swapping models'
        assert not (B/'pl_test_private_snapshot.json').exists()
        if sys.argv[1]=='activate':
            # An idle worker holds no DMA descriptors; its source/model are preserved.
            saved={'old_model_worker_pid':worker(B),'old_runtime':str(B),'new_runtime':str(R)}
            path=R/'resident_private_snapshot.json'
            if not path.exists():
                with os.fdopen(os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump(saved,f)
            stop_idle(B)
            try:start(R)
            except BaseException:
                stop_idle(R,startup_cleanup=True);start(B);raise
            print('CONV_MODEL_RESIDENT_READY; baseline worker may be restarted by rollback',flush=True)
        elif sys.argv[1]=='rollback':
            stop_idle(R);start(B)
            print('PIPELINE_MODEL_RESIDENT_RESTORED',flush=True)
        else:
            stop_idle(R)
            path=R/'infer.sock'
            if path.exists():path.unlink()
            print('CONV_IDLE_MODEL_UNLOADED',flush=True)
