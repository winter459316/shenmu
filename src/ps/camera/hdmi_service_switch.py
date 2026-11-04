"""Finite prepare/stop/start steps for the authorized HDMI service update."""
import argparse,hashlib,json,os,signal,subprocess,time,zipfile
from pathlib import Path
from test_sgm_v4_transaction import request
ROOT=Path(__file__).resolve().parent
FILES=('full_camera.py','usb_full_engine.py','hardware_catalog.py','physical_keys.py',
       'hdmi_output.py','hdmi_mmio.so','restore_held.py','loaded.json')

def alive(pid):
    try:return (Path('/proc')/str(pid)/'stat').read_text().split(') ',1)[1][0]!='Z'
    except FileNotFoundError:return False

def owners():
    out={}
    for p in Path('/proc').glob('[0-9]*'):
        try:
            cmd=[v.decode() for v in (p/'cmdline').read_bytes().split(b'\0') if v]
            scripts={Path(v).name for v in cmd}&{'full_camera.py','physical_keys.py'}
            if not scripts:continue
            assert len(scripts)==1 and (p/'cwd').resolve()==ROOT
            name=scripts.pop();assert name not in out
            out[name]={'pid':int(p.name),'command':cmd,
                       'start_ticks':(p/'stat').read_text().split(') ',1)[1].split()[19],
                       'environment':dict(v.split('=',1) for v in (p/'environ').read_bytes().decode().split('\0') if '=' in v)}
        except (FileNotFoundError,ProcessLookupError):continue
    return out

def prepare():
    state=request('/stereo/status');assert not state['busy'] and not state['section_busy']
    from save_held_for_update import main as save
    save();current=owners();assert set(current)=={'full_camera.py','physical_keys.py'}
    path=ROOT/'hdmi_before_activation.zip';assert not path.exists(),'Do not overwrite the previous backup'
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            if (ROOT/name).exists():archive.write(ROOT/name,name)
    record={'owners':current,'held':json.loads((ROOT/'held_restore.json').read_text()),
            'standby':state['standby'],'backup_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    p=ROOT/'hdmi_service_before.json';p.write_text(json.dumps(record,indent=2));p.chmod(0o600)
    print(json.dumps({'prepared':True,'owners':{k:v['pid'] for k,v in current.items()},'held':record['held'],'backup_sha256':record['backup_sha256']}))

def stop():
    saved=json.loads((ROOT/'hdmi_service_before.json').read_text());current=owners()
    assert current==saved['owners'],'Process identity changed; recheck before stopping'
    state=request('/stereo/status')
    assert not state['busy'] and not state['section_busy'] and state['result_id']==saved['held']['job_id']
    for name in ('physical_keys.py','full_camera.py'):
        pid=current[name]['pid'];os.kill(pid,signal.SIGTERM);deadline=time.monotonic()+10
        while alive(pid) and time.monotonic()<deadline:time.sleep(.1)
        assert not alive(pid),'Service did not drain; do not reconfigure'
    assert not owners();print(json.dumps({'stopped':True,'pids':[v['pid'] for v in current.values()]}))

def start():
    assert not owners(),'Camera/key service already running'
    saved=json.loads((ROOT/'hdmi_service_before.json').read_text())
    loaded=json.loads((ROOT/'loaded.json').read_text())
    from hardware_catalog import HDMI_V1_SHA
    assert loaded['sha256']==HDMI_V1_SHA and loaded['state']=='operating'
    env=saved['owners']['full_camera.py']['environment'].copy()
    env.update(USB_HDMI='1',USB_RESTORE_HELD='1',USB_SURFACE_NATIVE='1',USB_DEVICE='/dev/video0',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with (ROOT/'full_camera_hdmi.log').open('ab',buffering=0) as log:
        camera=subprocess.Popen(['python3','-u',str(ROOT/'full_camera.py')],cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True,start_new_session=True)
    (ROOT/'full_camera.pid').write_text(str(camera.pid));deadline=time.monotonic()+18
    while time.monotonic()<deadline and camera.poll() is None:
        try:
            status=request('/status');runtime=request('/stereo/status');hdmi=request('/hdmi/status')
            if not status['error'] and status['age_seconds']<3 and hdmi['frames']>=2 and not hdmi['error']:
                assert runtime['result_id']==saved['held']['job_id'] and runtime['metadata']['package_sha256']==saved['held']['sha256']
                break
        except (OSError,AssertionError):pass
        time.sleep(.2)
    else:raise RuntimeError('HDMI camera service failed readiness; inspect full_camera_hdmi.log')
    if saved['standby']:request('/standby',{'enabled':True})
    with (ROOT/'physical_keys_hdmi.log').open('ab',buffering=0) as log:
        keys=subprocess.Popen(['python3','-u',str(ROOT/'physical_keys.py'),'--pl'],cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True,start_new_session=True)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline and keys.poll() is None:
        s=json.loads((ROOT/'physical_keys_status.json').read_text())
        if s['pid']==keys.pid and s['pl_keys_enabled']:break
        time.sleep(.1)
    else:raise RuntimeError('Key sidecar failed readiness')
    report={'passed':True,'camera_pid':camera.pid,'keys_pid':keys.pid,'hdmi':hdmi,
            'held':saved['held'],'physical_press_test_pending':True}
    (ROOT/'hdmi_service_active.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','stop','start'))
    globals()[parser.parse_args().action]()
