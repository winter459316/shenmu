import json,hashlib
from pathlib import Path
from live_verify import verify
ROOT=Path(__file__).resolve().parent;E=ROOT/'board_evidence'
state=json.loads((E/'dense_replay_status.json').read_text());data=(E/'dense_replay.npz').read_bytes()
a,m,b,report=verify(data,state,state['result_id'],lambda s:print(s,flush=True))
assert m['test_only'];report['test_only']=True
(E/'dense_replay_pc_verified.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'passed':True,'seconds':report['seconds'],'dense':report['dense_fill']}))
