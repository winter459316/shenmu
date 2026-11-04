"""Finite loopback HTTP verification; the board transport is replaced by a stub."""
import hashlib,io,json,tempfile,threading,types,urllib.error,urllib.request
from pathlib import Path
import full_host as host

def main():
    job='a'*32;forwarded=[]
    class Transport:
        def open(self,request,timeout):
            assert request.full_url==host.BOARD+'/hdmi/frame'
            digest=hashlib.sha256(request.data).hexdigest()
            assert request.get_header('X-frame-sha256')==digest
            assert request.get_header('X-photo-id')==job
            assert request.get_header('X-cast-generation')=='2'
            forwarded.append(digest)
            return io.BytesIO(json.dumps({'accepted':True,'job_id':job,'sha256':digest}).encode())
    host.OPENER=Transport()
    host.HOST=types.SimpleNamespace(lock=threading.Lock(),busy=False,job=job,result=True)
    def board_json(path,body=None):
        if path=='/hdmi/status':return {'enabled':True,'generation':2}
        assert path=='/hdmi/preview' and body=={}
        return {'preview_requested':True}
    host.board_json=board_json
    with tempfile.TemporaryDirectory(prefix='hdmi_host_test_') as temp:
        host.CAPTURES=Path(temp);(host.CAPTURES/job).mkdir();(host.CAPTURES/job/'verified.json').write_text('{}')
        server=host.ThreadingHTTPServer(('127.0.0.1',0),host.Handler)
        host.PORT=server.server_address[1];host.ORIGIN='http://127.0.0.1:'+str(host.PORT)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        headers={'Origin':host.ORIGIN,'X-Viewer-Token':host.TOKEN,'Content-Type':'application/octet-stream',
                 'X-Photo-Id':job,'X-Cast-Generation':'2'}
        def send(data,extra=None,path='/api/hdmi/frame'):
            request=urllib.request.Request(host.ORIGIN+path,data,headers=dict(headers,**(extra or {})))
            try:
                with opener.open(request,timeout=5) as response:return response.status,response.read()
            except urllib.error.HTTPError as error:return error.code,error.read()
        try:
            frame=bytes([17])*(1280*720*3)
            assert send(b'',{'X-Viewer-Token':'invalid'})[0]==403
            assert send(b'',{'X-Photo-Id':'b'*32})[0]==409
            assert send(b'short')[0]==409
            assert send(frame,{'X-Cast-Generation':'bad'})[0]==409
            assert forwarded==[]
            code,result=send(frame);assert code==200 and json.loads(result)['accepted'] and len(forwarded)==1
            code,result=send(b'{}',{'Content-Type':'application/json'},'/api/hdmi/preview')
            assert code==200 and json.loads(result)['preview_requested']
            print(json.dumps({'passed':True,'actual_loopback_http':True,'physical_board_used':False,
                              'token_job_length_generation_rejected':True,'frame_checksum_forwarded':True,'preview_route':True}))
        finally:server.shutdown();server.server_close();thread.join(timeout=2)
if __name__=='__main__':main()
