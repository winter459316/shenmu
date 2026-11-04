"""Exclusive volatile 640/320 switch; preserve the old source, photo and startup state."""
import base64,fcntl,hashlib,http.client,json,mmap,os,signal,struct,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'full_v2'
OLD_SHA='48350af24a1a760c9f555bd6e39c2d8a0216003a580d7c08204bab5e64c2c39d'
def request(port,path,body=None):
    c=http.client.HTTPConnection('192.168.137.2',port,timeout=15,source_address=('127.0.0.1',0))
    try:
        c.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),{} if body is None else {'Content-Type':'application/json'})
        r=c.getresponse();data=r.read();assert r.status==200,(r.status,data[:150]);return json.loads(data)
    finally:c.close()
def owners():
    out={}
    for p in Path('/proc').glob('[0-9]*'):
        try:
            cmd=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\0') if x]
            names={Path(x).name for x in cmd}&{'full_camera.py','physical_keys.py'}
            if not names:continue
            assert len(names)==1
            name=names.pop();assert name not in out
            out[name]={'pid':int(p.name),'cmd':cmd,'cwd':str((p/'cwd').resolve()),
                'start':(p/'stat').read_text().split(') ',1)[1].split()[19],
                'env':dict(x.split('=',1) for x in (p/'environ').read_bytes().decode().split('\0') if '=' in x)}
        except (FileNotFoundError,ProcessLookupError):pass
    return out
def alive(pid):
    try:return (Path('/proc')/str(pid)/'stat').read_text().split(') ',1)[1][0]!='Z'
    except FileNotFoundError:return False
def stop_all(items):
    for name in ('physical_keys.py','full_camera.py'):
        if name not in items:continue
        pid=items[name]['pid'];os.kill(pid,signal.SIGTERM);end=time.monotonic()+20
        while alive(pid) and time.monotonic()<end:time.sleep(.1)
        assert not alive(pid),'Service did not drain'
    assert not owners()
def prepare():
    assert not (ROOT/'switch_before.json').exists()
    state=request(8767,'/stereo/status');assert not state['busy'] and not state['section_busy']
    subprocess.run(['python3',str(OLD/'save_held_for_update.py')],cwd=str(OLD),check=True)
    current=owners();assert set(current)=={'full_camera.py','physical_keys.py'}
    assert all(Path(v['cwd'])==OLD.resolve() for v in current.values())
    metadata=(OLD/'loaded.json').read_bytes();assert json.loads(metadata)['sha256']==OLD_SHA
    assert hashlib.sha256((OLD/'hdmi_v1.bit.bin').read_bytes()).hexdigest()==OLD_SHA
    saved={'owners':current,'old_loaded':metadata.decode(),'held':json.loads((OLD/'held_restore.json').read_text()),'standby':state['standby']}
    p=ROOT/'switch_before.json';p.write_text(json.dumps(saved,indent=2));p.chmod(0o600)
    print(json.dumps({'prepared':True,'held':saved['held'],'owners':{k:v['pid'] for k,v in current.items()}}))
def program(directory,filename):
    path=Path('/sys/module/firmware_class/parameters/path');flags=Path('/sys/class/fpga_manager/fpga0/flags')
    before=path.read_text();old_flags=flags.read_text()
    try:
        path.write_text(str(directory));flags.write_text('0');Path('/sys/class/fpga_manager/fpga0/firmware').write_text(filename)
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
    finally:path.write_text(before);flags.write_text(old_flags)
def hardware_check(arena,tag):
    for name,expected in (('sgm',0x55534738),('images',0x55494632),('geometry',0x55474532),('completion',0x43475032)):
        value,_=arena.command(name,{0x20:0},timeout=2);assert value==expected
    for name in ('images','geometry'):
        value,_=arena.command(name,{0x20:3},timeout=2);assert value==tag
    value,_=arena.command('sgm',{0x20:3},timeout=2);assert value==0x53574e34
    if tag==0x6dbbd7ca:
        value,_=arena.command('completion',{0x20:4},timeout=2);assert value==320
def switch():
    saved=json.loads((ROOT/'switch_before.json').read_text());assert owners()==saved['owners']
    state=request(8767,'/stereo/status');assert not state['busy'] and not state['section_busy'] and state['result_id']==saved['held']['job_id']
    proof=json.loads((ROOT/'hardware_320_verified.json').read_text())
    assert all(proof[k] for k in ('timing_passed','cdc_review_passed','keys_passed','hls_passed'))
    assert hashlib.sha256((ROOT/'usb320.bit.bin').read_bytes()).hexdigest()==proof['sha256']
    stop_all(saved['owners'])
    from board_dma import Arena,TAG
    with (OLD/'hdmi.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);a=Arena(False)
        try:
            for i,name in enumerate(('sgm','images','geometry','completion')):
                a.controls[name]=mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0xA1010000+0x10000*i)
            assert all(a.read(name,0)&4 for name in a.controls)
            with mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0xA1050000) as vdma:
                assert struct.unpack_from('<I',vdma,4)[0]&1,'HDMI DMA not halted'
            program(ROOT,'usb320.bit.bin');hardware_check(a,TAG)
            fault=ROOT/'dma.fault'
            if fault.exists():fault.rename(ROOT/('dma_fault_before_verified_reload_%d.txt'%time.time_ns()))
            loaded=json.loads(saved['old_loaded']);loaded.update(sha256=proof['sha256'],state='operating',eye_size=[320,360],calibration_tag=TAG)
            (ROOT/'loaded.json').write_text(json.dumps(loaded,indent=2))
            (OLD/'loaded.json').write_text(json.dumps(dict(json.loads(saved['old_loaded']),state='suspended',active_project='usb320')))
        except BaseException:
            program(OLD,'hdmi_v1.bit.bin');hardware_check(a,0xa3a4a2ef)
            (OLD/'loaded.json').write_text(saved['old_loaded']);raise
        finally:a.close()
    print(json.dumps({'switched':True,'sha256':proof['sha256'],'services_started':False}))
def start():
    assert not owners()
    saved=json.loads((ROOT/'switch_before.json').read_text());env=saved['owners']['full_camera.py']['env'].copy()
    env.update(USB_HDMI='1',USB_RESTORE_HELD='0',USB_SURFACE_NATIVE='1',USB_MESH_NATIVE='1',USB_HOLES_PARALLEL='1',USB_ARCHIVE_STORED='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with (ROOT/'camera320.log').open('ab',buffering=0) as log:
        p=subprocess.Popen(['python3','-u',str(ROOT/'full_camera.py')],cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    (ROOT/'full_camera.pid').write_text(str(p.pid));end=time.monotonic()+18
    while time.monotonic()<end and p.poll() is None:
        try:
            s=request(8768,'/status');h=request(8768,'/hdmi/status')
            if not s['error'] and s['age_seconds']<2 and h['frames']>=2 and not h['error']:break
        except OSError:pass
        time.sleep(.2)
    else:raise RuntimeError('320 camera did not become ready')
    with (ROOT/'keys320.log').open('ab',buffering=0) as log:
        keys=subprocess.Popen(['python3','-u',str(ROOT/'physical_keys.py'),'--pl'],cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    end=time.monotonic()+5
    while time.monotonic()<end and keys.poll() is None:
        record=ROOT/'physical_keys_status.json'
        if record.exists() and json.loads(record.read_text()).get('pid')==keys.pid:break
        time.sleep(.2)
    else:raise RuntimeError('320 key service did not become ready')
    report={'passed':True,'camera_pid':p.pid,'keys_pid':keys.pid,'hdmi':h,'old_held_preserved':saved['held']}
    (ROOT/'activation_320.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

def rollback():
    saved=json.loads((ROOT/'switch_before.json').read_text())
    current=owners()
    assert all(Path(v['cwd'])==ROOT.resolve() for v in current.values()),'Unexpected service owner; rollback stopped'
    if 'full_camera.py' in current:
        s=request(8768,'/stereo/status');assert not s['busy'] and not s['section_busy']
    stop_all(current)
    from board_dma import Arena
    with (OLD/'hdmi.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);a=Arena(False)
        try:
            for i,name in enumerate(('sgm','images','geometry','completion')):
                a.controls[name]=mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0xA1010000+0x10000*i)
            assert all(a.read(name,0)&4 for name in a.controls),'Compute DMA not idle'
            with mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0xA1050000) as vdma:
                assert struct.unpack_from('<I',vdma,4)[0]&1,'HDMI DMA not halted'
            assert hashlib.sha256((OLD/'hdmi_v1.bit.bin').read_bytes()).hexdigest()==OLD_SHA
            program(OLD,'hdmi_v1.bit.bin');hardware_check(a,0xa3a4a2ef)
            (OLD/'loaded.json').write_text(saved['old_loaded'])
            if (ROOT/'loaded.json').exists():
                m=json.loads((ROOT/'loaded.json').read_text());m['state']='suspended';(ROOT/'loaded.json').write_text(json.dumps(m))
        finally:a.close()
    for name in ('full_camera.py','physical_keys.py'):
        v=saved['owners'][name];env=v['env'].copy()
        if name=='full_camera.py':env['USB_RESTORE_HELD']='1'
        with (OLD/'rollback_from_320.log').open('ab',buffering=0) as log:
            p=subprocess.Popen(v['cmd'],cwd=v['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        if name=='full_camera.py':
            end=time.monotonic()+25
            while time.monotonic()<end and p.poll() is None:
                try:
                    s=request(8767,'/status');h=request(8767,'/hdmi/status')
                    if not s['error'] and h['frames']>=2 and not h['error']:break
                except OSError:pass
                time.sleep(.2)
            else:raise RuntimeError('Old camera restart needs attention')
    print(json.dumps({'rollback':True,'old_held':saved['held'],'old_sha256':OLD_SHA}))
if __name__=='__main__':
    import sys
    assert sys.argv[1] in ('prepare','switch','start','rollback');globals()[sys.argv[1]]()
