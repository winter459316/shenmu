"""Exclusive access to explicitly reserved, uncached DDR and verified PL cores.

No arbitrary Linux physical memory is accepted. Firmware loading is separate.
"""
import ctypes,fcntl,json,mmap,os,re,struct,time
from pathlib import Path
BASE=0x60000000;SIZE=0x08000000
TAG=0x6dbbd7ca

def require_legacy_compute():
    from hardware_catalog import loaded_variant
    record=json.loads((Path(__file__).resolve().parent/'loaded.json').read_text())
    if not loaded_variant(record).get('legacy_compute',True):
        raise ValueError('Legacy SGM/completion/PL geometry is unavailable in the preview-only hardware; use Fast capture')

def reservation():
    node=Path('/proc/device-tree/reserved-memory/usb-pl-dma@60000000')
    reg=struct.unpack('>QQ',(node/'reg').read_bytes())
    assert reg==(BASE,SIZE) and (node/'no-map').is_file(),'DMA reservation mismatch'
    iomem=Path('/proc/iomem').read_text()
    for line in iomem.splitlines():
        m=re.fullmatch(r'([0-9a-f]+)-([0-9a-f]+) : System RAM',line)
        if m:
            lo,hi=[int(v,16) for v in m.groups()]
            assert hi<BASE or lo>=BASE+SIZE,'DMA overlaps Linux System RAM'
    assert 'System RAM' in iomem,'Cannot verify RAM map'
    assert Path('/proc/device-tree/amba_pl@0/status').read_bytes().rstrip(b'\0')==b'disabled'
    return {'base':hex(BASE),'size':SIZE,'no_map':True,'excluded_from_system_ram':True}

class Arena:
    def __init__(self,controls=False):
        if controls:require_legacy_compute()
        self.reservation=reservation()
        self.lock=open('/tmp/usb_stereo_probe/full_v2/dma.lock','a+')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        self.memory=mmap.mmap(self.fd,SIZE,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=BASE)
        self.library=ctypes.CDLL(str(Path(__file__).parent/'dma_barrier.so'))
        self.fence=self.library.dma_barrier
        self.fence.argtypes=[];self.fence.restype=None
        self.controls={}
        if controls:
            assert not (Path(__file__).resolve().parent/'dma.fault').exists(),'Previous DMA fault requires verified PL reload'
            loaded=json.loads((Path(__file__).resolve().parent/'loaded.json').read_text())
            assert loaded['version']=='usb_full_v2' and loaded['state']=='operating'
            for i,name in enumerate(('sgm','images','geometry','completion')):
                self.controls[name]=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0xA1010000+0x10000*i)
    def write(self,core,offset,value):struct.pack_into('<I',self.controls[core],offset,int(value)&0xffffffff)
    def read(self,core,offset):return struct.unpack_from('<I',self.controls[core],offset)[0]
    def command(self,core,args,timeout=30):
        if not self.read(core,0)&4:raise RuntimeError(core+' is not idle')
        for offset,value in args.items():self.write(core,offset,value)
        self.fence();self.write(core,0,1);self.fence();start=time.monotonic()
        while not self.read(core,0)&2:
            if time.monotonic()-start>timeout:
                (Path(__file__).resolve().parent/'dma.fault').write_text(core+' timeout')
                raise TimeoutError(core+' timeout; do not reuse this PL until reload')
            time.sleep(.001)
        self.fence();return self.read(core,0x10),time.monotonic()-start
    def close(self):
        for value in self.controls.values():value.close()
        self.memory.close();os.close(self.fd);self.lock.close()

if __name__=='__main__':
    a=Arena(False)
    offsets=[0,4096,SIZE//2,SIZE-4096]
    saved=[a.memory[o:o+16] for o in offsets]
    try:
        for i,o in enumerate(offsets):a.memory[o:o+16]=struct.pack('<IIII',0x55444132,i,o,~o&0xffffffff)
        assert all(a.memory[o:o+16]==struct.pack('<IIII',0x55444132,i,o,~o&0xffffffff) for i,o in enumerate(offsets))
        result=dict(a.reservation,cpu_read_write_verified=True,pl_dma_started=False)
        print(json.dumps(result));Path('/tmp/usb_stereo_probe/usb320_dense3d/dma_reservation_verified.json').write_text(json.dumps(result,indent=2))
    finally:
        for o,b in zip(offsets,saved):a.memory[o:o+16]=b
        a.close()
