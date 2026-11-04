"""Root-only Unix socket, one job at a time, one persistent model session."""
from pathlib import Path
import fcntl,json,os,re,socket,time,traceback,signal
R=Path(__file__).resolve().parent

def status(state,**extra):
    temp=R/'worker_status.tmp';temp.write_text(json.dumps({'pid':os.getpid(),'state':state,'ready':state in ('ready','busy'),'updated':time.time(),**extra}));temp.replace(R/'worker_status.json')

if __name__=='__main__':
    with (R/'infer_worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        signal.signal(signal.SIGALRM,signal.SIG_DFL)
        status('loading')
        try:
            from infer_runtime_pl3_v5_quad import Runtime
            runtime=Runtime()
        except BaseException as exc:
            status('failed',error=repr(exc));raise
        path=R/'infer.sock'
        if path.exists():path.unlink()
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(path));os.chmod(str(path),0o600);listener.listen(2)
        status('ready',initial_load_seconds=runtime.initial_load)
        try:
            while True:
                connection,_=listener.accept();connection.settimeout(5)
                try:
                    with connection.makefile('rb') as f:raw=f.readline(200)
                    data=json.loads(raw);assert set(data) in ({'job_id'},{'job_id','action'}) and re.fullmatch('[0-9a-f]{32}',data['job_id'])
                    action=data.get('action','infer');assert action in ('infer','rectify','geometry')
                    status('busy',job_id=data['job_id'],initial_load_seconds=runtime.initial_load)
                    signal.alarm(590)
                    try:report={'rectify':runtime.rectify,'infer':runtime.run,'geometry':runtime.finish_geometry}[action](data['job_id'])
                    finally:signal.alarm(0)
                    reply={'ok':True,'job_id':data['job_id'],'action':action}
                    reply.update({'rectification':report} if action=='rectify' else {'forward_seconds':report['forward_seconds']})
                except BaseException as exc:
                    traceback.print_exc();reply={'ok':False,'error':repr(exc)}
                try:connection.sendall((json.dumps(reply)+'\n').encode())
                except (BrokenPipeError,ConnectionResetError):pass
                finally:connection.close()
                if (R/'dma.fault').exists() or (R.parent/'fast_pl/dma.fault').exists():
                    status('failed',error='PL DMA fault; inspect the board before reuse');break
                status('ready',initial_load_seconds=runtime.initial_load,completed=runtime.completed)
        finally:
            listener.close()
            if path.exists():path.unlink()
