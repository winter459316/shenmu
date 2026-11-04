"""One saved-photo profile, with exact output checks; never opens the camera."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import cProfile,hashlib,io,json,pstats,time
from pathlib import Path
import numpy as np
from surface_holes import repair_surface
ROOT=Path(__file__).resolve().parent
with np.load(ROOT/'full_pipeline_result.npz',allow_pickle=False) as z:
    a={k:z[k] for k in ('Q','completion_origin','completed_disparity_q4','completed_geometry_flags')}
with np.load(ROOT/'surface_native_result.npz',allow_pickle=False) as z:
    b={k:z[k] for k in z.files if k!='metadata_json'}
geometry={'Q_grid':a['Q'],'provenance':a['completion_origin'],
          'measured_valid':(a['completion_origin']==0)&((a['completed_geometry_flags']&1)!=0),
          'completed_q4':a['completed_disparity_q4'],'preview_valid':b['preview_valid'],'max_disparity_px':127}
detail={'valid':b['detail_valid'],'xyz_mm':b['detail_xyz_mm'],
        'disparity_px':b['detail_disparity_px'],'grid_faces':b['detail_faces']}
profile=cProfile.Profile();start=time.monotonic();profile.enable()
out=repair_surface(geometry,detail)
profile.disable();elapsed=time.monotonic()-start
keys={'xyz_mm':'repaired_xyz_mm','valid':'repaired_valid','disparity_px':'repaired_disparity_px',
      'provenance':'repaired_origin','restored_inferred':'restored_inferred','grid_faces':'repaired_faces'}
for name,expected in keys.items():
    assert out[name].dtype==b[expected].dtype and out[name].shape==b[expected].shape
    assert out[name].tobytes()==b[expected].tobytes(),name
stream=io.StringIO();pstats.Stats(profile,stream=stream).sort_stats('cumulative').print_stats(30)
report={'passed':True,'seconds_with_profiler':elapsed,'exact_arrays':list(keys),
        'source_sha256':hashlib.sha256((ROOT/'surface_holes.py').read_bytes()).hexdigest(),
        'profile':stream.getvalue(),'repair':out['report']}
(ROOT/'surface_holes_profile.json').write_text(json.dumps(report,indent=2))
print(stream.getvalue(),flush=True);print('HOLE_PROFILE_EXACT_PASS',flush=True)
