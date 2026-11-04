"""Stage new mode files only, verify installed aliases, do not switch services."""
from pathlib import Path
import hashlib
import json
import shlex
import sys

U=Path(__file__).resolve().parent
E=U.parent
sys.path.insert(0,str(E))
from transfer import upload,command


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    m=json.loads((U/'pl3_usable_v5_quad_manifest_20261028.json').read_text())
    files={n:Path(p) for n,p in json.loads((U/'payload_local.json').read_text()).items()}
    assert {n:sha(p) for n,p in files.items()}==m['files']
    files['pl3_usable_v5_quad_manifest_20261028.json']=U/'pl3_usable_v5_quad_manifest_20261028.json'
    files['pl3_usable_v5_quad_activate_board_20261028.py']=U/'activate_board.py'
    upload(files)
    program='''from pathlib import Path
import hashlib,json,zipfile
H=Path('/tmp/usb_stereo_probe/pl_pipeline_20261025');R=H.parent/'fast_infer2'
m=json.loads((H/'pl3_usable_v5_quad_manifest_20261028.json').read_text())
assert not(R/'pl_test_private_snapshot.json').exists()
for n,d in m['files'].items():assert hashlib.sha256((H/n).read_bytes()).hexdigest()==d,n
for n,d in m['stable_files'].items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==d,n
for name,source in m['board_aliases'].items():
 p=R/name;data=(H/source).read_bytes()
 if p.exists():assert p.read_bytes()==data,name
 else:
  t=p.with_suffix('.install.tmp');t.write_bytes(data);t.replace(p)
 if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
payload=H.parent/'deploy.zip'
with zipfile.ZipFile(payload) as z:
 assert z.testzip() is None
 expected=json.loads(z.read('transfer_manifest.json'))
 assert all(hashlib.sha256((H/n).read_bytes()).hexdigest()==d for n,d in expected.items())
payload.unlink()
print('PL3_USABLE_PAYLOAD_STAGED_STABLE_SOURCES_UNCHANGED')
'''
    out=command('python3 -c '+shlex.quote(program),30).replace('\r','')
    assert '\nPL3_USABLE_PAYLOAD_STAGED_STABLE_SOURCES_UNCHANGED\n' in out,out[-1000:]
    print('New mode aliases staged, all stable sources unchanged, no services switched')
    (U/'staged.json').write_text(json.dumps(dict(passed=True,manifest_sha256=sha(U/'pl3_usable_v5_quad_manifest_20261028.json'),activation_script_sha256=sha(U/'activate_board.py'),source_sha256={str(Path(__file__)):sha(Path(__file__))}),indent=2))


if __name__=='__main__':main()
