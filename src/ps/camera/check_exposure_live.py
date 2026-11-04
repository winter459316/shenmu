"""One finite live acceptance run. No photo/shutter, no numerical recomputation."""
import hashlib,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path,body=None,raw=False):
    request=urllib.request.Request('http://192.168.137.2:8788'+path,
        None if body is None else json.dumps(body).encode(),headers={} if body is None else {'Content-Type':'application/json'})
    with opener.open(request,timeout=15) as r:data=r.read()
    return data if raw else json.loads(data)
held=call('/stereo/status');assert not held['busy'] and not held['section_busy']
record=json.loads((ROOT/'held_restore.json').read_text())
assert held['result_id']==record['job_id']
assert hashlib.sha256(call('/stereo/result.npz?id='+record['job_id'],raw=True)).hexdigest()==record['sha256']
before=call('/status');began=time.monotonic();time.sleep(6);after=call('/status');elapsed=time.monotonic()-began
assert not after['error'] and after['auto_exposure']['mode']=='camera_auto'
fps=(after['sequence']-before['sequence'])/elapsed
preview=(after['jpeg_frames']-before['jpeg_frames'])/elapsed
old_mode=after['mode']
try:
    call('/preview/mode',{'mode':'rectified'});time.sleep(.5)
    rect_before=call('/status');began=time.monotonic();time.sleep(4);rect_after=call('/status');dt=time.monotonic()-began
    rect_fps=(rect_after['jpeg_frames']-rect_before['jpeg_frames'])/dt
    call('/standby',{'enabled':True});time.sleep(1)
    assert call('/status')['standby']
finally:
    call('/standby',{'enabled':False})
deadline=time.monotonic()+8
while True:
    resumed=call('/status')
    if not resumed['error'] and resumed['auto_exposure']['mode']=='camera_auto' and resumed['auto_exposure']['samples']>=2:break
    if time.monotonic()>deadline:raise RuntimeError('Exposure did not recover after standby')
    time.sleep(.25)
call('/preview/mode',{'mode':old_mode})
assert call('/stereo/status')['result_id']==held['result_id']
hdmi=call('/hdmi/status');assert not hdmi['error'] and hdmi['frames']>0
evidence={'passed':True,'color_capture_fps':fps,'color_preview_fps':preview,'rectified_preview_fps':rect_fps,
          'held_photo_sha256_unchanged':True,'shutter_triggered':False,'standby_resume':True,
          'hdmi':hdmi,'camera':resumed,'measurement_camera':after}
(ROOT/'exposure_live_verified.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps({k:v for k,v in evidence.items() if k not in ('camera','measurement_camera','hdmi')}))
