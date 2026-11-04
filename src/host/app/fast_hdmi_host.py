"""PC coordinator: physical capture requests use the same Fast web workflow."""
import hashlib,http.client,json,re,socket,threading,time,urllib.request,uuid

class Controller:
    def __init__(self,workflow,board,photo_source=None):
        self.workflow=workflow;self.board=board;self.session=uuid.uuid4().hex
        self.lock=threading.Lock();self.frame_lock=threading.Lock();self.connection=None;self.cached={};self.metrics=dict(frames=0,bytes=0,seconds=0);self.seen=set();self.stop=threading.Event()
        self.photo_source=photo_source;self.photo_attempts={}
        self.connection_last_used=0;self.metrics.update(reconnects=0,recent=[])
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def snapshot(self):
        with self.lock:return dict(self.cached,transport=dict(self.metrics))
    def control(self,op,**args):
        reply=json.loads(self.board('/fast/control',dict(op=op,**args),port=8788,timeout=3))
        with self.lock:self.cached=reply
        return reply
    def begin(self,job):
        # The board expires idle HTTP uploads after 10s. A Fast inference spans
        # that timeout, so do not carry its old upload socket into the next photo.
        with self.frame_lock:
            if self.connection is not None:self.connection.close()
            self.connection=None
        return self.control('begin',job_id=job)
    def ready(self,job):return self.control('result',job_id=job)
    def restore_display_job(self,photo=False):
        with self.workflow.lock:result=self.workflow.result;busy=self.workflow.busy
        state=self.control('poll',session=self.session)
        if result and not busy and state.get('job_id')!=result['job_id']:
            state=self.ready(result['job_id'])
        if photo and result and not state.get('photo_ready'):
            self.upload_photo(result['job_id'],state['generation'])
        return state
    def upload_photo(self,job,generation):
        if self.photo_source is None:return
        token=(job,generation);count=self.photo_attempts.get(token,0)
        if count>=3:return
        self.photo_attempts[token]=count+1
        data=self.photo_source(job);started=time.monotonic()
        req=urllib.request.Request('http://192.168.137.2:8788/fast/photo',data,headers={
            'Content-Type':'application/octet-stream','X-Photo-Id':job,'X-Fast-Generation':generation,
            'X-Frame-SHA256':hashlib.sha256(data).hexdigest()})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5) as response:
            reply=json.load(response);assert reply['accepted']
        with self.lock:self.metrics['photo_source_seconds']=time.monotonic()-started;self.metrics['photo_source_bytes']=len(data)
    def failed(self,job,error):
        try:self.control('error',job_id=job,error=str(error)[:250])
        except Exception:pass
    def run(self):
        while not self.stop.wait(.25):
            if getattr(self,'section',None) and self.section.switching:continue
            with self.workflow.lock:busy=self.workflow.busy
            if busy:
                # The qualified Fast pipeline deliberately freezes the camera
                # HTTP process while PL is borrowed. This is not a disconnect.
                with self.lock:self.cached.update(busy=True,view='processing',error='',pc_online=True)
                continue
            try:
                state=self.control('poll',session=self.session)
                section=getattr(self,'section',None)
                if section and section.active and section.display_armed and state.get('display_epoch',-1)>=section.display_epoch and not section.switching and (state.get('view')=='preview' or state.get('view','').startswith('photo_')):
                    requested_view=state['view'];requested_mode=state.get('preview_mode','color');requested_job=state.get('job_id')
                    section.leave()
                    self.restore_display_job(photo=requested_view.startswith('photo_'))
                    state=self.control('preview',mode=requested_mode) if requested_view=='preview' else self.control('photo',job_id=requested_job,mode=requested_view[6:])
                request=state.get('pending')
                if request:
                    rid=request['id'];assert re.fullmatch('[0-9a-f]{32}',rid)
                    if rid not in self.seen:
                        self.seen.add(rid)
                        try:self.workflow.start(rid,physical_created=request['created'])
                        except Exception as exc:
                            with self.lock:self.cached['error']='Physical capture: '+str(exc)
                    self.control('ack',id=rid)
                    continue
                with self.workflow.lock:result=self.workflow.result;busy=self.workflow.busy
                if result and not busy and section:section.prewarm(result['job_id'])
                if result and not busy and state.get('job_id')!=result['job_id'] and not state.get('busy'):
                    state=self.ready(result['job_id'])
                if result and not busy and state.get('job_id')==result['job_id'] and not state.get('busy') and not state.get('photo_ready'):
                    self.upload_photo(result['job_id'],state['generation'])
            except Exception as exc:
                with self.workflow.lock:busy=self.workflow.busy
                with self.lock:
                    self.cached.update(pc_online=busy,error='' if busy else str(exc))
    def frame(self,data,job,generation,view,mime='image/png',epoch=None,activate=False):
        if getattr(self,'replay',None) and self.replay.status()['active']:raise ValueError('Video replay owns HDMI')
        if view not in ('pair','points','surface','clay'):raise ValueError('Invalid HDMI view')
        with self.workflow.lock:
            if self.workflow.busy or not self.workflow.result or self.workflow.result['job_id']!=job:raise ValueError('Photo changed')
        headers={'Content-Type':mime,'X-Photo-Id':job,'X-Fast-Generation':generation,'X-Fast-View':view,'X-Frame-SHA256':hashlib.sha256(data).hexdigest()}
        if epoch is not None:headers.update({'X-HDMI-Epoch':str(epoch),'X-HDMI-Activate':'1' if activate else '0'})
        started=time.monotonic()
        with self.frame_lock:
            if self.connection is not None and time.monotonic()-self.connection_last_used>5:
                self.connection.close();self.connection=None
            # Static cache writes are idempotent for (job,generation,view).
            # Retry one lost connection, never a stale-generation/physical-key
            # rejection, and never an interactive frame that may activate a view.
            for attempt in range(2 if epoch is None else 1):
                attempt_started=time.monotonic()
                try:
                    if self.connection is None:
                        self.connection=http.client.HTTPConnection('192.168.137.2',8788,timeout=5)
                        self.connection.connect();self.connection.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                        with self.lock:self.metrics['reconnects']+=1
                    self.connection.request('POST','/fast/frame',data,headers=headers)
                    response=self.connection.getresponse();raw=response.read(8192)
                    if not 200<=response.status<300:raise ValueError(raw.decode(errors='replace')[:180])
                    reply=json.loads(raw);self.connection_last_used=time.monotonic()
                    with self.lock:
                        self.metrics['recent'].append(dict(job_id=job,view=view,attempt=attempt,seconds=self.connection_last_used-attempt_started,bytes=len(data),ok=True))
                        self.metrics['recent']=self.metrics['recent'][-24:]
                    break
                except Exception as exc:
                    if self.connection is not None:self.connection.close()
                    self.connection=None
                    with self.lock:
                        self.metrics['recent'].append(dict(job_id=job,view=view,attempt=attempt,seconds=time.monotonic()-attempt_started,ok=False,error=type(exc).__name__+': '+str(exc)[:180]))
                        self.metrics['recent']=self.metrics['recent'][-24:]
                    retryable=isinstance(exc,(OSError,http.client.RemoteDisconnected,http.client.BadStatusLine))
                    if epoch is not None or attempt or not retryable:raise
        with self.lock:
            self.metrics['frames']+=1;self.metrics['bytes']+=len(data);self.metrics['seconds']+=time.monotonic()-started
            self.metrics['last_ms']=(time.monotonic()-started)*1000
        return reply
