"""Volatile plane-photo update with exact held-photo rollback, unchanged PL/API."""
import hashlib,http.client,json,os,shutil,sys
from pathlib import Path
from switch_320_board import owners,request
from switch_direct3d_board import stop,start_services
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb320_plane'
SNAP=ROOT/'mesh_private_snapshot.json'
BIT='1040bc3c95d76794e479d8d039f21cbfebc3086e838c507afe81a4e971c6d0b4'
def prepare():
    assert not SNAP.exists()
    state=request(8788,'/stereo/status');assert not state['busy'] and not state['section_busy']
    current=owners();assert set(current)=={'full_camera.py','physical_keys.py'}
    assert all(Path(v['cwd']).resolve()==OLD.resolve() for v in current.values())
    loaded=(OLD/'loaded.json').read_bytes();assert json.loads(loaded)['sha256']==BIT
    for name in ('usb_full_engine.py','board_completion.py','dense_fill.py','full_camera.py','physical_keys.py','shared_preview.py','preview_native.so','stereo_parameters.json','rectification_maps.npz'):
        assert (ROOT/name).read_bytes()==(OLD/name).read_bytes(),name
    job=state['result_id'];assert job and job==state['job_id']
    c=http.client.HTTPConnection('192.168.137.2',8788,timeout=30,source_address=('127.0.0.1',0))
    try:
        c.request('GET','/stereo/result.npz?id='+job);r=c.getresponse();assert r.status==200;data=r.read()
    finally:c.close()
    digest=hashlib.sha256(data).hexdigest();assert digest==state['metadata']['package_sha256']
    assert request(8788,'/stereo/status')['result_id']==job
    (ROOT/'baseline_photo.npz').write_bytes(data)
    held={'job_id':job,'sha256':digest,'bytes':len(data),'total_seconds':state['metadata']['total_seconds']}
    saved={'owners':current,'loaded':loaded.decode(),'held':held,'standby':state['standby'],'mode':request(8788,'/status')['mode']}
    fd=os.open(str(SNAP),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(saved,f)
    (ROOT/'baseline_public.json').write_text(json.dumps({'held':held,'standby':state['standby'],'mode':saved['mode']},indent=2))
    print(json.dumps({'prepared':True,'held':held}),flush=True)
def restore_files(directory,saved):
    (directory/'loaded.json').write_text(saved['loaded'])
    assert hashlib.sha256((ROOT/'baseline_photo.npz').read_bytes()).hexdigest()==saved['held']['sha256']
    shutil.copyfile(ROOT/'baseline_photo.npz',directory/'held_restore.npz')
    (directory/'held_restore.json').write_text(json.dumps(saved['held']))
def rollback():
    saved=json.loads(SNAP.read_text());current=owners()
    assert all(Path(v['cwd']).resolve() in (ROOT.resolve(),OLD.resolve()) for v in current.values())
    if current:
        state=request(8788,'/stereo/status');assert not state['busy'] and not state['section_busy']
    stop(current);restore_files(OLD,saved);report=start_services(OLD,8788,saved,True)
    request(8788,'/preview/mode',{'mode':saved['mode']});request(8788,'/standby',{'enabled':saved['standby']})
    print('ROLLED_BACK',json.dumps(report),flush=True)
def activate():
    saved=json.loads(SNAP.read_text());assert owners()==saved['owners']
    state=request(8788,'/stereo/status');assert not state['busy'] and not state['section_busy']
    assert state['result_id']==saved['held']['job_id']
    proof=json.loads((ROOT/'mesh_replay_verified.json').read_text());assert proof['passed'] and proof['cancel_passed']
    restore_files(ROOT,saved)
    candidate=json.loads((ROOT/'candidate_held.json').read_text())
    shutil.copyfile(ROOT/'candidate_photo.npz',ROOT/'held_restore.npz')
    (ROOT/'held_restore.json').write_text(json.dumps(candidate))
    active=dict(saved,held=candidate)
    try:
        stop(saved['owners']);report=start_services(ROOT,8788,active,True)
        request(8788,'/preview/mode',{'mode':saved['mode']});request(8788,'/standby',{'enabled':saved['standby']})
        report.update(held=active['held'],original_held=saved['held'],mesh_limits_enabled=True)
        (ROOT/'mesh_activation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    except Exception:
        rollback();raise
if __name__=='__main__':
    assert sys.argv[1] in ('prepare','activate','rollback');globals()[sys.argv[1]]()
