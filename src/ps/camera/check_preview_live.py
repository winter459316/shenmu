"""Finite read-only camera/HDMI check; never takes a photograph."""
import json,mmap,os,time
from pathlib import Path
import cv2
import numpy as np
from switch_320_board import request
ROOT=Path(__file__).resolve().parent
c0=request(8788,'/status');h0=request(8788,'/hdmi/status');s0=request(8788,'/stereo/status')
t=time.monotonic();time.sleep(3)
c=request(8788,'/status');h=request(8788,'/hdmi/status');s=request(8788,'/stereo/status');elapsed=time.monotonic()-t
assert c['mode']=='rectified' and not c['error'] and not h['error'] and h['source']=='preview'
assert s0['result_id']==s['result_id'] and not s['busy']
assert c['sequence']>c0['sequence'] and h['frames']>h0['frames']
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    # Read only the existing display allocation, never registers or compute DMA.
    with mmap.mmap(fd,1280*720*3*2,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x679E0000) as m:
        for attempt in range(5):
            before=request(8788,'/hdmi/status');start=before['front_buffer']*1280*720*3
            pixels=bytes(m[start:start+1280*720*3]);after=request(8788,'/hdmi/status')
            if before['frames']==after['frames']:break
        else:raise AssertionError('Could not read one stable scanout buffer')
finally:os.close(fd)
image=np.frombuffer(pixels,np.uint8).reshape(720,1280,3)
for y in (200,280,360,440,520):
    assert np.all(image[y,1:639]==np.array([0,220,0],np.uint8)),'HDMI alignment guide missing'
assert cv2.imwrite(str(ROOT/'hdmi_rectified.png'),image)
report={'passed':True,'capture_fps':(c['sequence']-c0['sequence'])/elapsed,
        'jpeg_fps':(c['jpeg_frames']-c0['jpeg_frames'])/elapsed,
        'hdmi_present_fps':(h['frames']-h0['frames'])/elapsed,
        'camera':c,'hdmi':h,'held_job_unchanged':s['result_id'],'scanout_guides_verified':True,
        'physical_button_test':'pending_user','photo_triggered':False}
(ROOT/'preview_live_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
