"""Finite held-photo section and standby checks; never triggers a shutter."""
from pathlib import Path
import json,urllib.request,urllib.error,time
from live_verify import verify_section,np
ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'live_host.json').read_text());op=urllib.request.build_opener(urllib.request.ProxyHandler({}));origin=cfg['origin']
def req(path,body=None,auth=True):
    headers={'Content-Type':'application/json','Origin':origin}
    if auth:headers['X-Viewer-Token']=cfg['token']
    r=urllib.request.Request(origin+path,None if body is None else json.dumps(body).encode(),headers=headers)
    with op.open(r,timeout=30) as f:return json.load(f)
s=req('/api/status');assert not s['busy'] and s['stage']=='ready';job=s['job_id']
with np.load(ROOT/'live_captures'/job/'board_result.npz') as z:a={k:z[k] for k in ('completed_xyz_q12','completed_geometry_flags')}
checks=[]
for axis,center,thickness,include in ((0,0,10,False),(1,0,10,True),(2,700,20,True)):
    section_args={'revision':job,'axis':axis,'center_mm':center,'thickness_mm':thickness,'include_inferred':include}
    r=req('/api/section',section_args);verify_section(r,a,job,section_args)
    checks.append({k:r[k] for k in ('axis','count','measured','inferred','board_ms','csv_url')})
for path,body,auth,expected in (('/api/section',dict(section_args,revision='0'*32),True,409),('/api/capture',{},False,403)):
    try:req(path,body,auth)
    except urllib.error.HTTPError as e:assert e.code==expected
    else:raise AssertionError('Rejected operation unexpectedly accepted')
try:
    req('/api/standby',{'enabled':True})
    for _ in range(12):
        camera=req('/api/camera')
        if camera['standby'] and camera['error']=='Standby':break
        time.sleep(.2)
    assert camera['standby'] and camera['error']=='Standby'
finally:req('/api/standby',{'enabled':False})
for _ in range(20):
    camera=req('/api/camera')
    if not camera['standby'] and not camera['error'] and camera['age_seconds']<3:break
    time.sleep(.2)
assert not camera['standby'] and not camera['error'] and camera['age_seconds']<3
r=req('/api/section',section_args);verify_section(r,a,job,section_args)
report={'passed':True,'job_id':job,'sections':checks,'stale_photo_rejected':True,'unauthorized_capture_rejected':True,
        'standby_resume_fresh_preview':True,'held_section_after_resume_verified':True}
(ROOT/'board_evidence/live_lifecycle_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
