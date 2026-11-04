"""Idempotent RAM-only deployment of the saved-frame input companion."""
from pathlib import Path
import hashlib,json,sys,threading,time,urllib.request
P=Path(__file__).resolve().parents[2]
E=P/'experiments/switch_latency_20261030'
LOCK=threading.Lock()
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def health():
    with OP.open('http://192.168.137.2:8853/health',timeout=3) as response:
        h=json.load(response)
    assert h['version']=='fast_pl3_usable_v5_quad','Video API runtime differs'
    if h.get('video_input_version')!='video_stereo_v5_display':raise ValueError('Video API update required')
    assert h['ready'],'V5 model worker is not ready'
    if h.get('switch_latency_version')!='overlap_v1':raise ValueError('Fast transition overlap update required')
    if not h.get('model_worker',{}).get('hdmi_hold_active'):raise ValueError('V5 static display hooks need restoration')
    with OP.open('http://192.168.137.2:8788/fast/status',timeout=3) as response:camera=json.load(response)
    if camera.get('hdmi_addon')!='hold_replay_v1':raise ValueError('HDMI replay owner needs restoration')
    if 'vessel' not in camera.get('photo_modes',[]):raise ValueError('Frozen-photo vessel mode needs restoration')
    return h
def ensure_board():
    with LOCK:
        try:return health()
        except (OSError,ValueError):pass
        sys.path.insert(0,str(P/'experiments/pl_pipeline_20261025'))
        from transfer import upload
        manifest=json.loads((E/'hdmi_addon_manifest_v4.json').read_text())
        files={n:E/n for n in manifest}
        for n,h in manifest.items():assert hashlib.sha256(files[n].read_bytes()).hexdigest()==h
        files['hdmi_addon_manifest_v4.json']=E/'hdmi_addon_manifest_v4.json'
        files['install_hdmi_v4.py']=E/'install_hdmi_v4.py'
        upload(files,run='install_hdmi_v4.py')
        for _ in range(100):
            try:return health()
            except (OSError,ValueError):time.sleep(.5)
        raise RuntimeError('视频帧输入服务未就绪，请检查 video_job_server.log；勿重复重配 PL')
if __name__=='__main__':
    print(json.dumps(ensure_board()))
