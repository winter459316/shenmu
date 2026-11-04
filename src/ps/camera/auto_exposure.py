"""Shared UVC exposure for the two halves; no pixel/gamma modifications.

V4L2 exposure_absolute uses 100 us units. A separate low-rate worker keeps
USB control latency out of the capture and shared-preview threads.
"""
import os, struct, threading, time
import numpy as np
from pathlib import Path
import sys,json
_config=Path(__file__).resolve().parent/'preview_config.json'
_PL_METER=sys.platform.startswith('linux') and _config.is_file() and json.loads(_config.read_text()).get('enabled',False)
if _PL_METER:import pl_preview

AUTO=0x009a0901
ABSOLUTE=0x009a0902
MAINS=0x00980918

class Controls:
    def __init__(self,device):
        import fcntl
        self.ioctl=fcntl.ioctl
        self.fd=os.open(device,os.O_RDWR|os.O_NONBLOCK)
    def get(self,cid):
        data=bytearray(struct.pack('Ii',cid,0))
        self.ioctl(self.fd,0xc008561b,data,True)  # VIDIOC_G_CTRL
        return struct.unpack('Ii',data)[1]
    def set(self,cid,value):
        data=bytearray(struct.pack('Ii',cid,int(value)))
        self.ioctl(self.fd,0xc008561c,data,True)  # VIDIOC_S_CTRL
        actual=self.get(cid)
        if actual!=int(value):raise RuntimeError('UVC control readback differs: %x'%cid)
        return actual
    def limits(self,cid):
        data=bytearray(68);struct.pack_into('I',data,0,cid)
        self.ioctl(self.fd,0xc0445624,data,True)  # VIDIOC_QUERYCTRL
        minimum,maximum,step,default,flags=struct.unpack_from('iiiiI',data,40)
        if flags&1:raise RuntimeError('UVC control disabled')
        return minimum,maximum,step,default
    def close(self):os.close(self.fd)

def meter_cpu(frame):
    if frame.dtype!=np.uint8 or frame.shape!=(480,1280,3):
        raise ValueError('Exposure requires native stereo BGR')
    eyes=[]
    for x in (0,640):
        # Central 80% of each eye; identical sampling and shared exposure.
        p=frame[48:432:8,x+64:x+576:8].astype(np.float32)
        y=.114*p[:,:,0]+.587*p[:,:,1]+.299*p[:,:,2]
        eyes.append({'mean':float(y.mean()),'bright_fraction':float((y>245).mean()),
                     'dark_fraction':float((y<12).mean())})
    return {'left':eyes[0],'right':eyes[1],
            'mean':sum(e['mean'] for e in eyes)/2,
            'bright_fraction':max(e['bright_fraction'] for e in eyes),
            'eye_difference':abs(eyes[0]['mean']-eyes[1]['mean'])}

def meter(frame):return pl_preview.meter(frame) if _PL_METER else meter_cpu(frame)

def decide(stats,current,minimum=3,maximum=300,step=1):
    """Dead band and bounded multiplicative steps avoid visible oscillation."""
    level=stats['mean'];clip=stats['bright_fraction']
    if clip>.06:factor=.80;reason='reduce_highlights'
    elif level>125:factor=max(.8,(112/max(level,1))**.6);reason='bright'
    elif level<99 and clip<.02:factor=min(1.25,(112/max(level,1))**.6);reason='dark'
    else:return current,'stable'
    value=minimum+int(round((current*factor-minimum)/step))*step
    value=max(minimum,min(maximum,value))
    if value==current:reason='limit_dark' if factor>1 else 'limit_bright'
    return value,reason

class AutoExposure:
    def __init__(self,device,sample,controls=Controls):
        self.device=device;self.sample=sample;self.controls=controls
        self.stop=threading.Event();self.lock=threading.Lock()
        self.state={'mode':'starting','error':'','interval_seconds':.5,
                    'shared_stereo_control':True,'hardware_sync_verified':False,
                    'pixel_transform':False,'updates':0,'samples':0,
                    'exposure_ms':None,'actual_exposure_time_available':False,
                    'controller':'Camera AE/AGC; PL metering; A53 UVC control' if _PL_METER else 'Camera AE/AGC; A53 supervision',
                    'metering_backend':'PL PXP1' if _PL_METER else 'A53',
                    'exposure_limit_enforced':False}
        self.worker=threading.Thread(target=self.run,name='uvc-auto-exposure',daemon=True)
        self.worker.start()
    def update(self,**values):
        with self.lock:self.state.update(values)
    def status(self):
        with self.lock:return dict(self.state)
    def run(self):
        ctl=None;old={};last_sequence=None;updates=0;samples=0;last_check=0;warning_since=None
        try:
            ctl=self.controls(self.device)
            old={AUTO:ctl.get(AUTO),MAINS:ctl.get(MAINS)}
            ctl.set(MAINS,1)  # 50 Hz local lighting; camera implements anti-flicker.
            ctl.set(AUTO,3)
            self.update(mode='camera_auto',power_line_hz=50,auto_control=3)
            while not self.stop.wait(.5):
                sample=self.sample()
                if sample is None:continue
                frame,seq=sample
                if seq==last_sequence:continue
                last_sequence=seq;began=time.monotonic();stats=meter(frame)
                if stats is None:continue
                # Do not fight the sensor's AE/AGC or trust the stale manual
                # exposure value: this camera reports 166 even while in auto.
                if began-last_check>=2:
                    if ctl.get(AUTO)!=3:ctl.set(AUTO,3);updates+=1
                    last_check=began
                reason='dark' if stats['mean']<60 else 'bright' if stats['bright_fraction']>.15 else 'normal'
                if reason=='normal':warning_since=None
                elif warning_since is None:warning_since=began
                warning=reason if warning_since is not None and began-warning_since>3 else ''
                samples+=1
                self.update(mode='camera_auto',reason=reason,warning=warning,
                            metering=stats,updates=updates,samples=samples,
                            sequence=seq,last_control_ms=(time.monotonic()-began)*1000)
        except Exception as exc:
            # A failed optional controller must not stop camera acquisition.
            fallback_error=''
            if ctl is not None:
                try:ctl.set(AUTO,3)
                except Exception as fallback:fallback_error=str(fallback)
            self.update(mode='error' if ctl is None or fallback_error else 'camera_auto_fallback',
                        error=str(exc),fallback_error=fallback_error)
            self.stop.wait()
        finally:
            if ctl is not None:
                try:
                    if AUTO in old:ctl.set(AUTO,old[AUTO])
                    if MAINS in old:ctl.set(MAINS,old[MAINS])
                except Exception as exc:self.update(restore_error=str(exc))
                finally:ctl.close()
    def close(self):
        self.stop.set();self.worker.join(timeout=3)
        if self.worker.is_alive():raise RuntimeError('Exposure worker did not drain')
