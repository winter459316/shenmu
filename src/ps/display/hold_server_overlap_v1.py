"""One immutable stereo photo across the existing qualified PL2 and PL3 images."""
from pathlib import Path
import ctypes,fcntl,hashlib,json,mmap,os,re,socket,sys,time,traceback
R=Path(__file__).resolve().parent;S=R.parent/'usb320_hdmifps';H=R.parent/'pl_pipeline_20261025'
sys.path.insert(0,str(R.parent/'fast_board/deps'));sys.path.insert(0,str(S))
import cv2,numpy as np
import pause_preview_board as preview
from hdmi_output import Scanout,FRAME_BYTES,FB0

class FrozenScanout(Scanout):
    def __init__(self,saved,expected):
        preview.assert_frozen_lease(saved)
        assert json.loads((R/'loaded.json').read_text())['sha256']==expected
        assert json.loads((R/'configuration_state.json').read_text())['new']
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
        self.lock=(R/'processing_preview.lock').open('a+');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.loaded=(S/'loaded.json').read_bytes();assert json.loads(self.loaded)['state']=='suspended'
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        self.memory=mmap.mmap(self.fd,FRAME_BYTES*2,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=FB0)
        self.dma=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=preview.DMA)
        self.vtc=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=preview.VTC)
        lib=ctypes.CDLL(str(S/'dma_barrier.so'));self.fence=lib.dma_barrier;self.fence.argtypes=[];self.fence.restype=None;self.library=lib
        self.mmio=ctypes.CDLL(str(S/'hdmi_mmio.so'))
        self.mmio.hdmi_read32.argtypes=[ctypes.c_void_p];self.mmio.hdmi_read32.restype=ctypes.c_uint32
        self.mmio.hdmi_write32.argtypes=[ctypes.c_void_p,ctypes.c_uint32];self.mmio.hdmi_write32.restype=None
        self.front=0;self.frames=0;self.last_sha256=None
        self.initialize()

def main(job):
    assert re.fullmatch('[0-9a-f]{32}',job);cv2.setNumThreads(1)
    folder=R/'jobs'/job;path=folder/'hdmi_hold.sock';assert not path.exists()
    saved=json.loads((R/'pl_test_private_snapshot.json').read_text())
    # Preparation touches cached RAM only. FrozenScanout checks the frozen lease
    # again at activation, after the FPGA image has been loaded.
    owner=os.getppid();assert owner==saved['pl3_runtime_owner']['pid']
    image=cv2.imread(str(folder/'input.png'));assert image is not None and image.shape==(480,1280,3)
    ok,jpg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,90]);assert ok
    (folder/'processing_preview.jpg').write_bytes(jpg.tobytes())
    canvas=np.zeros((720,1280,3),np.uint8);canvas[120:600]=image;pixels=canvas.tobytes()
    profiles={'pl2':json.loads((R/'hardware_verified.json').read_text())['sha256'],
              'pl3':json.loads((H/'pl3_usable_v5_quad_manifest_20261028.json').read_text())['physical_bridge']['physical']['sha256']}
    display=None;segments=[];current=None;failure='';stopped=False
    def report():
        result=dict(job_id=job,pid=os.getpid(),running=not stopped,segments=segments,error=failure,
                    native_sha256=hashlib.sha256(image.tobytes()).hexdigest(),frame_sha256=hashlib.sha256(pixels).hexdigest(),
                    framebuffer=[hex(FB0),hex(FB0+FRAME_BYTES)],frames=len(segments),display_mode='captured_still',vdma_drained=display is None)
        temp=folder/'hdmi_hold.tmp';temp.write_text(json.dumps(result,indent=2));temp.replace(folder/'hdmi_hold.json')
    def drain():
        nonlocal display,current
        if display is not None:
            display.close();display=None;current['end_monotonic']=time.monotonic();current['vdma_drained']=True;current=None
        report()
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(path));os.chmod(str(path),0o600);server.listen(2);server.settimeout(.5)
        try:
            while not stopped:
                if os.getppid()!=owner:raise RuntimeError('Capture display owner exited')
                try:connection,_=server.accept()
                except socket.timeout:continue
                with connection:
                    connection.settimeout(5)
                    try:
                        with connection.makefile('rb') as f:args=json.loads(f.readline(512))
                        assert args['job_id']==job
                        action=args['action']
                        if action in ('stop','exit'):drain();stopped=action=='exit'
                        elif action=='start':
                            assert display is None
                            profile=args['profile'];expected=profiles[profile]
                            assert not (R/'dma.fault').exists()
                            display=FrozenScanout(saved,expected);display.present(pixels)
                            current=dict(profile=profile,sha256=expected,start_monotonic=time.monotonic(),vdma_drained=False,frame_sha256=display.last_sha256)
                            segments.append(current);report()
                        else:raise ValueError('Unknown display command')
                        connection.sendall((json.dumps(dict(ok=True,segments=len(segments),active=display is not None))+'\n').encode())
                    except BaseException as exc:
                        failure=repr(exc);report();connection.sendall((json.dumps(dict(ok=False,error=failure))+'\n').encode());raise
        finally:
            drain();stopped=True;report();path.unlink()
    if failure:raise RuntimeError(failure)
if __name__=='__main__':main(sys.argv[1])
