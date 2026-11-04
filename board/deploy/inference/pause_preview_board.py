"""Borrow the HDMI lease only while its verified camera process is fully frozen.

No concurrent owner can touch MMIO. VDMA is explicitly drained, then reconstructed
before the same camera process resumes; the original held package remains in RAM.
"""
from pathlib import Path
import ctypes,hashlib,http.client,json,mmap,os,signal,subprocess,time
import test_hardware_board as h
R=h.R;S=h.S
DMA=0xA1050000;VTC=0xA1060000
VIDEO_REGS=(0x60,0x68,0x6c,0x70,0x74,0x78,0x7c,0x80,0x84,0x88,0x8c,0x90)

def prepare():
    assert not h.SNAP.exists()
    assert not (S/'preview.dma.fault').exists(),'Preview DMA fault requires recovery'
    assert not (S/'filter.dma.fault').exists(),'Display DMA fault requires recovery'
    h.reservation();state=h.request(8788,'/stereo/status')
    assert not state['busy'] and not state['section_busy'] and not state['standby']
    current=h.owners();assert set(current)=={'full_camera.py','physical_keys.py'}
    assert all(Path(v['cwd']).resolve()==S for v in current.values())
    loaded=(S/'loaded.json').read_text();assert json.loads(loaded)['sha256']==h.OLD_SHA
    assert h.sha(S/'usb320.bit.bin')==h.OLD_SHA
    job=state['result_id'];assert job and job==state['job_id']
    metadata=state['metadata'];held=dict(job_id=job,sha256=metadata['package_sha256'],bytes=metadata['package_bytes'],total_seconds=metadata['total_seconds'])
    cached=R/'stable_held.npz'
    if not cached.is_file() or h.sha(cached)!=held['sha256']:
        c=http.client.HTTPConnection('192.168.137.2',8788,timeout=20,source_address=('127.0.0.1',0))
        try:
            c.request('GET','/stereo/result.npz?id='+job);response=c.getresponse();assert response.status==200
            temp=R/'stable_held.tmp';digest=hashlib.sha256()
            with temp.open('wb') as f:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    digest.update(chunk);f.write(chunk)
            assert digest.hexdigest()==held['sha256'];temp.replace(cached)
        finally:c.close()
    preview=h.request(8788,'/status')
    saved=dict(owners=current,loaded=loaded,held=held,standby=False,mode=preview['mode'],tone=preview['tone_map']['enabled'],restore_files={})
    fd=os.open(str(h.SNAP),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(saved,f)
    return saved

def process_state(item):
    root=Path('/proc')/str(item['pid'])
    fields=(root/'stat').read_text().split(') ',1)[1].split()
    assert fields[19]==item['start'],'Camera/key PID was reused'
    return fields[0]

def wait_state(item,frozen):
    for _ in range(100):
        state=process_state(item)
        if frozen:
            tasks=list((Path('/proc')/str(item['pid'])/'task').glob('*/stat'))
            if state in ('T','t') and tasks and all(p.read_text().split(') ',1)[1][0] in ('T','t') for p in tasks):return
        elif state not in ('T','t'):return
        time.sleep(.01)
    raise TimeoutError('Camera process did not reach the requested stop/resume state')

def journal(saved):
    temp=R/'pl_test_private_snapshot.tmp'
    fd=os.open(str(temp),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(saved,f);f.flush();os.fsync(f.fileno())
    temp.replace(h.SNAP)

def assert_frozen_lease(saved):
    camera=saved['owners']['full_camera.py'];wait_state(camera,True)
    assert saved.get('pause_lease',{}).get('frozen')
    inode=(R.parent/'full_v2/hdmi.lock').stat().st_ino
    locks=[line.split() for line in Path('/proc/locks').read_text().splitlines() if '->' not in line]
    assert any(len(v)>5 and v[1:4]==['FLOCK','ADVISORY','WRITE'] and int(v[4])==camera['pid'] and int(v[5].split(':')[-1])==inode for v in locks),'Frozen camera does not own the HDMI lease'

class MMIO:
    def __enter__(self):
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        self.dma=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=DMA)
        self.vtc=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=VTC)
        self.lib=ctypes.CDLL(str(S/'hdmi_mmio.so'))
        self.lib.hdmi_read32.argtypes=[ctypes.c_void_p];self.lib.hdmi_read32.restype=ctypes.c_uint32
        self.lib.hdmi_write32.argtypes=[ctypes.c_void_p,ctypes.c_uint32];self.lib.hdmi_write32.restype=None
        return self
    def read(self,reg,offset):return int(self.lib.hdmi_read32(ctypes.addressof(ctypes.c_char.from_buffer(reg,offset))))
    def write(self,reg,offset,value):self.lib.hdmi_write32(ctypes.addressof(ctypes.c_char.from_buffer(reg,offset)),value)
    def wait(self,offset,mask,value):
        deadline=time.monotonic()+1
        while self.read(self.dma,offset)&mask!=value:
            if time.monotonic()>deadline:raise TimeoutError('VDMA drain/restart failed')
            time.sleep(.001)
    def __exit__(self,*unused):self.dma.close();self.vtc.close();os.close(self.fd)

def wait_key_exit(key):
    for _ in range(100):
        try:
            if process_state(key)=='Z':return
        # /proc/stat can open successfully then return ESRCH during read when
        # the kernel reaps the process. Both cases mean the verified PID exited.
        except (FileNotFoundError,ProcessLookupError):return
        time.sleep(.02)
    raise TimeoutError('Keys did not drain')

def pause(saved):
    assert h.owners()==saved['owners']
    lease=saved['pause_lease']=dict(keys_stopped=False,frozen=False,registers=None);journal(saved)
    key=saved['owners']['physical_keys.py'];process_state(key);os.kill(key['pid'],signal.SIGTERM)
    wait_key_exit(key)
    lease['keys_stopped']=True;journal(saved)
    previous_frame=h.request(8788,'/hdmi/status')['frames']
    h.request(8788,'/standby',{'enabled':True})
    assert h.request(8788,'/stereo/status')['standby']
    device=os.path.realpath(saved['owners']['full_camera.py']['env'].get('USB_DEVICE','/dev/video0'))
    descriptors=Path('/proc')/str(saved['owners']['full_camera.py']['pid'])/'fd'
    for _ in range(300):
        opened=[]
        for path in descriptors.iterdir():
            try:
                if os.path.realpath(path)==device:opened.append(path.name)
            except FileNotFoundError:pass
        video=h.request(8788,'/hdmi/status')
        if not opened and video['source']=='standby' and video['frames']>previous_frame and not video['error']:break
        time.sleep(.01)
    else:raise TimeoutError('UVC descriptors/standby scanout did not drain before freezing')
    lease['uvc_descriptors_closed']=True;lease['standby_frame_presented']=True
    lease['frozen']=True;journal(saved)
    os.kill(saved['owners']['full_camera.py']['pid'],signal.SIGSTOP)
    assert_frozen_lease(saved)
    with MMIO() as io:
        assert io.read(io.dma,0x2c)>>28==6 and io.read(io.vtc,0x10)>>24==6
        registers=dict(dma={str(o):io.read(io.dma,o) for o in (0,0x28,0x50,0x54,0x58,0x5c,0x60)},vtc={str(o):io.read(io.vtc,o) for o in (0,)+VIDEO_REGS})
        lease['registers']=registers;journal(saved)
        io.write(io.dma,0,0);io.wait(4,1,1)
    print('PREVIEW_FROZEN_VDMA_DRAINED',flush=True)

def resume(saved):
    timings={};started=time.monotonic()
    lease=saved.get('pause_lease',{});camera=saved['owners']['full_camera.py']
    if lease.get('frozen'):
        assert_frozen_lease(saved)
        regs=lease.get('registers')
        if regs:
            with MMIO() as io:
                d={int(k):v for k,v in regs['dma'].items()};v={int(k):v for k,v in regs['vtc'].items()}
                io.write(io.dma,0,0);io.wait(4,1,1);io.write(io.dma,0,4);io.wait(0,4,0)
                io.write(io.vtc,0,0)
                for off in VIDEO_REGS:io.write(io.vtc,off,v[off])
                io.write(io.vtc,0,v[0]);io.write(io.dma,4,0xff0);io.write(io.dma,0,d[0]);io.wait(4,1,0)
                for off in (0x5c,0x60,0x58,0x54):io.write(io.dma,off,d[off])
                io.write(io.dma,0x50,d[0x50]);park=d[0x28]&0xffff
                io.write(io.dma,0x28,park);io.wait(0x28,0x1f0000,(park&0x1f)<<16)
        (S/'loaded.json').write_text(saved['loaded'])
        os.kill(camera['pid'],signal.SIGCONT);wait_state(camera,False)
    timings['restore_mmio_and_thaw']=time.monotonic()-started;started=time.monotonic()
    h.request(8788,'/standby',{'enabled':saved['standby']})
    for _ in range(80):
        c=h.request(8788,'/status');video=h.request(8788,'/hdmi/status')
        if not c['error'] and not c.get('preview_error') and not c.get('jpeg_error') and c['age_seconds']<.3 and not video['error'] and video['source']=='preview':break
        time.sleep(.05)
    else:
        # The original bit is already restored. A failed UVC reopen may safely use
        # the proven full-service restart; never leave a completed photo stranded.
        assert not json.loads((R/'configuration_state.json').read_text())['new']
        assert not (S/'hdmi.fault').exists()
        current=h.owners();assert set(current)=={'full_camera.py'} and current['full_camera.py']==camera
        h.stop(current);h.restore_services(saved)
        report=json.loads((R/'stable_restored.json').read_text())
        report.update(camera_process_preserved=False,preview_restart_fallback=True)
        (R/'stable_restored.json').write_text(json.dumps(report,indent=2))
        return report
    timings['uvc_reopen_and_fresh_preview']=time.monotonic()-started;started=time.monotonic()
    state=h.request(8788,'/stereo/status')
    assert state['result_id']==saved['held']['job_id'] and state['metadata']['package_sha256']==saved['held']['sha256']
    if lease.get('keys_stopped'):
        assert set(h.owners())=={'full_camera.py'}
        key=saved['owners']['physical_keys.py']
        with (S/'physical_keys_fast_resume.log').open('ab',buffering=0) as log:
            p=subprocess.Popen(key['cmd'],cwd=key['cwd'],env=key['env'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        for _ in range(80):
            assert p.poll() is None
            status=json.loads((S/'physical_keys_status.json').read_text())
            if status.get('pid')==p.pid:break
            time.sleep(.05)
        else:raise RuntimeError('Key service did not recover')
    owners=h.owners();assert set(owners)=={'full_camera.py','physical_keys.py'}
    assert owners['full_camera.py']==camera
    timings['keys_and_ownership_verification']=time.monotonic()-started
    report=dict(resume_breakdown_seconds=timings,passed=True,held=saved['held'],camera_pid=camera['pid'],keys_pid=owners['physical_keys.py']['pid'],camera_process_preserved=True,preview=c,hdmi=video,stable_bitstream_sha256=h.OLD_SHA)
    (R/'stable_restored.json').write_text(json.dumps(report,indent=2))
    print('PREVIEW_RESUMED_SAME_CAMERA',camera['pid'],flush=True)
    return report
