"""Private saved-state, bounded experiment, automatic verified stable rollback."""
from pathlib import Path
import base64,contextlib,fcntl,hashlib,http.client,json,mmap,os,struct,subprocess,sys,time,traceback
R=Path(__file__).resolve().parent;S=R.parent/'usb320_hdmifps'
sys.path.insert(0,str(S))
from switch_320_board import owners,request,program
from switch_direct3d_board import stop,start_services
from board_dma import Arena,TAG,reservation
from preview_hardware import PREVIEW_CORES,check_preview
OLD_SHA='96802d44051c4bac8ce75704894771543e5dca4e94a77c4f6b460a6beb327af4'
SNAP=R/'pl_test_private_snapshot.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare():
 assert not SNAP.exists(),'An unfinished private snapshot already exists'
 assert not (S/'preview.dma.fault').exists(),'Preview DMA fault requires recovery'
 assert not (S/'filter.dma.fault').exists(),'Display DMA fault requires recovery'
 reservation();s=request(8788,'/stereo/status');assert not s['busy'] and not s['section_busy']
 current=owners();assert set(current)=={'full_camera.py','physical_keys.py'}
 assert all(Path(v['cwd']).resolve()==S for v in current.values())
 assert sha(S/'usb320.bit.bin')==OLD_SHA
 loaded=(S/'loaded.json').read_text();assert json.loads(loaded)['sha256']==OLD_SHA
 job=s['result_id'];assert job and job==s['job_id']
 c=http.client.HTTPConnection('192.168.137.2',8788,timeout=30,source_address=('127.0.0.1',0))
 try:
  c.request('GET','/stereo/result.npz?id='+job);r=c.getresponse();assert r.status==200;data=r.read()
 finally:c.close()
 digest=hashlib.sha256(data).hexdigest();assert digest==s['metadata']['package_sha256']
 (R/'stable_held.npz').write_bytes(data)
 held=dict(job_id=job,sha256=digest,bytes=len(data),total_seconds=s['metadata']['total_seconds'])
 preview=request(8788,'/status')
 saved=dict(owners=current,loaded=loaded,held=held,standby=s['standby'],mode=preview['mode'],tone=preview['tone_map']['enabled'],restore_files={})
 for name in ('held_restore.npz','held_restore.json'):
  p=S/name;saved['restore_files'][name]=base64.b64encode(p.read_bytes()).decode() if p.exists() else None
 with os.fdopen(os.open(str(SNAP),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump(saved,f)
 return saved
@contextlib.contextmanager
def hdmi_lease(frozen=None):
 if frozen is not None:
  from pause_preview_board import assert_frozen_lease
  assert_frozen_lease(frozen)
  yield
 else:
  with (R.parent/'full_v2/hdmi.lock').open('a+') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);yield

def reconfigure(new,frozen=None):
 with hdmi_lease(frozen):
  a=Arena(False)
  try:
   # Never read the removed SGM/geometry/completion AXI ranges in the lite image.
   before=PREVIEW_CORES if new else (('images',0xA1020000),('fast',0xA1070000),('mixed',0xA1080000))
   for name,address in before:
    a.controls[name]=mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=address)
   assert all(a.read(n,0)&4 for n in a.controls),'Existing DMA not idle'
   with mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0xA1050000) as v:
    assert struct.unpack_from('<I',v,4)[0]&1,'HDMI DMA not halted'
   try:
    program(R if new else S,'fast_pl.bit.bin' if new else 'usb320.bit.bin')
    (R/'configuration_state.json').write_text(json.dumps({'new':new}))
    for mapping in a.controls.values():mapping.close()
    a.controls={}
    if new:
     for name,address in (('images',0xA1020000),('fast',0xA1070000),('mixed',0xA1080000)):
      a.controls[name]=mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=address)
     value,_=a.command('images',{0x20:0},timeout=2);assert value==0x55494632
     value,_=a.command('images',{0x20:3},timeout=2);assert value==TAG
     value,_=a.command('fast',{0x20:0},timeout=2);assert value==0x46445032
     value,_=a.command('mixed',{0x28:0},timeout=2);assert value==0x4D503136
    else:
     check_preview(a)
   except BaseException:
    if new:
     # No compute/DMA command has been issued at this stage: identity calls only.
     program(S,'usb320.bit.bin')
     for mapping in a.controls.values():mapping.close()
     a.controls={}
     check_preview(a)
     (R/'configuration_state.json').write_text(json.dumps({'new':False}))
    raise
  finally:a.close()
def restore_services(saved):
 (S/'loaded.json').write_text(saved['loaded'])
 assert sha(R/'stable_held.npz')==saved['held']['sha256']
 (S/'held_restore.npz').write_bytes((R/'stable_held.npz').read_bytes())
 (S/'held_restore.json').write_text(json.dumps(saved['held']))
 try:
  report=start_services(S,8788,saved,True)
  request(8788,'/preview/tone',{'enabled':saved['tone']});request(8788,'/preview/mode',{'mode':saved['mode']})
  request(8788,'/standby',{'enabled':saved['standby']})
 finally:
  for name,encoded in saved['restore_files'].items():
   if encoded is None:(S/name).unlink()
   else:(S/name).write_bytes(base64.b64decode(encoded))
 report['held']=saved['held'];report['stable_bitstream_sha256']=OLD_SHA
 (R/'stable_restored.json').write_text(json.dumps(report,indent=2))
 print('STABLE_RESTORED',json.dumps({'held':saved['held'],'camera_pid':report['camera_pid']}),flush=True)
if __name__=='__main__':
 raise SystemExit('Use fast_capture_board.py JOB [--replay OLDJOB]; imported switch helper only')
