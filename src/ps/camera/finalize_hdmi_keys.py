"""Save the accepted HDMI/key runtime evidence and a local release checkpoint."""
import datetime,hashlib,json,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;E=ROOT/'board_evidence'
JOBS=('c74ae5e5c0e94fe18b39913c2510f03f','6fc7677660f5402da1aeae97794a12e4')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')

def main():
    now=datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path):
        with opener.open('http://127.0.0.1:8771'+path,timeout=10) as r:return json.loads(r.read())
    host=get('/api/status');camera=get('/api/camera');hdmi=get('/api/hdmi/status')
    assert host['stage']=='ready' and not host['busy'] and not host['section_busy'] and not host['error']
    assert host['job_id']==JOBS[-1] and not camera['standby'] and not camera['error'] and camera['age_seconds']<3
    assert hdmi['enabled'] and not hdmi['error'] and hdmi['source']=='preview' and not hdmi['vdma_status']&0xff1
    keys=json.loads((E/'physical_keys_status.json').read_text());assert keys['pl_keys_enabled']
    assert all(keys['counts'][k]>=1 for k in ('ps_key1','ps_key2','pl_key1','pl_key2'))
    events=[json.loads(line) for line in (E/'physical_keys_hdmi.log').read_text().splitlines() if line.startswith('{')]
    for key,result in (('pl_key1','mode'),('pl_key1','preview'),('pl_key2','captured'),('ps_key2','standby'),('ps_key1','resumed')):
        assert any(v['key']==key and v['result']==result for v in events),(key,result)
    loaded=json.loads((E/'loaded.json').read_text());activation=json.loads((E/'hdmi_activation.json').read_text())
    assert activation['passed'] and activation['loaded_sha256']==loaded['sha256']=='48350af24a1a760c9f555bd6e39c2d8a0216003a580d7c08204bab5e64c2c39d'
    assert sha(E/'hdmi_before_activation.zip')=='c3dbb453acbfb16f6ab70255a3ea18edff590fe20e262243bbde4c1ca21b99d6'
    captures=[]
    for job in JOBS:
        folder=ROOT/'live_captures'/job;v=json.loads((folder/'verified.json').read_text(encoding='utf8'))
        assert v['passed'] and v['job_id']==job and v['source_sha256']==sha(folder/'board_result.npz')
        assert v['board_metadata']['bitstream_sha256']==loaded['sha256']
        captures.append({'job_id':job,'verified_sha256':sha(folder/'verified.json'),'package_sha256':v['source_sha256'],
                         'verification_seconds':v['seconds'],'total_seconds':v['elapsed_seconds']})
    section=ROOT/'live_captures'/JOBS[-1]/'section_6d5fd281d7f9.json'
    data=json.loads(section.read_text());assert data['response']['pc_verified'] and data['response']['count']==594
    report={'time':now,'hdmi_and_keys_functionally_verified':True,'production_promoted':True,
        'loaded_sha256':loaded['sha256'],'host_pid':41792,'camera_pid':6150,'keys_pid':6182,
        'user_confirmed_3d_hdmi_and_oblique_view':True,'user_confirmed_resume_preview':True,
        'physical_key_events':events,'camera':camera,'hdmi':hdmi,'captures':captures,
        'post_resume_pl_section':{'count':594,'report_sha256':sha(section),'pc_verified':True},
        'old_held_photo_preserved':'6bed0c1a3fcd43a08fcbb8ff69838f67',
        'current_job':JOBS[-1],'current_timing':host['result'],
        'historical_photo_timing_issue':'Initial host restoration lacked runtime-only total_seconds. Photo bytes and point data were preserved. Two new key captures passed and published. Source now falls back to matching saved timing or displays unavailable; that host-only fix awaits a future authorized restart.',
        'second_host_restart':'Automatic approval rejected the repeat restart; no workaround termination used. Existing process recovered through normal key capture.',
        'scope':'HDMI and key functionality accepted; physical metric accuracy, multi-scene quality and further optimization are not claimed complete.'}
    save(E/'hdmi_keys_live_verified.json',report)
    proof=json.loads((ROOT/'hdmi_hardware_verified.json').read_text());proof.update(production_promoted=True,activation_deferred_by_user=False,live_evidence_sha256=sha(E/'hdmi_keys_live_verified.json'))
    save(ROOT/'hdmi_hardware_verified.json',proof)
    scope=json.loads((ROOT/'scope.json').read_text(encoding='utf8'))
    scope['latest_user_boundary'].update(activation_deferred=False,latest_reply='开始吧',hdmi_keys_completed=True,stop_further_optimization=True)
    for item in scope['requirements']:
        if item['id'] in ('hdmi','board_controls'):
            item.update(status='verified',evidence='hdmi_keys_live_verified.json: actual HDMI preview/3D cast/oblique view, PL_KEY1 mode/return, two PL_KEY2 captures independently verified, PS_KEY2 standby/PS_KEY1 resume, post-resume PL section594points exact. User confirmed external display/resume.')
    save(ROOT/'scope.json',scope)
    note=(now+' HDMI/KEYS ACTIVATED AND ACCEPTED; STOP FURTHER OPTIMIZATION\n'
        '- User authorized switch with 开始吧. PC8771 PID41792, board camera6150, physical_keys --pl PID6182. Running HDMI48350af24a1a760c9f555bd6e39c2d8a0216003a580d7c08204bab5e64c2c39d; actual4-core identities/calibration/revision passed.\n'
        '- Four physical keys logged and user confirmed3D HDMI/oblique view and PS_KEY1 resumed preview. PL_KEY2 two actual photos c74ae5e5/6fc76776 passed independent matching/XYZ/surface verification; busy repeats ignored. Latest total62.172s(board50.628s,PC8.156s), no controlled speed comparison claim.\n'
        '- Latest held6fc7677660f5402da1aeae97794a12e4; color preview, standbyfalse. Afterresume PLZsection594points verified. Old6bed photo bytes preserved. Prior stable firmware/checkpoints intact; RAM sourcebackup board_evidence/hdmi_before_activation.zip.\n'
        '- Initial held-photo hostrestore failed only on missing runtime total_seconds. Fixed full_host.py/full_control.html on disk; repeat restart autoreview blocked, did not execute or bypass. Existing host recovered normally when physical PL_KEY2 captured nextphoto. Running host41792 predates this timing fallback; next authorized startup uses corrected disk source.\n'
        '- Viewer cast feedback now explains key/standby/photo cancellation instead of generic409; template and two liveexports updated with originals preserved. No geometry change.\n'
        '- User stopping boundary reached: finish HDMI/keys then stop additionaloptimization. This is NOT full original quality/latency/cold-start goal completion. Do not use save_hdmi_checkpoint.py now: it encodes the PRE-ACTIVATION stable snapshot.\n\n')
    p=ROOT/'CURRENT_STATE.txt';p.write_text(note+p.read_text(encoding='utf8'),encoding='utf8')
    instructions='''USB 双目 HDMI / 按键版（2026-10-16）

控制页：http://127.0.0.1:8771/ （8766 入口继续跳转）
PL_KEY1：彩色/灰度/中值/边缘；三维投屏时按一次返回彩色预览。
PL_KEY2：拍一张照片。计算时再按不会重复拍照；HDMI 仍显示实时预览。
PS_KEY2：待机，停止相机预览。
PS_KEY1：恢复相机预览。
不要用 PS_RST 或 PL_RST 当成功能按键。

三维页点击“投到板上 HDMI”，旋转/显示选项会同步；点击“恢复相机预览”或按 PL_KEY1 返回。
投屏依赖电脑网页保持打开；网页后台/断开后租约到期会回到预览。
本次实测两张照片约60–62秒完成，场景不同不能直接作为加速比。
匹配、校正/特征、XYZ和截面由PL执行；补全PL/PS协同，表面处理在A53，三维渲染仍由电脑完成。

旧7020/OV5640工程、USB稳定版和旧照片保留。本版是RAM中的易失加载，不保证断电后自动恢复。
本次验收完成HDMI/按键；后续精度、空洞、速度优化按用户要求暂不继续。
当前主机服务已能处理新照片。恢复旧照片的历史耗时字段兼容修复已保存到源码，因重复重启被自动审批拦截，需下次获准重启后生效。
'''
    (ROOT/'HDMI_KEYS_RELEASE.txt').write_text(instructions,encoding='utf8')
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.py','.c','.h','.so','.html','.tcl','.xdc','.v','.sv','.txt','.npz'}]
    files += [ROOT/n for n in ('hdmi_v1.bit.bin','usb_full.bit.bin','scope.json','hdmi_hardware_verified.json')]
    files += [p for p in (ROOT/'hdmi_v1').iterdir() if p.is_file() and p.suffix in {'.tcl','.v','.sv','.xdc','.rpt','.txt'}]
    files += [p for p in E.iterdir() if p.is_file() and (p.suffix=='.json' or p.name in {'hdmi_before_activation.zip','physical_keys_hdmi.log','hdmi_keys_live_viewer.png'})]
    for job in JOBS:
        folder=ROOT/'live_captures'/job
        files += [folder/n for n in ('board_result.npz','verified.json','viewer.html','reference.png')]
        files += list(folder.glob('section_*'))
    files=sorted(set(p for p in files if p.is_file()))
    manifest={p.relative_to(ROOT).as_posix():sha(p) for p in files}
    archive=ROOT/'checkpoints'/('usb_hdmi_keys_live_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
        z.writestr('ARCHIVE_SHA256.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(archive) as z:
        for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
    result={'passed':True,'archive':str(archive),'sha256':sha(archive),'files':len(files),'bytes':archive.stat().st_size,'live_evidence_sha256':sha(E/'hdmi_keys_live_verified.json')}
    save(E/'hdmi_keys_release_verified.json',result);print(json.dumps(result))

if __name__=='__main__':main()
