"""One explicit live photo cancelled during PL SGM; no automatic recovery shutter."""
import json,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'live_host.json').read_text());op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def req(path,body=None):
    headers={'Content-Type':'application/json','Origin':cfg['origin'],'X-Viewer-Token':cfg['token']}
    with op.open(urllib.request.Request(cfg['origin']+path,None if body is None else json.dumps(body).encode(),headers=headers),timeout=10) as r:return json.load(r)
before=req('/api/status');assert not before['busy'] and not before['section_busy']
job=req('/api/capture',{})['job_id'];deadline=time.monotonic()+20;phase=None
while time.monotonic()<deadline:
    s=req('/api/status');assert s['job_id']==job
    if s['stage'].startswith('pl_sgm_'):phase=s['stage'];break
    if not s['busy']:raise AssertionError(s)
    time.sleep(.15)
start=time.monotonic();req('/api/cancel',{})
for _ in range(60):
    s=req('/api/status');assert s['job_id']==job
    if not s['busy']:break
    time.sleep(.2)
assert phase and not s['busy'] and s['stage']=='cancelled' and not s['result'] and not s['error'],s
with op.open('http://192.168.137.2:8767/stereo/status',timeout=5) as r:b=json.load(r)
assert not b['busy'] and b['result_id'] is None and b['stage']=='cancelled' and not b['error'],b
try:op.open('http://192.168.137.2:8767/stereo/result.npz?id='+job,timeout=5)
except urllib.error.HTTPError as e:assert e.code==409
else:raise AssertionError('Cancelled result was served')
report={'passed':True,'job_id':job,'cancel_stage':phase,'drain_seconds':time.monotonic()-start,'no_partial_result_published':True,
        'next_photo_recovery_pending':True}
(ROOT/'board_evidence/live_cancel_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
