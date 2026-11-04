"""Read-only live guide checks without freezing the 30-fps scanout."""
import json,mmap,os
from pathlib import Path
import numpy as np
from switch_320_board import request
ROOT=Path(__file__).resolve().parent
c=request(8788,'/status');h=request(8788,'/hdmi/status');s=request(8788,'/stereo/status')
assert c['mode']=='rectified' and c['rectification_backend']=='A53 exact integer two-eye'
assert not c['error'] and not c['preview_error'] and c['preview_age_seconds']<.25
assert not h['error'] and h['source']=='preview' and h['preview_unique_frames']>30
assert not s['busy'] and not s['section_busy']
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    with mmap.mmap(fd,1280*720*3*2,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x679E0000) as m:
        for buffer in (0,1):
            for y in (200,280,360,440,520):
                start=buffer*1280*720*3+y*1280*3
                row=np.frombuffer(bytes(m[start:start+640*3]),np.uint8).reshape(-1,3)[1:639]
                assert np.all(row==np.array([0,220,0],np.uint8))
finally:os.close(fd)
report={'passed':True,'camera':c,'hdmi':h,'held_job':s['result_id'],
        'both_scanout_buffer_guides_verified':True,'photo_triggered':False,
        'full_frame_screenshot':'Not taken; full DDR read cannot guarantee stable frame at 30 FPS',
        'physical_button_retest':'not requested; identical key code and finite cycle regression passed'}
(ROOT/'preview_live_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
