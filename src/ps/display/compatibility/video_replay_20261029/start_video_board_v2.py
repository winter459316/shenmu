"""Start a separate input API only; keep the qualified V5 worker and all PL unchanged."""
from pathlib import Path
import fcntl,hashlib,json,subprocess,time
H=Path(__file__).resolve().parent;R=H.parent/'fast_infer2'
with (R/'resident_switch.lock').open('a+') as switch:
    fcntl.flock(switch,fcntl.LOCK_EX|fcntl.LOCK_NB)
    m=json.loads((H/'video_companion_manifest_v2.json').read_text())
    for name,digest in m.items():
        raw=(H/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        target=R/name
        if target.exists():assert target.read_bytes()==raw
        else:target.write_bytes(raw)
    worker=json.loads((R/'worker_status.json').read_text())
    assert worker['ready'] and worker['state']=='ready'
    cmd=(Path('/proc')/str(worker['pid'])/'cmdline').read_bytes().split(b'\0')
    assert any(Path(x.decode()).name=='infer_worker_pl3_v5_quad.py' for x in cmd if x)
    # No existing process or foreign port may be replaced.
    import socket,os,signal
    with (R.parent/'fast_pl/capture.lock').open('a+') as legacy,(R/'capture.lock').open('a+') as capture:
        for f in (legacy,capture):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (R/'pl_test_private_snapshot.json').exists() and not list(R.glob('*.fault'))
        previous=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                args=(proc/'cmdline').read_bytes().split(b'\0')
                if str(R/'video_job_server_v1.py').encode() in args:
                    assert hashlib.sha256((R/'video_job_server_v1.py').read_bytes()).hexdigest()=='422b942a3ad2d0e7439bb17e210448f45c12ddff60f5d2a15fb9885be84bc253'
                    previous.append(int(proc.name))
            except (FileNotFoundError,PermissionError):pass
        assert len(previous)<=1
        for pid in previous:
            os.kill(pid,signal.SIGTERM)
            for _ in range(30):
                try:
                    if (Path('/proc')/str(pid)/'stat').read_text().split(') ',1)[1].startswith('Z'):break
                except FileNotFoundError:break
                time.sleep(.1)
            else:raise TimeoutError('Previous idle input API did not exit')
    with socket.socket() as probe:assert probe.connect_ex(('192.168.137.2',8853))!=0,'Video API port already in use'
    with (R/'video_job_server.log').open('ab',buffering=0) as log:
        child=subprocess.Popen(['python3','-u',str(R/'video_job_server_v2.py')],cwd=str(R),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    print('VIDEO_INPUT_API_STARTED',child.pid,flush=True)
