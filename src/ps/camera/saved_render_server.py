"""Loopback-only saved-result viewer and PNG export, without board controls."""
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import json,struct
ROOT=Path(__file__).resolve().parent/'saved_render'
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def do_POST(self):
        if self.path!='/api/render-export' or self.headers.get('Origin')!='http://127.0.0.1:8770':self.send_error(403);return
        length=int(self.headers.get('Content-Length','0'))
        if self.headers.get('Content-Type')!='image/png' or not 32<=length<=16*1024*1024:self.send_error(400);return
        data=self.rfile.read(length)
        if len(data)!=length or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR':self.send_error(400);return
        w,h=struct.unpack('>II',data[16:24])
        if not 1<=w<=8192 or not 1<=h<=8192:self.send_error(400);return
        (ROOT/'latest_render.png').write_bytes(data)
        result=json.dumps({'url':'latest_render.png'}).encode();self.send_response(200)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(result)));self.end_headers();self.wfile.write(result)
ThreadingHTTPServer(('127.0.0.1',8770),Handler).serve_forever()
