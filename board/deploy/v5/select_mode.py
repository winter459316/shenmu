"""Select a verified idle runtime; leave the fixed web URL and photos intact."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time
import urllib.request

U=Path(__file__).resolve().parent
E=U.parent
P=U.parents[2]
sys.path.insert(0,str(E))
from transfer import command,pull_json


def health():
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open('http://192.168.137.2:8850/health',timeout=4) as response:return json.load(response)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--rollback',action='store_true');a=ap.parse_args()
    desired='fast_infer2_v1' if a.rollback else 'fast_pl3_usable_v5_quad'
    current=health()
    if current.get('ready') and current['version']==desired:
        print('SELECTED_RUNTIME_READY',desired);return
    assert current.get('ready'),'Wait for the current model startup or job to finish'
    assert current['model_worker']['state']=='ready','Only an idle worker may be switched'
    assert current['version'] in ('fast_infer2_v1','fast_pl3_usable_v2','fast_pl3_usable_v3_io','fast_pl3_usable_v4_cache','fast_pl3_usable_v5_quad')
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open('http://127.0.0.1:8849/api/status',timeout=3) as response:status=json.load(response)
    except urllib.error.URLError:status={'busy':False}
    assert not status['busy'],'Wait for the photo workflow to finish'
    if not a.rollback:
        subprocess.run([sys.executable,'-X','utf8',str(U/'stage.py')],check=True)
    mode='rollback' if a.rollback else 'activate'
    runner='/tmp/usb_stereo_probe/pl_pipeline_20261025/pl3_usable_v5_quad_activate_board_20261028.py'
    log='/tmp/usb_stereo_probe/pl_pipeline_20261025/pl3_usable_v5_quad_select_'+mode+'.log'
    answer=command('(python3 -u '+runner+' '+mode+' > '+log+' 2>&1 < /dev/null &)',8)
    deadline=time.monotonic()+75
    while time.monotonic()<deadline:
        time.sleep(1)
        try:current=health()
        except (OSError,ValueError):continue
        if current.get('ready') and current['version']==desired:
            receipt=pull_json('pl3_usable_v5_quad_'+mode+'_20261028.json')
            assert receipt['passed'] and receipt['worker_pid']==current['model_worker']['pid']
            print('SELECTED_RUNTIME_READY',desired)
            return
    raise TimeoutError('Runtime selection did not complete; inspect the exact selection log without repeating it')


if __name__=='__main__':main()
