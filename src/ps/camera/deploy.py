"""Deploy only this candidate's explicit files to an isolated RAM directory."""
import hashlib,io,sys,urllib.request,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
USB=HERE.parents[1]/'experiments/usb_camera_20261016'
sys.path.insert(0,str(USB));from board_console import command
files=[Path(p).resolve() for p in sys.argv[1:]]
assert files and len({p.name for p in files})==len(files)
assert all(p.is_file() and p.is_relative_to(HERE) for p in files)
buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
 for p in files:z.writestr(p.name,p.read_bytes())
data=buf.getvalue();assert len(data)<32*1024*1024
print(command("sed -i 's/524288/33554432/' /tmp/usb_stereo_probe/deploy_receive.py; python3 /tmp/usb_stereo_probe/deploy_receive.py >/tmp/usb_stereo_probe/deploy.log 2>&1 & echo READY",8))
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
request=urllib.request.Request('http://192.168.137.2:8769/',data,method='POST')
with opener.open(request,timeout=30) as r:assert r.read()==b'OK'
digest=hashlib.sha256(data).hexdigest()
assert digest in command('sha256sum /tmp/usb_stereo_probe/deploy.zip',8)
code="import zipfile,pathlib; z=zipfile.ZipFile('/tmp/usb_stereo_probe/deploy.zip'); assert all('/' not in n and '..' not in n for n in z.namelist()); p=pathlib.Path('/tmp/usb_stereo_probe/usb320_hdmifps'); p.mkdir(exist_ok=True); z.extractall(p); print(z.namelist())"
print(command('python3 -c "'+code+'"',10));print('DEPLOY_SHA256_PASS',digest)
