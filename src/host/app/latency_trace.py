"""Observation only: monotonic timestamps, clock bounds, first event per photo."""
from pathlib import Path
import copy,json,math,re,threading,time

WEB_EVENTS={'web_result_seen','viewer_load_started','depth_maps_ready','viewer_ready','web_first_frame','hdmi_prepare_started','hdmi_frames_uploaded'}

class Trace:
    def __init__(self,root):
        self.root=Path(root);self.lock=threading.RLock();self.record=None;self.origin=0;self.offset=0
    def begin(self,job,origin,source,offset,uncertainty_ms):
        assert re.fullmatch('[0-9a-f]{32}',job)
        with self.lock:
            self.origin=origin;self.offset=offset
            self.record=dict(version=1,job_id=job,source=source,started_unix=time.time(),board_clock_bound_ms=uncertainty_ms,
                events={'trigger':0.0},note='Cumulative seconds from physical key detection, or PC receipt of a web request. HDMI ready is framebuffer publish acknowledgement, not monitor photon latency.')
            self.persist()
    def persist(self):
        try:
            folder=self.root/'timings';folder.mkdir(exist_ok=True)
            payload=json.dumps(self.record,indent=2,ensure_ascii=False)
            p=folder/(self.record['job_id']+'.json');tmp=p.with_suffix('.tmp');tmp.write_text(payload,encoding='utf8');tmp.replace(p)
            capture=self.root/'captures'/self.record['job_id']
            if capture.is_dir():
                p=capture/'latency.json';tmp=p.with_suffix('.tmp');tmp.write_text(payload,encoding='utf8');tmp.replace(p)
        except OSError as exc:self.record['persistence_error']=str(exc)
    def snapshot(self):
        with self.lock:return copy.deepcopy(self.record)
    def mark(self,name,stamp=None,job=None,detail=None):
        with self.lock:
            if self.record is None or (job is not None and job!=self.record['job_id']):return
            if name not in self.record['events']:
                self.record['events'][name]=(time.monotonic() if stamp is None else stamp)-self.origin
                if detail:self.record['error']=detail
                self.persist()
    def board_events(self,events):
        with self.lock:
            for name,value in events.items():
                if name in {'api_received','script_entered','checks_done','core_finished','ready'} and isinstance(value,(int,float)) and math.isfinite(value):
                    self.mark('board_'+name,value+self.offset)
    def browser(self,args):
        assert set(args)=={'job_id','client_id','clock_bound_ms','events'}
        assert isinstance(args['client_id'],str) and re.fullmatch('[0-9a-f-]{36}',args['client_id'])
        bound=float(args['clock_bound_ms']);assert math.isfinite(bound) and 0<=bound<=30000
        assert isinstance(args['events'],list) and len(args['events'])<=16
        for event in args['events']:
            assert set(event)=={'name','stamp'} and event['name'] in WEB_EVENTS
            assert isinstance(event['stamp'],(int,float)) and math.isfinite(event['stamp'])
        with self.lock:
            if self.record is None or self.record['job_id']!=args['job_id']:return dict(accepted=False,reason='No trace for this photo')
            client=self.record.get('browser_client')
            if client and client!=args['client_id']:return dict(accepted=False,reason='First viewer already owns measurement')
            if client is None:
                if not any(e['name']=='web_result_seen' for e in args['events']):return dict(accepted=False,reason='Waiting for first result load')
                self.record['browser_client']=args['client_id'];self.record['browser_clock_bound_ms']=bound
            now=time.monotonic()
            for event in args['events']:
                assert self.origin-2<=event['stamp']<=now+bound/1000+1,'Timestamp outside capture'
                self.mark(event['name'],event['stamp'])
            return dict(accepted=True)
