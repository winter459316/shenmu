"""Keep the familiar 8766 entry without allowing an obsolete UI to take photos."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
class Handler(BaseHTTPRequestHandler):
    def moved(self):
        data=json.dumps({'error':'USB full PL workflow moved to http://127.0.0.1:8771/','url':'http://127.0.0.1:8771/'}).encode()
        self.send_response(410);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def do_GET(self):
        if self.path.split('?',1)[0] in ('/','/index.html'):
            self.send_response(302);self.send_header('Location','http://127.0.0.1:8771/');self.send_header('Content-Length','0');self.end_headers()
        else:self.moved()
    def do_POST(self):self.moved()
    def log_message(self,*args):pass
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',8766),Handler).serve_forever()
