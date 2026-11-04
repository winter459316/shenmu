"""Build a separate release, retaining the meshguard source and held photo."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'usb_320_meshguard'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
preserved={p.name:sha(p) for p in OLD.iterdir() if p.is_file() and p.suffix in ('.py','.so','.json','.html','.npz') and 'private' not in p.name and p.name!='live_host.json'}
(ROOT/'PRESERVED_MESHGUARD_SHA256.json').write_text(json.dumps(preserved,indent=2))
assert sha(OLD/'mesh_guard_20261017.zip')=='c9126f67d4b43045f14a5fd174179582028785daf926d9ef6487dfa220248cd8'
for p in OLD.iterdir():
    if p.is_file() and p.suffix in ('.html','.js','.css'):
        shutil.copy2(p,ROOT/p.name)
bit=ROOT.parent/'usb_320_display/usb320.bit.bin'
assert sha(bit)=='1040bc3c95d76794e479d8d039f21cbfebc3086e838c507afe81a4e971c6d0b4'
shutil.copy2(bit,ROOT/bit.name)
for name in ('hardware_320_verified.json',):
    if not (ROOT/name).exists():shutil.copy2(ROOT.parent/'usb_320'/name,ROOT/name)
job='dbad4e94a767485eb050e2f0c31984b8'
photo=OLD/'live_captures'/job/'board_result.npz'
shutil.copy2(photo,ROOT/'held_restore.npz')
record={'job_id':job,'sha256':sha(photo),'bytes':photo.stat().st_size}
(ROOT/'held_restore.json').write_text(json.dumps(record,indent=2))
# Existing historical modules must not look up a different release's loaded state.
p=ROOT/'board_dma.py';text=p.read_text();text=text.replace("Path('/tmp/usb_stereo_probe/usb320_dense3d/dma.fault')","(Path(__file__).resolve().parent/'dma.fault')")
text=text.replace("Path('/tmp/usb_stereo_probe/usb320_dense3d/loaded.json')","(Path(__file__).resolve().parent/'loaded.json')");p.write_text(text)
p=ROOT/'deploy.py';p.write_text(p.read_text().replace('/usb320_meshguard','/usb320_exposure'))
p=ROOT/'cold_start_board.py';text=p.read_text().replace("USB_RESTORE_HELD='0'","USB_RESTORE_HELD='1'").replace("request(8768,","request(8788,")
p.write_text(text)
for p in ROOT.glob('*.py'):compile(p.read_text(encoding='utf8'),str(p),'exec')
print('Separate exposure candidate prepared; original source and archive preserved.')
