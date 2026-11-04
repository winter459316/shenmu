"""Recover an interrupted candidate transaction only after inference is idle."""
from pathlib import Path
import fcntl,json
import test_hardware_board as h
import pause_preview_board as preview
from resident_switch_board import worker
if __name__=='__main__':
    with (h.R.parent/'fast_pl/capture.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert h.SNAP.exists(),'No unfinished candidate transaction'
        worker(h.R) # Reject a busy or unexpectedly owned model process.
        assert not (h.R.parent/'fast_pl/dma.fault').exists(),'Inspect outstanding DMA before recovery'
        saved=json.loads(h.SNAP.read_text())
        active=h.R/'configuration_state.json'
        if active.exists() and json.loads(active.read_text())['new']:h.reconfigure(False,saved)
        (h.R/'loaded.json').write_text(json.dumps(dict(state='inactive',stable_restored_sha256=h.OLD_SHA)))
        try:frozen=preview.process_state(saved['owners']['full_camera.py']) in ('T','t')
        except FileNotFoundError:frozen=False
        if frozen:preview.resume(saved)
        else:
            current=h.owners()
            if 'full_camera.py' in current:assert current['full_camera.py']==saved['owners']['full_camera.py']
            assert all(Path(v['cwd']).resolve()==h.S for v in current.values())
            h.stop(current);h.restore_services(saved)
        h.SNAP.replace(h.R/'pl_test_private_completed.json')
        print('FAST_PAUSE_RECOVERED',flush=True)
