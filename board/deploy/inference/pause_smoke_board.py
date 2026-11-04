from pathlib import Path
import fcntl,hashlib,http.client,json,sys,time
import test_hardware_board as h
import pause_preview_board as p
if __name__=='__main__':
    assert sys.argv[1:] in (['stay'],['switch'])
    with (h.R.parent/'fast_pl/capture.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        saved=p.prepare();start=time.monotonic();new=False
        try:
            p.pause(saved)
            if sys.argv[1]=='switch':h.reconfigure(True,saved);new=True;time.sleep(2);h.reconfigure(False,saved);new=False
        finally:
            if new:h.reconfigure(False,saved)
            report=p.resume(saved)
            h.SNAP.replace(h.R/'pl_test_private_completed.json')
        c=http.client.HTTPConnection('192.168.137.2',8788,timeout=20,source_address=('127.0.0.1',0))
        try:c.request('GET','/stereo/result.npz?id='+saved['held']['job_id']);r=c.getresponse();assert r.status==200;assert hashlib.sha256(r.read()).hexdigest()==saved['held']['sha256']
        finally:c.close()
        assert report['camera_process_preserved']
        output=dict(passed=True,mode=sys.argv[1],seconds=time.monotonic()-start,held_bytes_hash_exact=True,camera_process_preserved=True,camera_pid=report['camera_pid'],hdmi_error=report['hdmi']['error'])
        (h.R/('pause_smoke_'+sys.argv[1]+'.json')).write_text(json.dumps(output,indent=2));print(json.dumps(output),flush=True)
