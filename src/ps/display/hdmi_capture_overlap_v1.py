"""One new camera frame -> PL rectification -> Fast PS+PL; restore preview."""
import time
SCRIPT_ENTERED=time.monotonic()
from pathlib import Path
from hold_client_overlap_v1 import prepare as prepare_hold, start as start_hold, finish as finish_hold
import fcntl,hashlib,http.client,json,mmap,re,shutil,subprocess,sys,time,traceback
R=Path(__file__).resolve().parent;S=R.parent/'usb320_hdmifps'
sys.path.insert(0,str(S))
import test_hardware_board as h
import pause_preview_board as preview
from resume_overlap_v1 import resume as resume_overlap

def state(folder,stage,**extra):
    p=folder/'status.json';data=json.loads(p.read_text()) if p.exists() else {}
    now=time.monotonic()
    if data.get('stage')!=stage:
        times=data.setdefault('stage_seconds',{})
        if 'stage_began' in data:times[data['stage']]=times.get(data['stage'],0)+now-data['stage_began']
        data['stage_began']=now
    data.update(job_id=folder.name,stage=stage,updated=time.time(),**extra)
    temp=folder/'status.tmp';temp.write_text(json.dumps(data,indent=2));temp.replace(p)

def rectify(folder):
    stamp=time.monotonic();parts={};optimized=json.loads((R/'transport_config.json').read_text())['enabled']
    import cv2,numpy as np
    from usb_full_engine import FullEngine,W,H,N,CALIBRATION_SHA256
    from board_dma import Arena,BASE,TAG
    from board_geometry import view
    parts['imports']=time.monotonic()-stamp;stamp=time.monotonic()
    native=cv2.imread(str(folder/'input.png'));assert native.shape==(480,1280,3)
    engine=FullEngine()
    frame=np.concatenate([cv2.resize(native[:,eye*640:(eye+1)*640],(W,H),interpolation=cv2.INTER_AREA) for eye in (0,1)],axis=1)
    a=Arena(False);out={'Q':engine.p['Q'],'P1':engine.p['P1'],'P2':engine.p['P2'],'native_bgr':native,'domain':engine.support[0]}
    parts['setup']=time.monotonic()-stamp;elapsed=[];input_seconds=0;output_seconds=0
    try:
        a.controls['images']=mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0xA1020000)
        identity,_=a.command('images',{0x20:3},2);assert identity==TAG
        for eye,name in ((0,'left'),(1,'right')):
            stamp=time.monotonic()
            raw=view(a,19*N+eye*N//4,N*4,np.uint8).reshape(H,W,4)
            if optimized:
                # Pack on cached RAM; one contiguous transfer into uncached DDR.
                packed=np.zeros((H,W,4),np.uint8);packed[:,:,:3]=frame[:,eye*W:(eye+1)*W]
                raw[:]=packed
            else:raw[:,:,:3]=frame[:,eye*W:(eye+1)*W];raw[:,:,3]=0
            del raw
            view(a,19*N+N//2+eye*N//2,N,np.uint64)[:]=engine.maps[eye].ravel()
            input_seconds+=time.monotonic()-stamp
            rc,dt=a.command('images',{0x18:BASE,0x20:1,0x28:W,0x30:H,0x38:eye,0x40:TAG},10)
            assert rc==1
            stamp=time.monotonic()
            rgba=view(a,20*N+N//2+eye*N//4,N*4,np.uint8).reshape(H,W,4)
            if optimized:rgba=rgba.copy() # contiguous DDR read before BGR extraction
            out['rectified_'+name]=rgba[:,:,:3].copy();del rgba
            output_seconds+=time.monotonic()-stamp;elapsed.append(dt)
    finally:a.close()
    parts.update(input_copy=input_seconds,output_copy=output_seconds,pl=sum(elapsed));stamp=time.monotonic()
    # Check calibrated preview and PL images agree exactly, before any inference.
    from preview_rectify import PreviewRectifier
    expected=PreviewRectifier().rectified_grid(frame)
    assert np.array_equal(expected,np.concatenate([out['rectified_left'],out['rectified_right']],1)),'Rectification parity failed'
    parts['parity']=time.monotonic()-stamp;stamp=time.monotonic()
    out['calibration_sha256']=np.array(CALIBRATION_SHA256)
    out['maps_sha256']=np.array(engine.maps_sha256)
    np.savez(str(folder/'rectified.npz'),**out)
    parts['archive']=time.monotonic()-stamp
    return dict(transport_optimized=optimized,breakdown_seconds=parts,pl_rectification_seconds=sum(elapsed),rectification_parity=True,native_sha256=hashlib.sha256(native.tobytes()).hexdigest())

def resident_rectify(job):
    import socket
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(45);connection.connect(str(R/'infer.sock'))
        connection.sendall((json.dumps({'job_id':job,'action':'rectify'})+'\n').encode())
        with connection.makefile('rb') as f:reply=json.loads(f.readline(8192))
    assert reply['ok'] and reply['job_id']==job and reply['action']=='rectify',reply
    return reply['rectification']

def resident_geometry(job):
    import socket
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(15);connection.connect(str(R/'infer.sock'))
        connection.sendall((json.dumps({'job_id':job,'action':'geometry'})+'\n').encode())
        with connection.makefile('rb') as f:reply=json.loads(f.readline(8192))
    assert reply['ok'] and reply['job_id']==job and reply['action']=='geometry',reply

def compare_replay(source,folder):
    import numpy as np
    with np.load(str(source/'result.npz'),allow_pickle=False) as old,np.load(str(folder/'result.npz'),allow_pickle=False) as now:
        exact={n:bool(old[n].dtype==now[n].dtype and old[n].shape==now[n].shape and old[n].tobytes()==now[n].tobytes()) for n in old.files if n!='metadata_json'}
    state(folder,'geometry',same_photo_exact=exact,quality_passed=all(exact.values()),quality_scope='All input, calibration, disparity, validity, depth and XYZ array bytes equal')
    assert all(exact.values()),exact


def main(job,replay=None,video_input=False):
    assert re.fullmatch('[0-9a-f]{32}',job)
    assert replay is None or re.fullmatch('[0-9a-f]{32}',replay)
    folder=R/'jobs'/job;folder.mkdir(parents=True,exist_ok=True)
    with (R.parent/'fast_pl/capture.lock').open('a+') as legacy_lock, (R/'capture.lock').open('a+') as lock:
        fcntl.flock(legacy_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        proof=json.loads((R/'hardware_verified.json').read_text())
        assert all(proof[k] for k in ('timing_passed','cdc_review_passed','hls_passed'))
        assert h.sha(R/'fast_pl.bit.bin')==proof['sha256']
        for name in ('fast_pl.onnx','libfast_pl.so'):assert h.sha(R/name)==proof['sources'][name]
        state(folder,'capture',busy=True,error='',started=time.time())
        saved=None;stopped=False;new=False;success=False;failure='';live=None;start=time.monotonic()
        try:
            assert shutil.disk_usage(R).free>=64*1024**2,'Temporary filesystem needs at least 64MiB free; preview remains running'
            meminfo=dict((line.split(':')[0],int(line.split()[1])) for line in Path('/proc/meminfo').read_text().splitlines() if line.split(':')[0] in ('MemAvailable','CmaFree'))
            assert meminfo['MemAvailable']-meminfo.get('CmaFree',0)>=280*1024,'Insufficient non-CMA available RAM; preview remains running'
            saved=preview.prepare()
            import os
            proc=(Path('/proc')/str(os.getpid())/'stat').read_text().split(') ',1)[1].split()
            saved['pl3_runtime_owner']=dict(pid=os.getpid(),start=proc[19],job_id=job)
            preview.journal(saved)
            assert not saved['standby'],'Resume the camera before Fast capture'
            if video_input:
                (folder/'video_input.png').replace(folder/'input.png')
                png=(folder/'input.png').read_bytes()
                state(folder,'capture',video_frame_input=True)
            elif replay:
                source=R/'replay_sources'/replay
                if not (source/'result.npz').is_file():source=R.parent/'fast_mixed/replay_sources'/replay
                if not (source/'result.npz').is_file():source=R.parent/'fast_fused/jobs'/replay
                if not (source/'result.npz').is_file():source=R.parent/'fast_conv/jobs'/replay
                if not (source/'result.npz').is_file():source=R.parent/'fast_pipeline/jobs'/replay
                if not (source/'result.npz').is_file():source=R.parent/'fast_lite/jobs'/replay
                if not (source/'result.npz').is_file():source=R.parent/'fast_pl/jobs'/replay
                assert (source/'result.npz').is_file()
                png=(source/'input.png').read_bytes()
                state(folder,'capture',source_job_id=replay,replay_only=True)
            else:
                c=http.client.HTTPConnection('192.168.137.2',8788,timeout=15,source_address=('127.0.0.1',0))
                try:
                    c.request('GET','/snapshot.png');response=c.getresponse();assert response.status==200
                    png=response.read(8*1024*1024);assert len(png)>1000
                finally:c.close()
            (folder/'input.png').write_bytes(png)
            live=prepare_hold(job)
            assert h.owners()==saved['owners']
            check=h.request(8788,'/stereo/status');assert not check['busy'] and not check['section_busy'] and check['result_id']==saved['held']['job_id']
            state(folder,'pause_preview');stopped=True;preview.pause(saved)
            suspended=json.loads(saved['loaded']);suspended.update(state='suspended',active_project='fast_capture')
            (S/'loaded.json').write_text(json.dumps(suspended))
            state(folder,'load_pl');h.reconfigure(True,saved);new=True
            (R/'loaded.json').write_text(json.dumps(dict(state='operating',sha256=proof['sha256'])))
            start_hold(job,live)
            state(folder,'rectification')
            optimized=json.loads((R/'transport_config.json').read_text())['enabled']
            details=resident_rectify(job) if optimized else rectify(folder)
            # Processing progress remains available in the PC page.
            state(folder,'fast_inference',rectification=details)
            with (folder/'infer.log').open('wb') as log:
                subprocess.run(['python3','-u',str(R/'fast_infer_board.py'),job],cwd=str(R),stdout=log,stderr=log,timeout=650,check=True)
            success=True
        except BaseException as exc:
            failure=repr(exc);traceback.print_exc()
        finally:
            restore_parts={};restore_stamp=time.monotonic()
            state(folder,'restore_preview')
            try:
                if live is not None:
                    try:finish_hold(job,live)
                    except BaseException as exc:
                        success=False;failure+='; static HDMI: '+repr(exc)
                        with preview.MMIO() as io:assert io.read(io.dma,4)&1,'Static HDMI DMA is not halted'
                    state(folder,'restore_preview',processing_preview=json.loads((folder/'hdmi_hold.json').read_text()) if (folder/'hdmi_hold.json').exists() else {})
                restore_parts['static_hdmi_stop']=time.monotonic()-restore_stamp;restore_stamp=time.monotonic()
                active=R/'configuration_state.json'
                assert not (R/'dma.fault').exists() and not (R.parent/'fast_pl/dma.fault').exists(),'DMA fault: keep frozen for inspection'
                if new or (active.exists() and json.loads(active.read_text())['new']):h.reconfigure(False,saved)
                restore_parts['bit_restore']=time.monotonic()-restore_stamp;restore_stamp=time.monotonic()
                (R/'loaded.json').write_text(json.dumps({'state':'inactive','stable_restored_sha256':h.OLD_SHA}))
                if success:
                    state(folder,'geometry')
                    try:
                        resident_geometry(job)
                        if replay:compare_replay(source,folder)
                    except BaseException as exc:
                        success=False;failure+='; geometry: '+repr(exc);traceback.print_exc()
                restore_parts['geometry']=time.monotonic()-restore_stamp;restore_stamp=time.monotonic()
                state(folder,'restore_preview')
                assert not (R/'dma.fault').exists() and not (R/'geometry.dma.fault').exists(),'Geometry fault: keep camera frozen and snapshot intact'
                if stopped:
                    resume_report=resume_overlap(saved)
                    restore_parts['resume_detail']=resume_report.get('resume_breakdown_seconds',{})
                restore_parts['camera_keys_resume']=time.monotonic()-restore_stamp
                if saved and h.SNAP.exists():h.SNAP.replace(R/'pl_test_private_completed.json')
                # Validate the asynchronous display AFTER safely restoring the
                # original PL/camera/keys, including failed-render cases.
                if success and optimized and live is not None:
                    p=folder/'hdmi_hold.json'
                    shown=json.loads(p.read_text()) if p.exists() else {}
                    if not(shown.get('frames',0)>0 and not shown.get('error') and shown.get('vdma_drained') and not shown.get('running')):
                        success=False;failure+='; static HDMI presentation failed: '+repr(shown)
            except BaseException as exc:
                success=False;failure+='; restore: '+repr(exc);traceback.print_exc()
            core_finished=time.monotonic()
            info={'restore_breakdown_seconds':restore_parts,'busy':False,'error':failure,'total_seconds':time.monotonic()-start,'stable_restored':bool(stopped and not h.SNAP.exists())}
            if success:
                result=folder/'result.npz';info.update(package_sha256=h.sha(result),package_bytes=result.stat().st_size,
                                                     inference=json.loads((folder/'inference.json').read_text()))
            timing_file=folder/'request_timing.json'
            timing=json.loads(timing_file.read_text()) if timing_file.exists() else {}
            timing.update(script_entered=SCRIPT_ENTERED,checks_done=start,core_finished=core_finished,ready=time.monotonic())
            info['trace_monotonic']=timing
            state(folder,'ready' if success else 'failed',**info)
        if not success:raise RuntimeError(failure)

if __name__=='__main__':
    assert len(sys.argv) in (2,3)
    if len(sys.argv)==3:assert sys.argv[2]=='--video-input'
    main(sys.argv[1],video_input=len(sys.argv)==3)
