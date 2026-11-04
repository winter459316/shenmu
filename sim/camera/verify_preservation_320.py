import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_full'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
baseline=json.loads((ROOT/'SOURCE_BASELINE_SHA256.json').read_text())
# Mutable host state is runtime evidence, not source.
excluded={'live_host.json','live_latest.json'}
changes=[n for n,v in baseline.items() if n not in excluded and sha(OLD/n)!=v]
assert not changes,changes
archive=OLD/'checkpoints/usb_photo_speed_20261016_225517.zip'
assert sha(archive)=='6d450eb7df9c9046beba4c4672013b44a20f2fdcc3bf0d80c8a7868bc1b84200'
report={'passed':True,'original_usb_files_unchanged':len(baseline)-len(excluded),'old_archive':str(archive),'old_archive_sha256':sha(archive),
        'scope':'Original USB source and its accepted stable checkpoint. All writes for 320 source/builds are in the independent usb_320 candidate; original OV5640 and 7020 projects were not edited.'}
(ROOT/'board_evidence/preservation_320_verified.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
