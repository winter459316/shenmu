"""Finite preview-only measurements. No photograph, no repeated benchmark."""
import json,sys,time
from pathlib import Path
from switch_320_board import request
ROOT=Path(__file__).resolve().parent
label=sys.argv[1];assert label in ('before','after')
saved=request(8788,'/status')['mode'];results=[]
try:
    for mode in (('rectified',) if label=='before' else ('rectified','color')):
        s=request(8788,'/stereo/status');assert not s['busy'] and not s['section_busy'] and not s['standby']
        request(8788,'/preview/mode',{'mode':mode});time.sleep(1)
        c0=request(8788,'/status');h0=request(8788,'/hdmi/status');began=time.monotonic()
        time.sleep(5)
        c=request(8788,'/status');h=request(8788,'/hdmi/status');elapsed=time.monotonic()-began
        state=request(8788,'/stereo/status');assert not state['busy'] and state['result_id']==s['result_id']
        assert c['mode']==mode and not c['error'] and not c.get('preview_error') and not h['error']
        assert h['source']=='preview','Exit 3D casting before preview measurement'
        count=c.get('preview_count',0)-c0.get('preview_count',0)
        result={'mode':mode,'seconds':elapsed,'capture_fps':(c['sequence']-c0['sequence'])/elapsed,
                'jpeg_fps':(c['jpeg_frames']-c0['jpeg_frames'])/elapsed,
                'hdmi_present_fps':(h['frames']-h0['frames'])/elapsed,'held_job':s['result_id']}
        if 'preview_unique_frames' in h:
            result['hdmi_unique_fps']=(h['preview_unique_frames']-h0['preview_unique_frames'])/elapsed
            result['rectifications']=c['rectification_calls']-c0['rectification_calls']
            result['published_frames']=count
            result['skipped_frames']=c['preview_skipped']-c0['preview_skipped']
            result['average_stage_ms']={k:(v-c0['preview_total_ms'].get(k,0))/max(1,count) for k,v in c['preview_total_ms'].items()}
            result['preview_age_ms']=c['preview_age_seconds']*1000
        results.append(result);print(json.dumps(result),flush=True)
finally:request(8788,'/preview/mode',{'mode':saved})
(ROOT/('preview_speed_'+label+'.json')).write_text(json.dumps({'passed':True,'results':results,'original_mode':saved,'photo_triggered':False},indent=2))
