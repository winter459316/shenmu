"""Idle RAM-only display extension; original files, bitstreams and model remain intact."""
from pathlib import Path
import fcntl,hashlib,json,os,signal,subprocess,sys,time
H=Path(__file__).resolve().parent;R=H.parent/'fast_infer2';S=H.parent/'usb320_hdmifps'
sys.path[:0]=[str(S),str(R),str(H.parent/'fast_board/deps')]
import test_hardware_board as h
from switch_320_board import owners,request
from switch_direct3d_board import stop,start_services

def process(name):
    found=[]
    for p in Path('/proc').glob('[0-9]*'):
        try:
            if (str(R/name).encode() in (p/'cmdline').read_bytes().split(b'\0')):
                st=(p/'stat').read_text().split(') ',1)[1].split()
                if st[0]!='Z':found.append((int(p.name),st[19]))
        except (FileNotFoundError,ProcessLookupError):pass
    assert len(found)<=1
    return found
def terminate(item):
    pid,start=item;p=Path('/proc')/str(pid)
    assert (p/'stat').read_text().split(') ',1)[1].split()[19]==start
    os.kill(pid,signal.SIGTERM)
    for _ in range(120):
        try:
            if (p/'stat').read_text().split(') ',1)[1].split()[0]=='Z':return
        except (FileNotFoundError,ProcessLookupError):return
        time.sleep(.1)
    raise TimeoutError('Idle service did not exit; no forced termination')
def launch(name,env):
    with (R/(name+'.log')).open('ab',buffering=0) as log:
        return subprocess.Popen(['python3','-u',str(R/name)],cwd=str(R),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
def main():
    manifest=json.loads((H/'hdmi_addon_manifest_v4.json').read_text())
    for name,digest in manifest.items():
        raw=(H/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        target=R/name
        if target.exists():assert target.read_bytes()==raw
        else:target.write_bytes(raw)
    addon=R/'hdmi_addon_v4';addon.mkdir(exist_ok=True)
    target=addon/'sitecustomize.py';raw=(H/'hdmi_sitecustomize_v4.py').read_bytes()
    if target.exists():assert target.read_bytes()==raw
    else:target.write_bytes(raw)
    with (R.parent/'fast_pl/capture.lock').open('a+') as legacy,(R/'capture.lock').open('a+') as capture,(R/'resident_switch.lock').open('a+') as switch:
        for f in (legacy,capture,switch):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not h.SNAP.exists()
        for d in (R,S,R.parent/'fast_pl'):assert not list(d.glob('*.fault'))
        assert json.loads((S/'loaded.json').read_text())['sha256']==h.OLD_SHA
        worker=json.loads((R/'worker_status.json').read_text());assert worker['state']=='ready'
        previous=process('infer_worker_pl3_v5_quad.py');assert previous and previous[0][0]==worker['pid']
        runtime=request(8788,'/stereo/status');assert not runtime['busy'] and not runtime['section_busy'] and not runtime['standby']
        for name in ('video_job_server_v1.py','video_job_server_v2.py','hdmi_job_server_v1.py','hdmi_job_server_v2.py','hdmi_job_server_v3.py','hdmi_job_server_v4.py'):
            for item in process(name):terminate(item)
        saved=h.prepare()
        keyfile=S/'physical_keys.py';keyblob=(H/'physical_keys_overlap_v1.py').read_bytes()
        assert hashlib.sha256(keyfile.read_bytes()).hexdigest() in ('30b12bff46ca6bc7ddc9f7bc889e9efee9e2e36cec11ad0393639e9e597dab0f','8ce20c90abbe6b17cb81d7e30346c2dc50a75637d05e0344aab8fbabebc7b4af')
        if not (H/'physical_keys_before_overlap.py').exists():(H/'physical_keys_before_overlap.py').write_bytes(keyfile.read_bytes())
        keyfile.write_bytes(keyblob)
        startup=S/'startup_payload_sha256.json';hashes=json.loads(startup.read_text());hashes['physical_keys.py']=hashlib.sha256(keyblob).hexdigest();startup.write_text(json.dumps(hashes,indent=2))
        for item in previous:terminate(item)
        before_env=saved['owners']['full_camera.py']['env'].copy()
        env=before_env.copy();env['ZU4EV_HDMI_ADDON']='hold_replay_v4';env['PYTHONPATH']=str(addon)+(':'+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        saved['owners']['full_camera.py']['env']=env
        try:
            stop(owners());h.restore_services(saved)
            assert request(8788,'/fast/status')['hdmi_addon']=='hold_replay_v1'
            assert 'vessel' in request(8788,'/fast/status')['photo_modes']
            model=launch('infer_worker_pl3_v5_quad.py',env)
            for _ in range(120):
                state=json.loads((R/'worker_status.json').read_text())
                if state['pid']==model.pid and state['state']=='ready':break
                assert model.poll() is None,'HDMI model worker exited'
                time.sleep(.1)
            else:raise TimeoutError('HDMI model worker did not load')
            api=launch('hdmi_job_server_v4.py',env)
            time.sleep(.3);assert api.poll() is None
            h.SNAP.replace(R/('hdmi_install_completed_%d.json'%int(time.time())))
            result=dict(passed=True,worker_pid=model.pid,api_pid=api.pid,camera_pid=owners()['full_camera.py']['pid'],version='video_stereo_v5_display',bits_unchanged=True)
            (H/'hdmi_install_verified_v4.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
        except BaseException:
            # No inference was dispatched. Retain the install snapshot for inspection.
            raise
if __name__=='__main__':main()
