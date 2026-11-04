"""Deploy only the reviewed lite runtime into a separate RAM directory."""
from pathlib import Path
import hashlib,io,json,sys,urllib.request,zipfile
R=Path(__file__).resolve().parent;P=R.parents[1]
sys.path.insert(0,str(P/'experiments/usb_camera_20261016'))
from board_console import command

def main():
    assert sys.argv[1:] in ([],['--code-only'])
    proof=json.loads((R/'hardware_verified.json').read_text())
    assert all(proof[k] for k in ('timing_passed','cdc_review_passed','hls_passed'))
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port,path in [(8788,'/stereo/status')]:
        with op.open('http://192.168.137.2:%d%s'%(port,path),timeout=5) as response:status=json.load(response)
        assert not status.get('busy') and not status.get('section_busy'),'Wait for the current photo to finish'
    files=['fast_pl.bit.bin','fast_pl.onnx','libfast_pl.so','hardware_verified.json','test_hardware_board.py','fast_capture_board.py','fast_infer_board.py','infer_runtime.py','infer_worker.py','fast_job_server.py','start_runtime_board.py','resident_switch_board.py','install_payload_board.py','repair_keys_board.py','pause_preview_board.py','processing_preview_board.py','pause_smoke_board.py','compress_completed_private_board.py']
    files.extend(['fast_sample.onnx','libfast_sample.so','inference_config.json','fast_layout.onnx','layout_config.json','transport_config.json','processing_preview_board.py','cache_release.py','restart_job_server_board.py','recover_paused_board.py','micro/0_cpu.onnx','micro/1_cpu.onnx','fallback_runtime.py','replay_sources/ee92f94446ea4a0eaedcf029e852871c/input.png','replay_sources/ee92f94446ea4a0eaedcf029e852871c/result.npz'])
    files=list(dict.fromkeys(n for n in files if n not in ('fast_pl.onnx','fast_layout.onnx')))
    if sys.argv[1:]:files=[n for n in files if n.endswith('.py') or n=='hardware_verified.json']
    content=io.BytesIO()
    with zipfile.ZipFile(content,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for name in files:
            data=(R/name).read_bytes()
            expected=proof['sha256'] if name=='fast_pl.bit.bin' else proof['sources'].get(name)
            if expected:assert hashlib.sha256(data).hexdigest()==expected
            z.writestr(name,data)
    blob=content.getvalue();assert len(blob)<104857600
    # The accepted receiver validates host, source address and archive paths.
    print(command("python3 /tmp/usb_stereo_probe/deploy_receive.py >/tmp/usb_stereo_probe/deploy.log 2>&1 & echo RECEIVER_STARTED",10),flush=True)
    with op.open(urllib.request.Request('http://192.168.137.2:8769/',blob,method='POST'),timeout=90) as f:assert f.read()==b'OK'
    digest=hashlib.sha256(blob).hexdigest()
    code="import pathlib,hashlib,zipfile; p=pathlib.Path('/tmp/usb_stereo_probe/deploy.zip'); assert hashlib.sha256(p.read_bytes()).hexdigest()=='"+digest+"'; z=zipfile.ZipFile(p); exec(compile(z.read('install_payload_board.py'),'install_payload_board.py','exec'),{'__name__':'__main__','DEPLOY_SHA256':'"+digest+"'})"
    result=command('python3 -c "'+code+'"',35);print(result,flush=True)
    assert 'CONV_PAYLOAD_VERIFIED' in result,'Board deployment failed; inspect the preserved console output'

if __name__=='__main__':main()
