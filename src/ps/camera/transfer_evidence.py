from pathlib import Path
import sys,urllib.request,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016'))
from board_console import command
names=sys.argv[1:]
assert names and all(Path(n).name==n and all(c.isalnum() or c in '._' for c in n) for n in names)
print(command('python3 /tmp/usb_stereo_probe/usb320_sharedpreview/serve_results.py '+' '.join(names)+' >/tmp/usb_stereo_probe/usb320_sharedpreview/evidence_server.log 2>&1 & echo EVIDENCE_READY',10))
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));out=ROOT/'board_evidence';out.mkdir(exist_ok=True)
for name in names:
    with opener.open('http://192.168.137.2:8769/'+name,timeout=30) as r:data=r.read()
    (out/name).write_bytes(data);print(name,len(data),hashlib.sha256(data).hexdigest())

