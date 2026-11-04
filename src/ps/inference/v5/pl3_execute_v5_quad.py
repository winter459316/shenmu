"""Production bridge lifecycle under the existing one-photo capture lease."""
from pathlib import Path
import ctypes as C
import fcntl
import hashlib
import json
import os
import sys
import time

os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='4')
R = Path(__file__).resolve().parent
H = R.parent/'pl_pipeline_20261025'
sys.path.insert(0,str(R.parent/'fast_board/deps'))
sys.path.insert(0,str(R.parent/'usb320_hdmifps'))
sys.path.insert(0, str(H))
import pause_preview_board as preview
import test_hardware_board as h
from usable_v5_quad_physical_bridge_20261028 import PhysicalBridge


def configuration():
    p = H/'pl3_usable_v5_quad_manifest_20261028.json'
    m = json.loads(p.read_text())
    assert m['mode'] == 'usable_pl2_pl3_v5_quad' and m['numerical_policy'] == 'preserve_existing_results'
    for name, digest in m['files'].items():
        assert Path(name).name == name
        assert hashlib.sha256((H/name).read_bytes()).hexdigest() == digest, name
    for name, digest in m['stable_files'].items():
        assert hashlib.sha256((R/name).read_bytes()).hexdigest() == digest, name
    for name, source in m['board_aliases'].items():
        assert hashlib.sha256((R/name).read_bytes()).hexdigest() == m['files'][source], name
    return m


def execute(runtime, job, feed):
    assert runtime.pl3_manifest == json.loads((H/'pl3_usable_v5_quad_manifest_20261028.json').read_text())
    saved = json.loads(h.SNAP.read_text())
    owner = saved['pl3_runtime_owner']
    assert owner['job_id'] == job
    capture_paths = [R.parent/'fast_pl/capture.lock', R/'capture.lock']

    with (R/'resident_switch.lock').open('a+') as switch:
        fcntl.flock(switch, fcntl.LOCK_EX | fcntl.LOCK_NB)

        def owned():
            assert not switch.closed
            stat = (Path('/proc')/str(owner['pid'])/'stat').read_text().split(') ', 1)[1].split()
            assert stat[19] == owner['start'] and stat[0] != 'Z', 'Capture owner exited or PID changed'
            locks = [line.split() for line in Path('/proc/locks').read_text().splitlines() if '->' not in line]
            for path in capture_paths:
                inode = path.stat().st_ino
                assert any(len(row)>5 and row[1:4] == ['FLOCK','ADVISORY','WRITE'] and
                    int(row[4]) == owner['pid'] and int(row[5].split(':')[-1]) == inode for row in locks), str(path)

        owned()
        bridge = PhysicalBridge(H/'libfastpl3_hook_20261028.so', H, runtime.pl3_manifest, owned, job)
        calls_before = bridge.library.fastpl3_calls()
        try:
            bridge.arm(saved)
            began = time.monotonic()
            d = runtime.session.run(None, feed)[0][0, 0, 12:-12, :].copy()
            elapsed = time.monotonic()-began
            assert not bridge.active() and not bridge.errors and not bridge.failed_native_states
            assert len(bridge.records) == 3 and bridge.library.fastpl3_calls()-calls_before == 3
            detail = dict(enabled=True, candidate_sha256=bridge.qualified['sha256'],
                clock_mhz=bridge.qualified['clock_mhz'], nodes=bridge.records,
                interval=bridge.interval, commands=sum(row['commands'] for row in bridge.records),
                backend='PL3 exact FP32 Conv3D MAC; PS bias and existing activations',
                automatic_switch=True, speedup_qualified=False)
            return d, elapsed, detail
        finally:
            if bridge.active():
                bridge.recover_or_guard(RuntimeError('Inference exited inside the PL3 interval'))
            bridge.close()
