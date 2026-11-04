"""Finite persistent connection/unique-frame checks; no capture or recomputation."""
import hashlib,http.client,json,statistics,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    with op.open('http://192.168.137.2:8788'+path,timeout=20) as r:return json.load(r)
s=get('/stereo/status');assert not s['busy'] and not s['section_busy']
c=http.client.HTTPConnection('127.0.0.1',8805,timeout=4);cursor='';keys=[];ages=[];sockets=[]
began=time.monotonic()
try:
    for i in range(100):
        c.request('GET','/preview.jpg'+('?after='+cursor if cursor else ''))
        r=c.getresponse();data=r.read();assert r.status==200 and data[:2]==b'\xff\xd8'
        key=(int(r.getheader('X-Frame-Sequence')),int(r.getheader('X-Frame-Epoch')))
        assert not keys or key!=keys[-1],'Duplicate frame delivered'
        keys.append(key);cursor=','.join(map(str,key));ages.append(float(r.getheader('X-Frame-Age-Ms')))
        sockets.append(c.sock.getsockname())
finally:c.close()
elapsed=time.monotonic()-began;assert len(set(sockets))==1,'Connection was not reused'
assert get('/stereo/status')['result_id']==s['result_id']
with op.open('http://192.168.137.2:8788/stereo/result.npz?id='+s['result_id'],timeout=30) as r:payload=r.read()
sha=hashlib.sha256(payload).hexdigest();assert sha==s['metadata']['package_sha256']
(ROOT/'held_restore.npz').write_bytes(payload)
held={'job_id':s['result_id'],'sha256':sha,'bytes':len(payload)}
if 'total_seconds' in s['metadata']:held['total_seconds']=s['metadata']['total_seconds']
(ROOT/'held_restore.json').write_text(json.dumps(held,indent=2))
report={'passed':True,'unique_frames':len(keys),'seconds':elapsed,'delivered_fps':(len(keys)-1)/elapsed,
 'one_keepalive_connection':True,'board_jpeg_send_age_mean_ms':statistics.mean(ages),
 'board_jpeg_send_age_p95_ms':sorted(ages)[94],'held':held,'shutter_triggered':False,
 'scope':'age after UVC decoded frame delivery to A53; excludes exposure/USB/panel and browser display'}
(ROOT/'transport_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
