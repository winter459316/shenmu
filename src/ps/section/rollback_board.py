"""Idle rollback after the section server has restored the original preview bit."""
from pathlib import Path
import fcntl,hashlib,http.client,json,os,signal,sys,time,zipfile
B=Path('/tmp/usb_stereo_probe');E=B/'section_pl_20261024';R=B/'fast_infer2';S=B/'usb320_hdmifps'
sys.path[:0]=[str(R),str(S)]
import test_hardware_board as h
from switch_320_board import owners,request
from switch_direct3d_board import stop,start_services
def main():
 c=http.client.HTTPConnection('127.0.0.1',8852,timeout=30)
 try:
  c.request('POST','/exit',b'{}',{'X-Section-Token':(E/'token.txt').read_text().strip(),'Content-Type':'application/json'});response=c.getresponse();result=json.loads(response.read());assert response.status==200 and not result['active']
 finally:c.close()
 pid=int((E/'server.pid').read_text());proc=Path('/proc')/str(pid);assert str(E/'section_server.py').encode() in (proc/'cmdline').read_bytes().split(b'\0')
 os.kill(pid,signal.SIGTERM)
 for _ in range(100):
  if not proc.exists():break
  time.sleep(.02)
 with (B/'fast_pl/capture.lock').open('a+') as gl,(R/'capture.lock').open('a+') as cl:
  for f in (gl,cl):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert not h.SNAP.exists() and json.loads((S/'loaded.json').read_text())['sha256']==h.OLD_SHA
  state=request(8788,'/stereo/status');assert not state['busy'] and not state['section_busy'] and not state['standby']
  current=owners();assert set(current)=={'full_camera.py','physical_keys.py'}
  saved=json.loads((E/'private_snapshot.json').read_text());saved['owners']=current;saved['preview']=request(8788,'/status')['mode']
  manifest=json.loads((E/'deployed_manifest.json').read_text())
  for n,d in manifest.items():
   if n.startswith('runtime/'):assert hashlib.sha256((S/Path(n).name).read_bytes()).hexdigest()==d,n
  stop(current)
  hashes=json.loads((E/'before_sha256.json').read_text())
  with zipfile.ZipFile(E/'before.zip') as z:
   for n,digest in hashes.items():
    assert Path(n).name==n;p=S/n
    if digest is None:
     if p.exists():p.unlink()
    else:
     data=z.read(n);assert hashlib.sha256(data).hexdigest()==digest;p.write_bytes(data)
  active=start_services(S,8788,saved,True);request(8788,'/preview/mode',dict(mode=saved['preview']))
  (E/'rolled_back.json').write_text(json.dumps(dict(passed=True,preview_sha256=h.OLD_SHA,camera_pid=active['camera_pid'])))
  print('SECTION_ROLLBACK_COMPLETE',flush=True)
if __name__=='__main__':main()
