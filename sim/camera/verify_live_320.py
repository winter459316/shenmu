import json,struct,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
get=lambda p:json.load(urllib.request.urlopen('http://127.0.0.1:8772'+p,timeout=10))
status=get('/api/status');camera=get('/api/camera');hdmi=get('/api/hdmi/status')
assert status['stage']=='ready' and not status['busy'] and not status['error'] and not status['observer_error']
assert camera['error']=='' and camera['age_seconds']<3
assert hdmi['enabled'] and not hdmi['error'] and hdmi['source']=='preview'
folder=ROOT/'live_captures'/status['result']['job_id']
verified=json.loads((folder/'verified.json').read_text(encoding='utf8'));assert verified['passed']
assert verified['board_metadata']['eye_size']==[320,360]
images={}
for n in ('reference.png','disparity.png','depth.png'):
    data=(folder/n).read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
    size=struct.unpack('>II',data[16:24]);assert size==(320,360);images[n]=size
sections=list(folder.glob('section_*.json'));assert sections
report={'passed':True,'job_id':status['result']['job_id'],'result':status['result'],
        'camera':camera,'hdmi_restored_preview':hdmi,'images':images,
        'sections':[p.name for p in sections],'independent_verification':verified['passed'],
        'hdmi_cast_evidence':'live_320_hdmi_cast.json','ui_screenshot':'live_320_page.png'}
(ROOT/'board_evidence/live_320_verified.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'passed':True,'job_id':report['job_id'],'images':images,'sections':len(sections),'board_seconds':status['result']['board_seconds'],'total_seconds':status['result']['total_seconds']}))
