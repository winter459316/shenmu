"""Recover one already completed board result; never triggers a capture or PL load.

Run only after inspecting the failed PC export and confirming the same job is
still ready on the board. Stop the PC viewer before publishing the recovered
latest result, then restart it. Existing captures/latest results are preserved.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'.runtime/zu4ev_stereo'
HOST=RUNTIME/'candidates/usb_fast_infer2'
sys.path.insert(0,str(HOST))
from export_capture import export
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(url, body=None):
    req=urllib.request.Request(url,None if body is None else json.dumps(body).encode(),
                               headers={'Content-Type':'application/json'} if body is not None else {})
    with OP.open(req,timeout=30) as r:return r.read()


def main(job):
    if not re.fullmatch('[0-9a-f]{32}',job):raise ValueError('Invalid job identity')
    status=json.loads(request('http://192.168.137.2:8853/status?id='+job))
    assert status['job_id']==job and status['stage']=='ready' and not status['busy']
    assert not status['error'] and status['stable_restored']
    latest=HOST/'latest.json'
    if latest.exists():raise FileExistsError('Latest result already exists; preserve it and inspect manually')
    data=request('http://192.168.137.2:8853/result?id='+job)
    assert len(data)==status['package_bytes'] and hashlib.sha256(data).hexdigest()==status['package_sha256']
    folder=HOST/'captures'/job
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'board_result.npz').write_bytes(data)
    (folder/'board_status.json').write_text(json.dumps(status,indent=2),encoding='utf8')
    report=export(folder,status)
    receipt=json.loads(request('http://192.168.137.2:8853/cache-ack',dict(job_id=job,package_sha256=status['package_sha256'])))
    report.update(board_cache_released=bool(receipt['released']),pc_export_recovered=True)
    (folder/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    latest.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    request('http://192.168.137.2:8788/fast/control',dict(op='result',job_id=job))
    print(json.dumps(dict(recovered=True,job_id=job,board_result_verified=True,
                          cache_released=report['board_cache_released'],new_capture=False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',required=True)
    main(parser.parse_args().job)
