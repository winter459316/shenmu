"""Bounded local request to the resident inference worker; no per-photo model load."""
from pathlib import Path
import json,re,socket,sys
R=Path(__file__).resolve().parent;job=sys.argv[1];assert re.fullmatch('[0-9a-f]{32}',job)
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(620)
try:
 s.connect(str(R/'infer.sock'));s.sendall((json.dumps({'job_id':job})+'\n').encode())
 with s.makefile('rb') as f:reply=json.loads(f.readline(8192))
 assert reply['ok'],reply
 print(json.dumps(reply),flush=True)
finally:s.close()
