"""Temporary static HDMI owner while the original camera is verified frozen.

The capture owner starts this only after programming the Fast bitstream and
waits for a verified VDMA drain before programming the original image back.
One immutable captured photo is presented once; no UVC acquisition loop.
"""
from pathlib import Path
import ctypes,fcntl,json,mmap,os,signal,sys,time,traceback
R=Path(__file__).resolve().parent;S=R.parent/'usb320_hdmifps'
sys.path.insert(0,str(S))
import cv2,numpy as np
import pause_preview_board as preview
from hdmi_output import Scanout,FRAME_BYTES,FB0

class BorrowedScanout(Scanout):
    def __init__(self,saved):
        preview.assert_frozen_lease(saved)
        proof=json.loads((R/'hardware_verified.json').read_text())
        assert json.loads((R/'configuration_state.json').read_text())['new']
        assert json.loads((R/'loaded.json').read_text())['sha256']==proof['sha256']
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
        self.lock=open(R/'processing_preview.lock','a+');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.loaded=(S/'loaded.json').read_bytes()
        assert json.loads(self.loaded)['state']=='suspended'
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        self.memory=mmap.mmap(self.fd,FRAME_BYTES*2,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=FB0)
        self.dma=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=preview.DMA)
        self.vtc=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=preview.VTC)
        self.library=ctypes.CDLL(str(S/'dma_barrier.so'));self.fence=self.library.dma_barrier;self.fence.argtypes=[];self.fence.restype=None
        self.mmio=ctypes.CDLL(str(S/'hdmi_mmio.so'))
        self.mmio.hdmi_read32.argtypes=[ctypes.c_void_p];self.mmio.hdmi_read32.restype=ctypes.c_uint32
        self.mmio.hdmi_write32.argtypes=[ctypes.c_void_p,ctypes.c_uint32];self.mmio.hdmi_write32.restype=None
        self.front=0;self.frames=0;self.last_sha256=None
        self.initialize()

def main(job):
    import re
    assert re.fullmatch('[0-9a-f]{32}',job)
    folder=R/'jobs'/job;stop=False;video=None;count=0;error='';drained=False
    parent=os.getppid();started=time.monotonic();first=None;work=0
    def finish(*_):
        nonlocal stop
        stop=True
    def report(running):
        d=dict(job_id=job,pid=os.getpid(),running=running,display_mode='captured_still',
            frames=count,mean_fps=0,elapsed_seconds=time.monotonic()-started,
            first_frame_seconds=first,work_seconds=work,error=error,vdma_drained=drained,
            frame_sha256=video.last_sha256 if video else None,updated=time.time())
        temp=folder/'processing_preview.tmp';temp.write_text(json.dumps(d));temp.replace(folder/'processing_preview.json')
    signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish);cv2.setNumThreads(1)
    try:
        saved=json.loads((R/'pl_test_private_snapshot.json').read_text());preview.assert_frozen_lease(saved)
        frame=cv2.imread(str(folder/'input.png'));assert frame is not None and frame.shape==(480,1280,3)
        video=BorrowedScanout(saved)
        began=time.monotonic();canvas=np.zeros((720,1280,3),np.uint8);canvas[:]=(28,17,11)
        canvas[120:600]=frame
        cv2.putText(canvas,'FAST PROCESSING | CAPTURED STEREO PHOTO',(25,40),cv2.FONT_HERSHEY_SIMPLEX,.72,(230,235,240),2)
        cv2.putText(canvas,'STILL',(1140,40),cv2.FONT_HERSHEY_SIMPLEX,.65,(120,240,145),2)
        cv2.putText(canvas,'This is the frozen photo being processed. Results will appear automatically.',(25,680),cv2.FONT_HERSHEY_SIMPLEX,.6,(190,205,220),1)
        video.present(canvas.tobytes());count=1;first=time.monotonic()-started
        ok,jpg=cv2.imencode('.jpg',cv2.resize(frame,(640,240),interpolation=cv2.INTER_AREA),[cv2.IMWRITE_JPEG_QUALITY,75]);assert ok
        temp=folder/'processing_preview.jpg.tmp';temp.write_bytes(jpg.tobytes());temp.replace(folder/'processing_preview.jpg')
        work=time.monotonic()-began;report(True)
        # PL VDMA repeatedly scans the stored frame; no CPU rendering/capture loop.
        while not stop and os.getppid()==parent and time.monotonic()-started<720:time.sleep(.1)
    except BaseException as exc:error=repr(exc);traceback.print_exc()
    finally:
        if video is not None:video.close();drained=True
        else:
            with preview.MMIO() as io:drained=bool(io.read(io.dma,4)&1)
        report(False)
    if error:raise RuntimeError(error)

if __name__=='__main__':main(sys.argv[1])
