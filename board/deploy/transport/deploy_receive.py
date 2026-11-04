from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
class H(BaseHTTPRequestHandler):
 def do_POST(self):
  n=int(self.headers.get('Content-Length','0'))
  if self.client_address[0]!='192.168.137.1' or not 0<n<524288:
   self.send_error(403);return
  Path('/tmp/usb_stereo_probe/deploy.zip').write_bytes(self.rfile.read(n))
  self.send_response(200);self.end_headers();self.wfile.write(b'OK')
s=HTTPServer(('192.168.137.2',8769),H)
s.timeout=90
s.handle_request()
s.server_close()
