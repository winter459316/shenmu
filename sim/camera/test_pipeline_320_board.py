"""Finite full PL/PS pipeline on one preserved native frame; no camera opened."""
import os
os.environ.update(USB_SURFACE_NATIVE='1',USB_MESH_NATIVE='1',USB_HOLES_PARALLEL='1',USB_ARCHIVE_STORED='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
import hashlib,json,time
from pathlib import Path
import numpy as np
from usb_full_engine import FullEngine
from board_surface import prepare
from result_archive import pack_result
ROOT=Path(__file__).resolve().parent
def main():
    case=json.loads((ROOT/'case_320.json').read_text())
    assert hashlib.sha256((ROOT/'native_test_frame.npz').read_bytes()).hexdigest()==case['test_input_sha256']
    with np.load(ROOT/'native_test_frame.npz') as z:frame=z['frame']
    assert hashlib.sha256(frame.tobytes()).hexdigest()==case['native_frame_sha256']
    start=time.monotonic();a,m=FullEngine().compute(frame,lambda stage,details:print(stage,flush=True))
    display,report=prepare(a,lambda stage,details:print(stage,flush=True));a.update({'display_'+k:v for k,v in display.items()})
    m['surface_preparation']=report;m['test_only']=True;m['full_seconds_before_packing']=time.monotonic()-start
    data=pack_result(a,m);(ROOT/'pipeline_320_result.npz').write_bytes(data)
    result={'passed':True,'seconds':time.monotonic()-start,'primary_seconds':m['wall_seconds'],
        'surface_seconds':report['seconds'],'eye_size':m['eye_size'],'sha256':hashlib.sha256(data).hexdigest(),
        'valid_pixels':m['valid_pixels'],'valid_fraction':m['valid_fraction'],'surface_triangles':report['repaired']['output_triangles'],
        'native_frame_sha256':m['native_frame_sha256_bgr'],'case':case,'stage_seconds':m['stage_seconds'],
        'calibration_sha256':m['calibration_sha256'],'package_bytes':len(data),'shutter_triggered':False}
    (ROOT/'pipeline_320_verified.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    # Separate finite arithmetic check, excluded from production timing.
    from board_completion import complete
    q,origin,cpu=complete(a['rectified_left'],a['disparity_q4'],a['valid'],a['domain'],use_pl=False)
    assert np.array_equal(q,a['completed_disparity_q4'])
    assert np.array_equal(origin,a['completion_origin'])
    from board_dma import Arena
    from board_geometry import section
    records=np.concatenate((a['completed_xyz_q12'],a['completed_geometry_flags'][:,:,None]),axis=2).astype(np.int32)
    arena=Arena(True);sections=[]
    try:
        for axis,center,width,include in ((0,0,10,False),(1,0,10,True),(2,700,40,False),(2,700,40,True)):
            s=section(arena,records,axis,center,width,include)
            sections.append({'axis':axis,'center_mm':center,'thickness_mm':width,'include_inferred':include,'count':len(s['indices']),'seconds':s['board_seconds']})
    finally:arena.close()
    comparison={'passed':True,'pl_cpu_completion_bit_exact':True,'cpu_reference':cpu,'pl_completion':m['completion'],'sections':sections}
    (ROOT/'completion_320_reference.json').write_text(json.dumps(comparison,indent=2));print('COMPLETION_AND_SECTIONS_PASS',flush=True)
if __name__=='__main__':main()
