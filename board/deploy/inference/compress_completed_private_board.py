"""Losslessly compress completed recovery history locally; never export its contents."""
from pathlib import Path
import fcntl,gzip,hashlib,json,os,shutil,zlib
R=Path(__file__).resolve().parent
def digest_stream(f):
    h=hashlib.sha256()
    for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
if __name__=='__main__':
    with (R.parent/'fast_pl/capture.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=after=count=0
        for name in ('fast_pl','fast_lite','fast_pipeline','fast_conv','fast_infer2'):
            root=R.parent/name
            if not root.is_dir():continue
            assert not (root/'pl_test_private_snapshot.json').exists(),'Do not touch an unfinished transaction'
            for p in root.glob('pl_test_private_completed*.json'):
                assert p.is_file() and not p.is_symlink() and p.resolve().parent==root
                with p.open('rb') as f:original=digest_stream(f)
                target=p.with_name(p.name+'.'+original[:16]+'.gz')
                valid=False
                if target.exists():
                    try:
                        with gzip.open(target,'rb') as f:valid=digest_stream(f)==original
                    except (OSError,EOFError,zlib.error):pass
                if not valid:
                    temp=target.with_name(target.name+'.writing')
                    if temp.exists():temp.unlink()
                    fd=os.open(str(temp),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                    with os.fdopen(fd,'wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1) as zipped,p.open('rb') as source:shutil.copyfileobj(source,zipped,1024*1024)
                    with gzip.open(temp,'rb') as f:assert digest_stream(f)==original
                    temp.replace(target)
                with gzip.open(target,'rb') as f:assert digest_stream(f)==original
                before+=p.stat().st_size;after+=target.stat().st_size;count+=1
                p.unlink() # Complete, byte-verified .gz can restore the original private JSON.
        report=dict(passed=True,files=count,original_bytes=before,compressed_bytes=after,saved_bytes=before-after,contents_exported=False,boot_storage_changed=False)
        (R/'ram_compression_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
