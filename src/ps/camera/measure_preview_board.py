"""One bounded preview sample; no shutter or hardware commands."""
import json,os,time
from pathlib import Path
from test_sgm_v4_transaction import request
ROOT=Path(__file__).resolve().parent
def cpu(pid):
    fields=(Path('/proc')/str(pid)/'stat').read_text().split(') ',1)[1].split()
    return int(fields[11])+int(fields[12])
def main():
    pid=int((ROOT/'full_camera.pid').read_text());state=request('/stereo/status')
    a=request('/status');h=request('/hdmi/status');c=cpu(pid);start=time.monotonic()
    time.sleep(6)
    b=request('/status');k=request('/hdmi/status');elapsed=time.monotonic()-start
    print(json.dumps({'pid':pid,'seconds':elapsed,'capture_fps':(b['sequence']-a['sequence'])/elapsed,
        'hdmi_update_fps':(k['frames']-h['frames'])/elapsed,
        'jpeg_fps':(b.get('jpeg_frames',0)-a.get('jpeg_frames',0))/elapsed if 'jpeg_frames' in b else None,
        'process_cpu_percent_one_core_100':100*(cpu(pid)-c)/os.sysconf('SC_CLK_TCK')/elapsed,
        'busy':state['busy'],'job_id':state['job_id'],'camera_error':b['error'],'hdmi_error':k['error'],
        'mode':b['mode'],'standby':b['standby'],'shutter_triggered':False}))
if __name__=='__main__':main()
