"""Explicit, state-aware startup. No flash writes, no automatic reboot on timeout."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,json,socket,subprocess,sys,time,urllib.request
from legacy_adapter import PROJECT, HERE, run_script
from viewer_identity import ensure_viewer,get_identity,identity,matching,URL

CFG=json.loads((HERE/'config.json').read_text(encoding='utf-8-sig'))
LOG=HERE/'logs';LOG.mkdir(exist_ok=True)
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
ENDPOINTS={'pc':'http://127.0.0.1:8849/api/status','model':'http://192.168.137.2:8850/health','camera':'http://192.168.137.2:8788/status','hdmi':'http://192.168.137.2:8788/hdmi/status','section':'http://192.168.137.2:8852/status','video':'http://192.168.137.2:8853/health'}

def get(url):
    with OP.open(url,timeout=CFG['request_timeout_seconds']) as r:return json.load(r)

def probe(item):
    name,url=item
    try:
        d=get(url)
        keys=('ready','busy','error','version','stage','age_seconds','frames','active','switching','video_input_version','switch_latency_version')
        result={'reachable':True,'status':{k:d[k] for k in keys if k in d}}
        if name=='model':result['worker_state']=d.get('model_worker',{}).get('state')
        return name,result
    except (OSError,ValueError) as e:return name,{'reachable':False,'error':str(e)}

def snapshot():
    with ThreadPoolExecutor(max_workers=6) as pool:result=dict(pool.map(probe,ENDPOINTS.items()))
    (LOG/'status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result

def run(relative,*args):
    path=PROJECT/relative
    start=time.monotonic()
    print('执行：',relative,flush=True)
    with (LOG/'steps.jsonl').open('a',encoding='utf8') as f:
        try:run_script(path,args)
        finally:f.write(json.dumps({'step':relative,'seconds':round(time.monotonic()-start,3)})+'\n')

def board_ready(s):
    return all(s[k]['reachable'] and not s[k]['status'].get('error') for k in ('camera','model','section','video','hdmi')) and s['camera']['status'].get('age_seconds',99)<3 and s['hdmi']['status'].get('frames',0)>0 and s['model']['status'].get('ready') and s['model']['status'].get('version')=='fast_pl3_usable_v5_quad' and s['video']['status'].get('ready') and s['video']['status'].get('version')=='fast_pl3_usable_v5_quad'

def check_local():
    sys.path.insert(0,str(PROJECT/'handoff'))
    from check_current import local_checks
    r=local_checks()
    if not r['passed']:raise RuntimeError('版本校验失败：'+str([k for k,v in r['checks'].items() if not v]))
    profiles=[json.loads((PROJECT/'candidates/usb_fast_infer2/hardware_verified.json').read_text()),json.loads((PROJECT/'candidates/usb_fast_infer2/geometry_config.json').read_text()),json.loads((PROJECT/'experiments/pl_pipeline_20261025/usable_v5_quad/pl3_usable_v5_quad_manifest_20261028.json').read_text())['physical_bridge']['physical']]
    if not all(v.get('tool_version')=='2026.1' for v in profiles):raise RuntimeError('当前入口只运行已绑定的Vivado 2026.1配置，请使用匹配的完整运行包。')

def main():
    a=argparse.ArgumentParser()
    a.add_argument('action',choices=['status','check','start','stop','cold','open','diagnose'])
    args=a.parse_args()
    if args.action=='check':
        check_local();run('handoff/restore_fresh_ram.py','--check')
        sys.path.insert(0,str(PROJECT/'experiments/pl_pipeline_20261025/usable_v5_quad'))
        from legacy_adapter import relocate
        import hashlib
        u=PROJECT/'experiments/pl_pipeline_20261025/usable_v5_quad'
        files=json.loads((u/'payload_local.json').read_text())
        manifest=json.loads((u/'pl3_usable_v5_quad_manifest_20261028.json').read_text())
        assert {n:hashlib.sha256(relocate(p).read_bytes()).hexdigest() for n,p in files.items()}==manifest['files']
        print('本地版本、冷启动载荷和 v5 清单检查通过；未操作板卡。');return
    if args.action=='stop':
        receipt=LOG/'control.json'
        if not receipt.exists():raise RuntimeError('当前电脑服务不是由新入口管理，保持原服务不动。请关闭旧服务后使用新入口。')
        d=json.loads(receipt.read_text())
        req=urllib.request.Request('http://127.0.0.1:'+str(d['port'])+'/stop',data=b'',headers={'X-Shenmu-Control':d['token']},method='POST')
        with OP.open(req,timeout=5) as r:print(r.read().decode())
        return
    if args.action in ('start','open'):
        check_local()
        ensure_viewer(HERE)
        print('电脑网页已就绪：'+URL,flush=True)
        if args.action=='open':return
    s=snapshot()
    if args.action=='diagnose':
        try:
            local=check_local();profile_ok=True
        except Exception as exc:profile_ok=False;profile_error=str(exc)
        try:owned=matching(get_identity(),identity(HERE))
        except (OSError,ValueError,AssertionError):owned=False
        problems=[]
        if not profile_ok:problems.append('2026.1本地文件校验未通过：'+profile_error)
        if not s['pc']['reachable']:problems.append('电脑网页服务未就绪；运行open_web.cmd或start.cmd')
        elif not owned:problems.append('8849服务不属于本运行包；检查旧入口或其他目录中的服务')
        if not any(s[k]['reachable'] for k in ('camera','model','section','video')):problems.append('板端服务均不可达；检查供电、网线、192.168.137.1网卡及板卡启动状态')
        else:
            for k in ('camera','model','section','video','hdmi'):
                if not s[k]['reachable']:problems.append('板端'+k+'服务不可达；查看对应启动日志')
        result=dict(toolchain='2026.1',pc_identity_matches=owned,local_profile_ok=profile_ok,realtime_ready=bool(board_ready(s) and s['pc']['reachable'] and owned and profile_ok),problems=problems,endpoints=s,board_changed=False)
        (LOG/'diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if args.action=='status':
        for k,v in s.items():print(k,'：',json.dumps(v,ensure_ascii=False))
        print('实时系统就绪：',bool(board_ready(s)));return
    check_local()
    if args.action=='cold':
        if any(s[k]['reachable'] for k in ('model','camera','section','video')):
            raise RuntimeError('检测到板端服务，禁止冷启动覆盖；请使用普通启动入口。')
        from legacy_adapter import configure_serial
        configure_serial()
        sys.path.insert(0,str(PROJECT/'experiments/usb_camera_20261016'))
        from board_console import command
        # Prove a live factory Linux and absence of project runtime before any reboot.
        code="from pathlib import Path; import glob,os; assert not Path('/tmp/usb_stereo_probe').exists(); assert not Path('/dev/shm/usb_fast_infer2').exists(); assert not any(b'usb_stereo_probe' in Path(p).read_bytes() for p in glob.glob('/proc/[0-9]*/cmdline') if Path(p).exists() and Path(p).parent.name!=str(os.getpid())); print('SHENMU_FACTORY_IDLE')"
        import shlex,re
        result=command('python3 -c '+shlex.quote(code),10)
        if not re.search(r'(?m)^SHENMU_FACTORY_IDLE\r?$',result):raise RuntimeError('未确认出厂 Linux 空闲状态，不执行重启。')
        run('candidates/usb_320_hdmifps/start_reserved_boot.py','--reboot')
        command('ip addr replace 192.168.137.2/24 dev eth1; ip link set eth1 up',10)
        run('handoff/restore_fresh_ram.py','--apply')
        s=snapshot()
    preparation_error=''
    try:
        if s['model']['reachable'] and s['model']['status'].get('ready'):
            if s['model']['status'].get('version')!='fast_pl3_usable_v5_quad':
                if s['pc'].get('status',{}).get('busy'):raise RuntimeError('当前拍照处理未结束，暂不切换运行环境。')
                run('experiments/pl_pipeline_20261025/usable_v5_quad/select_mode.py')
            # Never install missing hooks while a photo/section is using the board.
            idle=s['section']['reachable'] and s['model'].get('worker_state')=='ready' and not s['pc'].get('status',{}).get('busy') and not s['section'].get('status',{}).get('active') and not s['section'].get('status',{}).get('switching')
            if idle:run('candidates/usb_fast_infer2/video_deploy.py')
            else:print('板卡正在处理或状态未确认，复用服务，不安装或切换。')
    except Exception as exc:
        preparation_error=str(exc)
        print('网页服务可用；板端准备未完成：'+preparation_error,flush=True)
    ensure_viewer(HERE)
    s=snapshot()
    print('电脑端已就绪：http://127.0.0.1:8849/')
    if board_ready(s) and not preparation_error:print('实时系统已就绪。')
    else:print('板端尚未全部就绪。可查看保存结果；实时预览、拍照需连接板卡。冷启动请使用独立入口；已有运行目录时请检查日志，不要重复重启。')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('未完成：',str(e),file=sys.stderr);sys.exit(1)
