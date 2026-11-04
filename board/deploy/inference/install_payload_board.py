"""Install the bound payload atomically; model uses a separate volatile RAM filesystem."""
from pathlib import Path
import fcntl,hashlib,json,os,re,shutil,zipfile
def install(digest):
    assert re.fullmatch('[0-9a-f]{64}',digest)
    p=Path('/tmp/usb_stereo_probe/deploy.zip');assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
    d=p.parent/'fast_infer2';d.mkdir(exist_ok=True)
    store=Path('/dev/shm/usb_fast_infer2');assert not store.is_symlink();store.mkdir(mode=0o700,exist_ok=True)
    assert store.stat().st_uid==0 and store.resolve()==store
    # /dev/shm on this image belongs to devtmpfs, also RAM backed; never use boot storage.
    assert any(line.split()[1]=='/dev' and line.split()[2]=='devtmpfs' for line in Path('/proc/mounts').read_text().splitlines())
    with (p.parent/'fast_pl/capture.lock').open('a+') as global_lock,(d/'capture.lock').open('a+') as lock:
        for f in (global_lock,lock):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (d/'pl_test_private_snapshot.json').exists()
        jobs=d/'jobs';stored_jobs=store/'jobs'
        if jobs.is_dir() and not jobs.is_symlink():
            assert jobs.resolve()==d.resolve()/'jobs' and not stored_jobs.exists()
            shutil.move(str(jobs),str(stored_jobs))
        stored_jobs.mkdir(exist_ok=True)
        if not jobs.exists():jobs.symlink_to(stored_jobs,target_is_directory=True)
        assert jobs.resolve()==stored_jobs
        completed=sorted(d.glob('pl_test_private_completed_*.json'),key=lambda p:p.stat().st_mtime)
        if completed:
            assert len(completed)==1 and not (d/'pl_test_private_completed.json').exists()
            completed[0].replace(d/'pl_test_private_completed.json')
        with zipfile.ZipFile(p) as z:
            assert all((('/' not in n and '..' not in n) or n in ('micro/0_cpu.onnx','micro/1_cpu.onnx','replay_sources/ee92f94446ea4a0eaedcf029e852871c/input.png','replay_sources/ee92f94446ea4a0eaedcf029e852871c/result.npz')) for n in z.namelist())
            (d/'micro').mkdir(exist_ok=True)
            (d/'replay_sources/ee92f94446ea4a0eaedcf029e852871c').mkdir(parents=True,exist_ok=True)
            if 'fast_layout.onnx' in z.namelist():assert not (d/'infer.sock').exists(),'Install before model activation; do not replace an active model'
            for n in z.namelist():
                data=z.read(n);target=store/n if n in ('fast_pl.onnx','fast_layout.onnx','fast_sample.onnx') else d/n
                if not target.is_file() or hashlib.sha256(target.read_bytes()).digest()!=hashlib.sha256(data).digest():
                    temp=target.with_name(target.name+'.deploytmp');temp.write_bytes(data);temp.replace(target)
                if n in ('fast_pl.onnx','fast_layout.onnx','fast_sample.onnx') and not (d/n).is_symlink():
                    temp=d/(n+'.deploylink');assert not temp.exists();temp.symlink_to(target);temp.replace(d/n)
        proof=json.loads((d/'hardware_verified.json').read_text());expected=dict(proof['sources']);expected['fast_pl.bit.bin']=proof['sha256']
        if not (d/'fast_pl.onnx').exists():
            original=d.parent/'fast_mixed2/fast_pl.onnx'
            assert hashlib.sha256(original.read_bytes()).hexdigest()==expected['fast_pl.onnx']
            (d/'fast_pl.onnx').symlink_to(original.resolve())
        if not (d/'fast_layout.onnx').exists():
            original=d.parent/'fast_transport2/fast_layout.onnx'
            assert hashlib.sha256(original.read_bytes()).hexdigest()==expected['fast_layout.onnx']
            (d/'fast_layout.onnx').symlink_to(original.resolve())
        assert all(hashlib.sha256((d/n).read_bytes()).hexdigest()==v for n,v in expected.items())
        p.unlink();print('CONV_PAYLOAD_VERIFIED',flush=True)
if __name__=='__main__':install(DEPLOY_SHA256)
