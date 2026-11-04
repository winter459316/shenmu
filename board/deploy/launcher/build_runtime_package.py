"""Build a runtime-only bundle from explicit bindings; no historical projects."""
from pathlib import Path
import hashlib,json,shutil,sys,zipfile

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'handoff'))
from check_current import local_checks

def build(destination):
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError('Use a fresh output directory: '+str(destination))
    destination.mkdir(parents=True)
    target=destination/'zu4ev_stereo';target.mkdir()
    checks=local_checks();assert checks['passed']
    paths={P/k for k in checks['checks'] if (P/k).is_file()}
    def direct(directory):
        paths.update(p for p in (P/directory).iterdir() if p.is_file() and p.suffix not in ('.log','.zip','.jpg','.png','.mp4') and p.name not in ('latest.json','host_process.json','replay_job.json'))
    for d in ('candidates/usb_fast_infer2','candidates/usb_320_hdmifps','experiments/cnn_stereo_20261018','experiments/pl_pipeline_20261025/usable_v5_quad','launcher'):
        direct(d)
    for d in ('candidates/usb_fast_infer2/micro','candidates/usb_fast_infer2/section_payload','experiments/usb_camera_20261016/deps/serial'):
        paths.update(p for p in (P/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for n in ('HANDOFF_NEXT_CHAT.txt','AGENTS.md','handoff/check_current.py','handoff/restore_fresh_ram.py','experiments/geometry_fast_20261024/promotion_verified.json','candidates/usb_full/boot_reserved.py','experiments/usb_camera_20261016/board_console.py','experiments/usb_camera_20261016/deploy_receive.py','experiments/pl_pipeline_20261025/transfer.py'):
        paths.add(P/n)
    paths.update(P.glob('*.cmd'))
    paths.update((P/'experiments/fast_board_20261018').glob('*.whl'))
    paths.update((P/'experiments/switch_latency_20261030').glob('*.py'))
    paths.update((P/'experiments/switch_latency_20261030').glob('*manifest*.json'))
    u=P/'experiments/pl_pipeline_20261025/usable_v5_quad'
    for value in json.loads((u/'payload_local.json').read_text()).values():paths.add(Path(value))
    # Include manifest-referenced installer files even when not Python.
    for manifest in (P/'experiments/switch_latency_20261030').glob('*manifest*.json'):
        for key in json.loads(manifest.read_text()):
            f=manifest.parent/key
            if f.is_file():paths.add(f)
    entries={}
    for p in sorted(paths):
        relative=p.resolve().relative_to(P.resolve())
        q=target/relative;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        entries[relative.as_posix()]=hashlib.sha256(q.read_bytes()).hexdigest()
    (target/'runtime_manifest.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf8')
    (destination/'README.md').write_bytes((P/'launcher/README.md').read_bytes())
    print(json.dumps({'directory':str(destination),'files':len(entries),'bytes':sum((target/n).stat().st_size for n in entries)},ensure_ascii=False))

if __name__=='__main__':build(sys.argv[1])
