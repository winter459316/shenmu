"""Record measured preview update and verify a compact source checkpoint."""
import datetime,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    evidence=ROOT/'board_evidence'
    live=json.loads((evidence/'preview_live_verified.json').read_text())
    active=json.loads((evidence/'preview_service_active.json').read_text())
    assert live['passed'] and active['passed']
    assert sha((evidence/'preview_before_update.zip').read_bytes())=='7fb2e95a0febfff540c4ba6395cec951ab455ff778934735365655f975a34733'
    now=datetime.datetime.now().astimezone();stamp=now.strftime('%Y%m%d_%H%M%S')
    files=['full_camera.py','hdmi_output.py','full_control.html','restore_held.py','save_held_for_update.py',
        'preview_service_switch.py','measure_preview_board.py','test_preview_live.py','test_restore_held.py',
        'finalize_preview.py','board_evidence/preview_live_verified.json','board_evidence/preview_service_active.json',
        'board_evidence/preview_before_update.zip','board_evidence/preview_fps_live.png']
    report={'timestamp':now.isoformat(),'passed':True,
        'baseline_sample':{'seconds':6.014331043,'capture_fps':29.928515526,'hdmi_update_fps':3.990468737,'process_cpu_percent_one_core_100':86.626425495},
        'updated_sample':{'seconds':6.011215582,'capture_fps':29.444959607,'hdmi_update_fps':29.611315311,'jpeg_fps':23.955221375,'process_cpu_percent_one_core_100':136.245321571},
        'browser_refresh_fps_observed':29.7,'browser_refresh_may_repeat_latest_jpeg':True,
        'camera_pid':active['camera_pid'],'keys_pid':active['keys_pid'],'pc_host_restarted':False,
        'preview_modes_and_standby':live,'new_pl_preprocessor_added':False,
        'existing_pl_role':'VDMA memory read and HDMI video output; matching/remap/features remain for still capture',
        'still_capture_and_matching_algorithm_unchanged':True,'physical_key_retest':False,
        'prior_full_checkpoint':'checkpoints/usb_hdmi_keys_live_20261016_215847.zip',
        'source_sha256':{name:sha((ROOT/name).read_bytes()) for name in files}}
    path=evidence/'preview_release_verified.json';path.write_text(json.dumps(report,indent=2),'utf8')
    files.append(str(path.relative_to(ROOT)).replace('\\','/'))
    archive=ROOT/'checkpoints'/('preview_fps_update_'+stamp+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for name in files:z.write(ROOT/name,name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name in files:assert sha(z.read(name))==sha((ROOT/name).read_bytes())
    summary={'file':str(archive.relative_to(ROOT)),'sha256':sha(archive.read_bytes()),'entries_verified':len(files)}
    (evidence/'preview_checkpoint_verified.json').write_text(json.dumps(summary,indent=2),'utf8')
    state=ROOT/'CURRENT_STATE.txt'
    prefix=f'''{now.isoformat()} PREVIEW FPS UPDATE LIVE; user requested higher FPS after prior HDMI/key stop boundary.
- Camera PID{active['camera_pid']}, keys PID{active['keys_pid']}; PC8771 host not restarted. Firmware48350af unchanged. Held6fc76776 package unchanged and original total_seconds restored.
- Actual6s sample: camera29.44FPS, HDMI29.61FPS (before3.99), JPEG23.96FPS. Browser refresh29.7FPS can repeat JPEG. Four-mode samples: HDMI color/gray/median29-30FPS, Sobel20.5FPS; JPEG21-26FPS. Preview process CPU136.25% (one core=100%), before86.63%.
- Tests PASS: camera recovery, HDMI software, held restore with timing, actual four modes and API standby/resume. Physical keys not repressed; no shutter, no capture algorithm change, no new PL preprocessing. Existing PL VDMA handles scanout. Idle preview30Hz target; processing10Hz; standby4Hz.
- Before-source backup checkpoints/preview_before_20261016 and board_evidence/preview_before_update.zip; full stable checkpoint usb_hdmi_keys_live_20261016_215847.zip preserved. New update checkpoint {summary['file']}, SHA{summary['sha256']}.
- No repeat PC host restart after prior automatic-review rejection. Old OV5640/7020 projects untouched. Further live PL camera processing would require a dedicated throughput-designed core; do not route30FPS preview through slow static remap core.

'''
    state.write_text(prefix+state.read_text('utf8'),'utf8')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
