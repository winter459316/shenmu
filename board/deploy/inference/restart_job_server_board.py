"""Restart only the idle candidate API after source/proof deployment."""
from pathlib import Path
import fcntl,os,signal,subprocess,time
R=Path(__file__).resolve().parent
from start_runtime_board import running
if __name__=='__main__':
    with (R.parent/'fast_pl/capture.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (R/'pl_test_private_snapshot.json').exists()
        for pid in running('fast_job_server.py'):
            os.kill(pid,signal.SIGTERM)
            for _ in range(50):
                proc=Path('/proc')/str(pid)
                if not proc.exists() or '\nState:\tZ' in (proc/'status').read_text():break
                time.sleep(.1)
            else:raise TimeoutError('Candidate API did not stop')
        subprocess.run(['python3',str(R/'start_runtime_board.py')],check=True,timeout=40)
        print('CONV_JOB_API_RESTARTED',flush=True)
