"""Resident preview/section core. PS culls bounding boxes; PL owns section pixels."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import base64,ctypes,fcntl,hashlib,json,os,socket,sys,threading,time,traceback,zlib
import numpy as np
E=Path(__file__).resolve().parent;R=E.parent/'fast_infer2';S=E.parent/'usb320_hdmifps'
sys.path[:0]=[str(R),str(S)]
import test_hardware_board as h
import pause_preview_board as preview
from board_dma import Arena,reservation
from preview_hardware import check_preview,PREVIEW_CORES
CONFIG=json.loads((E/'section_config.json').read_text())
TOKEN=(E/'token.txt').read_text().strip()

class Section:
    def __init__(self):
        self.lock=threading.RLock();self.active=False;self.switching=False;self.fault='';self.owner=None;self.mesh=None;self.count=0;self.calls=0;self.touched=0;self.leases=[];self.latest_seq=-1;self.last={}
        self.lib=ctypes.CDLL(str(E/'section_dma.so'))
        self.lib.section_upload.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        self.lib.section_select.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        self.lib.section_select.restype=ctypes.c_int
        self.lib.section_run.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p]
        self.lib.section_run.restype=ctypes.c_int
    def status(self):
        return dict(active=self.active,switching=self.switching,error=self.fault,owner=self.owner,mesh_sha256=self.mesh,calls=self.calls,latest_seq=self.latest_seq,last=self.last,backend='PL SEC1',sha256=CONFIG['sha256'] if self.active else h.OLD_SHA)
    def leases_open(self):
        try:
            for p in (R.parent/'fast_pl/capture.lock',R/'capture.lock'):
                f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);self.leases.append(f)
        except BaseException:
            self.leases_close();raise
    def leases_close(self):
        for f in self.leases:f.close()
        self.leases=[]
    def switch(self,on):
        self.switching=True;started=time.monotonic()
        try:
            assert not h.SNAP.exists(),'Recover the interrupted PL switch first'
            assert h.OLD_SHA==CONFIG['sha256'],'Preview must include the qualified SEC1 core'
            if on:
                reservation()
                assert json.loads((S/'loaded.json').read_text())['sha256']==CONFIG['sha256']
                state=h.request(8788,'/stereo/status')
                assert not state['busy'] and not state['section_busy'] and not state['standby']
                assert self.lib.section_open()==0,'Cannot open section DMA'
                assert self.lib.section_identity()==0x53454331,'Wrong section hardware'
            else:
                assert self.lib.section_idle(),'Section DMA not idle; keeping capture lease'
                self.lib.section_close()
            self.active=on;self.last=dict(switch_seconds=time.monotonic()-started);self.fault=''
        except BaseException as exc:
            self.fault=str(exc)
            # A timeout keeps the lease: Fast must never borrow outstanding DMA.
            raise
        finally:self.switching=False
    def enter(self,args,raw):
        with self.lock:
            owner=args['owner'];digest=args['mesh_sha256'];count=int(args['triangles'])
            assert len(owner)==32 and all(c in '0123456789abcdef' for c in owner)
            assert 0<count<=500000 and len(raw)==count*36 and hashlib.sha256(raw).hexdigest()==digest
            points=np.frombuffer(raw,dtype='<f4');assert np.isfinite(points).all() and np.max(abs(points))<1e7
            if self.active and self.owner!=owner:raise ValueError('截面正在另一页面使用，请先退出')
            if not self.active:
                self.leases_open()
                try:self.switch(True)
                except BaseException:
                    if not h.SNAP.exists() and self.lib.section_idle():
                        self.lib.section_close();self.leases_close()
                    raise
            blob=ctypes.create_string_buffer(raw);assert self.lib.section_upload(blob,len(raw))==0
            self.owner=owner;self.mesh=digest;self.count=count;self.latest_seq=-1;self.touched=time.monotonic()
            return self.status()
    def run(self,args):
        with self.lock:
            assert self.active and not self.fault and args['owner']==self.owner and args['mesh_sha256']==self.mesh,'截面会话已失效'
            seq=int(args['seq']);assert seq>self.latest_seq
            p=np.asarray(args['params'],dtype='<f4');assert p.shape==(16,) and np.isfinite(p).all()
            assert .99<np.linalg.norm(p[:3])<1.01 and .99<np.linalg.norm(p[4:7])<1.01 and .99<np.linalg.norm(p[7:10])<1.01
            assert max(abs(p[:3]@p[4:7]),abs(p[:3]@p[7:10]),abs(p[4:7]@p[7:10]))<.001 and 0<p[12]<100000
            out=np.zeros(262160,dtype='<u4');timing=np.zeros(2,np.float64);start=time.monotonic()
            select_timing=np.zeros(2,np.float64)
            candidates=self.lib.section_select(p.ctypes.data,select_timing.ctypes.data)
            assert 0<=candidates<=self.count,'Triangle scheduling failed'
            rc=self.lib.section_run(p.ctypes.data,out.ctypes.data,candidates,2,timing.ctypes.data)
            if rc:
                self.fault='PL section failed: '+str(rc);raise RuntimeError(self.fault)
            assert out[0]==0x53454331 and out[1]==candidates
            bounds_ms=float(timing[0]*1000);copy_ms=float(timing[1]*1000)
            if out[2]:
                limits=out[6:10].view('<f4').astype(float);assert np.isfinite(limits).all()
                low=limits[:2];high=limits[2:];assert (high>=low).all()
                width=max(float((high-low).max())*1.06+4,4);lower=(low+high)/2-width/2
                p[10:12]=p[10:12]+lower/float(p[12]);p[12]=np.float32(float(p[12])*512/width)
                rc=self.lib.section_run(p.ctypes.data,out.ctypes.data,candidates,1,timing.ctypes.data)
                if rc:self.fault='PL fill failed: '+str(rc);raise RuntimeError(self.fault)
            else:timing[:]=0
            if out[4]:raise RuntimeError('截面轮廓未闭合，已拒绝显示错误封盖')
            assert np.logical_or(out[16:]==0,out[16:]==255).all()
            self.calls+=1;self.latest_seq=seq;self.touched=time.monotonic()
            self.last=dict(original_triangles=self.count,candidate_triangles=candidates,broadphase_ms=float(select_timing[0]*1000),upload_ms=float(select_timing[1]*1000),device_ms=bounds_ms+float(timing[0]*1000),bounds_ms=bounds_ms,readback_ms=copy_ms+float(timing[1]*1000),total_ms=(time.monotonic()-start)*1000,segments=int(out[2]),pixels=int(out[3]),open_rows=int(out[4]),seq=seq)
            return dict(owner=self.owner,mesh_sha256=self.mesh,width=512,height=512,params=p.tolist(),mask=base64.b64encode(out[16:].astype('u1').tobytes()).decode(),backend='PL SEC1',**self.last)
    def leave(self,owner=None):
        with self.lock:
            if owner and self.owner and owner!=self.owner:raise ValueError('截面会话已切换')
            if self.active:self.switch(False)
            if not h.SNAP.exists():self.leases_close()
            self.owner=None;self.mesh=None;self.count=0
            return self.status()
ENGINE=Section()
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup();self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
    def send(self,data,code=200):
        raw=json.dumps(data).encode();compressed='deflate' in self.headers.get('Accept-Encoding','') and len(raw)>4096
        if compressed:raw=zlib.compress(raw,1)
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        if compressed:self.send_header('Content-Encoding','deflate')
        self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        if self.client_address[0] not in ('192.168.137.1','127.0.0.1'):self.send_error(403);return
        if self.path=='/status':self.send(ENGINE.status())
        else:self.send_error(404)
    def do_POST(self):
        if self.client_address[0] not in ('192.168.137.1','127.0.0.1') or self.headers.get('X-Section-Token')!=TOKEN:self.send_error(403);return
        try:
            n=int(self.headers.get('Content-Length','0'));assert 2<=n<=18000000
            raw=self.rfile.read(n);assert len(raw)==n
            if self.path=='/enter':result=ENGINE.enter(json.loads(self.headers['X-Section-Metadata']),raw)
            else:
                args=json.loads(raw)
                if self.path=='/run':result=ENGINE.run(args)
                elif self.path=='/exit':result=ENGINE.leave(args.get('owner'))
                elif self.path=='/heartbeat':
                    with ENGINE.lock:
                        assert args['owner']==ENGINE.owner;ENGINE.touched=time.monotonic();result=ENGINE.status()
                else:raise ValueError('Unknown operation')
            self.send(result)
        except Exception as exc:traceback.print_exc();self.send(dict(error=str(exc),status=ENGINE.status()),409)
    def log_message(self,*args):pass
def watchdog():
    while True:
        time.sleep(2)
        with ENGINE.lock:
            if ENGINE.active and not ENGINE.switching and time.monotonic()-ENGINE.touched>60:
                try:ENGINE.leave()
                except Exception:traceback.print_exc()
if __name__=='__main__':
    assert not h.SNAP.exists(),'Recover the interrupted PL switch first'
    assert json.loads((S/'loaded.json').read_text())['sha256']==h.OLD_SHA
    threading.Thread(target=watchdog,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',8852),Handler).serve_forever()
