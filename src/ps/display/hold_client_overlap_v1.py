"""Capture-owned static display, closed and drained before every PL image change."""
from pathlib import Path
import json,socket,subprocess,time
R=Path('/tmp/usb_stereo_probe/fast_infer2')
def call(job,action,profile=None):
    path=R/'jobs'/job/'hdmi_hold.sock'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
        c.settimeout(6);c.connect(str(path));c.sendall((json.dumps(dict(job_id=job,action=action,profile=profile))+'\n').encode())
        with c.makefile('rb') as f:answer=json.loads(f.readline(8192))
    assert answer['ok'],answer
    return answer
def prepare(job):
    folder=R/'jobs'/job
    with (folder/'hdmi_hold.log').open('wb') as log:
        p=subprocess.Popen(['python3','-u',str(R/'hold_server_overlap_v1.py'),job],cwd=str(R),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    return p

def start(job,p=None):
    p=prepare(job) if p is None else p
    folder=R/'jobs'/job
    for _ in range(100):
        assert p.poll() is None,'Static HDMI owner exited; inspect hdmi_hold.log'
        if (folder/'hdmi_hold.sock').exists():
            call(job,'start','pl2');return p
        time.sleep(.05)
    raise TimeoutError('Static HDMI owner did not start')
def finish(job,process):
    for _ in range(100):
        if process.poll() is not None:raise RuntimeError('Static HDMI helper exited before drain')
        if (R/'jobs'/job/'hdmi_hold.sock').exists():break
        time.sleep(.02)
    call(job,'exit');process.wait(timeout=6)
    assert process.returncode==0,'Static HDMI drain failed'
