"""Handoff recovery recipe: --check is offline; --apply requires a fresh reserved boot.

Does not reboot, flash, replace a running system, capture a photo, or start the
PC viewer. Newly assembled for the handoff; not cold-boot tested on hardware.
The currently qualified source/model/bitstream files are copied unchanged.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import io
import json
import re
import shlex
import sys
import time
import urllib.request
import zipfile
from check_current import P, R, S, local_checks

USB = P / 'experiments/usb_camera_20261016'
B = P / 'experiments/fast_board_20261018'
BASE = '/tmp/usb_stereo_probe'
STORE = '/dev/shm/usb_fast_infer2'
MODELS = ('fast_pl.onnx', 'fast_layout.onnx', 'fast_sample.onnx', 'fast_speed.onnx')
WHEELS = ('numpy-1.21.6-cp37-cp37m-manylinux_2_17_aarch64.manylinux2014_aarch64.whl',
          'onnxruntime-1.14.1-cp37-cp37m-manylinux_2_17_aarch64.manylinux2014_aarch64.whl')
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def marker(result, token):
    assert re.search(r'(?m)^' + re.escape(token) + r'\r?$', result), result


def plan():
    check = local_checks()
    assert check['passed'], [n for n, ok in check['checks'].items() if not ok]
    # Parse the explicit current payload list without executing a deploy script.
    tree = ast.parse((S / 'deploy_hdmifps_runtime.py').read_text(encoding='utf8'))
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets))
    names = ast.literal_eval(assignment.value.func.value).split()
    # Fast imports stop/start_services from this module even on the cold path.
    names.append('switch_direct3d_board.py')
    camera = {n: (S / n).read_bytes() for n in dict.fromkeys(names)}
    camera['startup_payload_sha256.json'] = json.dumps(
        {n: hashlib.sha256(v).hexdigest() for n, v in camera.items()}, indent=2).encode()
    proof = json.loads((R / 'hardware_verified.json').read_text(encoding='utf8'))
    fast_names = set(proof['sources']) - set(MODELS)
    fast_names.update(('fast_pl.bit.bin', 'hardware_verified.json', 'inference_config.json',
                       'layout_config.json', 'transport_config.json', 'recover_paused_board.py',
                       'restart_job_server_board.py', 'compress_completed_private_board.py',
                       'pause_smoke_board.py'))
    fast = {n: (R / n).read_bytes() for n in sorted(fast_names)}
    dependencies = {n: (B / n).read_bytes() for n in WHEELS}
    for files in (camera, fast):
        for n, blob in files.items():
            if n.endswith('.py'):
                compile(blob, n, 'exec')
    models = {n: (R / n).read_bytes() for n in MODELS}
    section_root=R/'section_payload'
    manifest=json.loads((section_root/'manifest.json').read_text())
    section={n:(section_root/n).read_bytes() for n in manifest}
    assert all(hashlib.sha256(blob).hexdigest()==manifest[n] for n,blob in section.items())
    assert section['token.txt']==(R/'section_token.txt').read_bytes()
    for n,blob in section.items():
        if n.endswith('.py'):compile(blob,n,'exec')
    return camera, dependencies, fast, models, section


def apply(camera, dependencies, fast, models, section):
    sys.path.insert(0, str(USB))
    from board_console import command, upload

    def board(code, timeout=20):
        return command('python3 -c ' + shlex.quote(code), timeout)

    # Fresh only: no overwriting or stopping any existing project, and no factory DMA owners.
    preflight = """from pathlib import Path
import struct
b=Path('/tmp/usb_stereo_probe')
for p in [b/'usb320_hdmifps',b/'fast_infer2',b/'fast_board',b/'section_pl_20261024',Path('/dev/shm/usb_fast_infer2')]:
 assert not p.exists(), 'Existing runtime: inspect instead of cold deployment: '+str(p)
assert not list(b.glob('**/*private_snapshot*.json')), 'Unfinished recovery state exists'
assert not list(Path('/sys/bus/platform/devices').glob('a0*/driver')), 'Factory PL drivers still bound'
dt=Path('/proc/device-tree')
assert (dt/'amba_pl@0/status').read_bytes().rstrip(b'\\0')==b'disabled'
assert struct.unpack('>4I',(dt/'reserved-memory/usb-pl-dma@60000000/reg').read_bytes())==(0,0x60000000,0,0x08000000)
assert (dt/'reserved-memory/usb-pl-dma@60000000/no-map').exists()
for p in Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try: args=(p/'cmdline').read_bytes().split(b'\\0')
 except OSError: continue
 assert not any(Path(a.decode(errors='replace')).name in ('full_camera.py','physical_keys.py','infer_worker.py','fast_job_server.py') for a in args), 'Existing process '+p.name
print('FRESH_RESERVED_BOOT_VERIFIED')
"""
    result = board(preflight)
    print(result, flush=True)
    marker(result, 'FRESH_RESERVED_BOOT_VERIFIED')
    # Only a tiny receiver uses serial. All models, images and native code use PS_ETH.
    upload(USB / 'deploy_receive.py', BASE + '/deploy_receive.py')
    result = board("from pathlib import Path; p=Path('/tmp/usb_stereo_probe/deploy_receive.py'); s=p.read_text(); assert '524288' in s; p.write_text(s.replace('524288','104857600')); print('RECEIVER_LIMIT_READY')")
    marker(result, 'RECEIVER_LIMIT_READY')

    def transfer(files, destination):
        assert destination in (BASE + '/usb320_hdmifps', BASE + '/fast_board', BASE + '/fast_infer2', BASE + '/section_pl_20261024', STORE)
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for n, blob in files.items():
                assert not n.startswith('/') and '..' not in Path(n).parts and '\\' not in n
                z.writestr(n, blob)
        payload = data.getvalue()
        assert len(payload) < 104857600
        digest = hashlib.sha256(payload).hexdigest()
        command('python3 ' + BASE + '/deploy_receive.py >' + BASE + '/deploy.log 2>&1 < /dev/null & echo RECEIVER_STARTED', 8)
        request = urllib.request.Request('http://192.168.137.2:8769/', payload, method='POST')
        with OP.open(request, timeout=90) as response:
            assert response.read() == b'OK'
        code = """from pathlib import Path
import hashlib,zipfile
p=Path('/tmp/usb_stereo_probe/deploy.zip')
assert hashlib.sha256(p.read_bytes()).hexdigest()==DIGEST
d=Path(DESTINATION); assert not d.is_symlink(); d.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(p) as z:
 assert z.testzip() is None
 for n in z.namelist():
  q=Path(n); assert not q.is_absolute() and '..' not in q.parts and '\\\\' not in n
  target=d/q; assert not target.exists() and not target.is_symlink(), 'Never overwrite '+str(target)
  assert d.resolve() in target.resolve().parents
  target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(z.read(n))
p.unlink()
print('PAYLOAD_VERIFIED')
""".replace('DIGEST', repr(digest)).replace('DESTINATION', repr(destination))
        result = board(code, 35)
        marker(result, 'PAYLOAD_VERIFIED')
        print('Uploaded', destination, sorted(files), 'sha256', digest, flush=True)

    transfer(camera, BASE + '/usb320_hdmifps')
    transfer(dependencies, BASE + '/fast_board')
    result = board("from pathlib import Path; import zipfile; r=Path('/tmp/usb_stereo_probe/fast_board'); [zipfile.ZipFile(p).extractall(r/'deps') for p in r.glob('*.whl')]; print('FAST_DEPS_READY')", 35)
    marker(result, 'FAST_DEPS_READY')
    transfer(fast, BASE + '/fast_infer2')
    transfer(section, BASE + '/section_pl_20261024')
    # Independent model archives avoid the receiver's 100 MiB bound.
    for n, blob in models.items():
        transfer({n: blob}, STORE)
    result = board("""from pathlib import Path
import hashlib,json
b=Path('/tmp/usb_stereo_probe'); r=b/'fast_infer2'; store=Path('/dev/shm/usb_fast_infer2')
assert any(l.split()[1]=='/dev' and l.split()[2]=='devtmpfs' for l in Path('/proc/mounts').read_text().splitlines())
for n in ('fast_pl.onnx','fast_layout.onnx','fast_sample.onnx','fast_speed.onnx'): (r/n).symlink_to(store/n)
(store/'jobs').mkdir(); (r/'jobs').symlink_to(store/'jobs',target_is_directory=True)
(b/'fast_pl').mkdir(exist_ok=True); (b/'full_v2').mkdir(exist_ok=True)
h=json.loads((r/'hardware_verified.json').read_text()); files=dict(h['sources']); files['fast_pl.bit.bin']=h['sha256']
for n,v in files.items(): assert hashlib.sha256((r/n).read_bytes()).hexdigest()==v,n
print('COLD_BINDINGS_VERIFIED')
""", 35)
    marker(result, 'COLD_BINDINGS_VERIFIED')

    # The qualified ONNX graphs embed the historical fallback path
    # /tmp/usb_stereo_probe/fast_mixed2/micro. Recreate that compatibility
    # view so the range-guard FP32 fallback can load the current micro models.
    result = board("""from pathlib import Path
b=Path('/tmp/usb_stereo_probe');link=b/'fast_mixed2/micro'
link.parent.mkdir(exist_ok=True)
if not link.exists():link.symlink_to(b/'fast_infer2/micro')
assert (link/'0_cpu.onnx').resolve()==(b/'fast_infer2/micro/0_cpu.onnx').resolve()
assert (link/'1_cpu.onnx').resolve()==(b/'fast_infer2/micro/1_cpu.onnx').resolve()
print('FALLBACK_COMPAT_VERIFIED')
""", 8)
    marker(result, 'FALLBACK_COMPAT_VERIFIED')

    def launch(directory, script, log):
        code = "import pathlib,subprocess; r=pathlib.Path(" + repr(directory) + "); f=(r/" + repr(log) + ").open('ab',buffering=0); p=subprocess.Popen(['python3','-u',str(r/" + repr(script) + ")],cwd=str(r),stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True); print('STARTED',p.pid)"
        print(board(code, 8), flush=True)

    def wait_ready(url, predicate, seconds):
        deadline = time.monotonic() + seconds
        last = None
        while time.monotonic() < deadline:
            try:
                with OP.open(url, timeout=3) as response:
                    last = json.load(response)
                if predicate(last):
                    return last
            except OSError as exc:
                last = str(exc)
            time.sleep(0.5)
        raise TimeoutError('Inspect startup logs before retrying; last status: ' + str(last))

    launch(BASE + '/usb320_hdmifps', 'cold_start_board.py', 'startup.log')
    wait_ready('http://192.168.137.2:8788/status', lambda d: not d.get('error') and d.get('age_seconds', 99) < 2, 40)
    wait_ready('http://192.168.137.2:8788/hdmi/status', lambda d: not d.get('error') and d.get('frames', 0) >= 2, 12)
    result = board("from pathlib import Path; import json; p=Path('/tmp/usb_stereo_probe/usb320_hdmifps/cold_start_verified.json'); assert p.exists() and json.loads(p.read_text())['passed']; print('CAMERA_COLD_START_VERIFIED')", 8)
    marker(result, 'CAMERA_COLD_START_VERIFIED')
    launch(BASE + '/fast_infer2', 'start_runtime_board.py', 'startup.log')
    status = wait_ready('http://192.168.137.2:8850/health', lambda d: d.get('ready') and d.get('version') == 'fast_infer2_v1', 45)
    print(board("from pathlib import Path; Path('/tmp/usb_stereo_probe/section_pl_20261024/token.txt').chmod(0o600)",8),flush=True)
    launch(BASE + '/section_pl_20261024','section_server.py','server.log')
    wait_ready('http://192.168.137.2:8852/status',lambda d:not d.get('active') and not d.get('error'),12)
    print(json.dumps(dict(board_ready=True, health=status, pc_next='candidates/usb_fast_infer2/start.ps1'), indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Offline binding/payload/syntax check only')
    mode.add_argument('--apply', action='store_true', help='Restore only after a fresh reserved boot and network setup')
    args = parser.parse_args()
    payloads = plan()
    print(json.dumps(dict(offline_check_passed=True, files=[len(p) for p in payloads],
                          raw_bytes=[sum(map(len, p.values())) for p in payloads],
                          cold_boot_hardware_tested=False), indent=2), flush=True)
    if args.apply:
        apply(*payloads)


if __name__ == '__main__':
    main()
