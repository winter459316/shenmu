"""Linux HDMI: private double buffers, VDMA/VT timing, shared camera preview.

Only the verified HDMI image may map these peripherals. The original compute
arena ends at FB0; no camera/matching/geometry buffer is used for scanout.
Register definitions follow SDK2018.2 xaxivdma_hw.h and xvtc.c/xvtc_hw.h.
"""
import ctypes,fcntl,hashlib,json,mmap,os,struct,threading,time
from pathlib import Path
import cv2
import numpy as np
from board_dma import BASE,SIZE,reservation
from hardware_catalog import loaded_variant
from hdmi_fps import FrameRate
import preview_zoom

ROOT=Path(__file__).resolve().parent
WIDTH,HEIGHT=1280,720
FRAME_BYTES=WIDTH*HEIGHT*3
FB0=0x679E0000
BUFFERS=(FB0,FB0+FRAME_BYTES)
assert FB0==BASE+26*640*480*16 and BUFFERS[1]+FRAME_BYTES<=BASE+SIZE


class Scanout:
    def __init__(self):
        reservation()
        self.loaded=(ROOT/'loaded.json').read_bytes()
        assert loaded_variant(json.loads(self.loaded))['hdmi'],'HDMI bitstream is not verified'
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
        self.lock=open('/tmp/usb_stereo_probe/full_v2/hdmi.lock','a+')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        self.memory=mmap.mmap(self.fd,FRAME_BYTES*2,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=FB0)
        self.dma=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0xA1050000)
        self.vtc=mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0xA1060000)
        self.library=ctypes.CDLL(str(ROOT/'dma_barrier.so'))
        self.fence=self.library.dma_barrier;self.fence.argtypes=[];self.fence.restype=None
        self.mmio=ctypes.CDLL(str(ROOT/'hdmi_mmio.so'))
        self.mmio.hdmi_read32.argtypes=[ctypes.c_void_p];self.mmio.hdmi_read32.restype=ctypes.c_uint32
        self.mmio.hdmi_write32.argtypes=[ctypes.c_void_p,ctypes.c_uint32];self.mmio.hdmi_write32.restype=None
        self.front=0;self.frames=0;self.last_sha256=None
        try:self.initialize()
        except Exception:
            self.close();raise
    def read(self,reg,offset):
        return self.mmio.hdmi_read32(ctypes.addressof(ctypes.c_char.from_buffer(reg,offset)))
    def write(self,reg,offset,value):
        self.mmio.hdmi_write32(ctypes.addressof(ctypes.c_char.from_buffer(reg,offset)),value)
    def registers(self):
        return {hex(off):hex(self.read(self.dma,off)) for off in (0,4,0x18,0x28,0x2c,0x50,0x54,0x58,0x5c,0x60)}
    def wait(self,offset,mask,value,timeout=.8):
        deadline=time.monotonic()+timeout
        while (self.read(self.dma,offset)&mask)!=value:
            if time.monotonic()>deadline:
                raise TimeoutError('HDMI VDMA state timeout: '+json.dumps(self.registers()))
            time.sleep(.001)
    def initialize(self):
        assert self.read(self.dma,0x2c)>>28==6,'Unexpected VDMA major version'
        assert self.read(self.vtc,0x10)>>24==6,'Unexpected VTC major version'
        # Drain first; never reset an outstanding AXI transfer.
        self.write(self.dma,0,0);self.wait(4,1,1)
        self.write(self.dma,0,4);self.wait(0,4,0)
        self.memory[:]=bytes(FRAME_BYTES*2);self.fence()
        # 1280x720 progressive, 1650x750 total, positive syncs. The verified
        # clock is ~75MHz, giving ~60.606Hz, not exactly CEA 59.94/60Hz.
        self.write(self.vtc,0,0)
        for off,value in ((0x60,(720<<16)|1280),(0x68,0),(0x6c,0x7f),
                          (0x70,1650),(0x74,(750<<16)|750),(0x78,(1430<<16)|1390),
                          (0x7c,(1280<<16)|1280),(0x80,(729<<16)|724),(0x84,(1390<<16)|1390),
                          (0x88,(1280<<16)|1280),(0x8c,(729<<16)|724),(0x90,(1390<<16)|1390)):
            self.write(self.vtc,off,value)
        self.write(self.vtc,0,0x03fdef07)
        self.write(self.dma,4,0xff0);self.write(self.dma,0x28,0)
        # PG020 direct-register programming sequence: start RUN first, then
        # program frame addresses/stride/HSIZE and finally trigger VSIZE.
        self.write(self.dma,0,0x00010001);self.fence();self.wait(4,1,0)
        for i,address in enumerate(BUFFERS):self.write(self.dma,0x5c+4*i,address)
        self.write(self.dma,0x58,WIDTH*3);self.write(self.dma,0x54,WIDTH*3)
        self.fence();self.write(self.dma,0x50,HEIGHT);self.fence()
    def present(self,bgr):
        if not isinstance(bgr,bytes) or len(bgr)!=FRAME_BYTES:raise ValueError('HDMI requires one complete 1280x720 BGR frame')
        if (ROOT/'loaded.json').read_bytes()!=self.loaded:raise RuntimeError('Hardware changed while HDMI was active')
        if self.read(self.dma,4)&0xff1:raise RuntimeError('HDMI VDMA error: '+json.dumps(self.registers()))
        self.wait(0x28,0x1f0000,self.front<<16)
        back=self.front^1;offset=back*FRAME_BYTES
        self.memory[offset:offset+FRAME_BYTES]=bgr;self.fence()
        self.write(self.dma,0x28,back);self.wait(0x28,0x1f0000,back<<16)
        self.front=back;self.frames+=1;self.last_sha256=hashlib.sha256(bgr).hexdigest()
        if self.read(self.dma,4)&0xff1:raise RuntimeError('HDMI frame scanout failed: '+json.dumps(self.registers()))
    def status(self):
        return {'frames':self.frames,'front_buffer':self.front,'vdma_status':self.read(self.dma,4),
                'vtc_status':self.read(self.vtc,0x64),'last_frame_sha256':self.last_sha256,
                'size':[WIDTH,HEIGHT],'buffers':[hex(x) for x in BUFFERS]}
    def close(self):
        # A failed drain remains an explicit fault; reconfiguration must stop.
        try:
            self.write(self.dma,0,0);self.wait(4,1,1)
            self.write(self.vtc,0,0)
        except Exception:
            (ROOT/'hdmi.fault').write_text('VDMA drain failed; do not reconfigure before resolving outstanding DMA')
            raise
        finally:
            self.dma.close();self.vtc.close();self.memory.close();os.close(self.fd);self.lock.close()


class HDMIOutput:
    def __init__(self,camera,runtime,scanout_factory=Scanout):
        self.camera=camera;self.runtime=runtime;self.scanout=scanout_factory()
        self.lock=threading.Lock();self.stop_event=threading.Event();self.updated=threading.Event()
        self.cast=None;self.cast_job=None;self.cast_until=0;self.error='';self.source='preview';self.received=0;self.generation=0
        self.external=None
        self.raw=None;self.raw_job=None;self.raw_report=None;self.raw_error=''
        self.last_result=runtime.status().get('result_id')
        self.scan_status=self.scanout.status()
        self.preview_unique_frames=0;self.preview_sequence=0;self.last_preview_key=None;self.last_caption=None
        self.latency_frames=0;self.ready_age_ms=0;self.present_age_ms=0;self.present_work_ms=0
        self.fps=FrameRate();self.fps_label='FPS: --'
        self.worker=threading.Thread(target=self.run,daemon=False);self.worker.start()
    def status(self):
        with self.lock:return dict(self.scan_status,enabled=True,source=self.source,error=self.error,
                                   received_frames=self.received,cast_job=self.cast_job,generation=self.generation,
                                   raw_job=self.raw_job,raw_report=self.raw_report,raw_error=self.raw_error,
                                   fast_job=self.external[1] if self.external else None,fast_view=self.external[2] if self.external else None,
                                   fps_label=self.fps_label,fps_scope='new content presented; not HDMI refresh rate',
                                   preview_latency={'frames':self.latency_frames,'ready_age_total_ms':self.ready_age_ms,
                                       'present_age_total_ms':self.present_age_ms,'present_work_total_ms':self.present_work_ms},
                                   preview_unique_frames=self.preview_unique_frames,preview_sequence=self.preview_sequence)
    def raw_disparity(self,job,expected_generation=None):
        from raw_disparity_hdmi import render
        with self.lock:
            generation=self.generation if expected_generation is None else expected_generation
        state=self.runtime.status()
        if state['busy'] or state['standby'] or not job or state['result_id']!=job:
            raise ValueError('Photo changed or board is not ready')
        package=self.runtime.result(job)
        if package is None:raise ValueError('Photo is no longer held')
        data,report=render(package,job)
        state=self.runtime.status()
        if state['busy'] or state['standby'] or state['result_id']!=job:
            raise ValueError('Photo changed during display preparation')
        with self.lock:
            if self.generation!=generation:raise ValueError('HDMI selection changed during preparation')
            self.cast=None;self.cast_job=None;self.cast_until=0
            self.raw=data;self.raw_job=job;self.raw_report=report;self.raw_error=''
            self.last_result=job;self.generation+=1
        return dict(report,display='raw_disparity',accepted=True)
    def accept(self,data,job,digest,generation):
        if len(data)!=FRAME_BYTES or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Incomplete HDMI frame or checksum mismatch')
        state=self.runtime.status()
        if state['busy'] or state['standby'] or state['result_id']!=job:raise ValueError('Photo changed or board is not ready')
        with self.lock:
            if self.error:raise RuntimeError(self.error)
            if generation!=self.generation:raise ValueError('HDMI returned to preview; start casting again explicitly')
            self.raw=None;self.raw_job=None
            self.cast=data;self.cast_job=job;self.cast_until=time.monotonic()+8;self.received+=1
        return {'accepted':True,'job_id':job,'sha256':digest}
    def present_external(self,data,job,view,dynamic=False):
        if not isinstance(data,bytes) or len(data)!=FRAME_BYTES:raise ValueError('Invalid Fast HDMI frame')
        with self.lock:
            if self.error:raise RuntimeError(self.error)
            self.cast=None;self.raw=None;self.cast_job=None;self.raw_job=None
            self.external=(data,job,view,dynamic);self.generation+=1
            self.updated.set()
    def preview(self):
        with self.lock:
            self.cast=None;self.cast_job=None;self.cast_until=0;self.raw=None;self.raw_job=None;self.external=None;self.generation+=1
            self.updated.set()
        return {'preview_requested':True}
    def run(self):
        canvas=np.zeros((HEIGHT,WIDTH,3),np.uint8);painted_caption=None;last_static=None
        try:
            while not self.stop_event.is_set():
                self.updated.clear()
                began=time.monotonic();state=self.runtime.status()
                # Observe publication only. Restored photos stay in preview until
                # explicitly requested; new successful photos show raw disparity.
                with self.lock:
                    new_result=state['result_id'] and state['result_id']!=self.last_result and not state['busy'] and not state['standby']
                    generation=self.generation
                    if new_result:self.last_result=state['result_id']
                if new_result:
                    try:self.raw_disparity(state['result_id'],generation)
                    except Exception as exc:
                        with self.lock:self.raw_error=str(exc)
                    state=self.runtime.status()
                with self.lock:
                    if self.raw is not None and (self.raw_job!=state['result_id'] or state['busy'] or state['standby']):
                        self.raw=None;self.raw_job=None;self.generation+=1
                    if self.cast is not None and (self.cast_job!=state['result_id'] or state['busy'] or state['standby'] or self.cast_until<=began):
                        self.cast=None;self.cast_job=None;self.cast_until=0;self.generation+=1
                    cast=self.cast if (self.cast_until>began and self.cast_job==state['result_id']
                                       and not state['busy'] and not state['standby']) else None
                    raw=self.raw
                    self.source='raw_disparity' if raw is not None else ('3d_cast' if cast is not None else ('standby' if state['standby'] else 'preview'))
                    if raw is not None:cast=raw
                    if self.external is not None and (state['busy'] or state['standby']):self.external=None
                    if self.external is not None:cast=self.external[0];self.source=('fast_live_' if self.external[3] else 'fast_')+self.external[2]
                    presented_generation=self.generation
                self.fps.select(self.source,time.monotonic())
                preview_key=None;caption_key=None;stamp=None
                # Static raw/3D images remain in VDMA scanout without CPU copies.
                # Keep polling control state; a different cast or preview wakes rendering.
                if cast is not None and cast is last_static:
                    self.updated.wait(.02);continue
                last_static=cast
                if cast is None:
                    mode=self.camera.status()['mode']
                    if not state['standby']:
                        try:
                            frame,sequence,stamp,mode,epoch=self.camera.preview_snapshot(self.last_preview_key)
                            preview_key=(sequence,epoch)
                            viewport=preview_zoom.status()
                            caption_key=(mode,state['stage'],viewport['revision'])
                            if preview_key==self.last_preview_key and caption_key==self.last_caption:
                                continue
                            preview_zoom.apply(frame,viewport,canvas[120:600])
                        except ValueError:
                            canvas[120:600]=0;self.stop_event.wait(.02)
                    else:canvas[120:600]=0
                    caption='FAST PROCESSING / PREVIEW PAUSED' if state['standby'] else 'USB STEREO | '+{'color':'COLOR ORIGINAL','auto_enhanced':'AUTO EXPOSURE'}.get(mode,mode.upper())+' | '+state['stage']
                    if painted_caption!=caption:
                        canvas[:120]=0;canvas[600:]=0
                        if not state['standby'] and mode=='rectified':
                            cv2.putText(canvas,'RECTIFIED L / R | 320x360 per eye | green lines: alignment',(24,78),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,220,0),1)
                        cv2.putText(canvas,caption,(24,42),cv2.FONT_HERSHEY_SIMPLEX,.8,(230,230,230),2)
                        cv2.putText(canvas,'PL_KEY2: Fast photo | PS_KEY1: results | PL_KEY1: preview',(24,685),cv2.FONT_HERSHEY_SIMPLEX,.65,(180,200,220),1)
                        painted_caption=caption
                    self.fps.draw(canvas);cast=canvas.tobytes()
                else:
                    # Display-only copy: raw disparity and incoming 3D payloads stay immutable.
                    overlay=np.frombuffer(cast,np.uint8).reshape(HEIGHT,WIDTH,3).copy()
                    self.fps.draw(overlay);cast=overlay.tobytes()
                present_began=time.monotonic()
                self.scanout.present(cast)
                content_key=preview_key if preview_key is not None else (presented_generation if self.source.startswith('fast_live_') else (self.received if self.source=='3d_cast' else None))
                self.fps.presented(content_key,time.monotonic())
                with self.lock:
                    self.fps_label=self.fps.label()
                    self.scan_status=self.scanout.status()
                    if preview_key is not None:
                        self.latency_frames+=1;self.ready_age_ms+=(present_began-stamp)*1000
                        self.present_age_ms+=(time.monotonic()-stamp)*1000
                        self.present_work_ms+=(time.monotonic()-present_began)*1000
                        if preview_key!=self.last_preview_key:self.preview_unique_frames+=1
                        self.last_preview_key=preview_key;self.preview_sequence=preview_key[0];self.last_caption=caption_key
                # Shared producer wakes preview at camera rate; no second 30-Hz
                # timer or repeated-frame presentations. Busy/standby stay bounded.
                interval=0 if (self.source=='preview' or self.source.startswith('fast_live_')) and not state['busy'] else .1
                if self.source=='standby':interval=.25
                self.stop_event.wait(max(0,interval-(time.monotonic()-began)))
        except Exception as exc:
            with self.lock:self.error=str(exc)
        finally:
            try:self.scanout.close()
            except Exception as exc:
                with self.lock:self.error=str(exc)
    def close(self):
        self.stop_event.set();self.updated.set();self.worker.join(timeout=4)
        if self.worker.is_alive():raise RuntimeError('HDMI worker did not drain')
