"""Transport and one-time display shell preparation; section mask comes from PL."""
from pathlib import Path
import hashlib,http.client,json,socket,threading,time,zlib
from section_mesh import shell,plane,render_geometry
R=Path(__file__).resolve().parent
class SectionHost:
    def __init__(self):
        self.prepare_lock=threading.Lock();self.cache=None;self.warming=set();self.warm_lock=threading.Lock();self.lock=threading.RLock();self.active=False;self.owner=None;self.meta=None;self.extra=b'';self.job=None;self.seq=-1;self.error='';self.switching=False;self.metrics={};self.display_armed=False;self.display_epoch=0
    def request(self,path,body,metadata=None):
        token=(R/'section_token.txt').read_text().strip();raw=body if isinstance(body,bytes) else json.dumps(body).encode()
        headers={'Content-Type':'application/octet-stream' if metadata else 'application/json','X-Section-Token':token,'Accept-Encoding':'deflate'}
        if metadata:headers['X-Section-Metadata']=json.dumps(metadata)
        c=http.client.HTTPConnection('192.168.137.2',8852,timeout=30)
        try:
            c.connect();c.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            c.request('POST',path,raw,headers);r=c.getresponse();n=int(r.getheader('Content-Length','-1'));assert 0<n<2*1024**2
            response=r.read(n)
            if r.getheader('Content-Encoding')=='deflate':
                decoder=zlib.decompressobj();response=decoder.decompress(response,2*1024**2)
                assert decoder.eof and not decoder.unconsumed_tail
            data=json.loads(response)
            if r.status!=200:raise RuntimeError(data.get('error','Section request failed'))
            return data
        finally:c.close()
    def recover_on_startup(self):
        c=http.client.HTTPConnection('192.168.137.2',8852,timeout=2)
        try:
            c.request('GET','/status');r=c.getresponse();status=json.loads(r.read(8192))
            if status.get('active'):self.request('/exit',{})
            elif status.get('error'):self.error=status['error']
        except Exception as exc:self.error='截面服务暂不可用：'+str(exc)
        finally:c.close()
    def snapshot(self):return dict(active=self.active,switching=self.switching,owner=self.owner,job_id=self.job,error=self.error,seq=self.seq,metrics=self.metrics,backend='PL SEC1')
    def prepare(self,job,thickness):
        # Captures are immutable; file metadata invalidates a replaced capture.
        folder=R/'captures'/job
        signature=tuple((p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in sorted(folder.glob('*.npz')))
        key=(job,float(thickness),signature)
        with self.prepare_lock:
            if self.cache and self.cache[0]==key:return self.cache[1]
            tri,extra,meta=shell(folder,thickness)
            result=(tri.tobytes(),extra.tobytes(),meta,len(tri))
            self.cache=(key,result);return result
    def prewarm(self,job):
        with self.warm_lock:
            if job in self.warming or (self.cache and self.cache[0][0]==job):return
            self.warming.add(job)
        def work():
            try:self.prepare(job,10.)
            except Exception:pass  # Entry reports preparation errors to the user.
            finally:
                with self.warm_lock:self.warming.discard(job)
        threading.Thread(target=work,daemon=True).start()
    def enter(self,job,owner,thickness):
        with self.lock:
            if self.active and self.owner!=owner:raise ValueError('另一页面正在使用截面，请先退出')
            self.switching=True
            try:
                start=time.monotonic();tri,extra,meta,count=self.prepare(job,thickness)
                preparation=time.monotonic()-start
                self.request('/enter',tri,dict(owner=owner,mesh_sha256=meta['mesh_sha256'],triangles=count))
                self.extra=extra;self.meta=meta;self.job=job;self.owner=owner;self.active=True;self.error='';self.seq=-1;self.display_armed=False
                self.metrics=dict(prepare_seconds=preparation,enter_seconds=time.monotonic()-start)
                return dict(meta,owner=owner,job_id=job,extra_bytes=len(self.extra),**self.metrics)
            except Exception as exc:
                self.error=str(exc)
                try:self.request('/exit',dict(owner=owner))
                except Exception as recovery:self.error+='; recovery: '+str(recovery)
                raise
            finally:self.switching=False
    def run(self,args):
        with self.lock:
            assert self.active and args['owner']==self.owner and args['job_id']==self.job,'截面会话或照片已切换'
            seq=int(args['seq']);assert seq>self.seq
            p,info=plane(self.meta,args['normal'],args['position'],args.get('flip',False))
            start=time.monotonic();r=self.request('/run',dict(owner=self.owner,mesh_sha256=self.meta['mesh_sha256'],seq=seq,params=p.tolist()))
            assert r['owner']==self.owner and r['mesh_sha256']==self.meta['mesh_sha256'] and r['seq']==seq
            assert r['params'][:10]==p.tolist()[:10]
            info=render_geometry(r['params'],args['position'],args.get('flip',False))
            self.seq=seq;self.metrics.update({k:r[k] for k in ('device_ms','readback_ms','total_ms','pixels','segments','open_rows','original_triangles','candidate_triangles','broadphase_ms','upload_ms')})
            self.metrics['roundtrip_ms']=(time.monotonic()-start)*1000
            return dict(r,geometry=info,roundtrip_ms=self.metrics['roundtrip_ms'])
    def heartbeat(self,owner):
        with self.lock:
            assert self.active and owner==self.owner
            self.request('/heartbeat',dict(owner=owner));return self.snapshot()
    def leave(self,owner=None):
        with self.lock:
            if owner and self.owner and owner!=self.owner:raise ValueError('截面会话已切换')
            if self.active:
                self.switching=True
                try:self.request('/exit',dict(owner=self.owner));self.active=False;self.error=''
                except Exception as exc:self.error=str(exc);raise
                finally:self.switching=False
            self.extra=b'';self.owner=None;self.job=None;self.meta=None;self.display_armed=False
            return self.snapshot()
