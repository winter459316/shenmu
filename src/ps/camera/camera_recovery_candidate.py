"""USB v2 camera/service, isolated from the preserved parent camera program.

Start only after stopping the parent UVC owner. Preview modes run on A53;
native lossless frozen BGR frames enter the explicitly labelled PL engine.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('USB_SURFACE_NATIVE','1')
import json,signal,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import cv2
from full_runtime import FullRuntime
cv2.setNumThreads(3)

class Camera:
    def __init__(self,opener=None):
        self.lock=threading.Lock();self.running=True;self.standby=False;self.mode='color'
        self.frame=None;self.jpeg=None;self.sequence=0;self.timestamp=0;self.error='Opening camera'
        self.device=os.environ.get('USB_DEVICE','/dev/video0')
        self.opener=opener or cv2.VideoCapture;self.recovery_count=0
        self.worker=threading.Thread(target=self.acquire,daemon=True);self.worker.start()
    def acquire(self):
        cap=None;encoded_at=0;retry_at=0
        try:
            while self.running:
                if self.standby:
                    if cap is not None:cap.release();cap=None
                    with self.lock:self.frame=None;self.jpeg=None;self.error='Standby'
                    retry_at=0;time.sleep(.05);continue
                if time.monotonic()<retry_at:
                    time.sleep(.05);continue
                try:
                    cap,encoded_at=self.acquire_frame(cap,encoded_at)
                except Exception as exc:
                    if cap is not None:
                        cap.release();cap=None
                    # Reject all stale snapshots while reopening. Never shutter.
                    with self.lock:
                        self.frame=None;self.jpeg=None;self.timestamp=0
                        self.error=str(exc);self.recovery_count+=1
                    retry_at=time.monotonic()+.5
        finally:
            if cap is not None:cap.release()
    def acquire_frame(self,cap,encoded_at):
        opened_here=cap is None
        try:
            if cap is None:
                cap=self.opener(self.device,cv2.CAP_V4L2)
                if not cap.isOpened():raise RuntimeError('Cannot open UVC camera; check its current owner')
                cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
                cap.set(cv2.CAP_PROP_FPS,30);cap.set(cv2.CAP_PROP_BUFFERSIZE,2)
            ok,frame=cap.read()
            if not ok or frame.shape!=(480,1280,3):raise RuntimeError('UVC requires a fresh 1280x480 stereo frame')
            now=time.monotonic()
            with self.lock:
                self.frame=frame;self.sequence+=1;self.timestamp=now;self.error='';mode=self.mode
            # Keep full capture resolution, limit only browser preview work.
            if now-encoded_at>=.1:
                small=cv2.resize(frame,(640,240),interpolation=cv2.INTER_AREA)
                if mode!='color':
                    small=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
                    if mode=='median':small=cv2.medianBlur(small,3)
                    elif mode=='sobel':
                        gx=cv2.Sobel(small,cv2.CV_16S,1,0);gy=cv2.Sobel(small,cv2.CV_16S,0,1)
                        small=cv2.addWeighted(cv2.convertScaleAbs(gx),.5,cv2.convertScaleAbs(gy),.5,0)
                ok,encoded=cv2.imencode('.jpg',small,[cv2.IMWRITE_JPEG_QUALITY,75])
                if not ok:raise RuntimeError('Preview encoding failed')
                with self.lock:self.jpeg=encoded.tobytes()
                encoded_at=now
            return cap,encoded_at
        except Exception:
            # The caller does not yet own a newly opened handle if this call fails.
            if opened_here and cap is not None:cap.release()
            raise
    def status(self):
        with self.lock:
            return {'sequence':self.sequence,'error':self.error,'age_seconds':time.monotonic()-self.timestamp,
                    'width':1280,'height':480,'preview_width':640,'preview_height':240,'device':self.device,
                    'source':'PS Linux UVC; native frozen frame for PL matching','preview_engine':'A53','mode':self.mode,'standby':self.standby,
                    'recovery_count':self.recovery_count}
    def snapshot(self):
        with self.lock:
            age=time.monotonic()-self.timestamp
            if self.standby or self.error or self.frame is None or age>3:raise ValueError('No fresh stereo frame')
            return self.frame.copy(),self.sequence,age

def main():
    runtime=FullRuntime();camera=Camera()
    class Handler(BaseHTTPRequestHandler):
        def allowed(self):
            if self.client_address[0] not in ('192.168.137.1','127.0.0.1'):
                self.send_error(403);return False
            if self.headers.get('Host') not in ('192.168.137.2:8767','127.0.0.1:8767'):
                self.send_error(403);return False
            return True
        def data(self,data,mime='application/json',code=200):
            if not isinstance(data,bytes):data=json.dumps(data).encode()
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            if not self.allowed():return
            route=urlsplit(self.path).path
            if route=='/status':self.data(camera.status());return
            if route=='/stereo/status':self.data(runtime.status());return
            if route=='/preview.jpg':
                status=camera.status()
                with camera.lock:jpeg=camera.jpeg
                if status['error'] or status['age_seconds']>3 or not jpeg:self.data({'error':'No fresh preview'},code=503)
                else:self.data(jpeg,'image/jpeg')
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
                if self.headers.get('Content-Type')!='application/json':raise ValueError('JSON required')
                size=int(self.headers.get('Content-Length','0'))
                if size<2 or size>1024:raise ValueError('Invalid body size')
                args=json.loads(self.rfile.read(size));route=urlsplit(self.path).path
                if route=='/stereo/capture':
                    if args!={}:raise ValueError('No capture parameters accepted')
                    frame,seq,age=camera.snapshot();accepted,job=runtime.start(frame,seq,age)
                    self.data({'accepted':accepted,'job_id':job},code=202 if accepted else 409)
                elif route=='/stereo/cancel':
                    if args!={}:raise ValueError('No cancellation parameters accepted')
                    self.data(runtime.cancel())
                elif route=='/stereo/section':self.data(runtime.compute_section(args))
                elif route=='/standby':
                    if set(args)!={'enabled'} or type(args['enabled']) is not bool:raise ValueError('Invalid standby request')
                    runtime.set_standby(args['enabled']);camera.standby=args['enabled'];self.data(runtime.status())
                elif route=='/preview/mode':
                    if set(args)!={'mode'} or args['mode'] not in ('color','gray','median','sobel'):raise ValueError('Invalid preview mode')
                    with camera.lock:camera.mode=args['mode']
                    self.data(camera.status())
                else:self.send_error(404)
            except Exception as exc:self.data({'error':str(exc)},code=409)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('192.168.137.2',8767),Handler)
    def stop(*args):
        runtime.cancel();camera.running=False;threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:server.serve_forever()
    finally:
        runtime.cancel();camera.running=False;server.server_close()
        camera.worker.join(timeout=3)
        if runtime.worker:runtime.worker.join(timeout=15)
if __name__=='__main__':main()
