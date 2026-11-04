"""Preserve the accepted runtime and copy editable files to an isolated candidate."""
import datetime,hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEST=ROOT.parent/'usb_320_linefill'
assert not DEST.exists(), 'Candidate already exists; do not overwrite'
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
latest=json.loads((ROOT/'live_latest.json').read_text(encoding='utf8'))
photo=ROOT/'live_captures'/latest['job_id']
files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.cpp','.c','.h','.hpp','.tcl','.html','.so','.json','.txt','.npz','.bin')]
files += [p for p in (ROOT/'hdmi_v1').iterdir() if p.is_file() and p.suffix in ('.tcl','.v','.sv','.xdc','.rpt','.txt','.bif')]
files += [p for p in photo.iterdir() if p.is_file()]
manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
backup=ROOT/'checkpoints'/('before_linefill_'+stamp+'.zip')
with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
    for p in files:z.write(p,p.relative_to(ROOT).as_posix())
    z.writestr('ARCHIVE_SHA256.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(backup) as z:
    assert z.testzip() is None
    for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
DEST.mkdir()
for p in files:
    if p.parent==ROOT or p.parent==ROOT/'hdmi_v1':
        target=DEST/p.relative_to(ROOT);target.parent.mkdir(exist_ok=True);shutil.copy2(p,target)
(DEST/'board_evidence').mkdir()
(DEST/'baseline_sha256.json').write_text(json.dumps(manifest,indent=2))
record={'passed':True,'backup':str(backup),'sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),
        'files':len(files),'photo':latest['job_id'],'candidate':str(DEST)}
(DEST/'STABLE_BACKUP.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record),flush=True)
