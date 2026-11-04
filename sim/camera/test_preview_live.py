"""Finite preview mode and standby regression, without shutter or PL reload."""
import hashlib,json,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import cv2,numpy as np
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def request(path,body=None,raw=False):
    r=urllib.request.Request('http://192.168.137.2:8767'+path,
        data=None if body is None else json.dumps(body).encode(),
        headers={} if body is None else {'Content-Type':'application/json'})
    with opener.open(r,timeout=10) as response:data=response.read()
    return data if raw else json.loads(data)
def sample():
    a=request('/status');h=request('/hdmi/status');start=time.monotonic()
    time.sleep(4)
    b=request('/status');k=request('/hdmi/status');seconds=time.monotonic()-start
    assert not b['error'] and not k['error'] and b['age_seconds']<1
    return {'seconds':seconds,'capture_fps':(b['sequence']-a['sequence'])/seconds,
        'jpeg_fps':(b['jpeg_frames']-a['jpeg_frames'])/seconds,
        'hdmi_update_fps':(k['frames']-h['frames'])/seconds,'mode':b['mode']}
def main():
    before=request('/stereo/status');camera=request('/status')
    assert not before['busy'] and not before['section_busy'] and not camera['standby']
    report={'passed':False,'shutter_triggered':False,'fpga_reconfigured':False,'samples':[]}
    try:
        for mode in ('color','gray','median','sobel'):
            request('/preview/mode',{'mode':mode});time.sleep(.4)
            item=sample();data=request('/preview.jpg',raw=True)
            img=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_UNCHANGED)
            assert img.shape[:2]==(240,640)
            assert mode=='color' or img.ndim==2
            assert item['capture_fps']>20 and item['hdmi_update_fps']>20
            item['jpeg_sha256']=hashlib.sha256(data).hexdigest();report['samples'].append(item)
        request('/standby',{'enabled':True});time.sleep(1)
        stopped=request('/status');hdmi=request('/hdmi/status')
        assert stopped['standby'] and hdmi['source']=='standby' and not hdmi['error']
        request('/standby',{'enabled':False});deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            recovered=request('/status')
            if not recovered['error'] and recovered['sequence']>stopped['sequence']:break
            time.sleep(.2)
        else:raise AssertionError('Preview did not recover')
        after=request('/stereo/status')
        assert after['result_id']==before['result_id']
        assert after['metadata']['package_sha256']==before['metadata']['package_sha256']
        assert after['metadata']['total_seconds']==before['metadata']['total_seconds']
        report.update(passed=True,standby_resume_passed=True,held_job=after['result_id'],
            held_sha256=after['metadata']['package_sha256'],physical_keys_not_retested=True)
    finally:
        request('/standby',{'enabled':False});request('/preview/mode',{'mode':camera['mode']})
        (ROOT/'board_evidence/preview_live_verified.json').write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
