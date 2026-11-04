"""Independent PC check of the fixed-photo v4 full-pipeline board export."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'experiments/usb_camera_20261016/deps'))
import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    hdmi='--hdmi' in sys.argv
    prefix='hdmi_full' if hdmi else 'sgm_v4_full'
    evidence = ROOT / 'board_evidence'
    primary_path = evidence / 'full_pipeline_result.npz'
    surface_path = evidence / 'surface_result.npz'
    result_path = evidence / (prefix+'_result.npz')
    assert digest(primary_path) == '7b2937f1b76895516c79b4047406474c146214aeb3d16033d16ef3cc515cbabd'
    assert digest(surface_path) == 'fd5a37bd3cbaf0e2b7e2210c78e79f1306fffe5bb6e43b98e0118f83c5fba8cc'
    board = json.loads((evidence / (prefix+'_verified.json')).read_text())
    for flag in ('passed', 'stable_restored', 'held_photo_unchanged',
                 'previous_standby_restored', 'fresh_preview_restored', 'full_pipeline'):
        assert board[flag] is True, flag
    assert board['shutter_triggered'] is False
    candidate='48350af24a1a760c9f555bd6e39c2d8a0216003a580d7c08204bab5e64c2c39d' if hdmi else '1b357aa3fe695f5f77239e8aedb85b4bb51accd4d3ab33867951d69750e99db1'
    assert board['candidate_sha256'] == candidate
    if hdmi:
        assert board['hdmi_drained'] and board['hdmi']['frames']==2
        assert not board['hdmi']['vdma_status']&0xff1
    meta = board['tests']['candidate']['metadata']
    assert meta['bitstream_sha256'] == board['candidate_sha256']
    assert meta['sgm_revision'] == 0x53574E34
    with np.load(primary_path, allow_pickle=False) as source:
        expected = {k: source[k] for k in source.files if k != 'metadata_json'}
    with np.load(surface_path, allow_pickle=False) as source:
        expected.update({'display_' + k: source[k] for k in source.files if k != 'metadata_json'})
    assert len(expected) == 51
    with np.load(result_path, allow_pickle=False) as result:
        assert set(result.files) == set(expected)
        checks = {k: (result[k].shape == v.shape and result[k].dtype == v.dtype
                      and result[k].tobytes() == v.tobytes()) for k, v in expected.items()}
    assert all(checks.values()), [k for k, value in checks.items() if not value]
    report = {'passed': True, 'array_count': len(checks), 'byte_exact_arrays': checks,
              'result_sha256': digest(result_path), 'primary_sha256': digest(primary_path),
              'surface_sha256': digest(surface_path), 'board_report_sha256': digest(evidence / (prefix+'_verified.json')),
              'full_capture_benchmarked': False, 'production_promoted': False,
              'stable_restored': True, 'held_photo_unchanged': True}
    (evidence / (prefix+'_pc_verified.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
