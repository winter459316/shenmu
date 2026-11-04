"""Finite active-service timing and identity checks, without taking a photo."""
import hashlib,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path,body=None,raw=False):
    req=urllib.request.Request('http://192.168.137.2:8788'+path,
        None if body is None else json.dumps(body).encode(),headers={} if body is None else {'Content-Type':'application/json'})
    with opener.open(req,timeout=20) as r:data=r.read()
    return data if raw else json.loads(data)
before=call('/stereo/status');assert not before['busy'] and not before['section_busy']
job=before['result_id'];assert job==json.loads((ROOT/'before_status.json').read_text())['result_id']
payload=call('/stereo/result.npz?id='+job,raw=True)
sha=hashlib.sha256(payload).hexdigest();assert sha==before['metadata']['package_sha256']
(ROOT/'held_restore.npz').write_bytes(payload)
held={'job_id':job,'sha256':sha,'bytes':len(payload)}
if 'total_seconds' in before['metadata']:held['total_seconds']=before['metadata']['total_seconds']
(ROOT/'held_restore.json').write_text(json.dumps(held,indent=2))
current=call('/status');old_mode=current['mode'];assert current['tone_map']['enabled']
rows=[]
try:
    for mode in ('color','rectified'):
        call('/preview/mode',{'mode':mode});time.sleep(.3)
        a=call('/status');ha=call('/hdmi/status');start=time.monotonic()
        time.sleep(5)
        b=call('/status');hb=call('/hdmi/status');elapsed=time.monotonic()-start
        assert not b['error'] and not b['preview_error'] and not hb['error']
        assert b['tone_map']['enabled'] and b['auto_exposure']['mode']=='camera_auto'
        count=b['preview_count']-a['preview_count']
        rows.append({'mode':mode,'capture_fps':(b['sequence']-a['sequence'])/elapsed,
                     'preview_fps':(b['jpeg_frames']-a['jpeg_frames'])/elapsed,
                     'hdmi_unique_fps':(hb['preview_unique_frames']-ha['preview_unique_frames'])/elapsed,
                     'tone_ms':(b['preview_total_ms']['tone_ms']-a['preview_total_ms']['tone_ms'])/count})
finally:call('/preview/mode',{'mode':old_mode})
assert call('/stereo/status')['result_id']==job
report={'passed':True,'timing':rows,'held_sha256':sha,'shutter_triggered':False,
        'tone_map':call('/status')['tone_map']}
(ROOT/'tone_live_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
