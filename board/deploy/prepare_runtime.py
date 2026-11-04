"""Assemble modular sources + private assets without changing the live project."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,shutil,stat,tempfile,zipfile,time

ROOT=Path(__file__).resolve().parents[2]
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def safe(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or str(p)!=name:
        raise ValueError('Unsafe relative path: '+name)
    return p
def ensure_runtime_dirs(destination):
    # Captures are mutable user data and are deliberately absent from the
    # source/asset inventory. A fresh machine must still have their parents.
    for name in ('captures','recordings'):
        (destination/'candidates/usb_fast_infer2'/name).mkdir(parents=True,exist_ok=True)

def prepare(archive,root=ROOT):
    root=Path(root).resolve()
    source_map=json.loads((root/'board/config/source_map.json').read_text())
    assets=json.loads((root/'board/config/runtime_assets.json').read_text())['files']
    expected={}
    for item in source_map:
        name=item['runtime'];safe(name);safe(item['source'])
        if name in expected:raise ValueError('Duplicate source '+name)
        source=root/item['source']
        if source.is_symlink() or sha(source)!=item['sha256']:raise ValueError('Source differs from qualified export: '+item['source'])
        expected[name]=item['sha256']
    for name,info in assets.items():
        safe(name)
        if name in expected:raise ValueError('Source/asset collision')
        expected[name]=info['sha256']
    destination=root/'.runtime/zu4ev_stereo'
    if destination.exists():
        for name,digest in expected.items():
            if sha(destination/name)!=digest:raise ValueError('Existing runtime changed; not overwritten: '+name)
        ensure_runtime_dirs(destination)
        print('Existing runtime verified; no files overwritten.');return destination
    with zipfile.ZipFile(archive) as z:
        members=z.infolist()
        if len(members)!=len(assets) or {m.filename for m in members}!=set(assets):raise ValueError('Asset inventory mismatch')
        if sum(m.file_size for m in members)>1024**3:raise ValueError('Asset package exceeds contract limit')
        for m in members:
            safe(m.filename)
            if stat.S_ISLNK(m.external_attr>>16) or m.file_size!=assets[m.filename]['bytes']:raise ValueError('Invalid asset entry')
        base=root/'.runtime';base.mkdir(exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='assembling_',dir=base))
        # Interrupted/failed staging is left for inspection; never overwrite a partial deployment.
        for item in source_map:
            target=staging/item['runtime'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(root/item['source'],target)
        for m in members:
            target=staging/m.filename;target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(m) as inp,target.open('xb') as out:shutil.copyfileobj(inp,out,1024*1024)
            if sha(target)!=assets[m.filename]['sha256']:raise ValueError('Asset digest mismatch: '+m.filename)
        for name,digest in expected.items():
            if sha(staging/name)!=digest:raise ValueError('Assembled file mismatch: '+name)
        (staging/'runtime_manifest.json').write_text(json.dumps(expected,indent=2),encoding='utf8')
        # Windows indexers/scanners may briefly retain a handle after extraction.
        # Retry only the atomic commit; never merge or overwrite a destination.
        for attempt in range(12):
            if destination.exists():raise FileExistsError('Runtime appeared during assembly; inspect both directories')
            try:
                staging.rename(destination)
                break
            except PermissionError:
                if os.name!='nt' or attempt==11:raise
                time.sleep(min(.2*(attempt+1),1.0))
    ensure_runtime_dirs(destination)
    print('Runtime assembled:',destination,'files:',len(expected));return destination

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True)
    prepare(p.parse_args().assets)
