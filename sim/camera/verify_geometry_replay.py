import json
from pathlib import Path
from live_verify import verify
ROOT=Path(__file__).resolve().parent;E=ROOT/'board_evidence'
s=json.loads((E/'geometry_replay_status.json').read_text());a,m,b,report=verify((E/'geometry_replay.npz').read_bytes(),s,s['result_id'],lambda v:print(v,flush=True))
assert m['test_only'];report['test_only']=True
(E/'geometry_replay_pc_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['dense_fill']))
