"""Archive the tested HDMI candidate without changing any running service."""
import datetime,hashlib,json,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
EVIDENCE=ROOT/'board_evidence'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')

def main():
    now=datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(url):
        with opener.open(url,timeout=8) as response:return json.loads(response.read())
    host=get('http://127.0.0.1:8771/api/status')
    board=get('http://192.168.137.2:8767/stereo/status')
    camera=get('http://192.168.137.2:8767/status')
    assert not host['busy'] and not board['busy'] and not board['section_busy']
    assert host['job_id']==board['result_id']=='6bed0c1a3fcd43a08fcbb8ff69838f67'
    assert board['metadata']['package_sha256']=='3026c9f32eef9d0d083e0565616ed7798a972643fd4fc964401b21be16ff0095'
    assert not camera['error'] and camera['age_seconds']<3
    save(EVIDENCE/'hdmi_deferred_runtime.json',{'time':now,'host_stage':host['stage'],
        'board_stage':board['stage'],'job_id':board['result_id'],
        'package_sha256':board['metadata']['package_sha256'],'camera':camera,
        'host_restart_performed':False,'production_promoted':False,
        'user_instruction':'暂时不要重启','physical_hdmi_test':'User confirmed photos and RGBW bars normal',
        'physical_key_press_test':'pending; PL keys not enabled in current stable hardware'})
    proof=json.loads((ROOT/'hdmi_hardware_verified.json').read_text())
    test=json.loads((EVIDENCE/'hdmi_full_verified.json').read_text())
    independent=json.loads((EVIDENCE/'hdmi_full_pc_verified.json').read_text())
    assert test['passed'] and test['stable_restored'] and test['hdmi_drained'] and independent['passed']
    assert sha(ROOT/'hdmi_v1.bit.bin')==proof['bin_sha256']==test['candidate_sha256']
    proof.update(board_test_passed=True,board_test_sha256=sha(EVIDENCE/'hdmi_full_verified.json'),
        independent_verification_sha256=sha(EVIDENCE/'hdmi_full_pc_verified.json'),
        user_hdmi_visual_confirmation='照片和四色条正常',production_promoted=False,
        activation_deferred_by_user=True)
    save(ROOT/'hdmi_hardware_verified.json',proof);save(EVIDENCE/'hdmi_hardware_verified.json',proof)
    state=('\n'+now+' HDMI VERIFIED; PRODUCTION ACTIVATION DEFERRED BY USER\n'
        '- Latest user reply: 暂时不要重启. Do not stop/restart PC8771 or promote hardware/services until authorized.\n'
        '- HDMI implementation passed timing/CDC review; bin48350af24a1a760c9f555bd6e39c2d8a0216003a580d7c08204bab5e64c2c39d.\n'
        '- User physically confirmed stereo photos and RGBW bars. Full compute while HDMI scanned out passed; all51 arrays independently byte-exact; VDMA drained and stable hardware/held photo/fresh preview restored.\n'
        '- Atomic32-bit MMIO helper hdmi_mmio.so fixes bytewise register-trigger writes. Temporary test evidence preserved.\n'
        '- HDMI preview/cast and four-key software ready; simulation/software tests passed. Physical PL key presses and production 3D casting still pending. Do not describe these as fully live or physically validated.\n'
        '- Running PC hostPID35932 and board cameraPID28833 remain unchanged; PS key sidecarPID31246, PL keys disabled. Stablebin8183863c879beb5bec68fc1e6a42e8b20df0a8ba4149af0e35871e9a0d0d854d.\n'
        '- Heldjob6bed0c1a package3026c9f32eef9d0d083e0565616ed7798a972643fd4fc964401b21be16ff0095 unchanged.\n'
        '- Follow-up requires authorized coordinated idle service update and restart, rollback-safe board loader, restored photo verification, actual HDMI cast/key check. load_verified_hdmi.py requires stopped owners and has no automatic failure rollback; do not run casually.\n'
        '- Preserve user stopping boundary: finish HDMI/keys then stop further optimization; broad original goal not complete. No additional optimization now.\n\n')
    path=ROOT/'CURRENT_STATE.txt';path.write_text(state+path.read_text(encoding='utf8'),encoding='utf8')
    scope=json.loads((ROOT/'scope.json').read_text(encoding='utf8'))
    scope['latest_user_boundary'].update(activation_deferred=True,latest_reply='暂时不要重启',latest_reply_time=now)
    for item in scope['requirements']:
        if item['id']=='hdmi':item['evidence']='Implemented timing/CDC and actual HDMI photo/RGBW display passed; HDMI concurrent full compute has51 byte-exact arrays. Preview/casting software ready. User deferred production restart; actual 3D cast acceptance pending.'
        if item['id']=='board_controls':item['evidence']='PL key debounce hardware simulation and software lifecycle tests passed; PS sidecar remains alive with PL disabled on stable image. Physical press test and production activation pending; user requested no restart now.'
        if item['id']=='deployment':item['evidence']='HDMI finite volatile test/drain/stable rollback passed, held package unchanged and preview fresh. Candidate ready; user explicitly deferred service restart. No flash/boot write. Production and cold-start integration remain incomplete.'
    save(ROOT/'scope.json',scope)
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.py','.c','.h','.so','.html','.tcl','.xdc','.v','.sv','.txt','.npz'}]
    files += [ROOT/name for name in ('scope.json','hardware_catalog.py','hdmi_hardware_verified.json','usb_full.bit.bin','sgm_window_v4.bit.bin','hdmi_v1.bit.bin')]
    files += [p for p in (ROOT/'hdmi_v1').iterdir() if p.is_file() and p.suffix in {'.tcl','.xdc','.v','.sv','.rpt','.txt','.bit','.bin','.bif','.log'}]
    files += [p for p in EVIDENCE.iterdir() if p.is_file() and (p.suffix=='.json' or p.name in {'hdmi_full_result.npz','hdmi_full_test.log','full_pipeline_result.npz','surface_result.npz'})]
    source_manifest={p.name:sha(p) for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.py','.c','.h','.so','.html'}}
    save(EVIDENCE/'integration_source_sha256.json',source_manifest);files.append(EVIDENCE/'integration_source_sha256.json')
    files=sorted(set(p for p in files if p.is_file()))
    manifest={p.relative_to(ROOT).as_posix():sha(p) for p in files}
    archive=ROOT/'checkpoints'/('usb_hdmi_tested_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.zip')
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as output:
        for p in files:output.write(p,p.relative_to(ROOT).as_posix())
        output.writestr('ARCHIVE_SHA256.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(archive) as check:
        for name,digest in manifest.items():assert hashlib.sha256(check.read(name)).hexdigest()==digest,name
    report={'passed':True,'archive':str(archive),'sha256':sha(archive),'file_count':len(files),
            'bytes':archive.stat().st_size,'time':now,'production_promoted':False,'restart_deferred_by_user':True}
    save(EVIDENCE/'hdmi_checkpoint_verified.json',report);print(json.dumps(report))

if __name__=='__main__':main()
