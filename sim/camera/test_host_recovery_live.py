"""Revalidate the already-held board photo in an isolated host directory.

No camera shutter, service shutdown, listener, or original capture overwrite.
"""
import datetime,hashlib,json,shutil,time,uuid
from pathlib import Path
import full_host as module
ROOT=Path(__file__).resolve().parent
state=module.board_json('/stereo/status');job=state['job_id']
assert not state['busy'] and not state['section_busy'] and state['stage']=='ready' and state['result_id']==job
source=ROOT/'live_captures'/job
before={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in ('board_result.npz','verified.json','viewer.html')}
previous=json.loads((source/'verified.json').read_text(encoding='utf8'))
directory=ROOT/'recovery_verification'/('run_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
module.CAPTURES=directory/'captures';destination=module.CAPTURES/job;destination.mkdir(parents=True)
for name in ('board_result.npz','verified.json'):shutil.copyfile(source/name,destination/name)
# Prevent test publication from updating the production live_latest.json.
module.ROOT=directory
host=module.Host();assert host.observe_once();print('RESTORING_EXISTING_JOB',job,flush=True)
deadline=time.monotonic()+120;last=None
while host.worker.is_alive() and time.monotonic()<deadline:
    status=host.status()
    if status['stage']!=last:print(status['stage'],flush=True);last=status['stage']
    host.worker.join(timeout=1)
assert not host.worker.is_alive(),'Observation deadline reached; inspect same worker before retry'
status=host.status();assert not status['busy'] and status['stage']=='ready' and not status['error'],status
assert status['result']['restored'] and status['result']['job_id']==job
assert status['result']['total_seconds']==previous['elapsed_seconds']
assert status['result']['verification_seconds']==previous['seconds']
after=module.board_json('/stereo/status')
assert after['job_id']==job and after['result_id']==job and not after['busy']
for name,digest in before.items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
assert not host.observe_once(),'Repeated verification for an unchanged photo'
report={'passed':True,'job_id':job,'original_photo_files_unchanged':True,'board_job_unchanged':True,
        'original_timing_preserved':True,'restore_verification_seconds':status['result']['restore_verification_seconds'],
        'directory':str(directory),'production_host_restarted':False}
(ROOT/'board_evidence/host_recovery_verified.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
