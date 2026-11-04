"""Local workbench identity and startup; no board or serial access."""
from pathlib import Path
import hashlib,json,socket,subprocess,sys,time,urllib.request

HERE=Path(__file__).resolve().parent
URL='http://127.0.0.1:8849/'
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def identity(here=None):
    root=Path(here or HERE).resolve().parent
    return dict(service='shenmu_workbench',protocol=1,toolchain='2026.1',runtime_id=hashlib.sha256(str(root).casefold().encode()).hexdigest()[:24])

def get_identity(timeout=1.5):
    with OP.open(URL+'api/workbench',timeout=timeout) as response:
        assert response.status==200
        raw=response.read(8193)
        if len(raw)>8192:raise ValueError('Unexpected workbench response size')
        return json.loads(raw)

def listening():
    with socket.socket() as sock:
        sock.settimeout(.4)
        return sock.connect_ex(('127.0.0.1',8849))==0

def matching(value,expected):
    return isinstance(value,dict) and all(value.get(k)==v for k,v in expected.items())

def ensure_viewer(here=None,python=None,timeout=25):
    here=Path(here or HERE);expected=identity(here)
    try:value=get_identity()
    except (OSError,ValueError,AssertionError):value=None
    if matching(value,expected):return dict(started=False,identity=value)
    if value is not None or listening():
        raise RuntimeError('8849已有另一份或无响应的服务。请用该服务所属目录的stop.cmd结束后重试；本入口不会强制结束它。')
    log=here/'logs';log.mkdir(exist_ok=True)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with (log/'host_stdout.log').open('ab') as out,(log/'host_stderr.log').open('ab') as err:
        process=subprocess.Popen([str(python or sys.executable),'-X','utf8',str(here/'managed_host.py')],cwd=here,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=flags)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError('电脑网页进程启动失败，请查看 launcher/logs/host_stderr.log。')
        try:value=get_identity()
        except (OSError,ValueError,AssertionError):value=None
        if matching(value,expected):return dict(started=True,identity=value,pid=process.pid)
        if value is not None:raise RuntimeError('启动期间8849被其他服务占用；请检查端口，未强制停止任何服务。')
        time.sleep(.15)
    raise RuntimeError('电脑网页启动超时，请查看 launcher/logs/host_stderr.log；未重启板卡。')
