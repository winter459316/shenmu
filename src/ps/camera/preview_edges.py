import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
from mesh_limits import restrict
from render_saved import export_result
with np.load(ROOT/'input_photo.npz') as z:a={k:z[k] for k in z.files}
m=json.loads(a.pop('metadata_json').tobytes());faces,report=restrict(a['dense3d_xyz_q12'],a['dense3d_faces'])
a['dense3d_faces']=faces;m['dense_geometry'].update(triangles=len(faces),mesh_limits=report,depth_jump_culling=True,stretch_culling=True)
export_result(a,m,{},m['surface_preparation'],ROOT/'comparison')
(ROOT/'offline_mesh_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
