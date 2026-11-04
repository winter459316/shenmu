"""Read-only publication/preview checks; never presses the shutter."""
from pathlib import Path
import json,urllib.request
R=Path(__file__).resolve().parent
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path,root='http://127.0.0.1:8849'):
    with op.open(root+path,timeout=10) as f:
        assert f.status==200
        return f.read()
status=json.loads(get('/api/status'))
assert not status['busy'] and not status['error'] and status['result']['iterations']==2
assert status['result']['stable_restored']
assert '2 次迭代'.encode() in get('/')
assert '2 / 4 / 8'.encode() in get('/comparison.html')
assert get('/preview.jpg').startswith(b'\xff\xd8')
data=json.loads(get('/comparison_data.json'));checked=[]
for c in data['cases']:
    for folder,job in [('captures',c['job_id']),('baseline_captures',c['baseline4_job_id']),('baseline_captures',c['baseline8_job_id'])]:
        base='/'+folder+'/'+job+'/'
        for name in ['depth.png','disparity.png','reference.png','viewer.html','report.json']:
            blob=get(base+name)
            assert len(blob)>100
            if name.endswith('.png'):assert blob[:8]==b'\x89PNG\r\n\x1a\n'
            if name=='viewer.html':assert b'<script id="cloud-data"' in blob
            checked.append(base+name)
health=json.loads(get('/health','http://192.168.137.2:8850'));assert health['ready']
camera=json.loads(get('/status','http://192.168.137.2:8788'))
hdmi=json.loads(get('/hdmi/status','http://192.168.137.2:8788'))
assert not camera['error'] and not camera['standby'] and camera['age_seconds']<.3
assert not hdmi['error'] and hdmi['source']=='preview'
result=dict(passed=True,endpoints=checked,iterations=2,shutter_pressed=False,
    model_ready=True,preview_age_seconds=camera['age_seconds'],hdmi=hdmi)
(R/'ui_smoke_verified.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(dict(passed=True,checked=len(checked),iterations=2,preview_age_seconds=camera['age_seconds'],hdmi_error=hdmi['error'])))
