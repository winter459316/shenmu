"""USB v2 camera/service, isolated from the preserved parent camera program.

Start only after stopping the parent UVC owner. Gray/median/Sobel use PL;
native lossless frozen BGR frames enter the explicitly labelled PL engine.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('USB_SURFACE_NATIVE','1')
os.environ.setdefault('USB_MESH_NATIVE','1')
os.environ.setdefault('USB_HOLES_PARALLEL','1')
os.environ.setdefault('USB_ARCHIVE_STORED','1')
import json,signal,socket,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import cv2
from full_runtime import FullRuntime
from preview_rectify import MODES
from shared_preview import SharedPreview,FILTER_GATE,PL_FILTERS_ENABLED,EXTRA_ENABLED
if EXTRA_ENABLED:import pl_preview
if PL_FILTERS_ENABLED:import pl_filters
from auto_exposure import AutoExposure
from tone_map import description as tone_description
cv2.setNumThreads(3)

class Camera:
    def __init__(self,opener=None):
        self.lock=threading.Lock();self.ready=threading.Condition(self.lock)
        self.wake=threading.Event();self.running=True;self.standby=False;self.mode='color';self.epoch=0
        self.frame=None;self.sequence=0;self.timestamp=0;self.error='Opening camera'
        self.jpeg=None;self.jpeg_frames=0;self.jpeg_sequence=0;self.packet=None;self.preview_error=''
        self.small_packet=None;self.jpeg_packet=None;self.jpeg_error=''
        self.jpeg_work_ms=0;self.jpeg_age_ms=0;self.jpeg_skipped=0;self.jpeg_last_ms=0
        self.preview_skipped=0;self.preview_timings={};self.preview_totals={};self.preview_count=0
        self.device=os.environ.get('USB_DEVICE','/dev/video0')
        self.opener=opener or cv2.VideoCapture;self.recovery_count=0
        self.exposure=None
        self.processor=SharedPreview()
        self.worker=threading.Thread(target=self.acquire,daemon=True)
        self.preview_worker=threading.Thread(target=self.process_preview,daemon=True)
        self.jpeg_worker=threading.Thread(target=self.process_jpeg,daemon=True)
        self.worker.start();self.preview_worker.start();self.jpeg_worker.start()

    def invalidate(self,error):
        with self.ready:
            self.frame=None;self.packet=None;self.jpeg=None;self.timestamp=0;self.error=error
            self.small_packet=None;self.jpeg_packet=None
            self.epoch+=1;self.ready.notify_all()

    def set_mode(self,mode):
        if mode not in MODES:raise ValueError('Invalid preview mode')
        with self.ready:
            if mode!=self.mode:
                self.mode=mode;self.epoch+=1;self.packet=None;self.jpeg=None
                self.small_packet=None;self.jpeg_packet=None
                self.wake.set();self.ready.notify_all()

    def set_standby(self,enabled):
        # Gate order is always filter -> camera. Returning from standby means
        # every filter DMA has completed and no new filter can start.
        with FILTER_GATE:
            if PL_FILTERS_ENABLED:pl_filters.suspend(enabled)
            with self.ready:
                self.standby=enabled;self.epoch+=1;self.frame=None;self.packet=None;self.jpeg=None
                self.small_packet=None;self.jpeg_packet=None
                self.error='Standby' if enabled else 'Opening camera';self.timestamp=0
                self.wake.set();self.ready.notify_all()

    def set_tone(self,enabled):
        self.set_mode('auto_enhanced' if enabled else 'color')

    def acquire(self):
        cap=None;retry_at=0
        def release():
            if self.exposure is not None:
                self.exposure.close();self.exposure=None
            if cap is not None:cap.release()
        try:
            while self.running:
                if self.standby:
                    if cap is not None:release();cap=None
                    retry_at=0;time.sleep(.02);continue
                if time.monotonic()<retry_at:time.sleep(.02);continue
                try:
                    if cap is None:
                        cap=self.opener(self.device,cv2.CAP_V4L2)
                        if not cap.isOpened():raise RuntimeError('Cannot open UVC camera; check its current owner')
                        cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
                        cap.set(cv2.CAP_PROP_FPS,30);cap.set(cv2.CAP_PROP_BUFFERSIZE,2)
                        if os.environ.get('USB_AUTO_EXPOSURE','1')=='1' and self.opener is cv2.VideoCapture:
                            self.exposure=AutoExposure(self.device,self.exposure_sample)
                    ok,frame=cap.read()
                    if not ok or frame.shape!=(480,1280,3):raise RuntimeError('UVC requires a fresh 1280x480 stereo frame')
                    with self.lock:
                        if self.standby or not self.running:continue
                        self.frame=frame;self.sequence+=1;self.timestamp=time.monotonic();self.error=''
                        self.wake.set()
                except Exception as exc:
                    if cap is not None:release();cap=None
                    self.invalidate(str(exc));self.recovery_count+=1;retry_at=time.monotonic()+.5
        finally:
            release()

    def exposure_sample(self):
        with self.lock:
            if self.standby or not self.running or self.error or self.frame is None or time.monotonic()-self.timestamp>.25:
                return None
            return self.frame,self.sequence

    def process_preview(self):
        last_key=None;last_sequence=0
        while self.running:
            self.wake.wait(.1)
            with self.lock:
                self.wake.clear()
                if not self.running:break
                if self.standby or self.error or self.frame is None:continue
                frame,seq,stamp,mode,epoch=self.frame,self.sequence,self.timestamp,self.mode,self.epoch
                key=(seq,epoch)
                if key==last_key:continue
            # One latest-frame slot, never a backlog. Capture never waits for this work.
            try:
                with FILTER_GATE:
                    with self.lock:
                        if self.standby or epoch!=self.epoch or not self.running:continue
                    hdmi,small,timings=self.processor.prepare(frame,seq,mode)
                with self.ready:
                    if epoch!=self.epoch or self.standby or self.error or not self.running:continue
                    if time.monotonic()-stamp>3:continue
                    self.packet=(hdmi,seq,stamp,mode,epoch)
                    self.small_packet=(small,seq,stamp,mode,epoch);self.preview_error=''
                    self.preview_skipped+=max(0,seq-last_sequence-1) if last_sequence else 0
                    self.preview_count+=1;self.preview_timings=timings
                    for k,v in timings.items():self.preview_totals[k]=self.preview_totals.get(k,0)+v
                    self.ready.notify_all()
                last_key=key;last_sequence=seq
            except Exception as exc:
                with self.ready:
                    self.preview_error=str(exc);self.packet=None;self.jpeg=None
                    self.small_packet=None;self.jpeg_packet=None;self.ready.notify_all()
                time.sleep(.02)

    def process_jpeg(self):
        last_key=None;last_sequence=0
        while self.running:
            with self.ready:
                self.ready.wait_for(lambda:not self.running or (self.small_packet is not None and
                    (self.small_packet[1],self.small_packet[4])!=last_key),timeout=.1)
                if not self.running:break
                p=self.small_packet
                if self.standby or self.error or p is None:continue
                small,seq,stamp,mode,epoch=p;key=(seq,epoch)
                if key==last_key:continue
            last_key=key
            try:
                began=time.monotonic();jpeg=self.processor.encode(small);elapsed=(time.monotonic()-began)*1000
                with self.ready:
                    if not self.running or self.standby or self.error or self.preview_error or epoch!=self.epoch:continue
                    self.jpeg=jpeg;self.jpeg_packet=(jpeg,seq,stamp,mode,epoch)
                    self.jpeg_sequence=seq;self.jpeg_frames+=1;self.jpeg_error=''
                    self.jpeg_last_ms=elapsed;self.jpeg_work_ms+=elapsed;self.jpeg_age_ms+=(time.monotonic()-stamp)*1000
                    self.jpeg_skipped+=max(0,seq-last_sequence-1) if last_sequence else 0
                    last_sequence=seq;self.ready.notify_all()
            except Exception as exc:
                with self.ready:self.jpeg_error=str(exc);self.jpeg=None;self.jpeg_packet=None;self.ready.notify_all()

    def status(self):
        exposure=self.exposure
        with self.lock:
            return {'sequence':self.sequence,'error':self.error,'age_seconds':time.monotonic()-self.timestamp,
                    'width':1280,'height':480,'preview_width':1280,'preview_height':480,'device':self.device,
                    'source':'PS Linux UVC; native frozen frame for PL matching','preview_engine':'PL filters + A53 scheduling' if PL_FILTERS_ENABLED else 'A53 shared producer',
                    'display_filters':pl_filters.status() if PL_FILTERS_ENABLED else {'backend':'A53'},'mode':self.mode,'standby':self.standby,
                    'preview_modes':list(MODES),'rectification_grid':[320,360],
                    'recovery_count':self.recovery_count,'jpeg_frames':self.jpeg_frames,
                    'jpeg_sequence':self.jpeg_sequence,'preview_target_fps':30,'preview_error':self.preview_error,
                    'jpeg_error':self.jpeg_error,'jpeg_skipped':self.jpeg_skipped,
                    'jpeg_latency':{'encode_last_ms':self.jpeg_last_ms,'encode_total_ms':self.jpeg_work_ms,
                        'publish_age_total_ms':self.jpeg_age_ms,'frames':self.jpeg_frames},
                    'preview_pipeline':'capture -> shared images -> parallel HDMI / JPEG -> frame-aware HTTP',
                    'rectification_calls':self.processor.rectifications,'preview_skipped':self.preview_skipped,
                    'preview_age_seconds':None if self.packet is None else time.monotonic()-self.packet[2],
                    'preview_count':self.preview_count,'preview_last_ms':self.preview_timings,
                    'rectification_backend':'PL PXP1 exact integer two-eye' if EXTRA_ENABLED else 'A53 exact integer two-eye',
                    'preview_processing':pl_preview.status() if EXTRA_ENABLED else {'backend':'A53'} if self.processor.rectifier.native is not None else 'A53 OpenCV',
                    'preview_total_ms':dict(self.preview_totals),'capture_display_separate':True,
                    'tone_map':dict(tone_description(self.mode=='auto_enhanced'),processor='PL PXP1' if EXTRA_ENABLED else 'A53',applied=self.mode=='auto_enhanced'),
                    'auto_exposure':exposure.status() if exposure is not None else {'mode':'inactive'}}

    def snapshot(self):
        with self.lock:
            age=time.monotonic()-self.timestamp
            if self.standby or self.error or self.frame is None or age>3:raise ValueError('No fresh stereo frame')
            return self.frame.copy(),self.sequence,age

    def preview_snapshot(self,after=None,timeout=.05):
        with self.ready:
            def available():
                return (not self.running or self.standby or self.error or
                        (self.packet is not None and (self.packet[1],self.packet[4])!=after))
            self.ready.wait_for(available,timeout)
            p=self.packet
            if self.standby or self.error or self.preview_error or p is None or time.monotonic()-p[2]>3:
                raise ValueError('No fresh shared preview')
            return p  # Arrays are immutable to consumers; HDMI only copies into its canvas.

    def preview_jpeg_packet(self,after=None,timeout=.12):
        with self.ready:
            if after is not None:
                self.ready.wait_for(lambda:not self.running or self.standby or self.error or self.jpeg_error or
                    (self.jpeg_packet is not None and (self.jpeg_packet[1],self.jpeg_packet[4])!=after),timeout)
            p=self.jpeg_packet
            if self.standby or self.error or self.preview_error or self.jpeg_error or p is None or time.monotonic()-p[2]>3:
                raise ValueError('No fresh shared preview')
            return p

    def preview_jpeg(self):return self.preview_jpeg_packet()[0]

    def close(self):
        with self.ready:self.running=False;self.wake.set();self.ready.notify_all()
        self.worker.join(timeout=3);self.preview_worker.join(timeout=3);self.jpeg_worker.join(timeout=3)
        if any(w.is_alive() for w in (self.worker,self.preview_worker,self.jpeg_worker)):raise RuntimeError('Camera workers did not drain')


def main():
    runtime=FullRuntime();camera=Camera()
    if os.environ.get('USB_RESTORE_HELD')=='1':
        from restore_held import restore
        restore(runtime)
    hdmi=None
    if os.environ.get('USB_HDMI')=='1':
        from hdmi_output import HDMIOutput
        hdmi=HDMIOutput(camera,runtime)
    from fast_console import FastConsole
    fast=FastConsole(hdmi,camera=camera)
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def setup(self):
            super().setup();self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        def allowed(self):
            if self.client_address[0] not in ('192.168.137.1','127.0.0.1'):
                self.send_error(403);return False
            if self.headers.get('Host') not in ('192.168.137.2:8788','127.0.0.1:8788'):
                self.send_error(403);return False
            return True
        def data(self,data,mime='application/json',code=200,headers=None):
            if not isinstance(data,bytes):data=json.dumps(data).encode()
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            for k,v in (headers or {}).items():self.send_header(k,str(v))
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            if not self.allowed():return
            route=urlsplit(self.path).path
            if route=='/fast/status':self.data(fast.status());return
            if route=='/preview/zoom':
                import preview_zoom
                self.data(preview_zoom.status());return
            if route=='/status':self.data(camera.status());return
            if route=='/stereo/status':self.data(runtime.status());return
            if route=='/hdmi/status':self.data(hdmi.status() if hdmi else {'enabled':False});return
            if route=='/preview.jpg':
                try:
                    query=parse_qs(urlsplit(self.path).query);after=None
                    if 'after' in query:
                        parts=query['after'][0].split(',')
                        if len(parts)!=2:raise ValueError('Invalid frame cursor')
                        after=tuple(map(int,parts))
                    jpeg,seq,stamp,mode,epoch=camera.preview_jpeg_packet(after)
                    self.data(jpeg,'image/jpeg',headers={'X-Frame-Sequence':seq,'X-Frame-Epoch':epoch,
                        'X-Frame-Age-Ms':round((time.monotonic()-stamp)*1000,3),'X-Frame-Mode':mode})
                except ValueError as exc:self.data({'error':str(exc)},code=503)
                return
            if route=='/snapshot.png':
                try:
                    frame,seq,age=camera.snapshot();ok,b=cv2.imencode('.png',frame,[cv2.IMWRITE_PNG_COMPRESSION,1])
                    if not ok:raise ValueError('PNG failed')
                    self.data(b.tobytes(),'image/png')
                except Exception as exc:self.data({'error':str(exc)},code=503)
                return
            if route=='/stereo/result.npz':
                job=parse_qs(urlsplit(self.path).query).get('id',[''])[0];package=runtime.result(job)
                if package is None:self.data({'error':'Result identity mismatch or not ready'},code=409)
                else:self.data(package,'application/octet-stream')
                return
            self.send_error(404)
        def do_POST(self):
            if not self.allowed():return
            try:
                self.connection.settimeout(10)
                route=urlsplit(self.path).path
                if route=='/fast/photo':
                    from photo_views import PACKET_BYTES
                    if self.client_address[0]!='192.168.137.1' or self.headers.get('Content-Type')!='application/octet-stream' or int(self.headers.get('Content-Length','0'))!=PACKET_BYTES:raise ValueError('Invalid frozen photo')
                    data=self.rfile.read(PACKET_BYTES)
                    self.data(fast.receive_photo(data,self.headers.get('X-Photo-Id',''),self.headers.get('X-Fast-Generation',''),self.headers.get('X-Frame-SHA256','')));return
                if route=='/fast/frame':
                    if self.client_address[0]!='192.168.137.1':raise ValueError('PC renderer required')
                    size=int(self.headers.get('Content-Length','0'))
                    if self.headers.get('Content-Type') not in ('image/png','application/octet-stream') or not 24<=size<=4*1024**2:raise ValueError('Invalid frame')
                    data=self.rfile.read(size)
                    self.data(fast.accept(data,self.headers.get('X-Photo-Id',''),self.headers.get('X-Fast-Generation',''),self.headers.get('X-Fast-View',''),self.headers.get('X-Frame-SHA256',''),self.headers.get('Content-Type'),int(self.headers['X-HDMI-Epoch']) if self.headers.get('X-HDMI-Epoch') is not None else None,self.headers.get('X-HDMI-Activate')=='1'));return
                if route=='/hdmi/frame':
                    if hdmi is None:raise ValueError('HDMI is not enabled')
                    if self.headers.get('Content-Type')!='application/octet-stream' or int(self.headers.get('Content-Length','0'))!=1280*720*3:raise ValueError('Invalid HDMI frame')
                    data=self.rfile.read(1280*720*3)
                    self.data(hdmi.accept(data,self.headers.get('X-Photo-Id',''),self.headers.get('X-Frame-SHA256',''),int(self.headers.get('X-Cast-Generation','-1'))));return
                if self.headers.get('Content-Type')!='application/json':raise ValueError('JSON required')
                size=int(self.headers.get('Content-Length','0'))
                if size<2 or size>1024:raise ValueError('Invalid body size')
                args=json.loads(self.rfile.read(size));route=urlsplit(self.path).path
                if route=='/fast/key':
                    if self.client_address[0]!='127.0.0.1' or set(args)!={'key'}:raise ValueError('Local physical key required')
                    self.data(fast.key(args['key']))
                elif route=='/fast/control':
                    if self.client_address[0]!='192.168.137.1':raise ValueError('PC controller required')
                    self.data(fast.control(args))
                elif route=='/hdmi/preview':
                    if hdmi is None or args!={}:raise ValueError('HDMI preview is unavailable')
                    self.data(hdmi.preview())
                elif route=='/hdmi/raw':
                    if hdmi is None or set(args)!={'job_id'}:raise ValueError('Raw disparity display requires job_id')
                    self.data(hdmi.raw_disparity(args['job_id']))
                elif route=='/stereo/capture':
                    if args!={}:raise ValueError('No capture parameters accepted')
                    frame,seq,age=camera.snapshot();accepted,job=runtime.start(frame,seq,age)
                    self.data({'accepted':accepted,'job_id':job},code=202 if accepted else 409)
                elif route=='/stereo/cancel':
                    if args!={}:raise ValueError('No cancellation parameters accepted')
                    self.data(runtime.cancel())
                elif route=='/stereo/section':self.data(runtime.compute_section(args))
                elif route=='/standby':
                    if set(args)!={'enabled'} or type(args['enabled']) is not bool:raise ValueError('Invalid standby request')
                    runtime.set_standby(args['enabled']);camera.set_standby(args['enabled']);self.data(runtime.status())
                elif route=='/preview/zoom':
                    if runtime.status()['busy'] or runtime.status()['section_busy']:raise ValueError('Preview zoom unavailable while computing')
                    import preview_zoom
                    self.data(preview_zoom.set_view(args))
                elif route=='/preview/mode':
                    if set(args)!={'mode'} or args['mode'] not in MODES:raise ValueError('Invalid preview mode')
                    camera.set_mode(args['mode'])
                    self.data(camera.status())
                elif route=='/preview/tone':
                    if set(args)!={'enabled'} or type(args['enabled']) is not bool:raise ValueError('Invalid tone request')
                    camera.set_tone(args['enabled']);self.data(camera.status())
                else:self.send_error(404)
            except Exception as exc:self.data({'error':str(exc)},code=409)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('192.168.137.2',8788),Handler)
    def stop(*args):
        runtime.cancel();camera.running=False;threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:server.serve_forever()
    finally:
        runtime.cancel();camera.running=False;server.server_close()
        if hdmi is not None:hdmi.close()
        camera.close()
        if runtime.worker:runtime.worker.join(timeout=15)
if __name__=='__main__':main()
