"""Small board job API; only explicit one-shot capture, never automatic looping."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import fcntl,json,re,subprocess,threading,time
from cache_release import acknowledge
R=Path(__file__).resolve().parent;PORT=8853
lock=threading.Lock();active=None;latest=None

class H(BaseHTTPRequestHandler):
    def allowed(self):
        return self.client_address[0]=='192.168.137.1' and self.headers.get('Host')=='192.168.137.2:8853'
    def data(self,data,code=200,mime='application/json'):
        if not isinstance(data,bytes):data=json.dumps(dict(data,server_monotonic=time.monotonic())).encode()
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        if not self.allowed():self.send_error(403);return
        route=urlsplit(self.path);job=parse_qs(route.query).get('id',[latest])[0]
        if route.path=='/health':
            worker={}
            try:
                worker=json.loads((R/'worker_status.json').read_text());pid=int(worker['pid'])
                cmd=[x.decode() for x in (Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0') if x]
                valid=any(Path(x).name=='infer_worker_pl3_v5_quad.py' and Path(x).resolve()==R/'infer_worker_pl3_v5_quad.py' for x in cmd)
                worker['ready']=bool(worker.get('ready') and valid and (R/'infer.sock').exists())
            except (OSError,ValueError,KeyError):worker={'ready':False,'state':'not_started'}
            self.data(dict(ready=worker['ready'],version='fast_pl3_usable_v5_quad',model_worker=worker,video_input_version='video_stereo_v2'));return
        if route.path=='/processing-preview.jpg':
            f=R/'jobs'/str(latest)/'processing_preview.jpg'
            if active is not None and active.poll() is None and f.is_file():self.data(f.read_bytes(),mime='image/jpeg')
            else:self.send_error(404)
            return
        if not job:self.data(dict(busy=False,stage='idle'));return
        if not re.fullmatch('[0-9a-f]{32}',job):self.send_error(400);return
        folder=R/'jobs'/job;p=folder/'status.json'
        if not p.exists():
            failed=job==latest and active is not None and active.poll() is not None
            self.data(dict(busy=not failed,stage='failed' if failed else 'starting',job_id=job,error='Worker could not acquire the shared capture lock; wait for the other flow to finish' if failed else ''));return
        s=json.loads(p.read_text())
        if route.path=='/status':
            if active and active.poll() is not None and s.get('busy'):s.update(busy=False,stage='failed',error='Board worker exited before completing restoration; inspect log')
            self.data(s)
        elif route.path=='/result' and s.get('stage')=='ready':
            if s.get('cache_released_to_pc'):self.data(dict(error='Result is preserved in the PC capture archive'),410)
            else:self.data((folder/'result.npz').read_bytes(),mime='application/octet-stream')
        else:self.send_error(409)
    def do_POST(self):
        global active,latest
        if not self.allowed():self.send_error(403);return
        try:
            route=urlsplit(self.path)
            if route.path=='/capture-frame':
                assert self.headers.get('Content-Type')=='image/png'
                job=parse_qs(route.query)['id'][0];assert re.fullmatch('[0-9a-f]{32}',job)
                n=int(self.headers.get('Content-Length','0'));assert 24<=n<=4*1024**2
                raw=self.rfile.read(n);assert len(raw)==n and raw[:8]==b'\x89PNG\r\n\x1a\n'
                import struct
                assert raw[12:16]==b'IHDR' and struct.unpack('>II',raw[16:24])==(1280,480)
                with lock,(R.parent/'fast_pl/capture.lock').open('a+') as legacy,(R/'capture.lock').open('a+') as capture:
                    for f in (legacy,capture):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    assert active is None or active.poll() is not None,'Fast is busy'
                    assert not (R/'pl_test_private_snapshot.json').exists(),'Recovery snapshot remains'
                    assert not list(R.glob('*.fault')),'DMA fault remains'
                    worker=json.loads((R/'worker_status.json').read_text());assert worker['state']=='ready'
                    folder=R/'jobs'/job;folder.mkdir(parents=True,exist_ok=False)
                    (folder/'video_input.png').write_bytes(raw)
                    (folder/'request_timing.json').write_text(json.dumps({'api_received':time.monotonic()}))
                    with (folder/'run.log').open('wb') as log:
                        active=subprocess.Popen(['python3','-u',str(R/'video_capture_v2.py'),job,'--video-input'],cwd=str(R),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                    latest=job
                self.data(dict(accepted=True,job_id=job),202);return
            assert self.path=='/cache-ack' and self.headers.get('Content-Type')=='application/json'
            n=int(self.headers.get('Content-Length','0'));assert 2<=n<=200
            args=json.loads(self.rfile.read(n))
            if self.path=='/cache-ack':
                assert set(args)=={'job_id','package_sha256'}
                with lock,(R/'capture.lock').open('a+') as capture:
                    fcntl.flock(capture,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    self.data(acknowledge(R/'jobs',args['job_id'],args['package_sha256']))
                return
        except Exception as exc:self.data(dict(error=str(exc)),409)
    def log_message(self,*args):pass

if __name__=='__main__':ThreadingHTTPServer(('192.168.137.2',PORT),H).serve_forever()
