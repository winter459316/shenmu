"""Display held original disparity; preserve every byte of geometry and photo data."""
import hashlib,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path,body=None,raw=False):
    req=urllib.request.Request('http://192.168.137.2:8788'+path,None if body is None else json.dumps(body).encode(),headers={} if body is None else {'Content-Type':'application/json'})
    with opener.open(req,timeout=30) as r:data=r.read()
    return data if raw else json.loads(data)
s=call('/stereo/status');assert not s['busy'] and not s['section_busy']
job=s['result_id'];payload=call('/stereo/result.npz?id='+job,raw=True)
sha=hashlib.sha256(payload).hexdigest();assert sha==s['metadata']['package_sha256']
report=call('/hdmi/raw',{'job_id':job})
deadline=time.monotonic()+5
while time.monotonic()<deadline:
    h=call('/hdmi/status')
    if h['source']=='raw_disparity' and h['raw_job']==job:break
    time.sleep(.1)
else:raise AssertionError('Raw HDMI did not become active')
assert not h['error'] and not h['raw_error']
assert call('/stereo/status')['result_id']==job
assert hashlib.sha256(call('/stereo/result.npz?id='+job,raw=True)).hexdigest()==sha
(ROOT/'held_restore.npz').write_bytes(payload)
held={'job_id':job,'sha256':sha,'bytes':len(payload)}
if 'total_seconds' in s['metadata']:held['total_seconds']=s['metadata']['total_seconds']
(ROOT/'held_restore.json').write_text(json.dumps(held,indent=2))
result={'passed':True,'held':held,'raw_display':report,'hdmi':h,'all_package_bytes_unchanged':True,'shutter_triggered':False}
(ROOT/'rawhdmi_live_verified.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
