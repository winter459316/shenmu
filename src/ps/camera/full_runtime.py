"""Exclusive single-photo lifecycle, held identity and PL sections for USB v2."""
import base64,hashlib,io,json,platform,threading,time,uuid,os
from pathlib import Path
import numpy as np
from usb_full_engine import FullEngine,BACKEND,CALIBRATION_SHA256
from board_completion import CompletionCancelled
from board_geometry import section
from board_dma import Arena,require_legacy_compute
from result_archive import pack_result
from dense_fill import fill
from dense_geometry import generate
from board_plane import apply as correct_plane

class FullRuntime:
    def __init__(self):
        self.engine=FullEngine();self.lock=threading.Lock();self.cancel_event=threading.Event()
        self.busy=False;self.stage='idle';self.details={};self.error='';self.job_id=None
        self.result_id=None;self.package=None;self.metadata=None;self.held=None;self.standby=False
        self.section_busy=False;self.started=0;self.worker=None
    def status(self):
        with self.lock:
            return {'busy':self.busy,'stage':self.stage,'details':self.details,'error':self.error,'job_id':self.job_id,
                    'result_id':self.result_id,'metadata':self.metadata,'backend':BACKEND,'schema':'usb_full_v2',
                    'machine':platform.machine(),'calibration_sha256':CALIBRATION_SHA256,'standby':self.standby,
                    'section_busy':self.section_busy,'elapsed_seconds':time.monotonic()-self.started if self.busy else None}
    def start(self,frame,sequence,age):
        require_legacy_compute()
        with self.lock:
            if self.busy or self.section_busy or self.standby:return False,self.job_id
            self.busy=True;self.stage='queued';self.details={};self.error='';self.started=time.monotonic()
            self.job_id=uuid.uuid4().hex;self.cancel_event.clear()
            # Never serve the previous photo under a new request or result id.
            self.result_id=None;self.package=None;self.metadata=None;self.held=None
            job=self.job_id
            self.worker=threading.Thread(target=self._work,args=(frame.copy(),sequence,age,job),daemon=False)
            self.worker.start();return True,job
    def progress(self,stage,details=None):
        with self.lock:self.stage=stage;self.details=details or {}
    def _work(self,frame,sequence,age,job):
        began=time.monotonic()
        try:
            arrays,metadata=self.engine.compute(frame,self.progress,self.cancel_event.is_set)
            metadata['surface_preparation']={'comparison_surfaces_removed':True,'seconds':0.0}
            self.progress('dense_fill')
            dense,fill_report=fill(arrays,cancel=self.cancel_event.is_set,progress=self.progress)
            arrays.update(dense_disparity_px=dense['filled_disparity_px'],dense_depth_mm=dense['filled_depth_mm'],dense_origin=dense['fill_origin'],dense_distance_px=dense['distance_to_measurement_px'])
            metadata['dense_fill']=fill_report
            self.progress('plane_correction')
            metadata['plane_correction']=correct_plane(arrays,self.cancel_event.is_set)
            self.progress('dense_geometry')
            dense_geometry,geometry_report=generate(arrays,self.cancel_event.is_set)
            arrays.update(dense_geometry);metadata['dense_geometry']=geometry_report
            arrays['dense_depth_mm']=arrays['dense3d_xyz_q12'][:,:,2].astype(np.float32)/4096
            if self.cancel_event.is_set():raise CompletionCancelled('Photo cancelled')
            metadata.update(job_id=job,camera_sequence=sequence,source_age_seconds=age,backend=BACKEND,
                            machine=platform.machine(),captured_unix=time.time()-(time.monotonic()-began)-age,
                            processing_seconds=time.monotonic()-began)
            metadata['archive_compression']=('ZIP stored; lossless array bytes' if os.environ.get('USB_ARCHIVE_STORED','0')=='1' else 'ZIP deflate level 1; lossless array bytes')
            self.progress('packing_result');package=pack_result(arrays,metadata)
            records=np.concatenate((arrays['completed_xyz_q12'],arrays['completed_geometry_flags'][:,:,None]),axis=2).astype(np.int32)
            digest=hashlib.sha256(package).hexdigest()
            with self.lock:
                if self.cancel_event.is_set():raise CompletionCancelled('Photo cancelled before publication')
                self.held=records;self.metadata=dict(metadata,package_sha256=digest,package_bytes=len(package),total_seconds=time.monotonic()-began)
                self.package=package;self.result_id=job;self.stage='ready';self.details={};self.busy=False
        except (CompletionCancelled,InterruptedError):
            with self.lock:self.stage='standby' if self.standby else 'cancelled';self.details={};self.busy=False
        except Exception as exc:
            with self.lock:self.stage='error';self.error=str(exc);self.details={};self.busy=False
    def cancel(self):
        with self.lock:
            self.cancel_event.set()
            return {'cancel_requested':self.busy,'quiescent':not self.busy and not self.section_busy}
    def set_standby(self,value):
        with self.lock:
            if not isinstance(value,bool):raise ValueError('standby must be boolean')
            if not value and (self.busy or self.section_busy):raise ValueError('Wait for in-flight work to drain before resume')
            self.standby=value
            if value:self.cancel_event.set()
            if not self.busy:self.stage='standby' if value else ('ready' if self.result_id else 'idle')
    def result(self,job):
        with self.lock:
            if self.busy or not self.package or job!=self.result_id:return None
            return self.package
    def compute_section(self,request):
        require_legacy_compute()
        if set(request)!={'job_id','axis','center_mm','thickness_mm','include_inferred'}:raise ValueError('Invalid section request fields')
        job=request['job_id'];axis=request['axis'];include=request['include_inferred']
        if type(axis) is not int or type(include) is not bool:raise ValueError('Invalid section types')
        with self.lock:
            if self.busy or self.section_busy or self.standby:raise ValueError('Board is busy or in standby')
            if not self.result_id or job!=self.result_id:raise ValueError('Held photo identity mismatch')
            self.section_busy=True;records=self.held
        try:
            a=Arena(True)
            try:r=section(a,records,axis,float(request['center_mm']),float(request['thickness_mm']),include)
            finally:a.close()
            stats=r.pop('stats');source=r.pop('source')
            encode=lambda x:base64.b64encode(np.ascontiguousarray(x).tobytes()).decode()
            return {'status':'PASS','job_id':job,'axis':axis,'center_q12':r['center_q12'],'half_width_q12':r['half_width_q12'],
                    'include_inferred':include,'count':int(stats[0,1]),'measured':int(stats[0,2]),'inferred':int(stats[0,1]-stats[0,2]),
                    'bounds_mm':[float(stats[row,k])/4096 for k in range(3) for row in (1,2)] if stats[0,1] else None,
                    'indices':encode(r['indices'].astype('<u4')),'xyz_q12':encode(r['xyz_q12'].astype('<i4')),
                    'origins':encode((source==3).astype(np.uint8)),'source':encode(source),'board_ms':r['board_seconds']*1000,
                    'calibration_sha256':CALIBRATION_SHA256,'geometry_engine':'PL usb_geometry command 2'}
        finally:
            with self.lock:self.section_busy=False
