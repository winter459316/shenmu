"""One finite fixed-frame hardware A/B, with exclusive DMA ownership and rollback.

This never captures, stops a service, initializes PS, or writes boot storage.
Both images keep the same AXI interfaces. Live capture is placed in standby;
the DMA flock is held across reconfiguration, all tests, and stable rollback.
"""
import base64,hashlib,http.client,json,mmap,os,platform,struct,sys,time,traceback
from pathlib import Path
import numpy as np
from board_dma import Arena,BASE,TAG,reservation
from board_geometry import view
ROOT=Path(__file__).resolve().parent
STABLE='8183863c879beb5bec68fc1e6a42e8b20df0a8ba4149af0e35871e9a0d0d854d'
CANDIDATE='1b357aa3fe695f5f77239e8aedb85b4bb51accd4d3ab33867951d69750e99db1'
CANDIDATE_FILE='sgm_window_v4.bit.bin'
HDMI_TEST=False
SOURCE='7b2937f1b76895516c79b4047406474c146214aeb3d16033d16ef3cc515cbabd'
W,H=640,480;N=W*H
def request(path,body=None,raw=False):
    c=http.client.HTTPConnection('192.168.137.2',8767,timeout=30,source_address=('127.0.0.1',0))
    try:
        c.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),
                  {} if body is None else {'Content-Type':'application/json'})
        response=c.getresponse();data=response.read();assert response.status in (200,202),(path,response.status,data[:200])
        return data if raw else json.loads(data)
    finally:c.close()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    full='--full-pipeline' in sys.argv
    prefix='hdmi_full' if HDMI_TEST else ('sgm_v4_full' if full else 'sgm_v4')
    assert platform.machine()=='aarch64';reservation()
    assert not list(Path('/sys/bus/platform/devices').glob('a0*/driver'))
    assert sha(ROOT/'usb_full.bit.bin')==STABLE and sha(ROOT/CANDIDATE_FILE)==CANDIDATE
    assert sha(ROOT/'full_pipeline_result.npz')==SOURCE
    with np.load(ROOT/'full_pipeline_result.npz',allow_pickle=False) as z:expected={k:z[k] for k in z.files}
    source_meta=json.loads(expected['metadata_json'].tobytes());assert source_meta['frame_sha256_bgr'].startswith('1c69fd2a')
    with np.load(ROOT/'rectification_maps.npz',allow_pickle=False) as z:maps=[z['map0'].copy(),z['map1'].copy()]
    before=request('/stereo/status');camera_before=request('/status')
    assert not before['busy'] and not before['section_busy'] and before['result_id']==before['job_id']
    held_job=before['result_id'];held_sha=before['metadata']['package_sha256']
    original_loaded=(ROOT/'loaded.json').read_bytes();assert json.loads(original_loaded)['sha256']==STABLE
    assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
    firmware_path=Path('/sys/module/firmware_class/parameters/path');previous_firmware_path=firmware_path.read_text()
    clock=Path('/sys/kernel/debug/clk/clk_summary').read_text()
    row=next(s.split() for s in clock.splitlines() if s.split() and s.split()[0]=='pl0_ref')
    rate=int(row[4]);assert 99000000<=rate<=100000000
    report={'passed':False,'source_sha256':SOURCE,'frame_sha256_bgr':source_meta['frame_sha256_bgr'],
            'stable_sha256':STABLE,'candidate_sha256':CANDIDATE,'clock_hz':rate,'shutter_triggered':False,
            'held_job':held_job,'held_sha256':held_sha,'tests':{},'stable_restored':False}
    report['full_pipeline']=full
    a=None;changed=False;guard_saved=None;failure=None;candidate_arrays={};display=None
    guard=0x08000000-4096 if HDMI_TEST else 26*N*16
    def idle():
        # This process owns ap_ctrl while holding the exclusive DMA flock.
        deadline=time.monotonic()+60
        while True:
            states={k:a.read(k,0) for k in a.controls}
            if all(v&4 for v in states.values()):return
            if time.monotonic()>deadline:raise RuntimeError('Outstanding DMA; leave standby and do not reset: '+str(states))
            time.sleep(.01)
    def identities(window=None):
        for core,value in (('sgm',0x55534738),('images',0x55494632),('geometry',0x55474532),('completion',0x43475032)):
            got,_=a.command(core,{0x20:0},2);assert got==value,(core,hex(got))
        for core in ('images','geometry'):
            got,_=a.command(core,{0x20:3},2);assert got==TAG
        if window:
            got,_=a.command('sgm',{0x20:3},2);assert got==window,hex(got)
    def load(filename,digest):
        idle();firmware_path.write_text(str(ROOT));Path('/sys/class/fpga_manager/fpga0/flags').write_text('0')
        t=time.monotonic();Path('/sys/class/fpga_manager/fpga0/firmware').write_text(filename)
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
        metadata=json.loads(original_loaded);metadata.update(sha256=digest,load_seconds=time.monotonic()-t,temporary_hardware_test=True)
        (ROOT/'loaded.json').write_text(json.dumps(metadata));identities(0x53574E34 if digest==CANDIDATE else None)
    def pipeline(label):
        times={};actual={};checks={};started=time.monotonic()
        def exact(name,got):
            assert np.array_equal(got,expected[name]),name+' differs'
            checks[name]=True;actual[name]=got
        def call(core,params,name):
            rc,t=a.command(core,params);assert rc==1,(name,rc);times[name]=t
            print(label,name,round(t,5),flush=True)
        for eye,name in ((0,'left'),(1,'right')):
            raw=view(a,19*N+eye*N//4,N*4,np.uint8).reshape(H,W,4)
            raw[:,:,:3]=expected['frame_bgr'][:,eye*W:(eye+1)*W];raw[:,:,3]=0;del raw
            view(a,19*N+N//2+eye*N//2,N,np.uint64)[:]=maps[eye].ravel()
            params={0x18:BASE,0x20:1,0x28:W,0x30:H,0x38:eye,0x40:TAG}
            call('images',params,'rectify_'+name)
            exact('rectified_'+name,view(a,20*N+N//2+eye*N//4,N*4,np.uint8).reshape(H,W,4)[:,:,:3].copy())
            params[0x20]=2;call('images',params,'features_'+name)
            exact('features_'+name,view(a,eye*N//2,N,np.uint64).reshape(H,W).copy())
        for profile,p1,p2 in (('detail',80,480),('surface',160,720)):
            for mirror,prefix in ((0,profile),(1,profile+'_right')):
                params={0x18:BASE,0x20:1,0x28:W,0x30:H,0x38:mirror,0x40:p1,0x48:p2}
                call('sgm',params,prefix+'_forward');params[0x20]=2;call('sgm',params,prefix+'_backward')
                packed=view(a,(18 if mirror else 17)*N,N*8,np.uint16).reshape(H,W,8).copy()
                if mirror:packed=packed[:,::-1].copy()
                exact(prefix+'_q4',packed[:,:,0].copy().view(np.int16))
                exact(prefix+'_score',packed[:,:,1].copy());exact(prefix+'_margin',packed[:,:,2].copy())
        assert a.memory[guard:guard+4096]==guard_pattern,'DMA guard changed'
        return actual,{'all_arrays_exact':checks,'times':times,'wall_seconds':time.monotonic()-started,
                       'sgm_command_seconds':sum(t for n,t in times.items() if n.endswith(('_forward','_backward'))),'dma_guard_unchanged':True}
    try:
        request('/standby',{'enabled':True})
        quiet=request('/stereo/status');assert quiet['standby'] and not quiet['busy'] and not quiet['section_busy'] and quiet['job_id']==held_job
        a=Arena(True);idle();identities()
        guard_saved=a.memory[guard:guard+4096];guard_pattern=bytes((i*17+33)%256 for i in range(4096));a.memory[guard:guard+4096]=guard_pattern
        if not full:_,report['tests']['stable']=pipeline('stable')
        changed=True;load(CANDIDATE_FILE,CANDIDATE)
        if HDMI_TEST:
            from hdmi_output import Scanout,FRAME_BYTES
            import cv2
            display=Scanout()
            picture=np.zeros((720,1280,3),np.uint8)
            picture[120:600]=expected['frame_bgr']
            cv2.putText(picture,'USB STEREO - HDMI HARDWARE TEST',(24,42),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
            for x,color in enumerate(((0,0,255),(0,255,0),(255,0,0),(255,255,255))):picture[630:700,x*320:(x+1)*320]=color
            frame=picture.tobytes();display.present(frame);display.present(frame)
            assert display.memory[:FRAME_BYTES]==frame and display.memory[FRAME_BYTES:]==frame
            print('HDMI_TEST_VISIBLE',flush=True)
        if full:
            import usb_full_engine_v4_candidate as candidate_engine
            # The transaction owns the real Arena; compute may borrow it but
            # must not release the global lock before verified rollback.
            class BorrowedArena:
                def __getattr__(self,name):return getattr(a,name)
                def close(self):pass
            candidate_engine.Arena=lambda controls:BorrowedArena()
            def progress(stage,details=None):print('full',stage,flush=True)
            output,metadata=candidate_engine.FullEngine().compute(expected['frame_bgr'],progress)
            assert metadata['bitstream_sha256']==CANDIDATE and metadata['sgm_revision']==0x53574E34
            keys=set(expected)-{'metadata_json'};assert set(output)==keys
            # The board's older NumPy lacks equal_nan. Compare the complete
            # representation, including NaNs, without relaxing exactness.
            checks={k:(output[k].shape==expected[k].shape and output[k].dtype==expected[k].dtype
                       and output[k].tobytes()==expected[k].tobytes()) for k in keys}
            assert all(checks.values()),[k for k,v in checks.items() if not v]
            os.environ['USB_SURFACE_NATIVE']='1'
            from board_surface import prepare
            surface,surface_report=prepare(output,progress)
            with np.load(ROOT/'surface_result.npz',allow_pickle=False) as z:old_surface={k:z[k] for k in z.files if k!='metadata_json'}
            assert set(surface)==set(old_surface)
            surface_checks={k:(surface[k].shape==old_surface[k].shape and surface[k].dtype==old_surface[k].dtype
                              and surface[k].tobytes()==old_surface[k].tobytes()) for k in surface}
            assert all(surface_checks.values()),[k for k,v in surface_checks.items() if not v]
            candidate_arrays=dict(output,**{'display_'+k:v for k,v in surface.items()})
            report['tests']['candidate']={'primary_exact':checks,'surface_byte_exact':surface_checks,
                'metadata':metadata,'surface_preparation':surface_report,
                'engine_source_sha256':sha(ROOT/'usb_full_engine_v4_candidate.py')}
            assert a.memory[guard:guard+4096]==guard_pattern
            if display is not None:
                report['hdmi']=display.status()
                assert not report['hdmi']['vdma_status']&0xff1
        else:candidate_arrays,report['tests']['candidate']=pipeline('candidate')
    except Exception:
        failure=traceback.format_exc();print(failure,flush=True)
    finally:
        try:
            if display is not None:
                display.close();display=None;report['hdmi_drained']=True
            if a is not None:
                if changed:load('usb_full.bit.bin',STABLE)
                identities();idle()
                if guard_saved is not None:a.memory[guard:guard+4096]=guard_saved
                (ROOT/'loaded.json').write_bytes(original_loaded)
                report['stable_restored']=True
        except Exception:
            report['rollback_error']=traceback.format_exc();failure=(failure or '')+report['rollback_error']
        finally:
            firmware_path.write_text(previous_firmware_path)
            if a is not None:a.close()
        if report['stable_restored']:
            now=request('/stereo/status')
            if now['job_id']==held_job and now['metadata']['package_sha256']==held_sha:
                request('/standby',{'enabled':before['standby']})
            else:failure=(failure or '')+'Held photo changed during test; do not automatically resume.'
    report['held_photo_unchanged']=hashlib.sha256(request('/stereo/result.npz?id='+held_job,raw=True)).hexdigest()==held_sha
    assert report['held_photo_unchanged']
    report['previous_standby_restored']=request('/stereo/status')['standby']==before['standby']
    if not before['standby'] and report['stable_restored']:
        deadline=time.monotonic()+8
        while True:
            camera=request('/status')
            if not camera['error'] and camera['age_seconds']<3 and camera['sequence']>camera_before['sequence']:break
            assert time.monotonic()<deadline,camera
            time.sleep(.1)
        report['fresh_preview_restored']=True
    if failure:report['error']=failure
    else:
        report['passed']=True
        if not full:report['sgm_speedup']=report['tests']['stable']['sgm_command_seconds']/report['tests']['candidate']['sgm_command_seconds']
        np.savez_compressed(ROOT/(prefix+'_result.npz'),**candidate_arrays)
    (ROOT/(prefix+'_verified.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    if failure:raise RuntimeError(failure)
if __name__=='__main__':main()
