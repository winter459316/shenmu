"""Preserve the current board result in RAM before a controlled update."""
import hashlib,json
from pathlib import Path
from test_sgm_v4_transaction import request
ROOT=Path(__file__).resolve().parent

def main():
    state=request('/stereo/status')
    assert not state['busy'] and not state['section_busy'] and state['result_id']==state['job_id']
    job=state['result_id'];assert job
    data=request('/stereo/result.npz?id='+job,raw=True)
    digest=hashlib.sha256(data).hexdigest()
    assert digest==state['metadata']['package_sha256']
    after=request('/stereo/status');assert after['job_id']==job and not after['busy']
    info={'job_id':job,'sha256':digest,'bytes':len(data)}
    if state['metadata'].get('total_seconds') is not None:info['total_seconds']=state['metadata']['total_seconds']
    path=ROOT/'held_restore.npz'
    path.write_bytes(data);assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    (ROOT/'held_restore.json').write_text(json.dumps(info,indent=2))
    print(json.dumps(dict(info,passed=True,shutter_triggered=False)))
if __name__=='__main__':main()
