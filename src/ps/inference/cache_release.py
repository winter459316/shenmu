"""Release only this candidate's temporary image buffers after verified PC receipt."""
from pathlib import Path
import hashlib,json,re
def acknowledge(root,job,digest):
    assert re.fullmatch('[0-9a-f]{32}',job) and re.fullmatch('[0-9a-f]{64}',digest)
    folder=Path(root)/job
    assert folder.is_dir() and not folder.is_symlink() and folder.resolve().parent==Path(root).resolve()
    status_path=folder/'status.json';status=json.loads(status_path.read_text())
    assert status['job_id']==job and status['stage']=='ready' and not status['busy'] and status['package_sha256']==digest
    receipt=folder/'pc_receipt.json';result=folder/'result.npz'
    if receipt.exists():assert json.loads(receipt.read_text())==dict(job_id=job,package_sha256=digest,pc_copy_verified=True)
    else:
        assert hashlib.sha256(result.read_bytes()).hexdigest()==digest
        temp=folder/'pc_receipt.tmp';temp.write_text(json.dumps(dict(job_id=job,package_sha256=digest,pc_copy_verified=True)));temp.replace(receipt)
    freed=0
    for name in ('input.png','rectified.npz','result.npz'):
        path=folder/name
        if path.exists():
            assert path.is_file() and not path.is_symlink();freed+=path.stat().st_size;path.unlink()
    status['cache_released_to_pc']=True;temp=folder/'status.tmp';temp.write_text(json.dumps(status,indent=2));temp.replace(status_path)
    return dict(released=True,job_id=job,package_sha256=digest,freed_bytes=freed)
