"""SHA-checked local-PC/board-RAM transfer for this experiment only."""
from pathlib import Path
import hashlib
import io
import json
import re
import shlex
import sys
import urllib.request
import zipfile

E = Path(__file__).resolve().parent
P = E.parents[1]
B = '/tmp/usb_stereo_probe/pl_pipeline_20261025'
sys.path.insert(0, str(P / 'experiments/usb_camera_20261016'))
from board_console import command
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def upload(files, run=None):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED) as z:
        manifest = {}
        for name, path in files.items():
            assert re.fullmatch(r'[a-zA-Z0-9_.-]+', name)
            data = Path(path).read_bytes()
            manifest[name] = hashlib.sha256(data).hexdigest()
            z.writestr(name, data)
        z.writestr('transfer_manifest.json', json.dumps(manifest))
    data = payload.getvalue()
    assert len(data) < 104857600
    digest = hashlib.sha256(data).hexdigest()
    print(command('(python3 /tmp/usb_stereo_probe/deploy_receive.py '
          '> /tmp/usb_stereo_probe/pipeline_receive.log 2>&1 < /dev/null &)', 8), flush=True)
    with OP.open(urllib.request.Request('http://192.168.137.2:8769/', data), timeout=60) as r:
        assert r.read() == b'OK'
    code = '''from pathlib import Path
import hashlib,json,zipfile
b=Path('/tmp/usb_stereo_probe'); e=b/'pl_pipeline_20261025'; p=b/'deploy.zip'
assert hashlib.sha256(p.read_bytes()).hexdigest()==DIGEST
e.mkdir(exist_ok=True)
with zipfile.ZipFile(p) as z:
 assert z.testzip() is None
 m=json.loads(z.read('transfer_manifest.json'))
 for n,h in m.items():
  assert Path(n).name==n and n not in ('.','..')
  target=e/n; blob=z.read(n)
  assert hashlib.sha256(blob).hexdigest()==h
  assert not target.is_symlink()
  if target.exists(): assert target.read_bytes()==blob, 'Refuse changed existing experiment file: '+n
  else: target.write_bytes(blob)
print('PIPELINE_TRANSFER_VERIFIED')
'''.replace('DIGEST', repr(digest))
    answer = command('python3 -c ' + shlex.quote(code), 30)
    assert 'PIPELINE_TRANSFER_VERIFIED' in answer, answer
    print('PIPELINE_TRANSFER_VERIFIED', sorted(files), flush=True)
    if run:
        assert run in files and run.endswith('.py')
        print(command('(python3 -u ' + B + '/' + run + ' > ' + B + '/' + run +
                      '.log 2>&1 < /dev/null &)', 8), flush=True)


def pull_json(name):
    assert re.fullmatch(r'[a-z_0-9]+\.json', name)
    code = ('import base64;from pathlib import Path;p=Path(' + repr(B + '/' + name) +
            ');assert p.stat().st_size<100000;print("PUBLIC_JSON "+base64.b64encode(p.read_bytes()).decode())')
    answer = command('python3 -c ' + shlex.quote(code), 12).replace('\r', '')
    found = re.findall(r'^PUBLIC_JSON ([A-Za-z0-9+/=]+)$', answer, re.M)
    assert len(found) == 1, answer[-1000:]
    import base64
    data = base64.b64decode(found[0])
    result = json.loads(data)
    (E / name).write_bytes(data)
    return result


if __name__ == '__main__':
    upload({'export_optimized_board.py': E / 'export_optimized_board.py'},
           run='export_optimized_board.py')
