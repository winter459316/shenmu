from pathlib import Path
import urllib.request,json,hashlib,time,uuid,sys,numpy as np
P=Path(__file__).resolve().parents[2];E=Path(__file__).resolve().parent;OP=urllib.request.build_opener(urllib.request.ProxyHandler({}));label=sys.argv[1]
assert not (E/(label+'_launch.json')).exists()
job=uuid.uuid4().hex;(E/(label+'_launch.json')).write_text(json.dumps({'job_id':job}))
req=urllib.request.Request('http://192.168.137.2:8853/capture-frame?id='+job,(E/'input.png').read_bytes(),headers={'Content-Type':'image/png'});print(OP.open(req,timeout=8).read().decode(),flush=True)
for i in range(100):
 time.sleep(1);s=json.loads(OP.open('http://192.168.137.2:8853/status?id='+job,timeout=6).read())
 if s.get('stage')=='failed':raise RuntimeError(s)
 if s.get('stage')=='ready':break
else:raise TimeoutError('Inspect launched job')
(E/(label+'_status.json')).write_text(json.dumps(s,indent=2))
data=OP.open('http://192.168.137.2:8853/result?id='+job,timeout=20).read();assert hashlib.sha256(data).hexdigest()==s['package_sha256'];archive=E/(label+'.npz');archive.write_bytes(data)
source=P/'candidates/usb_fast_infer2/captures/3d7c03a0a4d74231827f0d7fed5d5624/board_result.npz'
with np.load(source,allow_pickle=False) as a,np.load(archive,allow_pickle=False) as b:exact={n:a[n].dtype==b[n].dtype and a[n].shape==b[n].shape and a[n].tobytes()==b[n].tobytes() for n in a.files if n!='metadata_json'}
assert len(exact)==13 and all(exact.values()),exact
(E/(label+'_exact.json')).write_text(json.dumps(exact))
req=urllib.request.Request('http://192.168.137.2:8853/cache-ack',json.dumps({'job_id':job,'package_sha256':s['package_sha256']}).encode(),headers={'Content-Type':'application/json'});assert json.load(OP.open(req,timeout=10))['released']
print(json.dumps({'label':label,'total':s['total_seconds'],'stage':s['stage_seconds'],'restore':s['restore_breakdown_seconds'],'exact13':True},indent=2),flush=True)
