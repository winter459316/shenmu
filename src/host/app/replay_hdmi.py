"""Forward only the latest displayed replay frame; pauses retain a heartbeat lease."""
import hashlib,http.client,json,threading,time
class ReplayHDMI:
    def __init__(self,controller,workflow):
        self.controller=controller;self.workflow=workflow;self.lock=threading.RLock();self.wire=threading.Lock()
        self.owner=None;self.generation=None;self.pending=None;self.sequence=-1;self.presented=-1;self.last_touch=0;self.error='';self.sent=0
        self.wake=threading.Event();threading.Thread(target=self.run,daemon=True).start()
    def status(self):
        with self.lock:return dict(active=self.owner is not None,owner=self.owner,generation=self.generation,sequence=self.sequence,presented=self.presented,sent=self.sent,error=self.error)
    def begin(self,owner):
        self.end()
        with self.wire:
            result=self.controller.control('replay_begin',owner=owner)
            with self.lock:
                self.owner=owner;self.generation=result['replay']['generation'];self.sequence=-1;self.presented=-1;self.error='';self.last_touch=time.monotonic()
                return self.status()
    def touch(self,owner,generation):
        with self.lock:
            assert self.owner==owner and self.generation==generation,'回放会话已失效'
            self.last_touch=time.monotonic();return self.status()
    def submit(self,data,owner,generation,sequence):
        assert len(data)==1280*480*3
        with self.lock:
            assert self.owner==owner and self.generation==generation,'回放已退出'
            assert type(sequence) is int and sequence>self.sequence,'回放序号已过期'
            self.sequence=sequence;self.pending=(data,owner,generation,sequence);self.last_touch=time.monotonic();self.wake.set()
            return dict(accepted=True,sequence=sequence)
    def end(self,owner=None,generation=None):
        with self.wire:
            with self.lock:
                if not self.owner:return dict(active=False)
                if owner is not None and (self.owner!=owner or self.generation!=generation):return dict(active=False,stale=True)
                prior=(self.owner,self.generation);self.owner=None;self.generation=None;self.pending=None
            return self.controller.control('replay_end',owner=prior[0],generation=prior[1])
    def run(self):
        heartbeat=0
        while True:
            self.wake.wait(.15);self.wake.clear()
            try:
                with self.wire:
                    with self.lock:
                        owner=self.owner;generation=self.generation;pending=self.pending;self.pending=None;age=time.monotonic()-self.last_touch
                    if not owner:continue
                    if age>3:
                        with self.lock:self.owner=None;self.generation=None;self.pending=None
                        self.controller.control('replay_end',owner=owner,generation=generation);continue
                    if pending:
                        data,owner,generation,sequence=pending
                        headers={'Content-Type':'application/octet-stream','X-Photo-Id':owner,'X-Fast-Generation':generation,'X-Fast-View':'replay','X-HDMI-Epoch':str(sequence),'X-Frame-SHA256':hashlib.sha256(data).hexdigest()}
                        c=http.client.HTTPConnection('192.168.137.2',8788,timeout=3)
                        try:
                            c.connect();c.request('POST','/fast/frame',data,headers);r=c.getresponse();reply=json.loads(r.read(8192));assert r.status==200,reply
                        finally:c.close()
                        with self.lock:self.presented=sequence;self.sent+=1;self.error=''
                        heartbeat=time.monotonic()
                    elif time.monotonic()-heartbeat>.7:
                        self.controller.control('replay_heartbeat',owner=owner,generation=generation);heartbeat=time.monotonic()
            except Exception as exc:
                with self.lock:self.error=str(exc)
