import json
from pathlib import Path
from render_saved import export_result,np
ROOT=Path(__file__).resolve().parent;E=ROOT/'board_evidence'
assert json.loads((E/'geometry_replay_pc_verified.json').read_text())['passed']
with np.load(E/'geometry_replay.npz') as z:a={k:z[k] for k in z.files}
m=json.loads(a.pop('metadata_json').tobytes());b={k[8:]:v for k,v in a.items() if k.startswith('display_')}
raw={k:v for k,v in a.items() if not k.startswith('display_')}
out=ROOT/'live_captures'/m['job_id'];export_result(raw,m,b,m['surface_preparation'],out)
print('http://127.0.0.1:8787/captures/'+m['job_id']+'/viewer.html')
