from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import time
ROOT=Path(__file__).resolve().parent
allowed={'baseline_photo.npz','baseline_public.json','reference_replay.npz','reference_replay_status.json','baseline_replay.npz','baseline_replay_status.json','plane_replay_verified.json','plane_activation.json','preview_speed_after.json'}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        name=self.path.lstrip('/')
        if self.client_address[0]!='192.168.137.1' or name not in allowed:self.send_error(403);return
        data=(ROOT/name).read_bytes();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
s=HTTPServer(('192.168.137.2',8769),H);s.timeout=1;end=time.monotonic()+90
while time.monotonic()<end:s.handle_request()
s.server_close()
