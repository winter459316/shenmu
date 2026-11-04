"""Restart this RAM candidate after exact native tests; preserve current held photo."""
import hashlib,http.client,json,os,shutil
from pathlib import Path
from switch_320_board import owners,request
from switch_direct3d_board import stop,start_services
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb320_rectpreview'
s=request(8788,'/stereo/status');assert not s['busy'] and not s['section_busy']
current=owners();assert set(current)=={'full_camera.py','physical_keys.py'}
assert all(Path(v['cwd']).resolve()==ROOT.resolve() for v in current.values())
proof=json.loads((ROOT/'preview_native_verified.json').read_text());assert proof['passed']
assert proof['native_sha256']==hashlib.sha256((ROOT/'preview_native.so').read_bytes()).hexdigest()
assert json.loads((ROOT/'shared_preview_verified.json').read_text())['passed']
job=s['result_id'];assert job
c=http.client.HTTPConnection('192.168.137.2',8788,timeout=30,source_address=('127.0.0.1',0))
try:
    c.request('GET','/stereo/result.npz?id='+job);r=c.getresponse();assert r.status==200;data=r.read()
finally:c.close()
digest=hashlib.sha256(data).hexdigest();assert digest==s['metadata']['package_sha256']
held={'job_id':job,'sha256':digest,'bytes':len(data),'total_seconds':s['metadata']['total_seconds']}
(ROOT/'held_restore.npz').write_bytes(data);(ROOT/'held_restore.json').write_text(json.dumps(held))
mode=request(8788,'/status')['mode'];saved={'owners':current,'held':held}
p=ROOT/'refresh_private_snapshot.json';fd=os.open(str(p),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:json.dump(saved,f)
s2=request(8788,'/stereo/status');assert not s2['busy'] and not s2['section_busy'] and s2['result_id']==job
try:
    stop(current);report=start_services(ROOT,8788,saved,True)
    request(8788,'/preview/mode',{'mode':mode});request(8788,'/standby',{'enabled':s['standby']})
    report.update(held=held,mode=mode,native_preview=True)
    (ROOT/'shared_activation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
except Exception:
    stop(owners())
    shutil.copyfile(ROOT/'held_restore.npz',OLD/'held_restore.npz');shutil.copyfile(ROOT/'held_restore.json',OLD/'held_restore.json')
    start_services(OLD,8788,saved,True);request(8788,'/preview/mode',{'mode':mode});request(8788,'/standby',{'enabled':s['standby']})
    raise
