"""Start a separate input API only; keep the qualified V5 worker and all PL unchanged."""
from pathlib import Path
import fcntl,hashlib,json,subprocess,time
H=Path(__file__).resolve().parent;R=H.parent/'fast_infer2'
with (R/'resident_switch.lock').open('a+') as switch:
    fcntl.flock(switch,fcntl.LOCK_EX|fcntl.LOCK_NB)
    m=json.loads((H/'video_companion_manifest_v1.json').read_text())
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
    import socket
    with socket.socket() as probe:assert probe.connect_ex(('192.168.137.2',8853))!=0,'Video API port already in use'
    with (R/'video_job_server.log').open('ab',buffering=0) as log:
        child=subprocess.Popen(['python3','-u',str(R/'video_job_server_v1.py')],cwd=str(R),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    print('VIDEO_INPUT_API_STARTED',child.pid,flush=True)
