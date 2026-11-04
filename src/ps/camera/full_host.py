"""Loopback live control, integrity-checked reception and display of board-only results."""
import base64,datetime,hashlib,http.client,json,mimetypes,os,re,secrets,socket,struct,sys,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
from live_verify import verify_section,np
from receive_result import receive
from render_saved import export_result
import cv2
PORT=8805;ORIGIN='http://127.0.0.1:'+str(PORT);BOARD='http://192.168.137.2:8788'
CAPTURES=ROOT/'live_captures';CAPTURES.mkdir(exist_ok=True)
TOKEN=secrets.token_hex(24)
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def board(path,body=None,limit=2*1024*1024,timeout=8):
    request=urllib.request.Request(BOARD+path,None if body is None else json.dumps(body).encode(),
                                  headers={'Content-Type':'application/json'} if body is not None else {})
    with OPENER.open(request,timeout=timeout) as response:
        size=int(response.headers.get('Content-Length','-1'))
        if size<0 or size>limit:raise ValueError('Board response length rejected')
        data=response.read(size+1)
        if len(data)!=size:raise ValueError('Incomplete board response')
    return data
def board_json(path,body=None,**kwargs):return json.loads(board(path,body,**kwargs))

class Cancelled(Exception):pass
class Host:
    def __init__(self):
        self.lock=threading.Lock();self.cancelled=threading.Event();self.busy=False;self.section_busy=False
        self.stage='idle';self.error='';self.job=None;self.result=None;self.arrays=None;self.folder=None
        self.started=0;self.worker=None;self.captured_pc=None;self.board_status=None
        self.observer_stop=threading.Event();self.observer_error='';self.observer=None
    def status(self):
        with self.lock:return {'busy':self.busy,'section_busy':self.section_busy,'stage':self.stage,'error':self.error,
                              'job_id':self.job,'result':self.result,'board':self.board_status,
                              'observer_error':self.observer_error,
                              'elapsed_seconds':round(time.monotonic()-self.started,1) if self.busy else None}
    def observe_once(self):
        """Adopt an existing board job only. This method never triggers a shutter."""
        state=board_json('/stereo/status')
        if state.get('schema')!='usb_full_v2':raise ValueError('Unexpected board service')
        job=state.get('job_id')
        with self.lock:
            self.observer_error=''
            if self.busy or self.section_busy or job==self.job:return False
            if job is not None and not re.fullmatch('[0-9a-f]{32}',job):raise ValueError('Invalid observed photo identity')
            self.job=job;self.result=None;self.arrays=None;self.folder=None;self.board_status=state
            self.error=state.get('error','');self.stage=state.get('stage','idle')
            if not job or (not state.get('busy') and not (state.get('stage')=='ready' and state.get('result_id')==job)):
                return False
            captured=datetime.datetime.now().astimezone().isoformat(timespec='seconds')
            saved=CAPTURES/job/'received.json'
            if saved.is_file():
                previous=json.loads(saved.read_text(encoding='utf8'))
                if previous.get('job_id')!=job or not previous.get('integrity_passed'):raise ValueError('Stored photo identity is invalid')
                captured=previous['captured_pc']
            self.busy=True;self.stage='restoring_photo';self.error='';self.cancelled.clear()
            self.started=time.monotonic();self.captured_pc=captured
            self.worker=threading.Thread(target=self.run,args=(job,captured),daemon=False)
            self.worker.start()
            return True
    def start_observer(self):
        if self.observer and self.observer.is_alive():return
        def observe():
            while not self.observer_stop.is_set():
                try:self.observe_once()
                except Exception as exc:
                    with self.lock:self.observer_error=str(exc)
                self.observer_stop.wait(1)
        self.observer=threading.Thread(target=observe,daemon=True);self.observer.start()
    def progress(self,stage):
        if self.cancelled.is_set():raise Cancelled('Capture cancelled')
        with self.lock:self.stage=stage
    def capture(self):
        with self.lock:
            if self.busy or self.section_busy:raise ValueError('A photo or section is already running')
            self.busy=True;self.stage='starting';self.error='';self.cancelled.clear();self.started=time.monotonic()
            self.captured_pc=datetime.datetime.now().astimezone().isoformat(timespec='seconds')
            self.result=None;self.arrays=None;self.folder=None;self.job=None
        try:
            status=board_json('/stereo/status')
            if status.get('schema')!='usb_full_v2':raise ValueError('The board is not running the full PL camera service')
            reply=board_json('/stereo/capture',{})
            if not reply.get('accepted') or not re.fullmatch('[0-9a-f]{32}',reply.get('job_id','')):raise ValueError('Board did not accept photo')
            with self.lock:self.job=reply['job_id']
            self.worker=threading.Thread(target=self.run,args=(self.job,self.captured_pc),daemon=False);self.worker.start()
            return {'accepted':True,'job_id':self.job}
        except Exception:
            with self.lock:self.busy=False;self.stage='error'
            raise
    def run(self,job,captured):
        try:
            # Poll this exact job. Transient observation failure never starts another photo.
            failures=0
            while True:
                try:state=board_json('/stereo/status');failures=0
                except Exception as exc:
                    failures+=1
                    with self.lock:self.stage='waiting_for_board';self.error=str(exc)
                    if failures>=30:raise RuntimeError('Board observation lost; no new capture was started')
                    time.sleep(1);continue
                if state.get('job_id')!=job:raise ValueError('Board photo changed while waiting')
                with self.lock:self.board_status=state;self.stage=state.get('stage','waiting');self.error=''
                if state.get('busy'):time.sleep(.5);continue
                if self.cancelled.is_set() or state.get('stage') in ('cancelled','standby'):raise Cancelled()
                if state.get('error'):raise RuntimeError(state['error'])
                if state.get('stage')!='ready' or state.get('result_id')!=job:raise ValueError('Board ended without the requested result')
                break
            self.progress('download');payload=board('/stereo/result.npz?id='+job,limit=96*1024*1024,timeout=90)
            fresh=board_json('/stereo/status')
            if fresh.get('busy') or fresh.get('result_id')!=job:raise ValueError('Board result superseded during transfer')
            folder=CAPTURES/job;folder.mkdir(exist_ok=True)
            original=folder/'board_result.npz';digest=hashlib.sha256(payload).hexdigest();previous=None
            if original.exists():
                if hashlib.sha256(original.read_bytes()).hexdigest()!=digest:raise ValueError('A stored photo has different bytes under the same identity')
                if (folder/'received.json').exists():
                    previous=json.loads((folder/'received.json').read_text(encoding='utf8'))
                    if not previous.get('integrity_passed') or previous.get('job_id')!=job or previous.get('source_sha256')!=digest:
                        raise ValueError('Stored verification does not match the held photo')
            else:original.write_bytes(payload)
            a,m,b,report=receive(payload,fresh,job,self.progress)
            self.progress('package_viewer');summary=export_result(a,m,b,m['surface_preparation'],folder,job,TOKEN,captured)
            # These previews map board arrays to colours only; no disparity/depth is computed here.
            for name,value in (('disparity',a['dense_disparity_px']),('depth',a['dense_depth_mm']),('raw_disparity',a['disparity_q4'].astype(np.float32)/16),('raw_depth',a['depth_mm'])):
                valid=np.isfinite(value) if not name.startswith('raw_') else a['valid']&np.isfinite(value)
                levels=np.zeros(value.shape,np.uint8)
                scale=(value/127 if 'disparity' in name else (3000-value)/2800)
                levels[valid]=np.clip(scale[valid]*255,0,255).astype(np.uint8)
                colored=cv2.applyColorMap(levels,cv2.COLORMAP_JET);colored[~valid]=0
                if not name.startswith('raw_'):assert not np.any(np.all(colored==0,axis=2))
                assert cv2.imwrite(str(folder/(name+'.png')),colored)
            report.update(captured_pc=captured,board_metadata=m,elapsed_seconds=time.monotonic()-self.started)
            if previous:
                report.update(restored_pc=datetime.datetime.now().astimezone().isoformat(),original_elapsed_seconds=previous['elapsed_seconds'])
                report_name='received_again_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.json'
            else:report_name='received.json'
            (folder/report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            board_seconds=fresh['metadata'].get('total_seconds')
            if board_seconds is None and previous:
                # Packing duration was only in the old runtime status, not the
                # immutable NPZ. Reuse it only for the exact preserved photo.
                latest=ROOT/'live_latest.json'
                if latest.exists():
                    saved_latest=json.loads(latest.read_text(encoding='utf8'))
                    if saved_latest.get('job_id')==job:board_seconds=saved_latest.get('board_seconds')
            self.progress('publishing')
            with self.lock:
                if self.cancelled.is_set():raise Cancelled()
                self.arrays=a;self.folder=folder;self.result={'job_id':job,'viewer_url':'/captures/'+job+'/viewer.html',
                    'captured_pc':captured,'valid_pixels':m['valid_pixels'],'valid_percent':round(100*m['valid_fraction'],2),
                    'board_seconds':board_seconds,'algorithm_verified':False,'verification_seconds':0.0,'integrity_seconds':(previous or report)['seconds'],
                    'total_seconds':(previous or report)['elapsed_seconds'],'summary':summary,'dense_fill':m['dense_fill'],
                    'restored':bool(previous),'restore_integrity_seconds':report['seconds'] if previous else None}
                self.stage='ready';self.busy=False
            (ROOT/'live_latest.json').write_text(json.dumps(self.result,ensure_ascii=False,indent=2),encoding='utf8')
        except Cancelled:
            with self.lock:self.stage='cancelled';self.busy=False;self.error=''
        except Exception as exc:
            import traceback;traceback.print_exc()
            with self.lock:self.stage='error';self.busy=False;self.error=str(exc) or repr(exc)
    def cancel(self):
        self.cancelled.set();return board_json('/stereo/cancel',{})
    def standby(self,value):
        if type(value) is not bool:raise ValueError('Standby requires boolean')
        if value:self.cancelled.set()
        with self.lock:
            if self.section_busy or (not value and self.busy):raise ValueError('Wait for active work to finish')
        return board_json('/standby',{'enabled':value})
    def section(self,args):
        if set(args)!={'revision','axis','center_mm','thickness_mm','include_inferred'}:raise ValueError('Invalid section request')
        if type(args['axis']) is not int or args['axis'] not in (0,1,2) or type(args['include_inferred']) is not bool:raise ValueError('Invalid section types')
        center=float(args['center_mm']);thickness=float(args['thickness_mm'])
        if not np.isfinite(center) or not np.isfinite(thickness) or abs(center)>500000 or not 0<=thickness<=20000:raise ValueError('Section is out of range')
        with self.lock:
            if self.busy or self.section_busy or not self.result or args['revision']!=self.job:raise ValueError('Photo changed or board is busy')
            self.section_busy=True;a=self.arrays;job=self.job;folder=self.folder
        request={'job_id':job,'axis':args['axis'],'center_mm':center,'thickness_mm':thickness,'include_inferred':args['include_inferred']}
        try:
            result=board_json('/stereo/section',request,limit=12*1024*1024,timeout=30)
            indices,coords,source=verify_section(result,a,job,request)
            stamp=secrets.token_hex(6);stem='section_'+stamp
            with (folder/(stem+'.csv')).open('w',encoding='utf8',newline='') as f:
                f.write('pixel_index,image_u,image_v,x_mm,y_mm,z_mm,source\n')
                for i,xyz,src in zip(indices,coords,source):
                    f.write('%d,%d,%d,%.9f,%.9f,%.9f,%d\n'%(i,i%320,i//320,*[v/4096 for v in xyz],src))
            result.update(csv_url='/captures/'+job+'/'+stem+'.csv',pc_verified=True)
            (folder/(stem+'.json')).write_text(json.dumps({'request':request,'response':result},indent=2))
            return result
        finally:
            with self.lock:self.section_busy=False

HOST=Host()
FILES={'viewer.html','reference.png','disparity.png','depth.png','raw_disparity.png','raw_depth.png','geometry.npz','board_result.npz','received.json','report.json',
       'matched_points_all.ply','completed_points_preview.ply','dense_points.ply','dense_surface.ply','surface_repaired.ply'}
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup();self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.preview_connection=None
    def finish(self):
        try:
            if self.preview_connection is not None:self.preview_connection.close()
        finally:super().finish()
    def preview(self):
        query=parse_qs(urlsplit(self.path).query);path='/preview.jpg'
        if 'after' in query:
            cursor=query['after'][0]
            if not re.fullmatch(r'[0-9]{1,20},[0-9]{1,20}',cursor):raise ValueError('Invalid frame cursor')
            path+='?after='+cursor
        try:
            if self.preview_connection is None:
                self.preview_connection=http.client.HTTPConnection('192.168.137.2',8788,timeout=3)
                self.preview_connection.connect()
                self.preview_connection.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            self.preview_connection.request('GET',path)
            reply=self.preview_connection.getresponse();size=int(reply.getheader('Content-Length','-1'))
            if not 0<=size<=512*1024:raise ValueError('Invalid preview length')
            data=reply.read(size+1)
            if len(data)!=size or reply.status!=200:raise ValueError('Preview is not ready')
            headers={k:reply.getheader(k) for k in ('X-Frame-Sequence','X-Frame-Epoch','X-Frame-Age-Ms','X-Frame-Mode')}
            if not all(v is not None for v in headers.values()):raise ValueError('Frame identity is missing')
            self.data(data,'image/jpeg',headers=headers)
        except Exception:
            if self.preview_connection is not None:self.preview_connection.close();self.preview_connection=None
            raise
    def allowed(self,post=False):
        if self.headers.get('Host')!='127.0.0.1:'+str(PORT):self.send_error(403);return False
        if post and (self.headers.get('Origin')!=ORIGIN or self.headers.get('X-Viewer-Token')!=TOKEN):self.send_error(403);return False
        return True
    def data(self,data,mime='application/json',code=200,headers=None):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        for k,v in (headers or {}).items():self.send_header(k,str(v))
        self.end_headers()
        try:self.wfile.write(data)
        except (ConnectionResetError,BrokenPipeError,ConnectionAbortedError):pass
    def do_GET(self):
        if not self.allowed():return
        path=urlsplit(self.path).path
        try:
            if path=='/':self.data((ROOT/'full_control.html').read_text(encoding='utf8').replace('__LIVE_TOKEN__',TOKEN).encode(),'text/html; charset=utf-8')
            elif path=='/api/status':self.data(HOST.status())
            elif path=='/api/point':
                query=parse_qs(urlsplit(self.path).query,strict_parsing=True)
                if set(query)!={'job','x','y'} or any(len(v)!=1 for v in query.values()):raise ValueError('Invalid pixel query')
                x,y=int(query['x'][0]),int(query['y'][0])
                if not (0<=x<320 and 0<=y<360):raise ValueError('Pixel outside 320x360')
                with HOST.lock:
                    if HOST.busy or HOST.arrays is None or HOST.job!=query['job'][0]:raise ValueError('Photo changed')
                    a=HOST.arrays;valid=True
                    value={'job':HOST.job,'x':x,'y':y,'valid':valid,
                           'depth_m':float(a['dense_depth_mm'][y,x])/1000 if valid else None,
                           'disparity_px':float(a['dense_disparity_px'][y,x]) if valid else None,
                           'origin':int(a['dense_origin'][y,x])}
                self.data(value)
            elif path=='/api/camera':self.data(board_json('/status'))
            elif path=='/api/hdmi/status':self.data(board_json('/hdmi/status'))
            elif path=='/preview.jpg':self.preview()
            elif path.startswith('/captures/'):
                parts=path.split('/')
                if len(parts)!=4 or not re.fullmatch('[0-9a-f]{32}',parts[2]):raise ValueError('Invalid capture path')
                name=parts[3]
                if name not in FILES and not re.fullmatch(r'(section_[0-9a-f]{12}\.csv|render_[0-9a-f]{12}\.png)',name):raise ValueError('Unsupported export')
                file=CAPTURES/parts[2]/name
                if not file.is_file():self.send_error(404);return
                mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
                self.data(file.read_bytes(),mime)
            else:self.send_error(404)
        except Exception as exc:self.data({'error':str(exc)},code=503)
    def do_POST(self):
        if not self.allowed(True):return
        try:
            size=int(self.headers.get('Content-Length','0'));path=urlsplit(self.path).path
            if path=='/api/hdmi/frame':
                self.connection.settimeout(15)
                job=self.headers.get('X-Photo-Id','')
                if not re.fullmatch('[0-9a-f]{32}',job) or not (CAPTURES/job/'received.json').is_file():raise ValueError('Unknown photo')
                with HOST.lock:
                    if HOST.busy or HOST.job!=job or not HOST.result:raise ValueError('Photo changed or verification is not ready')
                if self.headers.get('Content-Type')!='application/octet-stream' or size!=1280*720*3:raise ValueError('Invalid HDMI frame length')
                data=self.rfile.read(size)
                if len(data)!=size:raise ValueError('Incomplete HDMI frame')
                digest=hashlib.sha256(data).hexdigest()
                generation=self.headers.get('X-Cast-Generation','')
                if not re.fullmatch('[0-9]{1,10}',generation):raise ValueError('Invalid HDMI generation')
                request=urllib.request.Request(BOARD+'/hdmi/frame',data,headers={'Content-Type':'application/octet-stream','X-Photo-Id':job,'X-Frame-SHA256':digest,'X-Cast-Generation':generation})
                with OPENER.open(request,timeout=10) as response:reply=json.loads(response.read(4096))
                if reply.get('sha256')!=digest or reply.get('job_id')!=job or not reply.get('accepted'):raise ValueError('HDMI frame acknowledgement mismatch')
                self.data(reply);return
            if path=='/api/render-export':
                job=self.headers.get('X-Photo-Id','')
                if not re.fullmatch('[0-9a-f]{32}',job) or not (CAPTURES/job/'received.json').is_file():raise ValueError('Unknown photo')
                if self.headers.get('Content-Type')!='image/png' or not 32<=size<=16*1024*1024:raise ValueError('Invalid PNG length')
                data=self.rfile.read(size)
                if len(data)!=size or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR':raise ValueError('Invalid PNG')
                w,h=struct.unpack('>II',data[16:24])
                if not 1<=w<=8192 or not 1<=h<=8192:raise ValueError('Invalid PNG dimensions')
                name='render_'+secrets.token_hex(6)+'.png';(CAPTURES/job/name).write_bytes(data)
                self.data({'url':'/captures/'+job+'/'+name});return
            if self.headers.get('Content-Type')!='application/json' or not 2<=size<=2048:raise ValueError('JSON body required')
            args=json.loads(self.rfile.read(size))
            if path in ('/api/capture','/api/cancel') and args!={}:raise ValueError('Unexpected parameters')
            if path=='/api/capture':self.data(HOST.capture(),code=202)
            elif path=='/api/cancel':self.data(HOST.cancel())
            elif path=='/api/section':self.data(HOST.section(args))
            elif path=='/api/standby':
                if set(args)!={'enabled'}:raise ValueError('Invalid standby request')
                self.data(HOST.standby(args['enabled']))
            elif path=='/api/mode':
                if set(args)!={'mode'} or args['mode'] not in ('color','auto_enhanced','rectified','gray','median','sobel'):raise ValueError('Invalid preview mode')
                self.data(board_json('/preview/mode',args))
            elif path=='/api/tone':
                if set(args)!={'enabled'} or type(args['enabled']) is not bool:raise ValueError('Invalid tone request')
                self.data(board_json('/preview/tone',args))
            elif path=='/api/hdmi/preview':
                if args!={}:raise ValueError('No HDMI preview parameters accepted')
                self.data(board_json('/hdmi/preview',{}))
            elif path=='/api/hdmi/raw':
                if set(args)!={'job_id'}:raise ValueError('Photo id required')
                self.data(board_json('/hdmi/raw',args))
            else:self.send_error(404)
        except Exception as exc:self.data({'error':str(exc) or repr(exc)},code=409)
    def log_message(self,*args):pass

if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    (ROOT/'live_host.json').write_text(json.dumps({'pid':os.getpid(),'port':PORT,'token':TOKEN,'origin':ORIGIN}))
    print('LIVE_HOST_READY',ORIGIN,flush=True)
    HOST.start_observer()
    try:server.serve_forever()
    finally:HOST.observer_stop.set();server.server_close()
