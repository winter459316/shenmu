"""No board access: test refusal gates and real loopback idle shutdown."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util,json,tempfile,threading,time,unittest,urllib.request,urllib.error
from unittest.mock import patch
import startup,managed_host

class Tests(unittest.TestCase):
    def test_relocation(self):
        from legacy_adapter import relocate,PROJECT
        self.assertEqual(relocate(r'C:\old\zu4ev_stereo\experiments\file.bin'),PROJECT/'experiments/file.bin')

    def test_cold_never_reboots_live_board(self):
        state={k:{'reachable':False} for k in startup.ENDPOINTS}
        state['camera']={'reachable':True,'status':{}}
        with patch('sys.argv',['startup','cold']),patch.object(startup,'snapshot',return_value=state),patch.object(startup,'check_local'),patch.object(startup,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'检测到板端服务'):startup.main()
            run.assert_not_called()

    def test_concurrent_probes(self):
        def fake(item):time.sleep(.15);return item[0],{'reachable':False}
        with tempfile.TemporaryDirectory() as d,patch.object(startup,'LOG',Path(d)),patch.object(startup,'probe',side_effect=fake):
            t=time.monotonic();self.assertEqual(len(startup.snapshot()),6);self.assertLess(time.monotonic()-t,.65)

    def test_managed_shutdown_auth_and_busy(self):
        from types import SimpleNamespace
        busy={'value':True}
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):self.send_response(200);self.end_headers()
        fake={'Handler':Handler,'MODE_LOCK':threading.RLock(),'W':SimpleNamespace(status=lambda:{'busy':busy['value']}),'SECTION':SimpleNamespace(active=False,switching=False),'VIDEOS':SimpleNamespace(status=lambda:{'recording':False}),'REPLAY':SimpleNamespace(status=lambda:{'active':False})}
        with tempfile.TemporaryDirectory() as d:
            here=Path(d);(here/'config.json').write_text('{"control_port":0}')
            servers=[]
            def server(address,handler):
                s=ThreadingHTTPServer(('127.0.0.1',0),handler);servers.append(s);return s
            with patch.object(managed_host,'HERE',here),patch.object(managed_host,'configure_serial'),patch.object(managed_host.runpy,'run_path',return_value=fake),patch.object(managed_host,'ThreadingHTTPServer',side_effect=server):
                t=threading.Thread(target=managed_host.main,daemon=True);t.start()
                receipt=here/'logs/control.json'
                for _ in range(100):
                    if receipt.exists():break
                    time.sleep(.02)
                data=json.loads(receipt.read_text());port=servers[1].server_address[1]
                op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                def request(token):return op.open(urllib.request.Request(f'http://127.0.0.1:{port}/stop',data=b'',headers={'X-Shenmu-Control':token}),timeout=3)
                for token,code in [('wrong',403),(data['token'],409)]:
                    with self.assertRaises(urllib.error.HTTPError) as e:request(token)
                    self.assertEqual(e.exception.code,code)
                busy['value']=False
                with request(data['token']) as r:self.assertTrue(json.load(r)['stopped'])
                t.join(4);self.assertFalse(t.is_alive())

if __name__=='__main__':unittest.main(verbosity=2)
