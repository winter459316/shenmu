"""Switch only RAM camera services, preserving the verified PL and rollback photo."""
import hashlib,http.client,json,os,shutil,signal,subprocess,time
from pathlib import Path
from switch_320_board import owners,alive,request
ROOT=Path(__file__).resolve().parent;OLD=(ROOT.parent/'usb320_autofill').resolve()
BIT='1040bc3c95d76794e479d8d039f21cbfebc3086e838c507afe81a4e971c6d0b4'
SNAP=ROOT/'dense3d_startup_snapshot.json'

def stop(items):
    for name in ('physical_keys.py','full_camera.py'):
        if name not in items:continue
        now=owners();assert now.get(name)==items[name],'Owner changed'
        pid=items[name]['pid'];os.kill(pid,signal.SIGTERM);deadline=time.monotonic()+25
        while alive(pid) and time.monotonic()<deadline:time.sleep(.1)
        assert not alive(pid),'Service did not drain'
    assert not owners()

def launch(directory,name,args,env):
    with (directory/(name+'_dense3d_switch.log')).open('ab',buffering=0) as log:
        p=subprocess.Popen(['python3','-u',str(directory/(name+'.py'))]+args,cwd=str(directory),env=env,
                           stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    (directory/(name+'.pid')).write_text(str(p.pid));return p

def start_services(directory,port,saved,restore):
    env=saved['owners']['full_camera.py']['env'].copy()
    env.update(USB_HDMI='1',USB_RESTORE_HELD='1' if restore else '0')
    camera=launch(directory,'full_camera',[],env);deadline=time.monotonic()+30
    while time.monotonic()<deadline and camera.poll() is None:
        try:
            c=request(port,'/status');h=request(port,'/hdmi/status')
            if not c['error'] and c['age_seconds']<2 and h['frames']>=2 and not h['error']:break
        except (OSError,AssertionError):pass
        time.sleep(.2)
    else:raise RuntimeError('Preview readiness failed')
    keys=launch(directory,'physical_keys',['--pl'],saved['owners']['physical_keys.py']['env']);deadline=time.monotonic()+8
    while time.monotonic()<deadline and keys.poll() is None:
        p=directory/'physical_keys_status.json'
        if p.exists() and json.loads(p.read_text()).get('pid')==keys.pid:break
        time.sleep(.2)
    else:raise RuntimeError('Key service readiness failed')
    if restore and saved['held']:
        s=request(port,'/stereo/status');assert s['result_id']==saved['held']['job_id']
        assert s['metadata']['package_sha256']==saved['held']['sha256']
    return {'passed':True,'camera_pid':camera.pid,'keys_pid':keys.pid,'camera':c,'hdmi':h,'bitstream_unchanged':True}

def prepare():
    assert not SNAP.exists(),'Snapshot already exists'
    s=request(8782,'/stereo/status');assert not s['busy'] and not s['section_busy']
    current=owners();assert set(current)=={'full_camera.py','physical_keys.py'}
    assert all(Path(v['cwd']).resolve()==OLD for v in current.values())
    loaded=(OLD/'loaded.json').read_bytes();assert json.loads(loaded)['sha256']==BIT
    held=None
    if s['result_id']:
        job=s['result_id'];assert job==s['job_id']
        c=http.client.HTTPConnection('192.168.137.2',8782,timeout=30,source_address=('127.0.0.1',0))
        try:
            c.request('GET','/stereo/result.npz?id='+job);r=c.getresponse();assert r.status==200;data=r.read()
        finally:c.close()
        digest=hashlib.sha256(data).hexdigest();assert digest==s['metadata']['package_sha256']
        assert request(8782,'/stereo/status')['result_id']==job
        (ROOT/'baseline_photo.npz').write_bytes(data)
        held={'job_id':job,'sha256':digest,'bytes':len(data),'total_seconds':s['metadata']['total_seconds']}
    saved={'owners':current,'loaded':loaded.decode(),'held':held,'standby':s['standby']}
    # Contains process environment; private on-board only, never exported.
    fd=os.open(str(SNAP),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(saved,f)
    print(json.dumps({'prepared':True,'held':held}),flush=True)

def rollback():
    saved=json.loads(SNAP.read_text());current=owners()
    assert all(Path(v['cwd']).resolve() in (ROOT.resolve(),OLD) for v in current.values())
    if current:
        port=8784 if Path(current['full_camera.py']['cwd']).resolve()==ROOT.resolve() else 8782
        state=request(port,'/stereo/status');assert not state['busy'] and not state['section_busy']
    stop(current)
    (OLD/'loaded.json').write_text(saved['loaded'])
    if saved['held']:
        assert hashlib.sha256((ROOT/'baseline_photo.npz').read_bytes()).hexdigest()==saved['held']['sha256']
        shutil.copyfile(ROOT/'baseline_photo.npz',OLD/'held_restore.npz')
        (OLD/'held_restore.json').write_text(json.dumps(saved['held']))
    report=start_services(OLD,8782,saved,bool(saved['held']))
    request(8782,'/standby',{'enabled':saved['standby']})
    print('STABLE_RESTORED',json.dumps(report),flush=True)

def activate():
    saved=json.loads(SNAP.read_text());assert owners()==saved['owners']
    s=request(8782,'/stereo/status');assert not s['busy'] and not s['section_busy']
    assert s['result_id']==(saved['held'] or {}).get('job_id')
    proof=json.loads((ROOT/'dense_geometry_replay_verified.json').read_text());assert proof['passed'] and proof['cancel_passed']
    assert proof['bitstream_sha256']==BIT
    from full_runtime import FullRuntime
    from physical_keys import discover
    FullRuntime();discover()
    try:
        stop(saved['owners']);(ROOT/'loaded.json').write_text(saved['loaded'])
        report=start_services(ROOT,8784,saved,False)
        (ROOT/'dense3d_activation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    except Exception:
        rollback();raise

if __name__=='__main__':
    import sys
    assert sys.argv[1] in ('prepare','activate','rollback');globals()[sys.argv[1]]()
