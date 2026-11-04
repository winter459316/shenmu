"""External/held job observation must never send a capture POST or repeat work."""
import tempfile
from pathlib import Path
import full_host as module
calls=[];workers=[];job='7'*32
state={'schema':'usb_full_v2','job_id':job,'busy':True,'stage':'pl_sgm_detail_forward','error':''}
def board(path,body=None,**unused):
    assert path=='/stereo/status' and body is None,'Observer attempted a mutation'
    calls.append(path);return dict(state)
class Worker:
    def __init__(self,target,args,daemon):self.args=args;workers.append(self)
    def start(self):pass
module.board_json=board
original_thread=module.threading.Thread;module.threading.Thread=Worker
try:
    with tempfile.TemporaryDirectory() as temp:
        module.CAPTURES=Path(temp);host=module.Host()
        assert host.observe_once() and host.busy and host.job==job and len(workers)==1
        assert not host.observe_once() and len(workers)==1
        host.busy=False;host.stage='error';assert not host.observe_once() and len(workers)==1
        state.update(job_id='8'*32,busy=False,stage='cancelled')
        assert not host.observe_once() and not host.result and host.stage=='cancelled'
        state.update(job_id=None,busy=False,stage='idle')
        assert not host.observe_once() and host.job is None
        state.update(job_id='9'*32,result_id='9'*32,busy=False,stage='ready')
        host.section_busy=True;assert not host.observe_once()
        host.section_busy=False;assert host.observe_once() and len(workers)==2
        assert all(p=='/stereo/status' for p in calls)
finally:module.threading.Thread=original_thread
print('HOST_OBSERVER_PASS: read-only adoption, no repeated job, busy/section/cancel guards')
