"""Recover only a missing stable key service after the exhausted temporary filesystem."""
from pathlib import Path
import fcntl,json,subprocess,sys,time
R=Path(__file__).resolve().parent;S=R.parent/'usb320_hdmifps';sys.path.insert(0,str(S))
from switch_320_board import owners,request
if __name__=='__main__':
    with (R.parent/'fast_pl/capture.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        current=owners();assert set(current)=={'full_camera.py'}
        camera=current['full_camera.py'];assert Path(camera['cwd']).resolve()==S
        assert not request(8788,'/stereo/status')['busy']
        assert json.loads((S/'loaded.json').read_text())['sha256']=='96802d44051c4bac8ce75704894771543e5dca4e94a77c4f6b460a6beb327af4'
        assert owners()==current
        # Reuse environment only inside the board; never print or export it.
        with (S/'physical_keys_recovery.log').open('ab',buffering=0) as log:
            p=subprocess.Popen(['python3','-u',str(S/'physical_keys.py'),'--pl'],cwd=str(S),env=camera['env'].copy(),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        for _ in range(50):
            assert p.poll() is None,'Key service exited; inspect its board-local log'
            try:
                status=json.loads((S/'physical_keys_status.json').read_text())
                if status.get('pid')==p.pid:break
            except (OSError,ValueError):pass
            time.sleep(.1)
        else:raise TimeoutError('Key service did not become ready')
        found=owners();assert set(found)=={'full_camera.py','physical_keys.py'} and found['full_camera.py']==camera
        (S/'physical_keys.pid').write_text(str(p.pid))
        print('STABLE_KEYS_RESTORED',p.pid,flush=True)
