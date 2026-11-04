"""Native USB pipeline: PL rectification/Census/SGM/CG/XYZ, PS validity/guidance.

No CPU matcher is imported. Reference results are never inputs to compute().
"""
import hashlib,json,time
from pathlib import Path
import cv2
import numpy as np
from board_dma import Arena,BASE,TAG
from board_geometry import project,view
from board_completion import complete,CompletionCancelled
from hardware_catalog import loaded_variant
ROOT=Path(__file__).resolve().parent
W,H,D=320,360,128;N=W*H
CALIBRATION_SHA256='6dbbd7ca2aa6f013e4f4f0861a18f7cd2d00f2434dc2e5d53185caae2d81128d'
BIT_SHA256='8183863c879beb5bec68fc1e6a42e8b20df0a8ba4149af0e35871e9a0d0d854d'
MAP_CONTENT_SHA256='a4d933cbd6d001ce84cec73775358464689d46f95146a4fd9be05400472b2779'
BACKEND='ZU4EV PL eight-path SGM + PL completion vectors + PL XYZ; A53 control/filter/guidance'
PROFILES=(('detail',80,480),('surface',160,720))

def validity(q,score,margin,rq,rscore,rmargin,left_support,right_support):
    """Confidence + calibrated support + <=1 pixel reverse consistency."""
    y,x=np.indices(q.shape);xr0=np.rint(x-q/16).astype(np.int32);xr=xr0.clip(0,W-1)
    confidence=margin>=np.maximum(24,score.astype(np.float64)*.03)
    reverse_confidence=rmargin>=np.maximum(24,rscore.astype(np.float64)*.03)
    valid=(q>=16)&(q<127*16)&(xr0>=3)&(xr0<W-3)&left_support&right_support[y,xr]&confidence&reverse_confidence[y,xr]
    valid&=(rq[y,xr]>=16)&(abs(q.astype(np.int32)-rq[y,xr])<=16)
    return valid

class FullEngine:
    def __init__(self):
        raw=(ROOT/'stereo_parameters.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==CALIBRATION_SHA256,'Calibration changed; rebuild bound cores/maps'
        config=json.loads(raw);assert config['eye_size']==[W,H] and config['units']=='mm'
        self.p={k:np.array(config[k],np.float64) for k in ('Q','P1','P2','K1','D1','K2','D2','R1','R2','T')}
        self.maps=[];self.support=[]
        with np.load(ROOT/'rectification_maps.npz',allow_pickle=False) as z:
            assert z['calibration_sha256'].tobytes().decode()==CALIBRATION_SHA256
            for eye in (0,1):
                m=z['map%d'%eye].copy();assert m.dtype==np.uint64 and m.shape==(H,W)
                self.maps.append(m);self.support.append(((m>>42)&1).astype(bool))
        assert hashlib.sha256(b''.join(m.tobytes() for m in self.maps)).hexdigest()==MAP_CONTENT_SHA256,'Rectification map content mismatch'
        self.maps_sha256=hashlib.sha256((ROOT/'rectification_maps.npz').read_bytes()).hexdigest()
    def compute(self,frame,progress=None,cancel=None):
        if frame.dtype!=np.uint8 or frame.shape!=(480,1280,3):raise ValueError('Expected native USB capture')
        native_digest=hashlib.sha256(frame.tobytes()).hexdigest()
        frame=np.concatenate([cv2.resize(frame[:,eye*640:(eye+1)*640],(W,H),interpolation=cv2.INTER_AREA) for eye in (0,1)],axis=1)
        def stage(name,details=None):
            if cancel and cancel():raise CompletionCancelled('Photo cancelled')
            if progress:progress(name,details or {})
        loaded=json.loads((ROOT/'loaded.json').read_text())
        hardware=loaded_variant(loaded)
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
        start=time.monotonic();cpu=time.process_time();times={};out={'frame_bgr':frame.copy(),'Q':self.p['Q'],'P1':self.p['P1'],'P2':self.p['P2']}
        a=Arena(True)
        def call(core,params,label):
            stage(label);rc,elapsed=a.command(core,params)
            if rc!=1:raise RuntimeError('%s rejected arguments (%s)'%(label,rc))
            times[label]=elapsed
        try:
            for core,identity in (('images',0x55494632),('sgm',0x55534738),('geometry',0x55474532),('completion',0x43475032)):
                got,_=a.command(core,{0x20:0},timeout=2);assert got==identity,(core,got)
            for core in ('images','geometry'):
                got,_=a.command(core,{0x20:3},timeout=2);assert got==TAG
            got,_=a.command('completion',{0x20:4},timeout=2);assert got==W,'Completion row width differs from the image grid'
            if hardware['sgm_revision'] is not None:
                revision,_=a.command('sgm',{0x20:3},timeout=2)
                if revision!=hardware['sgm_revision']:raise RuntimeError('SGM hardware revision mismatch')
            for eye,name in ((0,'left'),(1,'right')):
                stage('upload_'+name)
                raw=view(a,19*N+eye*N//4,N*4,np.uint8).reshape(H,W,4)
                raw[:,:,:3]=frame[:,eye*W:(eye+1)*W];raw[:,:,3]=0;del raw
                view(a,19*N+N//2+eye*N//2,N,np.uint64)[:]=self.maps[eye].ravel()
                params={0x18:BASE,0x20:1,0x28:W,0x30:H,0x38:eye,0x40:TAG}
                call('images',params,'pl_rectify_'+name)
                out['rectified_'+name]=view(a,20*N+N//2+eye*N//4,N*4,np.uint8).reshape(H,W,4)[:,:,:3].copy()
                params[0x20]=2;call('images',params,'pl_features_'+name)
                out['features_'+name]=view(a,eye*N//2,N,np.uint64).reshape(H,W).copy()
            for profile,p1,p2 in PROFILES:
                for mirrored,prefix in ((0,profile),(1,profile+'_right')):
                    params={0x18:BASE,0x20:1,0x28:W,0x30:H,0x38:mirrored,0x40:p1,0x48:p2}
                    call('sgm',params,'pl_sgm_'+prefix+'_forward');params[0x20]=2
                    call('sgm',params,'pl_sgm_'+prefix+'_backward')
                    packed=view(a,(18 if mirrored else 17)*N,N*8,np.uint16).reshape(H,W,8).copy()
                    if mirrored:packed=packed[:,::-1].copy()
                    out[prefix+'_q4']=packed[:,:,0].copy().view(np.int16)
                    out[prefix+'_score']=packed[:,:,1].copy();out[prefix+'_margin']=packed[:,:,2].copy()
                out[profile+'_valid']=validity(out[profile+'_q4'],out[profile+'_score'],out[profile+'_margin'],
                        out[profile+'_right_q4'],out[profile+'_right_score'],out[profile+'_right_margin'],*self.support)
            stage('validity_and_fusion');t=time.monotonic()
            d,s=out['detail_valid'],out['surface_valid']
            conflict=d&s&(abs(out['detail_q4'].astype(np.int32)-out['surface_q4'].astype(np.int32))>16)
            source=np.zeros((H,W),np.uint8);source[d&~conflict]=1;source[~d&s]=2
            q=np.full((H,W),-32768,np.int16);q[source==1]=out['detail_q4'][source==1];q[source==2]=out['surface_q4'][source==2]
            before_speckles=int((source>0).sum());cv2.filterSpeckles(q,-32768,20,16);source[q==-32768]=0
            valid=source>0
            out.update(disparity_q4=q,valid=valid,match_source=source,domain=self.support[0].copy(),profile_conflict=conflict)
            times['validity_fusion']=time.monotonic()-t
            stage('pl_raw_geometry');raw_records,t=project(a,q,source);times['pl_raw_geometry']=t
            out['raw_xyz_q12']=raw_records[:,:,:3].copy();out['raw_geometry_flags']=raw_records[:,:,3].copy()
            stage('completion');completed,origin,completion=complete(out['rectified_left'],q,valid,self.support[0],a,True,stage,cancel)
            out['completed_disparity_q4']=completed;out['completion_origin']=origin
            completed_source=np.where(origin==0,source,np.where(origin==3,0,3)).astype(np.uint8)
            stage('pl_completed_geometry');records,t=project(a,completed,completed_source);times['pl_completed_geometry']=t
            out['completed_xyz_q12']=records[:,:,:3].copy();out['completed_geometry_flags']=records[:,:,3].copy()
            out['depth_mm']=raw_records[:,:,2].astype(np.float32)/4096;out['depth_mm'][~valid]=np.nan
            stage('geometry_ready')
            metadata={'schema':'usb_full_v2','backend':BACKEND,'eye_size':[W,H],'disparity_scale':16,'depth_units':'mm','xyz_scale':4096,
                      'calibration_sha256':CALIBRATION_SHA256,'maps_sha256':self.maps_sha256,'bitstream_sha256':loaded['sha256'],
                      'hardware_variant':hardware['name'],'sgm_revision':hardware['sgm_revision'],
                      'native_frame_sha256_bgr':native_digest,'native_capture_size':[1280,480],'resampling':'INTER_AREA before PL rectification','frame_sha256_bgr':hashlib.sha256(frame.tobytes()).hexdigest(),'profiles':[{'name':n,'p1':p,'p2':q} for n,p,q in PROFILES],
                      'valid_pixels':int(valid.sum()),'valid_fraction':float(valid.mean()),'profile_conflict_pixels':int(conflict.sum()),
                      'speckles_removed':before_speckles-int(valid.sum()),'completed_inside_domain_pixels':int((completed_source>0).sum()),
                      'accepted_measured_pixels':int((origin==0).sum()),'completion':completion,'stage_seconds':times,
                      'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,
                      'source_codes':{'0':'invalid','1':'PL detail match','2':'PL surface match','3':'inferred completion'},
                      'completion_origin_codes':{'0':'accepted match','1':'local plane','2':'guided','3':'outside domain','4':'rejected candidate, guided replacement'},
                      'left_right_tolerance_px':1.0,'confidence_min_margin':24,'confidence_score_ratio':.03,'inter_profile_tolerance_px':1.0,
                      'measurement_policy':'Raw maps remain separate; display completion is explicitly inferred.'}
            return out,metadata
        finally:a.close()
