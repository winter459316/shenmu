"""Publish the two-iteration trial without changing preserved four/eight artifacts."""
from pathlib import Path
from datetime import datetime
import ast,hashlib,json,shutil,urllib.request
R=Path(__file__).resolve().parent;P=R.parents[1];E=P/'experiments/fast_iter2_20261020'
B4=R.parent/'usb_fast_mixed4';B8=R.parent/'usb_fast_mixed';S=R.parent/'usb_fast_fused'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
write=lambda p,v:p.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf8')
data=read(R/'replays_verified.json');cases=data['cases']
assert data['functional_passed'] and len(cases)==2 and all(c['reference2']['passed'] for c in cases)
assert all(c['mixed_pl']['integer_stage_calls']==5 and c['mixed_pl']['fp32_fallback_blocks']==0 for c in cases)
means={}
for count,prefix in [(2,''),(4,'baseline4_'),(8,'baseline8_')]:
    means[str(count)]={k:sum(c[prefix+k] for c in cases)/len(cases) for k in ['forward_seconds','total_seconds']}
assert means['2']['forward_seconds']<means['4']['forward_seconds']
assert means['2']['total_seconds']<means['4']['total_seconds']
preserved=read(E/'preserved.json')
changed=[n for n,v in preserved.items() if sha(P/n)!=v]
assert not changed,changed
for root in (R,E):
    for p in root.glob('*.py'):ast.parse(p.read_text(encoding='utf8'),filename=str(p))
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with op.open('http://192.168.137.2:8850/health',timeout=5) as f:assert json.load(f)['ready']
with op.open('http://192.168.137.2:8788/status',timeout=5) as f:
    camera=json.load(f);assert not camera.get('error') and not camera['standby']
for c in cases:
    for root,key in [(B4,'baseline4_job_id'),(B8,'baseline8_job_id')]:
        shutil.copytree(root/'captures'/c[key],R/'baseline_captures'/c[key],dirs_exist_ok=True)
comparison=dict(data,means=means,
    reductions_vs4={k:100*(means['4'][k]-means['2'][k])/means['4'][k] for k in means['2']},
    reductions_vs8={k:100*(means['8'][k]-means['2'][k])/means['8'][k] for k in means['2']},
    interpretation='Changes from four/eight iterations, not ground-truth error; only two saved scenes.',
    baseline_method='Previously measured identical images on the same mixed PL/native architecture; no new shutter')
write(R/'comparison_data.json',comparison)
hw=read(R/'hardware_verified.json')
state=dict(name='Fast mixed2 trial',date=datetime.now().astimezone().isoformat(),
    status='active separate two-iteration trial; four/eight sources, captures and archives preserved',
    pc_url='http://127.0.0.1:8849/',comparison_url='http://127.0.0.1:8849/comparison.html',
    board_api='http://192.168.137.2:8850',board_runtime='/tmp/usb_stereo_probe/fast_infer2',
    input_wh=[320,360],iterations=2,max_disparity=192,hardware_unchanged_from='usb_fast_mixed',
    bit_sha256=hw['sha256'],model_sha256=hw['sources']['fast_pl.onnx'],
    library_sha256=hw['sources']['libfast_pl.so'],resources=hw['resources'],comparison=comparison,
    no_new_shutter=True,persistent_boot_changed=False,
    original_stable='usb_fast_fused / PC8829 / API8830; model inactive while trial is active',
    rollback='When idle: python3 /tmp/usb_stereo_probe/fast_infer2/resident_switch_board.py rollback; then PC8833',
    phase_scope='PL rectification +5 INT16 convs +2 FP32 deconvs; PS remaining network and XYZ; PC meshes and displays. Idle preview/HDMI/PL_KEY2 remain original usb320_hdmifps.',
    release_name='usb_fast_infer2_trial_20261020.zip')
write(R/'LATEST_CHECKPOINT.json',state)
write(R/'preservation_verified.json',dict(passed=True,protected_files=len(preserved),
    protected_artifacts=preserved,latest4=read(B4/'latest.json')['job_id'],latest8=read(S/'latest.json')['job_id']))
summary=f"""ACTIVE SEPARATE TWO-ITERATION TRIAL; four-iteration trial and eight-iteration stable are preserved.
PC8849 / board8850 / RAMfast_infer2. Use the web capture button.
Actual two recurrent updates; both disparity and final mask use the second hidden state.
Same PL/native as mixed8. Mean inference 8/4/2: {means['8']['forward_seconds']:.3f}/{means['4']['forward_seconds']:.3f}/{means['2']['forward_seconds']:.3f}s.
Mean board flow 8/4/2: {means['8']['total_seconds']:.3f}/{means['4']['total_seconds']:.3f}/{means['2']['total_seconds']:.3f}s.
Differences are recorded; no ground-truth accuracy claim.
Rollback to four when idle: python3 /tmp/usb_stereo_probe/fast_infer2/resident_switch_board.py rollback
Then open PC8833. Four's own rollback can subsequently restore fused8 / PC8829.
Only one model is resident. Opening an old web page does not restart its model.
Camera/HDMI/physical PL_KEY2 retain the original non-Fast flow.
No new shutter, hardware rebuild or persistent boot changes.
"""
(R/'CURRENT_STATE.txt').write_text(summary,encoding='utf8')
write(E/'WORKING_STATE.json',dict(status=state['status'],candidate=str(R),comparison=comparison,
    remaining='Finite validation complete',stable_preserved=True))
entry=f"- Active Fast2 trial (2026-10-20): `candidates/usb_fast_infer2`, PC8849 / comparison.html, board8850/RAMfast_infer2. User requested2iterations. Actual graph pruning4->2, both disparity and mask hidden state rewired; independent original PyTorch2 validated. Same qualified mixed8 bit/native;5 INT16 convs +2 FP32 deconvs remain PL. Two saved photos: mean forward {means['2']['forward_seconds']:.3f}s, board flow {means['2']['total_seconds']:.3f}s. Local disparities change relative to4/8; no identical-accuracy claim. Previous four/eight source/latest/captures/archives hash-preserved, workers inactive for RAM. Rollback with mixed2 resident_switch_board.py rollback then PC8833; subsequent mixed4 rollback restores fused8/PC8829. Read CURRENT_STATE/LATEST_CHECKPOINT. Idle preview/HDMI/physicalPL_KEY2 remain original API8788. No new shutter or boot changes; private recovery snapshots board-only.\n\n"
path=P/'AGENTS.md';text=path.read_text(encoding='utf8');assert '- Active Fast2 trial (2026-10-20):' not in text
path.write_text(text.replace('# ZU4EV migration\n\n','# ZU4EV migration\n\n'+entry,1),encoding='utf8')
print(summary,flush=True)
