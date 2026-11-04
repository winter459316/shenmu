"""One preserved frame: independently verify actual 320 outputs and compare grids."""
import hashlib,json,time
from pathlib import Path
from live_verify import verify_arrays,verify_surfaces,np
from evaluate_reference import cv2
from render_saved import export_result
ROOT=Path(__file__).resolve().parent

def main():
    source=ROOT/'board_evidence/pipeline_320_result.npz'
    with np.load(source,allow_pickle=False) as z:a={k:z[k] for k in z.files}
    m=json.loads(a.pop('metadata_json').tobytes())
    expected=json.loads((ROOT/'case_320.json').read_text())
    assert m['native_frame_sha256_bgr']==expected['native_frame_sha256']
    with np.load(ROOT/'native_test_frame.npz') as z:frame=z['frame']
    low=np.concatenate([cv2.resize(frame[:,e*640:(e+1)*640],(320,360),interpolation=cv2.INTER_AREA) for e in (0,1)],axis=1)
    assert np.array_equal(low,a['frame_bgr'])
    primary=verify_arrays(a,m)
    b={k[8:]:v for k,v in a.items() if k.startswith('display_')}
    surface=verify_surfaces(a,b,m['surface_preparation'])
    old=ROOT.parent/'usb_full/live_captures/6fc7677660f5402da1aeae97794a12e4/board_result.npz'
    assert hashlib.sha256(old.read_bytes()).hexdigest()==expected['source_package_sha256']
    with np.load(old) as z:
        old_meta=json.loads(z['metadata_json'].tobytes());old_depth=z['depth_mm'];old_valid=z['valid']
    speed=json.loads((ROOT.parent/'usb_full/board_evidence/photo_speed_update_verified.json').read_text())
    assert speed['passed'] and speed['tests']['surface']['input_sha256']==expected['source_package_sha256']
    scaled_depth=cv2.resize(old_depth,(320,360),interpolation=cv2.INTER_NEAREST)
    common=a['valid']&np.isfinite(scaled_depth)&(scaled_depth>0)
    delta=abs(a['depth_mm'][common]/scaled_depth[common]-1)
    comparison={'old_eye_size':old_meta['eye_size'],'new_eye_size':m['eye_size'],
      'old_valid_fraction':old_meta['valid_fraction'],'new_valid_fraction':m['valid_fraction'],
      'old_matching_pipeline_seconds':old_meta['wall_seconds'],'new_matching_pipeline_seconds':m['wall_seconds'],
      'old_surface_seconds_latest_same_frame':speed['tests']['surface']['accelerated_seconds'],'new_surface_seconds':m['surface_preparation']['seconds'],
      'common_measured_pixels_nearest_grid':int(common.sum()),
      'depth_relative_difference_percentiles':dict(zip(('median','p90','p95'),map(float,np.percentile(delta*100,[50,90,95])))),
      'note':'Different sampling grids and interpolated rectification; nearest-grid agreement is a diagnostic, not metric ground truth. Old surface timing comes from the latest exact-output acceleration of this same saved frame.'}
    out=ROOT/'comparison_320';export_result({k:v for k,v in a.items() if not k.startswith('display_')},m,b,m['surface_preparation'],out)
    report={'passed':True,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'primary':primary,'surface':surface,'comparison':comparison}
    (ROOT/'board_evidence/pipeline_320_pc_verified.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
if __name__=='__main__':main()
