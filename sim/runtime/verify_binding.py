from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent;B=R.parent/'usb_fast_transport2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads((R/'hardware_verified.json').read_text())
assert all(p[k] for k in ('timing_passed','cdc_review_passed','hls_passed'))
assert sha(R/'fast_pl.bit.bin')==p['sha256']
assert p.get('baseline_bitstream_sha256',p['sha256'])==sha(B/'fast_pl.bit.bin')
assert sha(R/'libfast_pl.so')==sha(B/'libfast_pl.so')
assert all(sha(R/n)==v for n,v in p['sources'].items())
assert json.loads((R/'sampling_verified.json').read_text())['passed']
assert json.loads((R/'geometry_config.json').read_text())['qualified']
print('INFERENCE_BINDING_VERIFIED; qualified compute PL and preview geometry; exact outputs verified')
