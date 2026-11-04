"""Bounded no-shutter baseline using the same HTTP observations before/after."""
import json,sys,time,urllib.request,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path,body=None):
    req=urllib.request.Request('http://192.168.137.2:8788'+path,None if body is None else json.dumps(body).encode(),headers={} if body is None else {'Content-Type':'application/json'})
    with op.open(req,timeout=10) as r:return json.load(r)
old=call('/status');before=call('/stereo/status');hdmi=call('/hdmi/status')
assert not before['busy'] and not before['standby']
call('/hdmi/preview',{})
rows=[]
try:
    for mode in ('color','auto_enhanced','rectified'):
        call('/preview/mode',{'mode':mode});time.sleep(.25)
        a=call('/status');ha=call('/hdmi/status');start=time.monotonic();lags=[];ages=[]
        while time.monotonic()-start<3:
            c=call('/status');h=call('/hdmi/status')
            lags.append(max(0,c['sequence']-h['preview_sequence']))
            ages.append(c['preview_age_seconds']*1000)
            time.sleep(.025)
        dt=time.monotonic()-start;b=call('/status');hb=call('/hdmi/status');n=b['preview_count']-a['preview_count']
        rows.append({'mode':mode,'capture_fps':(b['sequence']-a['sequence'])/dt,'jpeg_fps':(b['jpeg_frames']-a['jpeg_frames'])/dt,
          'hdmi_fps':(hb['preview_unique_frames']-ha['preview_unique_frames'])/dt,'mean_hdmi_sequence_lag':statistics.mean(lags),
          'mean_latest_preview_age_ms':statistics.mean(ages),'stage_ms':{k:(b['preview_total_ms'].get(k,0)-a['preview_total_ms'].get(k,0))/n for k in b['preview_total_ms']},
          'hdmi_latency':hb.get('preview_latency'), 'jpeg_latency':b.get('jpeg_latency')})
finally:
    call('/preview/mode',{'mode':old['mode']})
    if hdmi['source']=='raw_disparity':call('/hdmi/raw',{'job_id':before['result_id']})
assert call('/stereo/status')['result_id']==before['result_id']
report={'rows':rows,'shutter_triggered':False,'held':before['result_id'],'latency_scope':'after cap.read completion; excludes sensor exposure, USB and panel latency'}
(ROOT/(sys.argv[1]+'.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report))
