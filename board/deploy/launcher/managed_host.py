"""Own only the PC viewer; idle shutdown is atomic with incoming mutations."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,runpy,secrets,sys,threading
from legacy_adapter import configure_serial
from viewer_identity import identity

HERE=Path(__file__).resolve().parent
HOST=HERE.parent/'candidates/usb_fast_infer2/host.py'
def main():
    configure_serial()
    sys.path.insert(0,str(HOST.parent))
    m=runpy.run_path(str(HOST),run_name='shenmu_managed_host')
    gate={'closing':False}
    class Viewer(m['Handler']):
        def do_GET(self):
            if self.path=='/api/workbench':
                body=json.dumps(identity(HERE)).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
            super().do_GET()
        def do_POST(self):
            with m['MODE_LOCK']:
                if gate['closing']:
                    self.data({'error':'系统正在关闭'},code=409); return
                super().do_POST()
    viewer=ThreadingHTTPServer(('127.0.0.1',8849),Viewer)
    token=secrets.token_hex(32)
    class Control(BaseHTTPRequestHandler):
        def do_POST(self):
            code=409;answer={'error':'正在计算、录制或交互，请结束后重试'}
            if self.path!='/stop' or not secrets.compare_digest(self.headers.get('X-Shenmu-Control',''),token):
                self.send_error(403);return
            with m['MODE_LOCK']:
                if not (m['W'].status()['busy'] or m['SECTION'].active or m['SECTION'].switching or m['VIDEOS'].status()['recording'] or m['REPLAY'].status()['active']):
                    gate['closing']=True;code=200;answer={'stopped':True,'scope':'PC viewer only; board unchanged'}
            body=json.dumps(answer,ensure_ascii=False).encode()
            self.send_response(code);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            if code==200:
                threading.Thread(target=viewer.shutdown,daemon=True).start()
        def log_message(self,*args):pass
    port=json.loads((HERE/'config.json').read_text(encoding='utf-8-sig'))['control_port']
    control=ThreadingHTTPServer(('127.0.0.1',port),Control)
    receipt=HERE/'logs/control.json';receipt.parent.mkdir(exist_ok=True)
    receipt.write_text(json.dumps({'port':port,'token':token}),encoding='utf8')
    threading.Thread(target=control.serve_forever,daemon=True).start()
    try:viewer.serve_forever()
    finally:
        control.shutdown();control.server_close();viewer.server_close();receipt.unlink(missing_ok=True)
if __name__=='__main__':main()
