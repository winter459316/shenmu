"""Archive the independent trial and finite evidence; preserve all prior archives."""
from pathlib import Path
import hashlib,json,zipfile
R=Path(__file__).resolve().parent;P=R.parents[1];E=P/'experiments/fast_iter2_20261020'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf8'))
cp=read(R/'LATEST_CHECKPOINT.json');assert cp['status'].startswith('active separate two')
assert read(R/'preservation_verified.json')['passed']
assert all(sha(P/n)==v for n,v in read(E/'preserved.json').items())
suffix={'.py','.cpp','.json','.txt','.ps1','.js','.css','.html','.so','.onnx','.bin'}
exclude={'host_process.json','archive_verified.json','release_sources_sha256.json'}
files={p for p in R.iterdir() if p.is_file() and p.suffix in suffix and p.name not in exclude}
files.update(p for p in E.iterdir() if p.is_file() and p.suffix in {'.py','.json','.npy','.onnx','.txt'})
files.update(p for p in (R/'micro').iterdir() if p.is_file())
for c in cp['comparison']['cases']:
    for folder,job in [('captures',c['job_id']),('baseline_captures',c['baseline4_job_id']),('baseline_captures',c['baseline8_job_id'])]:
        files.update(p for p in (R/folder/job).iterdir() if p.is_file() and p.suffix in {'.json','.npz','.html','.png','.ply'})
assert all(p.is_relative_to(P) for p in files)
assert not any(('private' in p.name.lower() and p.name!='compress_completed_private_board.py') or 'snapshot' in p.name.lower() for p in files)
manifest={p.relative_to(P).as_posix():sha(p) for p in sorted(files)}
mp=R/'release_sources_sha256.json';mp.write_text(json.dumps(manifest,indent=2));files.add(mp)
archive=P/'releases'/cp['release_name'];assert not archive.exists()
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
    for p in sorted(files):z.write(p,p.relative_to(P).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
digest=sha(archive)
archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
result=dict(passed=True,archive=str(archive),sha256=digest,files=len(files),bytes=archive.stat().st_size,
            inherited_hardware_source_archive='usb_fast_mixed_experiment_20261020.zip',
            inherited_hardware_archive_sha256='5986cee5450fa078c8a0b301a6d046c9cdef98177a931ca3a7c2749f74c80260',
            private_snapshots_included=False)
(R/'archive_verified.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
