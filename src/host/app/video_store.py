"""Timestamped stereo JPEG recording. Replay pixels and reconstruction use the same frame."""
from pathlib import Path
import http.client, json, re, shutil, threading, time, uuid
from functools import lru_cache

class VideoStore:
    def __init__(self, root):
        self.root=Path(root);self.root.mkdir(exist_ok=True)
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None
        self.recording=False;self.error='';self.frames=0;self.started=0;self.current=None
        self.last=None
        p=self.root/'latest.json'
        if p.exists():self.last=json.loads(p.read_text(encoding='utf8'))
    def status(self):
        with self.lock:
            return dict(recording=self.recording,error=self.error,frames=self.frames,
                        elapsed_seconds=max(0,time.monotonic()-self.started) if self.recording else 0,
                        last=self.last)
    def start(self):
        with self.lock:
            assert not self.recording and not (self.thread and self.thread.is_alive()),'正在录制或保存，请先结束'
            assert shutil.disk_usage(self.root).free>512*1024**2,'电脑磁盘空间不足 512 MB'
            self.current=uuid.uuid4().hex;folder=self.root/self.current;folder.mkdir()
            self.error='';self.frames=0;self.started=time.monotonic();self.stop_event.clear();self.recording=True
            self.thread=threading.Thread(target=self._record,args=(folder,),daemon=True);self.thread.start()
            return self.status()
    def stop(self):
        self.stop_event.set()
        thread=self.thread
        if thread:thread.join(8)
        assert not (thread and thread.is_alive()),'视频仍在保存，请稍候再试'
        return self.status()
    def _record(self,folder):
        c=http.client.HTTPConnection('192.168.137.2',8788,timeout=3)
        timestamps=[];identities=[];cursor='';first=None;error=''
        try:
            while not self.stop_event.is_set():
                if shutil.disk_usage(self.root).free<256*1024**2:raise RuntimeError('磁盘剩余空间不足，录制已结束')
                c.request('GET','/preview.jpg'+('?after='+cursor if cursor else ''))
                r=c.getresponse();n=int(r.getheader('Content-Length','-1'))
                assert r.status==200 and 0<n<=4*1024**2,'相机视频暂不可用'
                raw=r.read(n);assert len(raw)==n and raw[:2]==b'\xff\xd8'
                assert r.getheader('X-Frame-Mode')=='color','录制期间画面已切换，已保存此前彩色视频'
                seq=r.getheader('X-Frame-Sequence');epoch=r.getheader('X-Frame-Epoch')
                assert seq is not None and epoch is not None,'相机未返回帧编号'
                key=seq+','+epoch
                if key==cursor:
                    self.stop_event.wait(.003);continue
                assert not cursor or cursor.split(',')[1]==epoch,'相机已重新启动，录制已结束'
                now=time.monotonic();first=now if first is None else first
                (folder/('%08d.jpg'%len(timestamps))).write_bytes(raw)
                timestamps.append(round(now-first,6));identities.append(key);cursor=key
                with self.lock:self.frames=len(timestamps)
        except Exception as exc:error=str(exc)
        finally:
            c.close()
            with self.lock:
                if timestamps:
                    duration=timestamps[-1]+(max(.001,timestamps[-1]-timestamps[-2]) if len(timestamps)>1 else 1/30)
                    manifest=dict(id=folder.name,frames=len(timestamps),timestamps=timestamps,identities=identities,
                                  duration=duration,width=1280,height=480,mode='color',created=time.time(),error=error)
                    (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
                    summary={k:v for k,v in manifest.items() if k not in ('timestamps','identities')}
                    temp=self.root/'latest.tmp';temp.write_text(json.dumps(summary),encoding='utf8');temp.replace(self.root/'latest.json')
                    self.last=summary
                self.error=error;self.recording=False
    @lru_cache(maxsize=8)
    def manifest(self,identity):
        assert isinstance(identity,str) and re.fullmatch('[0-9a-f]{32}',identity),'视频编号无效'
        return json.loads((self.root/identity/'manifest.json').read_text(encoding='utf8'))
    def frame(self,identity,index):
        manifest=self.manifest(identity)
        assert type(index) is int and 0<=index<manifest['frames'],'视频帧编号无效'
        return (self.root/identity/('%08d.jpg'%index)).read_bytes(),manifest
