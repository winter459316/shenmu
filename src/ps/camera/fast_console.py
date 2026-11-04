"""Fast-only physical controls and three immutable HDMI result frames.

No matching or MMIO here. The existing HDMI owner retains the DMA lease.
"""
import hashlib,re,threading,time,uuid
import cv2
import numpy as np
from photo_views import PhotoViews,MODES,PACKET_BYTES
from preview_modes import PREVIEW_MODES

VIEWS=('pair','points','surface','clay')
def identity(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value):raise ValueError('Invalid identity')
    return value

class FastConsole:
    def __init__(self,hdmi,clock=time.monotonic,camera=None):
        self.hdmi=hdmi;self.clock=clock;self.lock=threading.RLock()
        self.session=None;self.heartbeat=-1e9;self.pending=None;self.job=None;self.generation=uuid.uuid4().hex
        self.frames={};self.view='preview';self.processing=False;self.waiting=False;self.error='';self.events=0;self.epoch=0;self.stream_frames=0
        self.camera=camera;self.photo=None
    def status(self):
        with self.lock:
            return dict(job_id=self.job,generation=self.generation,view=self.view,frames=list(self.frames),
                display_epoch=self.epoch,stream_frames=self.stream_frames,busy=self.processing,waiting_for_render=self.waiting,error=self.error,
                pc_online=self.clock()-self.heartbeat<5,pending=self.pending,events=self.events,
                photo_ready=self.photo is not None,preview_mode=self.camera.mode if self.camera else 'color',photo_modes=list(MODES),
                mapping={'pl_key2':'Fast capture','ps_key1':'pair -> points -> surface -> clay','pl_key1':'return preview; cycle filters in preview','ps_key2':'frozen photo filters'})
    def key(self,name):
        with self.lock:
            self.events+=1
            if self.processing:return dict(result='ignored_while_processing')
            if name=='pl_key1':
                current=self.camera.mode if self.camera else 'color'
                mode=PREVIEW_MODES[(PREVIEW_MODES.index(current)+1)%len(PREVIEW_MODES)] if self.view=='preview' else 'color'
                self.select_preview(mode);return dict(result='preview',mode=mode)
            if name=='ps_key2':
                if self.photo is None:return dict(result='waiting_for_photo')
                current=self.view[6:] if self.view.startswith('photo_') else None
                mode=MODES[(MODES.index(current)+1)%len(MODES)] if current in MODES else MODES[0]
                self.show_photo(mode);return dict(result='display',view=self.view,job_id=self.job)
            if name=='ps_key1':
                if len(self.frames)!=len(VIEWS):return dict(result='waiting_for_result')
                index=(VIEWS.index(self.view)+1)%len(VIEWS) if self.view in VIEWS else 0
                self.show(VIEWS[index]);return dict(result='display',view=self.view,job_id=self.job)
            if name!='pl_key2':raise ValueError('Unknown key')
            if self.clock()-self.heartbeat>=5:return dict(result='pc_offline')
            # Rendering an already completed photo must not lock the shutter.
            # The next begin() invalidates old frames by job and generation.
            if self.pending:return dict(result='ignored_while_pending')
            self.pending=dict(id=uuid.uuid4().hex,created=self.clock())
            return dict(result='capture_requested',request_id=self.pending['id'])
    def show(self,view):
        self.epoch+=1;self.hdmi.present_external(self.frames[view],self.job,view);self.view=view
    def select_preview(self,mode):
        if mode not in PREVIEW_MODES:raise ValueError('Invalid preview mode')
        if self.camera:self.camera.set_mode(mode)
        self.epoch+=1;self.hdmi.preview();self.view='preview'
    def show_photo(self,mode):
        if self.photo is None:raise ValueError('Frozen photo is not ready')
        pixels=self.photo.frame(mode);self.epoch+=1;self.view='photo_'+mode
        self.hdmi.present_external(pixels,self.job,self.view)
    def receive_photo(self,data,job,generation,digest):
        if len(data)!=PACKET_BYTES or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Photo checksum/size failed')
        with self.lock:
            if self.processing or job!=self.job or generation!=self.generation:raise ValueError('Stale photo')
            self.photo=PhotoViews(data,job)
            return dict(accepted=True,job_id=job,generation=generation,photo_ready=True)
    def control(self,args):
        with self.lock:
            op=args.get('op')
            if op=='poll':
                session=identity(args.get('session'))
                if self.session!=session:self.pending=None;self.session=session
                self.heartbeat=self.clock()
                if self.pending and self.clock()-self.pending['created']>4:self.pending=None
            elif op=='ack':
                if self.pending and self.pending['id']==args.get('id'):self.pending=None
            elif op in ('begin','result'):
                job=identity(args.get('job_id'))
                if op=='result' and self.processing and job!=self.job:raise ValueError('Another photo is processing')
                if op=='begin' and self.processing:raise ValueError('Fast already processing')
                self.epoch+=1;self.job=job;self.generation=uuid.uuid4().hex;self.frames={};self.photo=None;self.error=''
                self.processing=op=='begin';self.waiting=op=='result';self.view='processing' if self.processing else 'waiting'
                self.pending=None;self.hdmi.preview()
            elif op=='publish':
                if args.get('job_id')!=self.job or args.get('generation')!=self.generation:raise ValueError('Stale result')
                if self.processing or set(self.frames)!=set(VIEWS):raise ValueError('Four complete views required')
                self.waiting=False
                if self.view=='waiting':self.show('pair')
            elif op=='error':
                if args.get('job_id')==self.job:self.processing=False;self.waiting=False;self.error=str(args.get('error','Failed'))[:300]
            elif op=='section':
                if args.get('job_id')!=self.job or self.processing or 'surface' not in self.frames:raise ValueError('Three-dimensional display is not ready')
                self.show('surface')
            elif op in ('preview','photo'):
                if self.processing:raise ValueError('Photo computation is active')
                if op=='preview':self.select_preview(args.get('mode','color'))
                else:
                    if args.get('job_id')!=self.job:raise ValueError('Photo changed')
                    self.show_photo(args.get('mode','color'))
            else:raise ValueError('Invalid control')
            return self.status()
    def accept(self,data,job,generation,view,digest,mime='image/png',epoch=None,activate=False):
        if len(data)>4*1024**2 or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Frame checksum/size failed')
        if mime=='application/octet-stream':
            if len(data)==640*360*3:
                image=np.frombuffer(data,np.uint8).reshape(360,640,3)
                pixels=cv2.resize(image,(1280,720),interpolation=cv2.INTER_LINEAR).tobytes()
            elif len(data)==1280*720*3:pixels=data
            else:raise ValueError('640x360 or 1280x720 BGR required')
        elif mime=='image/png':
            import struct
            if data[:8]!=b'\x89PNG\r\n\x1a\n' or len(data)<24 or struct.unpack('>II',data[16:24])!=(1280,720):raise ValueError('1280x720 PNG required')
            image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
            if image is None or image.shape!=(720,1280,3):raise ValueError('Invalid HDMI image')
            pixels=image.tobytes()
        else:raise ValueError('Unsupported frame encoding')
        with self.lock:
            if self.processing or job!=self.job or generation!=self.generation or view not in VIEWS:raise ValueError('Stale HDMI frame')
            if epoch is not None and (epoch!=self.epoch or self.waiting or self.view not in VIEWS[1:]):raise ValueError('Physical display selection changed')
            self.frames[view]=pixels
            if epoch is not None and (activate or self.view==view):
                if self.view!=view:self.epoch+=1
                self.view=view;self.stream_frames+=1
                self.hdmi.present_external(pixels,self.job,view,dynamic=mime=='application/octet-stream')
            return dict(accepted=True,job_id=job,view=view,sha256=digest,display_epoch=self.epoch,active_view=self.view)
