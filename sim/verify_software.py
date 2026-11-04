"""Replay saved board arrays through the relocated host exporter, offline."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.runtime/zu4ev_stereo'
sys.path.insert(0,str(RUNTIME/'candidates/usb_fast_infer2'))
sys.path.insert(0,str(RUNTIME/'candidates/usb_320_hdmifps'))
from export_capture import export
import export_capture, mesh_limits, viewer_export


def main():
    for module in (export_capture,mesh_limits,viewer_export):
        assert Path(module.__file__).resolve().is_relative_to(RUNTIME.resolve()),module.__file__
    assets=ROOT/'private_runtime'
    if not assets.is_dir():assets=ROOT.parent/'private_runtime'
    fixture=assets/'sample/3ddbe9fdd3534aeb904db25b38fc322c/board_result.npz'
    digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as folder:
        capture=Path(folder)/fixture.parent.name
        capture.mkdir()
        shutil.copyfile(fixture,capture/fixture.name)
        status=json.loads((fixture.parent/'board_status.json').read_text(encoding='utf8'))
        status['replay_only']=True
        export(capture,status)
        with np.load(capture/'geometry.npz',allow_pickle=False) as output, np.load(fixture,allow_pickle=False) as source:
            for key in ('xyz_mm','valid','disparity'):
                assert output[key].dtype==source[key].dtype and output[key].shape==source[key].shape
                assert output[key].tobytes()==source[key].tobytes(),key
            assert output['faces'].ndim==2 and output['faces'].shape[1]==3
        for name in ('viewer.html','points.ply','dense_surface.ply','depth.png','disparity.png'):
            assert (capture/name).is_file() and (capture/name).stat().st_size>0,name
        assert hashlib.sha256((capture/fixture.name).read_bytes()).hexdigest()==digest
    assert hashlib.sha256(fixture.read_bytes()).hexdigest()==digest
    evidence=dict(passed=True,scope='Relocated saved-data export; no board or new hardware execution',
                  input_sha256=digest,coordinate_arrays_byte_exact=True,viewer_and_exports_generated=True,
                  python=sys.version.split()[0], imports_within_relocated_runtime=True)
    reports=ROOT/'sim/results';reports.mkdir(exist_ok=True)
    (reports/'software_offline.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':main()
