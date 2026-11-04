"""Reversibly replace the idle parent UVC service; no FPGA/boot/flash changes."""
import http.client,json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def request(path):
    connection=http.client.HTTPConnection('192.168.137.2',8768,timeout=2,source_address=('127.0.0.1',0))
    try:
        connection.request('GET',path);response=connection.getresponse()
        if response.status!=200:raise RuntimeError('Camera HTTP '+str(response.status))
        return json.loads(response.read())
    finally:connection.close()
def alive(pid):
    try:return Path('/proc/%d/stat'%pid).read_text().split(') ',1)[1][0]!='Z'
    except FileNotFoundError:return False
def owners():
    result=[]
    for p in Path('/proc').glob('[0-9]*'):
        try:
            if any(fd.resolve()==Path('/dev/video0') for fd in (p/'fd').iterdir()):result.append(int(p.name))
        except (FileNotFoundError,PermissionError):pass
    return result
def main():
    from full_runtime import FullRuntime
    FullRuntime()  # Check imports, calibration, maps and native libraries before stopping the old owner.
    if os.environ.get('USB_SURFACE_NATIVE','1')=='1':
        import numpy as np
        from surface_native import plane_filter_native
        from surface_cleanup import plane_filter_reference,SurfaceConfig
        y,x=np.indices((8,10));d=(20+.03*x+.02*y).astype(np.float32)
        valid=np.ones(d.shape,bool);confidence=np.ones_like(d);rgb=np.full(d.shape+(3,),128,np.float32)
        expected=plane_filter_reference(d,valid,confidence,rgb,SurfaceConfig())
        actual=plane_filter_native(d,valid,confidence,rgb,SurfaceConfig())
        assert actual.tobytes()==expected.tobytes(),'Native surface preflight failed; current service was not stopped'
    status=request('/stereo/status')
    is_full=status.get('schema')=='usb_full_v2'
    if is_full and '--restart' not in sys.argv:
        print(json.dumps({'already_running':True,'status':status}));return
    assert not status.get('busy') and not status.get('section_busy'),'Existing camera is processing a photo/section'
    current=owners();assert len(current)==1,('Unexpected UVC owners',current)
    old=current[0];cmd=Path('/proc/%d/cmdline'%old).read_bytes().split(b'\0')
    expected_script=str(ROOT/'full_camera.py').encode() if is_full else b'board_camera.py'
    expected_cwd=ROOT if is_full else ROOT.parent
    assert expected_script in cmd and Path('/proc/%d/cwd'%old).resolve()==expected_cwd,('Unknown camera owner',cmd)
    environment=dict(v.split('=',1) for v in Path('/proc/%d/environ'%old).read_bytes().decode().split('\0') if '=' in v)
    # Older camera versions had no native-surface flag and used the reference path.
    environment.setdefault('USB_SURFACE_NATIVE','0')
    saved={'old_pid':old,'old_command':[v.decode() for v in cmd if v],'old_cwd':str(expected_cwd),
           'USB_USE_PL':environment.get('USB_USE_PL'),'USB_DEVICE':environment.get('USB_DEVICE'),
           'new_script':str(ROOT/'full_camera.py')}
    (ROOT/('service_restart.json' if is_full else 'service_switch.json')).write_text(json.dumps(saved,indent=2))
    os.kill(old,signal.SIGTERM);deadline=time.monotonic()+8
    while alive(old) and time.monotonic()<deadline:time.sleep(.1)
    assert not alive(old) and not owners(),'Old service has not stopped; do not start a second camera owner'
    env=os.environ.copy();env['USB_DEVICE']='/dev/video0';env['OPENBLAS_NUM_THREADS']='1';env['OMP_NUM_THREADS']='1'
    log=open(ROOT/'full_camera.log','ab',buffering=0)
    process=subprocess.Popen(['python3','-u',str(ROOT/'full_camera.py')],cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,
                             stdout=log,stderr=log,close_fds=True,start_new_session=True)
    (ROOT/'full_camera.pid').write_text(str(process.pid));deadline=time.monotonic()+12
    while time.monotonic()<deadline and process.poll() is None:
        try:
            state=request('/stereo/status');camera=request('/status')
            if state.get('schema')=='usb_full_v2' and not camera.get('error') and camera['age_seconds']<3:
                print(json.dumps({'passed':True,'pid':process.pid,'camera':camera,'runtime':state}));return
        except Exception:pass
        time.sleep(.2)
    if process.poll() is None:
        process.terminate();process.wait(timeout=8)
    assert not owners(),'Failed candidate still owns the camera'
    rollback=subprocess.Popen(saved['old_command'],cwd=saved['old_cwd'],env=environment,stdin=subprocess.DEVNULL,
                              stdout=log,stderr=log,close_fds=True,start_new_session=True)
    raise RuntimeError('New service failed; parent restored as PID %d; inspect full_camera.log'%rollback.pid)
if __name__=='__main__':main()
