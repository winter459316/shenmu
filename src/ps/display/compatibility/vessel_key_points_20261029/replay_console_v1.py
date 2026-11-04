"""Lease-based video priority on the existing HDMI owner, with stale-frame rejection."""
import hashlib,time,uuid
import numpy as np
from fast_console import FastConsole,identity,VIEWS

class ReplayConsole(FastConsole):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.replay=None
    def end_replay(self,restore=True):
        if self.replay is None:return
        self.replay=None;self.epoch+=1
        if restore:
            if self.view in self.frames and not self.processing:self.show(self.view)
            elif self.view.startswith('photo_') and self.photo is not None:self.show_photo(self.view[6:])
            else:self.hdmi.preview()
    def expire(self):
        if self.replay and self.clock()>self.replay['until']:self.end_replay()
    def status(self):
        with self.lock:
            self.expire();s=super().status();s['hdmi_addon']='hold_replay_v1'
            s['replay']=None if self.replay is None else {k:v for k,v in self.replay.items() if k!='until'}
            if self.replay:s['view']='replay'
            return s
    def show(self,view):
        if self.replay:self.view=view;return
        super().show(view)
    def key(self,name):
        with self.lock:
            self.expire()
            if self.replay:
                if name=='pl_key2':self.end_replay()
                else:return dict(result='video_replay_priority')
            return super().key(name)
    def control(self,args):
        with self.lock:
            self.expire();op=args.get('op')
            if op=='replay_begin':
                assert not self.processing,'Fast is processing'
                owner=identity(args['owner']);self.epoch+=1
                self.replay=dict(owner=owner,generation=uuid.uuid4().hex,sequence=-1,frame_sha256=None,until=self.clock()+4)
                return self.status()
            if op in ('replay_heartbeat','replay_end'):
                if not self.replay:
                    if op=='replay_end':return self.status()
                    raise ValueError('Replay lease ended')
                assert args.get('owner')==self.replay['owner'] and args.get('generation')==self.replay['generation'],'Stale replay control'
                if op=='replay_end':self.end_replay()
                else:self.replay['until']=self.clock()+4
                return self.status()
            if op in ('begin','preview','photo','section'):self.end_replay(False)
            return super().control(args)
    def accept(self,data,job,generation,view,digest,mime='image/png',epoch=None,activate=False):
        with self.lock:
            self.expire()
            if view!='replay':
                if self.replay:raise ValueError('Video replay owns HDMI')
                return super().accept(data,job,generation,view,digest,mime,epoch,activate)
            assert self.replay and not self.processing,'Video replay is inactive'
            assert job==self.replay['owner'] and generation==self.replay['generation'],'Stale replay frame'
            assert type(epoch) is int and epoch>self.replay['sequence'],'Out-of-order replay frame'
            assert mime=='application/octet-stream' and len(data)==1280*480*3 and hashlib.sha256(data).hexdigest()==digest,'Invalid stereo replay pixels'
            canvas=np.zeros((720,1280,3),np.uint8);canvas[120:600]=np.frombuffer(data,np.uint8).reshape(480,1280,3)
            pixels=canvas.tobytes();self.hdmi.present_external(pixels,job,'replay',dynamic=True)
            self.replay.update(sequence=epoch,frame_sha256=hashlib.sha256(pixels).hexdigest(),until=self.clock()+4)
            return dict(accepted=True,sequence=epoch,display_epoch=self.epoch,active_view='replay',frame_sha256=self.replay['frame_sha256'])
