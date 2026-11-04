"""Switch only verified idle services; immutable stable source files stay intact."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

H = Path(__file__).resolve().parent
R = H.parent/'fast_infer2'
S = H.parent/'usb320_hdmifps'


def processes(name):
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            args=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\0') if x]
            cwd=(p/'cwd').resolve()
            matches=any(Path(a).name==name and (Path(a) if Path(a).is_absolute() else cwd/a).resolve()==R/name for a in args)
            if matches:
                st=(p/'stat').read_text().split(') ',1)[1].split()
                if st[0]!='Z':found.append(dict(pid=int(p.name),start=st[19],name=name))
        except (OSError,UnicodeError):pass
    assert len(found)<=1,(name,found)
    return found


def stop(proc):
    p=Path('/proc')/str(proc['pid'])
    st=(p/'stat').read_text().split(') ',1)[1].split()
    assert st[19]==proc['start']
    os.kill(proc['pid'],signal.SIGTERM)
    for _ in range(60):
        try:
            st=(p/'stat').read_text().split(') ',1)[1].split()
            if st[0]=='Z':return
            assert st[19]==proc['start']
        except (FileNotFoundError,ProcessLookupError):return
        time.sleep(.1)
    raise TimeoutError('Idle service did not exit; no stronger signal was sent')


def start(name, logname):
    assert not processes(name)
    with (R/logname).open('ab',buffering=0) as log:
        p=subprocess.Popen(['python3','-u',str(R/name)],cwd=str(R),stdin=subprocess.DEVNULL,
            stdout=log,stderr=log,start_new_session=True)
    return p.pid


def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['baseline','direct']);a=ap.parse_args()
    m=json.loads((H/'pl3_usable_v5_quad_manifest_20261028.json').read_text())
    for name,digest in m['stable_files'].items():
        assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
    if a.mode in ('baseline','direct'):
        for name,digest in m['files'].items():
            assert hashlib.sha256((H/name).read_bytes()).hexdigest()==digest,name
        for name,source in m['board_aliases'].items():
            assert hashlib.sha256((R/name).read_bytes()).hexdigest()==m['files'][source],name
    with (R.parent/'fast_pl/capture.lock').open('a+') as capture,(R/'capture.lock').open('a+') as local,(R/'resident_switch.lock').open('a+') as switch:
        for f in (capture,local,switch):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (R/'pl_test_private_snapshot.json').exists()
        for folder in (R,S,R.parent/'fast_pl'):
            assert not list(folder.glob('*.fault')),str(folder)
        loaded=json.loads((S/'loaded.json').read_text())
        assert loaded['sha256']=='3d166a23a3dd3d60a2cc3a34d43b3b5dc76878edd6522f4f3de620688ac758fe'
        old_worker=[]
        for name in ('infer_worker.py','infer_worker_pl3_v2.py','infer_worker_pl3_v3_io.py','infer_worker_pl3_v4_cache.py','infer_worker_pl3_v5_quad.py'):
            old_worker+=processes(name)
        assert len(old_worker)<=1
        if old_worker:
            state=json.loads((R/'worker_status.json').read_text())
            assert state['pid']==old_worker[0]['pid'] and state['state']=='ready','Only idle workers may be switched'
        old_servers=[]
        for name in ('fast_job_server.py','fast_job_server_pl3_v2.py','fast_job_server_pl3_v3_io.py','fast_job_server_pl3_v4_cache.py','fast_job_server_pl3_v5_quad.py'):
            old_servers+=processes(name)
        assert len(old_servers)<=1
        target='infer_worker_pl3_v5_quad.py' if a.mode=='direct' else 'infer_worker_pl3_v2.py'
        server='fast_job_server_pl3_v5_quad.py' if a.mode=='direct' else 'fast_job_server_pl3_v2.py'
        if old_worker and old_worker[0]['name']==target and old_servers and old_servers[0]['name']==server:
            print('PL3_MODE_ALREADY_SELECTED',a.mode);return
        # APIs own no hardware; stop accepting new photos before unloading idle model RAM.
        for proc in old_servers:stop(proc)
        for proc in old_worker:stop(proc)
        try:
            worker_pid=start(target,'infer_worker_pl3.log' if a.mode=='activate' else 'infer_worker.log')
            for _ in range(120):
                try:
                    state=json.loads((R/'worker_status.json').read_text())
                    if state['pid']==worker_pid and state['state']=='failed':raise RuntimeError(state)
                    if state['pid']==worker_pid and state['state']=='ready' and processes(target):break
                except (FileNotFoundError,json.JSONDecodeError):pass
                time.sleep(.5)
            else:raise TimeoutError('Selected model did not become ready')
            server_pid=start(server,'job_server_pl3.log' if a.mode=='activate' else 'job_server.log')
        except BaseException:
            # Startup has not dispatched any job or touched PL. Retire only this verified worker.
            current=processes(target)
            for proc in current:
                state=json.loads((R/'worker_status.json').read_text())
                assert state['pid']==proc['pid'] and state['state'] in ('loading','failed','ready')
                stop(proc)
            start(old_worker[0]['name'] if old_worker else 'infer_worker.py','infer_worker_startup_recovery.log')
            start(old_servers[0]['name'] if old_servers else 'fast_job_server.py','job_server_startup_recovery.log')
            raise
        receipt=dict(passed=True,mode=a.mode,worker_pid=worker_pid,server_pid=server_pid,
            worker_state=state['state'],stable_source_files_unchanged=True,
            hardware_access=False,manifest_sha256=hashlib.sha256((H/'pl3_usable_v5_quad_manifest_20261028.json').read_bytes()).hexdigest())
        p=H/('pl3_usable_v5_quad_'+a.mode+'_20261028.json')
        p.write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
