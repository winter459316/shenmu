"""Independent localhost photo entry, board-only matching/XYZ, PC display."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import http.client,socket
import hashlib,json,mimetypes,re,secrets,struct,threading,time,urllib.request,uuid
R=Path(__file__).resolve().parent;PORT=8849;ORIGIN='http://127.0.0.1:'+str(PORT)
TOKEN=secrets.token_hex(24);OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
from export_capture import export
from photo_store import PhotoStore,MODES
from preview_modes import PREVIEW_MODES
from video_store import VideoStore
VIDEOS=VideoStore(R/'recordings')
from latency_trace import Trace
TRACE=Trace(R)
PHOTOS=PhotoStore()
from section_host import SectionHost
from section_html import augment
from point_coverage import augment as point_coverage
SECTION=SectionHost()
SECTION.recover_on_startup()
MODE_LOCK=threading.RLock()

def board(path,body=None,port=8850,timeout=10):
    if path=='/fast/control' and body and body.get('op') in ('preview','photo','begin'):
        was_section=SECTION.active
        SECTION.leave()
        if was_section and body['op'] in ('preview','photo'):HDMI.restore_display_job(photo=body['op']=='photo')
    req=urllib.request.Request('http://192.168.137.2:'+str(port)+path,None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'} if body is not None else {})
    with OP.open(req,timeout=timeout) as f:
        n=int(f.headers.get('Content-Length','-1'));assert 0<=n<=32*1024**2
        data=f.read(n+1);assert len(data)==n;return data

class Workflow:
    def __init__(self):
        self.lock=threading.Lock();self.busy=False;self.stage='idle';self.error='';self.job=None;self.result=None;self.started=0;self.last_preview=None;self.last_preview_headers={};self.processing_port=8850;self.processing_frame=None;self.video_source=None
        p=R/'latest.json'
        if p.exists():self.result=json.loads(p.read_text(encoding='utf8'))
    def status(self):
        with self.lock:return dict(busy=self.busy,stage=self.stage,error=self.error,job_id=self.job,result=self.result,video_source=self.video_source,elapsed_seconds=round(time.monotonic()-self.started,1) if self.busy else None)
    def start(self,request_id=None,physical_created=None,video_source=None):
        with MODE_LOCK:
            assert not VIDEOS.status()['recording'],'请先结束视频录制'
            SECTION.leave()
            return self._start(request_id,physical_created,video_source)
    def _start(self,request_id=None,physical_created=None,video_source=None):
        request_received=time.monotonic()
        with self.lock:
            assert not self.busy,'正在处理，请等这张完成'
            from video_deploy import ensure_board
            ensure_board()
            REPLAY.end()
            clock_before=time.monotonic();health=json.loads(board('/health'));clock_after=time.monotonic();assert health['ready'],'板端模型尚未就绪，请稍候再拍照'
            s=json.loads(board('/stereo/status',port=8788));assert not s['busy'] and not s['section_busy'] and not s['standby'],'请先恢复相机并等待当前任务结束'
            self.job=request_id or uuid.uuid4().hex
            if not re.fullmatch('[0-9a-f]{32}',self.job):raise ValueError('Invalid photo identity')
            offset=(clock_before+clock_after)/2-health['server_monotonic']
            origin=physical_created+offset if physical_created is not None else request_received
            TRACE.begin(self.job,origin,'video_frame' if video_source else 'PL_KEY2' if physical_created is not None else 'web_request',offset,(clock_after-clock_before)*500)
            TRACE.mark('pc_request_received',request_received)
            TRACE.mark('preflight_done')
            HDMI.begin(self.job)
            self.processing_port=8853
            self.processing_frame=VIDEOS.frame(video_source['id'],video_source['frame'])[0] if video_source else None
            self.video_source=video_source
            TRACE.mark('capture_dispatched')
            self.busy=True;self.stage='capture';self.error='';self.started=time.monotonic()
            threading.Thread(target=self.run,args=(self.job,video_source),daemon=True).start()
            return dict(accepted=True,job_id=self.job)
    def run(self,job,video_source=None):
        try:
            port=8853
            if video_source:
                from video_deploy import ensure_board
                ensure_board()
                import cv2,numpy as np
                raw,manifest=VIDEOS.frame(video_source['id'],video_source['frame'])
                image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
                assert image is not None and image.shape==(480,1280,3),'录制双目图像尺寸无效'
                ok,png=cv2.imencode('.png',image);assert ok
                req=urllib.request.Request('http://192.168.137.2:8853/capture-frame?id='+job,png.tobytes(),headers={'Content-Type':'image/png'})
                with OP.open(req,timeout=20) as response:reply=json.load(response)
            else:reply=json.loads(board('/capture',dict(job_id=job),port=8853))
            assert reply['accepted']
            deadline=time.monotonic()+750
            while time.monotonic()<deadline:
                s=json.loads(board('/status?id='+job,port=port))
                with self.lock:self.stage=s['stage']
                if s.get('error'):raise RuntimeError(s['error'])
                if s['stage']=='ready':
                    TRACE.board_events(s.get('trace_monotonic',{}));TRACE.mark('pc_observed_board_ready');break
                time.sleep(.5 if s['stage']=='fast_inference' else .1)
            else:raise TimeoutError('板端处理尚未完成，请检查日志，勿重复启动')
            assert s['job_id']==job and s['stable_restored']
            TRACE.mark('receive_started')
            transfer_started=time.monotonic()
            data=board('/result?id='+job,port=port,timeout=60);assert len(data)==s['package_bytes'] and hashlib.sha256(data).hexdigest()==s['package_sha256']
            transfer_seconds=time.monotonic()-transfer_started
            TRACE.mark('receive_done')
            export_started=time.monotonic()
            folder=R/'captures'/job;folder.mkdir(exist_ok=False)
            (folder/'board_result.npz').write_bytes(data);(folder/'board_status.json').write_text(json.dumps(s,indent=2))
            with self.lock:self.stage='export_3d'
            result=export(folder,s)
            if video_source:
                result['video_source']=dict(video_source,timestamp_seconds=manifest['timestamps'][video_source['frame']],camera_identity=manifest['identities'][video_source['frame']],jpeg_sha256=hashlib.sha256(raw).hexdigest())
                (folder/'video_source.jpg').write_bytes(raw)
            result.update(pc_receive_seconds=transfer_seconds,pc_export_seconds=time.monotonic()-export_started,transfer_bytes=len(data),transport='PS_ETH / TCP IPv4 192.168.137.2')
            TRACE.mark('export_done')
            try:
                receipt=json.loads(board('/cache-ack',dict(job_id=job,package_sha256=s['package_sha256']),port=port))
                result['board_cache_released']=bool(receipt['released'])
            except Exception:result['board_cache_released']=False
            (folder/'report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
            (R/'latest.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
            TRACE.mark('cache_ack_done')
            HDMI.ready(job)
            with self.lock:self.result=result;self.stage='ready'
            TRACE.mark('pc_result_ready')
        except Exception as exc:
            TRACE.mark('failed',detail=str(exc))
            HDMI.failed(job,exc)
            with self.lock:self.error=str(exc);self.stage='failed'
        finally:
            with self.lock:self.busy=False

W=Workflow()
from fast_hdmi_host import Controller
HDMI=Controller(W,board,PHOTOS.packet)
HDMI.section=SECTION
from replay_hdmi import ReplayHDMI
REPLAY=ReplayHDMI(HDMI,W)
HDMI.replay=REPLAY
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup();self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.preview_connection=None;self.preview_port=None;self.preview_last=0
    def finish(self):
        if self.preview_connection:self.preview_connection.close()
        super().finish()
    def preview_read(self,port,path):
        if self.preview_connection is None or self.preview_port!=port or time.monotonic()-self.preview_last>5:
            if self.preview_connection:self.preview_connection.close()
            self.preview_connection=http.client.HTTPConnection('192.168.137.2',port,timeout=.5);self.preview_port=port
        try:
            self.preview_connection.request('GET',path);r=self.preview_connection.getresponse()
            n=int(r.getheader('Content-Length','-1'));assert r.status==200 and 0<n<=4*1024**2
            data=r.read(n+1);assert len(data)==n and data[:2]==b'\xff\xd8'
            headers={k:r.getheader(k) for k in ('X-Frame-Sequence','X-Frame-Epoch','X-Frame-Age-Ms','X-Frame-Mode') if r.getheader(k) is not None}
            headers['X-Frame-Source']='camera' if port==8788 else 'processing'
            self.preview_last=time.monotonic();return data,headers
        except Exception:
            self.preview_connection.close();self.preview_connection=None;raise
    def allowed(self):return self.client_address[0]=='127.0.0.1' and self.headers.get('Host')=='127.0.0.1:'+str(PORT)
    def data(self,data,mime='application/json',code=200,headers=None):
        if not isinstance(data,bytes):data=json.dumps(data).encode()
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items():self.send_header(k,str(v))
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        if not self.allowed():self.send_error(403);return
        path=urlsplit(self.path).path
        if path=='/api/video/status':self.data(dict(VIDEOS.status(),hdmi=REPLAY.status()));return
        if path=='/api/video/manifest':
            try:self.data(VIDEOS.manifest(parse_qs(urlsplit(self.path).query)['id'][0]))
            except (KeyError,ValueError,AssertionError,OSError) as exc:self.data(dict(error=str(exc)),code=404)
            return
        if path=='/api/video/frame':
            try:
                q=parse_qs(urlsplit(self.path).query);raw,_=VIDEOS.frame(q['id'][0],int(q['frame'][0]));self.data(raw,'image/jpeg')
            except (KeyError,ValueError,AssertionError,OSError) as exc:self.data(dict(error=str(exc)),code=404)
            return
        if path=='/video_ui.js':self.data((R/'video_ui.js').read_bytes(),'application/javascript; charset=utf-8');return
        if path=='/api/preview-zoom':
            try:self.data(json.loads(board('/preview/zoom',port=8788)))
            except Exception as exc:self.data(dict(error=str(exc)),code=503)
            return
        if path=='/api/status':self.data(dict(W.status(),hdmi=HDMI.snapshot(),timing=TRACE.snapshot(),section=SECTION.snapshot()));return
        if path=='/api/section/extra':
            owner=parse_qs(urlsplit(self.path).query).get('owner',[''])[0]
            with SECTION.lock:
                if not SECTION.active or owner!=SECTION.owner:self.send_error(409);return
                self.data(SECTION.extra,'application/octet-stream');return
        if path in ('/section_ui.js','/section_viewer.js'):
            self.data((R/path[1:]).read_bytes(),'application/javascript; charset=utf-8');return
        if path=='/api/timing-clock':self.data(dict(monotonic=time.monotonic()));return
        if path=='/latency.js':self.data((R/'latency.js').read_bytes(),'application/javascript; charset=utf-8');return
        if path in ('/comparison.html','/comparison_data.json','/same_photo_comparison.png'):
            p=R/path[1:]
            if p.is_file():self.data(p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream');return
        if path in ('/ui.css','/ui.js','/viewer_bridge.js','/hdmi_ui.js'):
            name=path[1:];mime='text/css' if name.endswith('.css') else 'application/javascript'
            self.data((R/name).read_bytes(),mime+'; charset=utf-8');return
        if path=='/preview.jpg':
            query=parse_qs(urlsplit(self.path).query);cursor=query.get('after',[''])[0]
            if cursor and not re.fullmatch('[0-9]{1,20},[0-9]{1,20}',cursor):self.send_error(400);return
            with W.lock:busy=W.busy;stage=W.stage;data=W.last_preview;headers=dict(W.last_preview_headers)
            try:
                processing=busy and stage in ('pause_preview','load_pl','rectification','live_preview_start','fast_inference','geometry')
                if busy and W.processing_frame:
                    data=W.processing_frame;headers={'X-Frame-Source':'processing'}
                else:data,headers=self.preview_read(W.processing_port if processing else 8788,'/processing-preview.jpg' if processing else '/preview.jpg'+('?after='+cursor if cursor else ''))
                with W.lock:W.last_preview=data;W.last_preview_headers=dict(headers)
            except Exception:headers['X-Frame-Stale']='1'
            if data:self.data(data,'image/jpeg',headers=headers)
            else:self.data(b'','image/jpeg',503)
            return
        if path=='/':self.data((R/'index.html').read_text(encoding='utf8').replace('__TOKEN__',TOKEN).encode(),'text/html; charset=utf-8');return
        photo_route=re.fullmatch(r'/captures/([0-9a-f]{32})/photo_(color|auto_enhanced|gray|sobel|vessel)\.png',path)
        if photo_route:
            try:self.data(PHOTOS.png(*photo_route.groups()),'image/png')
            except (OSError,ValueError) as exc:self.data(dict(error=str(exc)),code=404)
            return
        if re.fullmatch(r'/(captures|baseline_captures)/[0-9a-f]{32}/(viewer\.html|reference\.png|rectified\.png|disparity\.png|depth\.png|depth_values\.(json|bin)|latency\.json|points\.ply|dense_surface\.ply|geometry\.npz|report\.json|render_[0-9a-f]{16}\.png)',path):
            p=R/path.lstrip('/')
            if p.is_file():
                if p.name=='viewer.html':
                    html=point_coverage(augment(p.read_text(encoding='utf8')))
                    self.data(html.encode(),'text/html; charset=utf-8')
                else:self.data(p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
                return
        self.send_error(404)
    def do_POST(self):
        if not self.allowed():self.send_error(403);return
        try:
            assert self.headers.get('Origin')==ORIGIN and self.headers.get('X-Viewer-Token')==TOKEN
            if self.path=='/api/video/hdmi-frame':
                assert self.headers.get('Content-Type')=='application/octet-stream' and int(self.headers.get('Content-Length','0'))==1280*480*3
                with W.lock:assert not W.busy,'正在重建'
                raw=self.rfile.read(1280*480*3);assert len(raw)==1280*480*3
                self.data(REPLAY.submit(raw,self.headers.get('X-Replay-Owner'),self.headers.get('X-Replay-Generation'),int(self.headers.get('X-Replay-Sequence','-1'))));return
            if self.path.startswith('/api/video/'):
                size=int(self.headers.get('Content-Length','0'));assert self.headers.get('Content-Type')=='application/json' and 2<=size<=200
                args=json.loads(self.rfile.read(size));op=self.path.rsplit('/',1)[-1]
                if op=='start':
                    with MODE_LOCK,W.lock:
                        assert not W.busy and not SECTION.active and not SECTION.switching,'请先完成当前三维操作'
                        assert not VIDEOS.status()['recording'],'正在录制'
                        health=json.loads(board('/health'));assert health['ready'],'板卡未就绪'
                        HDMI.control('preview',mode='color')
                        result=VIDEOS.start()
                elif op=='stop':result=VIDEOS.stop()
                elif op=='replay-begin':
                    assert set(args)=={'owner'} and re.fullmatch('[0-9a-f]{32}',args['owner'])
                    with MODE_LOCK,W.lock:
                        assert not W.busy and not SECTION.active and not VIDEOS.status()['recording']
                        from video_deploy import ensure_board
                        ensure_board();result=REPLAY.begin(args['owner'])
                elif op=='replay-heartbeat':result=REPLAY.touch(args['owner'],args['generation'])
                elif op=='replay-end':result=REPLAY.end(args['owner'],args['generation'])
                elif op=='reconstruct':
                    assert set(args)=={'id','frame'}
                    VIDEOS.frame(args['id'],args['frame'])
                    result=W.start(video_source=args)
                else:raise ValueError('未知视频操作')
                self.data(result);return
            if self.path.startswith('/api/section/'):
                size=int(self.headers.get('Content-Length','0'));assert self.headers.get('Content-Type')=='application/json' and 2<=size<=2000
                args=json.loads(self.rfile.read(size));owner=args.get('owner','');assert re.fullmatch('[0-9a-f]{32}',owner)
                op=self.path.rsplit('/',1)[-1]
                if op=='enter':
                    with MODE_LOCK:
                        assert not VIDEOS.status()['recording'],'请先结束视频录制'
                        with W.lock:assert not W.busy and W.result and args['job_id']==W.result['job_id'],'照片已切换或正在处理'
                        result=SECTION.enter(args['job_id'],owner,args['thickness_mm'])
                        try:
                            # The qualified UVC recovery may restart the camera.
                            # Wait for the normal controller/browser to republish
                            # the saved model under its new display generation.
                            deadline=time.monotonic()+20
                            while True:
                                ready=json.loads(board('/fast/status',port=8788))
                                if ready.get('job_id')==args['job_id'] and 'surface' in ready.get('frames',[]) and not ready.get('waiting_for_render'):break
                                if time.monotonic()>deadline:raise RuntimeError('三维显示帧恢复超时，请保持网页打开后重试')
                                time.sleep(.15)
                            selected=json.loads(board('/fast/control',dict(op='section',job_id=args['job_id']),port=8788))
                            SECTION.display_epoch=selected['display_epoch']
                            SECTION.display_armed=True
                        except Exception:SECTION.leave(owner);raise
                elif op=='run':result=SECTION.run(args)
                elif op=='exit':
                    with MODE_LOCK:
                        was_section=SECTION.active;result=SECTION.leave(owner)
                        if was_section:
                            HDMI.restore_display_job()
                            deadline=time.monotonic()+20
                            while True:
                                ready=json.loads(board('/fast/status',port=8788))
                                if 'surface' in ready.get('frames',[]) and not ready.get('waiting_for_render'):break
                                if time.monotonic()>deadline:break
                                time.sleep(.15)
                            if 'surface' in ready.get('frames',[]):board('/fast/control',dict(op='section',job_id=ready['job_id']),port=8788)
                elif op=='heartbeat':result=SECTION.heartbeat(owner)
                else:raise ValueError('Unknown section operation')
                self.data(result);return
            if self.path=='/api/preview-zoom':
                size=int(self.headers.get('Content-Length','0'));assert self.headers.get('Content-Type')=='application/json' and 2<=size<=200
                args=json.loads(self.rfile.read(size))
                with W.lock:
                    assert not W.busy and not SECTION.active and not SECTION.switching,'正在处理三维操作'
                    self.data(json.loads(board('/preview/zoom',args,port=8788)))
                return
            if self.path=='/api/timing':
                size=int(self.headers.get('Content-Length','0'));assert self.headers.get('Content-Type')=='application/json' and 2<=size<=12000
                self.data(TRACE.browser(json.loads(self.rfile.read(size))));return
            if self.path=='/api/display':
                assert not VIDEOS.status()['recording'],'录制期间保持原始彩色预览，请先结束录制'
                size=int(self.headers.get('Content-Length','0'));assert self.headers.get('Content-Type')=='application/json' and 2<=size<=220
                args=json.loads(self.rfile.read(size));assert args.get('op') in ('preview','photo') and args.get('mode') in (PREVIEW_MODES if args.get('op')=='preview' else MODES)
                assert set(args)==({'op','mode','job_id'} if args['op']=='photo' else {'op','mode'})
                with W.lock:
                    assert not W.busy,'正在处理照片，请稍候'
                    if args['op']=='photo':assert W.result and W.result['job_id']==args['job_id'],'照片已切换'
                self.data(HDMI.control(args.pop('op'),**args));return
            if self.path=='/api/hdmi/frame':
                size=int(self.headers.get('Content-Length','0'));mime=self.headers.get('Content-Type');assert mime in ('image/png','application/octet-stream') and 24<=size<=4*1024**2
                data=self.rfile.read(size);assert len(data)==size
                if mime=='image/png':assert data[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',data[16:24])==(1280,720)
                else:assert size in (640*360*3,1280*720*3)
                self.data(HDMI.frame(data,self.headers.get('X-Photo-Id',''),self.headers.get('X-Fast-Generation',''),self.headers.get('X-Fast-View',''),mime,int(self.headers['X-HDMI-Epoch']) if self.headers.get('X-HDMI-Epoch') is not None else None,self.headers.get('X-HDMI-Activate')=='1'));return
            if self.path=='/api/hdmi/publish':
                size=int(self.headers.get('Content-Length','0'));assert self.headers.get('Content-Type')=='application/json' and 2<=size<=300
                args=json.loads(self.rfile.read(size));assert set(args)=={'job_id','generation','render_ms','prepare_ms'}
                timings={k:float(args.pop(k)) for k in ('render_ms','prepare_ms')};assert all(0<=v<120000 for v in timings.values())
                TRACE.mark('hdmi_publish_started',job=args['job_id'])
                result=HDMI.control('publish',**args)
                TRACE.mark('hdmi_ready',job=args['job_id'])
                timings['transport']=HDMI.snapshot().get('transport',{})
                (R/'captures'/args['job_id']/'hdmi_timing.json').write_text(json.dumps(timings,indent=2))
                self.data(result);return
            if self.path=='/api/render-export':
                assert self.headers.get('Content-Type')=='image/png'
                job=self.headers.get('X-Photo-Id','');assert re.fullmatch('[0-9a-f]{32}',job)
                folder=R/'captures'/job;assert (folder/'report.json').is_file()
                size=int(self.headers.get('Content-Length','0'));assert 24<=size<=12*1024**2
                data=self.rfile.read(size);assert len(data)==size and data[:8]==b'\x89PNG\r\n\x1a\n' and data[12:16]==b'IHDR'
                width,height=struct.unpack('>II',data[16:24]);assert 0<width<=4096 and 0<height<=4096
                name='render_'+uuid.uuid4().hex[:16]+'.png';(folder/name).write_bytes(data)
                self.data(dict(url='/captures/'+job+'/'+name,bytes=size,width=width,height=height));return
            assert self.path=='/api/capture'
            assert self.headers.get('Content-Type')=='application/json' and int(self.headers.get('Content-Length','0'))==2
            assert self.rfile.read(2)==b'{}'
            self.data(W.start(),code=202)
        except Exception as exc:self.data(dict(error=str(exc)),code=409)
    def log_message(self,*args):pass

if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
