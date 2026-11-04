"""Preserve one native photo for finite hardware/quality comparison."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
old=ROOT.parent/'usb_full/live_captures/6fc7677660f5402da1aeae97794a12e4/board_result.npz'
with np.load(old,allow_pickle=False) as z:
    frame=z['frame_bgr'];assert frame.shape==(480,1280,3)
    np.savez(ROOT/'native_test_frame.npz',frame=frame)
record={'source_job':'6fc7677660f5402da1aeae97794a12e4','source_package_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),
    'native_frame_sha256':hashlib.sha256(frame.tobytes()).hexdigest(),'test_input_sha256':hashlib.sha256((ROOT/'native_test_frame.npz').read_bytes()).hexdigest()}
(ROOT/'case_320.json').write_text(json.dumps(record,indent=2));print(record)
